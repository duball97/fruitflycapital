// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test, console2} from "forge-std/Test.sol";
import {FruitFlyFundVault} from "../src/FruitFlyFundVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";

contract FruitFlyFundVaultTest is Test {
    MockUSDC usdc;
    FruitFlyFundVault vault;
    address admin = makeAddr("admin");
    address alice = makeAddr("alice");
    address bob = makeAddr("bob");
    address charlie = makeAddr("charlie");
    address treasury = makeAddr("treasury");

    function setUp() public {
        usdc = new MockUSDC();
        vault = new FruitFlyFundVault(address(usdc), treasury, admin);
        usdc.mint(alice, 1_000e6);
        usdc.mint(bob, 1_000e6);
        usdc.mint(charlie, 1_000e6);
        vm.prank(alice); usdc.approve(address(vault), type(uint256).max);
        vm.prank(bob); usdc.approve(address(vault), type(uint256).max);
        vm.prank(charlie); usdc.approve(address(vault), type(uint256).max);
    }

    function testFirstDepositMintsOneToOneShares() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        assertEq(vault.balanceOf(alice), 100e18);
        assertEq(vault.navPerShareUsdc(), 1e6);
        console2.log("first deposit shares", vault.balanceOf(alice));
    }

    function testSecondDepositorAtInitialNav() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(bob); vault.deposit(100e6, bob);
        assertEq(vault.balanceOf(bob), 100e18);
        assertEq(vault.totalSupply(), 200e18);
    }

    function testDeploymentLeavesLiquidCashAndKeepsNav() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.deployCapital(40e6);
        assertEq(usdc.balanceOf(address(vault)), 60e6);
        assertEq(usdc.balanceOf(treasury), 40e6);
        assertEq(vault.totalNavUsdc(), 60e6);
        vm.prank(admin); vault.reportStrategyNav(40e6);
        assertEq(vault.totalNavUsdc(), 100e6);
    }

    function testStrategyGainRaisesNavAndLaterDepositGetsFewerShares() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.deployCapital(50e6);
        vm.prank(admin); vault.reportStrategyNav(60e6);
        assertEq(vault.navPerShareUsdc(), 1_100_000);
        vm.prank(bob); vault.deposit(110e6, bob);
        assertEq(vault.balanceOf(bob), 100e18);
        assertEq(vault.navPerShareUsdc(), 1_100_000);
    }

    function testStrategyLossLowersNav() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.deployCapital(50e6);
        vm.prank(admin); vault.reportStrategyNav(40e6);
        assertEq(vault.navPerShareUsdc(), 900_000);
    }

    function testWithdrawalLifecycleUsesRequestSnapshot() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.deployCapital(50e6);
        vm.prank(admin); vault.reportStrategyNav(60e6);
        vm.prank(alice); uint256 requestId = vault.requestRedeem(50e18);
        (address owner, uint256 shares, uint256 amount, uint256 price, FruitFlyFundVault.WithdrawalStatus status) = vault.withdrawalRequests(requestId);
        assertEq(owner, alice); assertEq(shares, 50e18); assertEq(amount, 55e6); assertEq(price, 1_100_000);
        assertEq(uint256(status), uint256(FruitFlyFundVault.WithdrawalStatus.REQUESTED));
        vm.prank(alice); vm.expectRevert("not claimable"); vault.claimWithdrawal(requestId);
        vm.prank(treasury); usdc.transfer(address(vault), 10e6);
        vm.prank(admin); vault.fundWithdrawal(requestId);
        vm.prank(alice); vault.claimWithdrawal(requestId);
        assertEq(usdc.balanceOf(alice), 955e6);
        vm.prank(alice); vm.expectRevert("not claimable"); vault.claimWithdrawal(requestId);
    }

    function testReturnCapitalFundsWithdrawal() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.deployCapital(80e6);
        vm.prank(admin); vault.reportStrategyNav(80e6);
        vm.prank(alice); uint256 requestId = vault.requestRedeem(60e18);
        vm.prank(admin); vm.expectRevert("insufficient liquidity"); vault.fundWithdrawal(requestId);
        vm.prank(treasury); usdc.transfer(address(vault), 60e6);
        vm.prank(admin); vault.fundWithdrawal(requestId);
        vm.prank(alice); vault.claimWithdrawal(requestId);
        assertEq(usdc.balanceOf(alice), 960e6);
    }

    function testUnauthorizedOperationsRevert() public {
        vm.prank(alice); vm.expectRevert(); vault.deployCapital(1e6);
        vm.prank(alice); vm.expectRevert(); vault.reportStrategyNav(1e6);
        vm.prank(alice); vm.expectRevert(); vault.setStrategyTreasury(alice);
    }

    function testPausePreventsDepositsDeploymentAndReports() public {
        vm.prank(admin); vault.pause();
        vm.prank(alice); vm.expectRevert(); vault.deposit(1e6, alice);
        vm.prank(admin); vm.expectRevert(); vault.deployCapital(1e6);
        vm.prank(admin); vm.expectRevert(); vault.reportStrategyNav(1e6);
        vm.prank(admin); vault.unpause();
        vm.prank(alice); vault.deposit(1e6, alice);
    }

    function testZeroAndRoundingInputsRejected() public {
        vm.prank(alice); vm.expectRevert("invalid deposit"); vault.deposit(0, alice);
        vm.prank(alice); vm.expectRevert("invalid redemption"); vault.requestRedeem(0);
    }

    function testMultipleInvestorsAndRoundingDoNotCreateFreeShares() public {
        vm.prank(alice); vault.deposit(100e6, alice);
        vm.prank(admin); vault.reportStrategyNav(100e6);
        vm.prank(bob); vault.deposit(1, bob);
        assertGt(vault.balanceOf(bob), 0);
        assertLe(vault.totalSupply(), 100e18 + 1e12);
        assertEq(vault.totalNavUsdc(), usdc.balanceOf(address(vault)) + vault.reportedStrategyNavUsdc());
        vm.prank(charlie); vm.expectRevert("invalid deposit"); vault.deposit(0, charlie);
    }
}
