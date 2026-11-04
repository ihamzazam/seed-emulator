#!/usr/bin/env python3
"""Compile RansomExchange.sol offline and write .abi/.bin beside the source.

Run from the example directory:  python3 compile_contract.py
Requires py-solc-x (pip install py-solc-x); the solc binary is fetched on
first use. The lab chain consumes the generated files at compile time.
"""

import json
from pathlib import Path

import solcx

HERE = Path(__file__).resolve().parent
SOL_VERSION = "0.8.20"
PRAGMA = f"pragma solidity {SOL_VERSION};"


def main():
    installed = [str(v) for v in solcx.get_installed_solc_versions()]
    if SOL_VERSION not in installed:
        solcx.install_solc(SOL_VERSION)

    source = (HERE / "RansomExchange.sol").read_text(encoding="utf-8")
    if PRAGMA not in source:
        raise SystemExit("contract pragma does not match the pinned solc version")

    result = solcx.compile_source(
        source,
        output_values=("abi", "bin"),
        solc_version=SOL_VERSION,
        optimize=True,
        optimize_runs=200,
        # The lab's geth image predates the Shanghai EVM: PUSH0 (0x5f) is an
        # invalid opcode there and silently burns all deployment gas.
        evm_version="london",
    )
    _, artifacts = next(iter(result.items()))

    (HERE / "RansomExchange.abi").write_text(
        json.dumps(artifacts["abi"], indent=2) + "\n", encoding="utf-8"
    )
    (HERE / "RansomExchange.bin").write_text(
        artifacts["bin"].strip() + "\n", encoding="utf-8"
    )
    print(f"compiled: {len(artifacts['bin']) // 2} bytes of bytecode")
    print("wrote RansomExchange.abi and RansomExchange.bin")


if __name__ == "__main__":
    main()
