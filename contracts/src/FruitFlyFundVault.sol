// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {AccessControl} from "@openzeppelin/contracts/access/AccessControl.sol";
import {ERC20} from "@openzeppelin/contracts/token/ERC20/ERC20.sol";
import {IERC20} from "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import {SafeERC20} from "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import {Math} from "@openzeppelin/contracts/utils/math/Math.sol";
import {Pausable} from "@openzeppelin/contracts/utils/Pausable.sol";
import {ReentrancyGuard} from "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/// @notice Explicit-share accounting for a multichain strategy fund.
/// @dev V1 uses an authorized offchain NAV reporter. It is not trustless
/// production fund accounting and is intentionally not upgradeable.
contract FruitFlyFundVault is ERC20, AccessControl, Pausable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    bytes32 public constant STRATEGY_ROLE = keccak256("STRATEGY_ROLE");
    bytes32 public constant NAV_REPORTER_ROLE = keccak256("NAV_REPORTER_ROLE");
    bytes32 public constant PAUSER_ROLE = keccak256("PAUSER_ROLE");
    uint256 public constant USDC_SCALE = 1e6;
    uint256 private constant SHARE_SCALE = 1e18;

    IERC20 public immutable accountingAsset;
    address public strategyTreasury;
    uint256 public reportedStrategyNavUsdc;
    uint256 public lastNavReportTimestamp;

    enum WithdrawalStatus { NONE, REQUESTED, FUNDED, CLAIMED }
    struct WithdrawalRequest {
        address owner;
        uint256 shares;
        uint256 amountUsdc;
        uint256 navPerShareUsdc;
        WithdrawalStatus status;
    }

    uint256 public nextWithdrawalId = 1;
    mapping(uint256 => WithdrawalRequest) public withdrawalRequests;

    event Deposit(address indexed caller, address indexed owner, uint256 assetsUsdc, uint256 shares);
    event CapitalDeployed(address indexed treasury, uint256 amountUsdc);
    event StrategyNavReported(uint256 strategyNavUsdc, uint256 totalNavUsdc, uint256 navPerShareUsdc, uint256 timestamp);
    event WithdrawalRequested(uint256 indexed requestId, address indexed owner, uint256 shares, uint256 amountUsdc, uint256 navPerShareUsdc);
    event WithdrawalFunded(uint256 indexed requestId, uint256 amountUsdc);
    event WithdrawalClaimed(uint256 indexed requestId, address indexed owner, uint256 amountUsdc);
    event StrategyTreasuryUpdated(address indexed oldTreasury, address indexed newTreasury);

    constructor(address usdc, address treasury, address admin)
        ERC20("Fruit Fly Capital Fund Share", "FFC")
    {
        require(usdc != address(0) && treasury != address(0) && admin != address(0), "zero address");
        accountingAsset = IERC20(usdc);
        strategyTreasury = treasury;
        _grantRole(DEFAULT_ADMIN_ROLE, admin);
        _grantRole(STRATEGY_ROLE, admin);
        _grantRole(NAV_REPORTER_ROLE, admin);
        _grantRole(PAUSER_ROLE, admin);
    }

    function totalNavUsdc() public view returns (uint256) {
        return accountingAsset.balanceOf(address(this)) + reportedStrategyNavUsdc;
    }

    /// @return USDC base units represented by one whole share unit (1e18).
    function navPerShareUsdc() public view returns (uint256) {
        if (totalSupply() == 0) return USDC_SCALE;
        return Math.mulDiv(totalNavUsdc(), SHARE_SCALE, totalSupply());
    }

    function deposit(uint256 assetsUsdc, address receiver) external nonReentrant whenNotPaused returns (uint256 shares) {
        require(assetsUsdc > 0 && receiver != address(0), "invalid deposit");
        uint256 price = navPerShareUsdc();
        shares = Math.mulDiv(assetsUsdc, SHARE_SCALE, price);
        require(shares > 0, "rounding to zero");
        accountingAsset.safeTransferFrom(msg.sender, address(this), assetsUsdc);
        _mint(receiver, shares);
        emit Deposit(msg.sender, receiver, assetsUsdc, shares);
    }

    function deployCapital(uint256 amountUsdc) external onlyRole(STRATEGY_ROLE) whenNotPaused {
        require(amountUsdc > 0 && amountUsdc <= accountingAsset.balanceOf(address(this)), "invalid deployment");
        accountingAsset.safeTransfer(strategyTreasury, amountUsdc);
        emit CapitalDeployed(strategyTreasury, amountUsdc);
    }

    function setStrategyTreasury(address newTreasury) external onlyRole(DEFAULT_ADMIN_ROLE) {
        require(newTreasury != address(0), "zero treasury");
        address oldTreasury = strategyTreasury;
        strategyTreasury = newTreasury;
        emit StrategyTreasuryUpdated(oldTreasury, newTreasury);
    }

    function reportStrategyNav(uint256 strategyNavUsdc) external onlyRole(NAV_REPORTER_ROLE) whenNotPaused {
        reportedStrategyNavUsdc = strategyNavUsdc;
        lastNavReportTimestamp = block.timestamp;
        emit StrategyNavReported(strategyNavUsdc, totalNavUsdc(), navPerShareUsdc(), block.timestamp);
    }

    function requestRedeem(uint256 shares) external nonReentrant whenNotPaused returns (uint256 requestId) {
        require(shares > 0 && shares <= balanceOf(msg.sender), "invalid redemption");
        uint256 price = navPerShareUsdc();
        uint256 amountUsdc = Math.mulDiv(shares, price, SHARE_SCALE);
        require(amountUsdc > 0, "rounding to zero");
        // Escrow shares until claim; this keeps the request's NAV snapshot
        // explicit and prevents the owner from spending them twice.
        _transfer(msg.sender, address(this), shares);
        requestId = nextWithdrawalId++;
        withdrawalRequests[requestId] = WithdrawalRequest(msg.sender, shares, amountUsdc, price, WithdrawalStatus.REQUESTED);
        emit WithdrawalRequested(requestId, msg.sender, shares, amountUsdc, price);
    }

    function fundWithdrawal(uint256 requestId) external onlyRole(STRATEGY_ROLE) whenNotPaused {
        WithdrawalRequest storage request = withdrawalRequests[requestId];
        require(request.status == WithdrawalStatus.REQUESTED, "not requested");
        require(request.amountUsdc <= accountingAsset.balanceOf(address(this)), "insufficient liquidity");
        request.status = WithdrawalStatus.FUNDED;
        emit WithdrawalFunded(requestId, request.amountUsdc);
    }

    function claimWithdrawal(uint256 requestId) external nonReentrant whenNotPaused {
        WithdrawalRequest storage request = withdrawalRequests[requestId];
        require(request.owner == msg.sender && request.status == WithdrawalStatus.FUNDED, "not claimable");
        request.status = WithdrawalStatus.CLAIMED;
        _burn(address(this), request.shares);
        accountingAsset.safeTransfer(msg.sender, request.amountUsdc);
        emit WithdrawalClaimed(requestId, msg.sender, request.amountUsdc);
    }

    function pause() external onlyRole(PAUSER_ROLE) { _pause(); }
    function unpause() external onlyRole(PAUSER_ROLE) { _unpause(); }
}

