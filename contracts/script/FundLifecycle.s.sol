// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Script} from "forge-std/Script.sol";
import {FruitFlyFundVault} from "../src/FruitFlyFundVault.sol";
import {MockUSDC} from "../src/mocks/MockUSDC.sol";

contract FundLifecycle is Script {
    function run() external {
        uint256 key = vm.envUint("PRIVATE_KEY");
        MockUSDC usdc = MockUSDC(vm.envAddress("FUND_USDC_ADDRESS"));
        FruitFlyFundVault vault = FruitFlyFundVault(vm.envAddress("FUND_CONTRACT_ADDRESS"));
        address alice = vm.addr(key);
        vm.startBroadcast(key);
        usdc.mint(alice, 100e6);
        usdc.approve(address(vault), 100e6);
        vault.deposit(100e6, alice);
        vault.deployCapital(50e6);
        vault.reportStrategyNav(55e6);
        console2.log("Alice shares", vault.balanceOf(alice));
        console2.log("NAV/share (USDC base units)", vault.navPerShareUsdc());
        vm.stopBroadcast();
    }
}

