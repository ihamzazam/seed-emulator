"""Configure a private teaching chain alongside the participant host.

Besides three Geth nodes and a faucet, this module registers the
RansomExchange smart contract for automatic deployment at emulator start.
The contract is compiled offline (contracts/compile_contract.py); its ABI
and bytecode are embedded as content, so no Solidity toolchain is needed
inside any container.
"""

import json
from pathlib import Path

from chainseed.services.ethereum import ConsensusMechanism, EthereumService
from chainseed.services.ethereum.EthTemplates import UtilityServerFileTemplates
from seedemu.core import Binding, Filter


# Our contract (RansomExchange.abi/bin) needs more deployment gas than
# ChainSeed's pinned 2,000,000 — the real cost of the creation plus the
# code deposit exceeded it and the deploy died silently (the template does
# not check receipt status). The deploy script is a template string that
# is only formatted when the utility server is configured, so the example
# overrides the knob here: our blueprint decides what the chain gets.
UtilityServerFileTemplates["deploy_contract"] = UtilityServerFileTemplates[
    "deploy_contract"
].replace("'gas': 2000000", "'gas': 4500000")


HERE = Path(__file__).resolve().parent
CONTRACT_DIR = HERE / "contracts"
CONTRACT_NAME = "RansomExchange"
# Lab ransom price: 1 lab ETH per victim. The faucet funds up to 5, so a
# participant can always pay once and still keep change.
RANSOM_WEI = 10**18
UTILITY_PORT = 8080


def add_chain(emu, lab_as):
    """Install Geth nodes, a faucet, and the RansomExchange deployment."""
    ethereum = EthereumService()
    chain = ethereum.createBlockchain(chainName="ParticipantLab", consensus=ConsensusMechanism.POA)
    chain.setChainId(18000)
    for index in range(3):
        name = f"chain{index}"
        lab_as.createHost(name).joinNetwork("net0", address=f"10.180.0.{81 + index}")
        node = chain.createNode(name)
        node.enableGethHttp()
        node.unlockAccounts()
        if index < 2:
            node.startMiner()
        if index == 0:
            node.setBootNode(True)
        emu.addBinding(Binding(name, filter=Filter(asn=180, nodeName=name)))
    lab_as.createHost("faucet").joinNetwork("net0", address="10.180.0.90")
    chain.createFaucetServer(
        vnode="faucet", port=80, linked_eth_node="chain2", balance=10000, max_fund_amount=10
    )
    emu.addBinding(Binding("faucet", filter=Filter(asn=180, nodeName="faucet")))

    # Utility server: deploys RansomExchange at start and serves the
    # deployed contract address over HTTP so hosts can discover it.
    lab_as.createHost("utility").joinNetwork("net0", address="10.180.0.95")
    utility = chain.createEthUtilityServer(
        vnode="utility", port=UTILITY_PORT, linked_eth_node="chain2", linked_faucet_node="faucet"
    )
    utility.deployContractByContent(
        CONTRACT_NAME,
        (CONTRACT_DIR / "RansomExchange.abi").read_text(encoding="utf-8"),
        (CONTRACT_DIR / "RansomExchange.bin").read_text(encoding="utf-8"),
    )
    emu.addBinding(Binding("utility", filter=Filter(asn=180, nodeName="utility")))

    emu.addLayer(ethereum)
    return {
        "chain_id": 18000,
        "rpc_url": "http://10.180.0.83:8545",
        "faucet_url": "http://10.180.0.90/fundme",
        "utility_url": f"http://10.180.0.95:{UTILITY_PORT}",
        "contract_name": CONTRACT_NAME,
        "ransom_wei": RANSOM_WEI,
        "contract_abi_path": "/opt/wannacry-v2/contracts/RansomExchange.abi",
        "contract_bin_path": "/opt/wannacry-v2/contracts/RansomExchange.bin",
    }
