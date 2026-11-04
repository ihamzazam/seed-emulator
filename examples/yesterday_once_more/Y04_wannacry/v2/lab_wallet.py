"""Local teaching wallet, read-only balance queries, and lab faucet requests."""

import json
import os
from pathlib import Path
import tempfile
from urllib.request import Request, urlopen

from eth_account import Account
from eth_utils import is_address, is_checksum_address, to_checksum_address


CONFIG = Path(__file__).with_name("chain.json")
FUND_AMOUNT = 5


def wallet_address(path: Path):
    """Read the public address without decrypting or displaying private keys."""
    if path.is_symlink():
        raise ValueError("wallet must not be a symbolic link")
    keyfile = json.loads(path.read_text(encoding="utf-8"))
    return to_checksum_address(keyfile["address"])


def create_wallet(path: Path, password: str):
    """Save one encrypted keystore without overwriting an existing wallet."""
    if not password:
        raise ValueError("choose a nonempty lab wallet password")
    keyfile = Account.encrypt(Account.create().key, password)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".wallet-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(keyfile, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
    return wallet_address(path)


def request_json(url: str, payload: dict, timeout: int = 5):
    """Send one HTTP request with a timeout; never automatically retry."""
    request = Request(
        url,
        json.dumps(payload).encode("utf-8"),
        {"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def rpc(config: dict, method: str, params: list):
    """Query the configured Ethereum node through JSON-RPC."""
    result = request_json(
        config["rpc_url"], {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    )
    if "error" in result:
        raise RuntimeError(f"Ethereum RPC error: {result['error']}")
    return result["result"]


def connect(config_file: Path = CONFIG):
    """Check the lab chain ID before querying funds or using its faucet."""
    config = json.loads(config_file.read_text(encoding="utf-8"))
    if config["chain_id"] != 18000 or int(rpc(config, "eth_chainId", []), 16) != 18000:
        raise ValueError("expected the private participant chain, ID 18000")
    return config


def balance_wei(config: dict, address: str):
    """Return the current on-chain balance as an exact integer."""
    return int(rpc(config, "eth_getBalance", [address, "latest"]), 16)


def format_ether(wei: int):
    """Format wei as ether without floating-point rounding."""
    whole, remainder = divmod(wei, 10**18)
    return f"{whole}.{remainder:018d}".rstrip("0").rstrip(".")


def validate_address(address: str):
    """Accept full addresses and reject mistyped mixed-case checksums."""
    address = address.strip()
    if not address.startswith("0x") or not is_address(address) or int(address, 16) == 0:
        raise ValueError("paste a full, nonzero Ethereum address beginning with 0x")
    letters = address[2:]
    if (
        letters != letters.lower()
        and letters != letters.upper()
        and not is_checksum_address(address)
    ):
        raise ValueError("address checksum does not match; copy the address again")
    return to_checksum_address(address)


def request_funds(config: dict, address: str, amount: int = FUND_AMOUNT):
    """Ask the faucet for lab funds; receipt confirmation is handled by it."""
    address = validate_address(address)
    if type(amount) is not int or not 1 <= amount <= FUND_AMOUNT:
        raise ValueError("choose a whole amount from 1 to 5 lab ETH")
    try:
        result = request_json(
            config["faucet_url"], {"address": address, "amount": amount}, timeout=30
        )
    except (OSError, ValueError) as error:
        raise RuntimeError(
            "Faucet response unavailable. The request may have been submitted; "
            "check your balance before requesting again."
        ) from error
    if result.get("status") != "success":
        raise RuntimeError(f"Faucet rejected request: {result.get('message', 'unknown error')}")
    return result
