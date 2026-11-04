#!/usr/bin/env python3
"""One-shot read-only status of the lab: contract, wallet, chain requests.

Run on the participant host:  python3 /opt/wannacry-v2/check_state.py
It sends no transactions and moves no money.
"""

import json
from pathlib import Path
from urllib.request import urlopen

import lab_keylogic
import lab_ransom_chain
import lab_wallet


LAB_DIR = Path("/opt/wannacry-v2")


def main():
    cfg = lab_wallet.connect()
    print(f"chain id {cfg['chain_id']} at {cfg['rpc_url']}")

    try:
        with urlopen("http://127.0.0.1:4450/status", timeout=3) as response:
            door = json.load(response)
        print(f"door:     {door.get('status')} (delivery inbox on :4450)")
    except OSError:
        print("door:     not running (delivery inbox service is down)")

    contract = lab_ransom_chain.discover_contract(cfg)
    code = lab_wallet.rpc(cfg, "eth_getCode", [contract, "latest"])
    code_bytes = (len(code) - 2) // 2
    print(f"contract: {contract}")
    print(f"  code on-chain: {code_bytes} bytes "
          f"({'ALIVE' if code_bytes > 0 else 'DEAD - deployment failed!'})")

    wallet_file = LAB_DIR / "wallet.json"
    if wallet_file.exists():
        address = lab_wallet.wallet_address(wallet_file)
        balance = lab_wallet.balance_wei(cfg, address)
        print(f"wallet:   {address}")
        print(f"  balance: {lab_wallet.format_ether(balance)} lab ETH "
              f"({'can pay 1 ETH ransom' if balance >= 10**18 else 'buy lab ETH on the SEED Exchange (menu option 3)'})")
    else:
        print("wallet:   none yet (create it in the participant menu, option 6)")

    keylog = LAB_DIR / "lab_keylogic.json"
    if keylog.exists():
        record = json.loads(keylog.read_text(encoding="utf-8"))
        print(f"payload:  executed on {record['participant_id']} "
              f"({len(record['files'])} files encrypted as .WNCRY)")
    else:
        print("payload:  not executed yet (waiting for the attacker's delivery)")

    request_path = LAB_DIR / "exchange_request.json"
    if request_path.exists():
        request = json.loads(request_path.read_text(encoding="utf-8"))
        rid = request.get("request_id")
        print(f"request:  built"
              + (f", registered on-chain as id {rid}" if rid is not None else ", not registered yet"))
    else:
        print("request:  none yet (menu option 5 builds it)")

    replies = []
    if code_bytes > 0:
        for entry in lab_ransom_chain.poll_requests(cfg):
            replies.append(entry)
    if replies:
        for entry in replies:
            state = "ANSWERED" if entry["answered"] else "waiting for attacker"
            print(f"chain:    request {entry['id']} from {entry['victim'][:10]}... -> {state}")
    else:
        print("chain:    no requests registered")

    reply_file = LAB_DIR / "exchange_reply.json"
    if reply_file.exists():
        print("reply:    received (next menu-5 press accepts it and decrypts)")
    else:
        print("reply:    not received yet")


if __name__ == "__main__":
    main()
