// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {FruitFlyFundVault} from "../src/FruitFlyFundVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";

contract DeployFund is Script {
    function run() external returns (MockUSDC usdc, FruitFlyFundVault vault) {
        uint256 deployerKey = vm.envUint("PRIVATE_KEY");
        address admin = vm.addr(deployerKey);
        address configuredUsdc = vm.envOr("FUND_USDC_ADDRESS", address(0));
        address treasury = vm.envOr("PRIVY_WALLET_ADDRESS", admin);
        vm.startBroadcast(deployerKey);
        if (configuredUsdc == address(0)) {
            usdc = new MockUSDC();
        } else {
            usdc = MockUSDC(configuredUsdc);
        }
        vault = new FruitFlyFundVault(address(usdc), treasury, admin);
        vm.stopBroadcast();
        console2.log("USDC", address(usdc));
        console2.log("FruitFlyFundVault", address(vault));
        console2.log("Strategy treasury", treasury);
    }
}

