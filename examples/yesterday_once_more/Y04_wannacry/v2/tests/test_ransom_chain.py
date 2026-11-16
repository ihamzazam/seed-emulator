"""Verify the on-chain transport without a running chain.

Covers: ABI selector agreement between lab_ransom_chain and the compiled
contract ABI, calldata round-trips through eth_abi, event-id extraction,
and the full offline reply encryption used by attacker_watch.
"""

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lab_keylogic
import lab_ransom_chain as chain
from eth_abi import encode as abi_encode, decode as abi_decode
from eth_utils import keccak


ABI = json.loads(
    (Path(__file__).resolve().parents[1] / "contracts" / "RansomExchange.abi").read_text()
)


def abi_selector(name: str, inputs: list) -> bytes:
    signature = f"{name}({','.join(inputs)})"
    return keccak(text=signature)[:4]


class SelectorAgreementTests(unittest.TestCase):
    """Selectors used by hand must match the compiled contract's ABI."""

    def test_register_selector_matches_abi(self):
        register = next(f for f in ABI if (f.get("name") or "") == "registerVictim")
        inputs = [i["type"] for i in register["inputs"]]
        self.assertEqual(chain.SELECTOR_REGISTER, abi_selector("registerVictim", inputs))

    def test_reply_and_read_selectors_match_abi(self):
        submit = next(f for f in ABI if (f.get("name") or "") == "submitReply")
        get = next(f for f in ABI if (f.get("name") or "") == "getReply")
        requests = next(f for f in ABI if (f.get("name") or "") == "requests")
        self.assertEqual(
            chain.SELECTOR_SUBMIT_REPLY,
            abi_selector("submitReply", [i["type"] for i in submit["inputs"]]),
        )
        self.assertEqual(
            chain.SELECTOR_GET_REPLY, abi_selector("getReply", [i["type"] for i in get["inputs"]])
        )
        self.assertEqual(
            chain.SELECTOR_REQUESTS,
            abi_selector("requests", [i["type"] for i in requests["inputs"]]),
        )

    def test_event_signature_matches_abi(self):
        event = next(f for f in ABI if f["type"] == "event" and (f.get("name") or "") == "VictimRegistered")
        inputs = [i["type"] for i in event["inputs"]]
        self.assertEqual(chain.EVENT_REGISTERED, keccak(text=f"VictimRegistered({','.join(inputs)})"))


class CalldataTests(unittest.TestCase):
    def test_register_calldata_round_trip(self):
        blob = json.dumps({"wrap": "x"}).encode()
        data = chain.SELECTOR_REGISTER + abi_encode(["bytes"], [blob])
        payload = data[len(chain.SELECTOR_REGISTER):]
        (decoded_blob,) = abi_decode(["bytes"], payload)
        self.assertEqual(decoded_blob, blob)

    def test_reply_calldata_round_trip(self):
        reply = json.dumps({"reply_pub_b64": "AA==", "nonce": "BQ==", "ct": "Ag=="}).encode()
        data = chain.SELECTOR_SUBMIT_REPLY + abi_encode(["uint256", "bytes"], [3, reply])
        decoded_id, decoded_reply = abi_decode(
            ["uint256", "bytes"], data[len(chain.SELECTOR_SUBMIT_REPLY):]
        )
        self.assertEqual((decoded_id, decoded_reply), (3, reply))

    def test_getreply_decode_round_trip(self):
        sealed = json.dumps({"ct": "Ag=="}).encode()
        encoded = abi_encode(["bytes"], [sealed])
        (decoded,) = abi_decode(["bytes"], encoded)
        self.assertEqual(json.loads(decoded.decode())["ct"], "Ag==")


class ReceiptTests(unittest.TestCase):
    def test_extract_request_id_from_receipt(self):
        topic = "0x" + chain.EVENT_REGISTERED.hex()
        receipt = {
            "logs": [
                {"topics": ["0x" + "aa" * 32]},
                {"topics": [topic, "0x" + hex(7)[2:].rjust(64, "0")]},
            ]
        }
        self.assertEqual(chain.extract_request_id(receipt), 7)

    def test_missing_event_raises(self):
        with self.assertRaises(RuntimeError):
            chain.extract_request_id({"logs": []})


class OfflineReplyTests(unittest.TestCase):
    """The offline crypto used inside attacker_watch, end to end."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        lab_keylogic.create_attacker_keys(self.root / "attacker_keys.json")
        # Build the payload keylog against a real generated corpus.
        import file_generator
        file_generator.generate(self.corpus)
        lab_keylogic.payload_exec(
            self.corpus, "as180-host_0",
            (self.root / "attacker_pub.pem").read_bytes() if False else
            json.loads((self.root / "attacker_keys.json").read_text())["attacker_pub_pem"].encode(),
            self.root / "lab_keylogic.json",
        )
        self.keylog = json.loads((self.root / "lab_keylogic.json").read_text())

    def test_attacker_watch_reply_round_trip(self):
        victim_priv_pem = lab_keylogic.attacker_open_victim_priv(
            lab_keylogic.unb64(
                json.loads((self.root / "attacker_keys.json").read_text())["attacker_priv_pem"]
            ),
            self.keylog,
        )
        # New protocol: the attacker replies with victim_priv in PLAINTEXT —
        # no ephemeral keys, no transport sealing.
        reply = lab_keylogic.attacker_build_reply(victim_priv_pem)
        self.assertEqual(reply["victim_priv_pem"], victim_priv_pem.decode())
        self.assertNotIn("ct", reply)

        # Victim accepts the plaintext reply and derives the file key locally.
        opened = lab_keylogic.victim_accept_reply(reply, self.keylog)
        plain = lab_keylogic.AESGCM(opened["file_key"]).decrypt(
            lab_keylogic.unb64(self.keylog["files"]["notes.txt"]["nonce"]),
            lab_keylogic.unb64(self.keylog["files"]["notes.txt"]["ciphertext"]),
            b"as180-host_0/notes.txt",
        )
        self.assertEqual(plain.decode(), "Team handover notes\nPrepare the weekly report on Friday.\nThe next team meeting is on Monday.\n")

    def test_decryptor_pasted_key_recovers_files(self):
        """The manual decryptor path: paste the granted key, get the files."""
        import base64
        import decryptor
        victim_priv_pem = lab_keylogic.attacker_open_victim_priv(
            lab_keylogic.unb64(
                json.loads((self.root / "attacker_keys.json").read_text())["attacker_priv_pem"]
            ),
            self.keylog,
        )
        file_key = lab_keylogic.victim_open_file_key(victim_priv_pem, self.keylog)
        state_path = self.root / "participant.json"
        state_path.write_text(json.dumps({
            "original_hashes": {
                name: hashlib.sha256(data).hexdigest()
                for name, data in lab_keylogic.SAMPLES.items()
            }
        }))
        decryptor.decrypt_everything(
            file_key, self.corpus,
            self.root / "lab_keylogic.json", state_path,
        )
        for name in lab_keylogic.SAMPLES:
            self.assertTrue((self.corpus / name).exists())
            self.assertFalse((self.corpus / (name + lab_keylogic.ENCRYPTED_SUFFIX)).exists())

    def test_decryptor_rejects_bad_key(self):
        from cryptography.exceptions import InvalidTag
        import decryptor
        state_path = self.root / "participant.json"
        state_path.write_text(json.dumps({"original_hashes": {}}))
        with self.assertRaises(InvalidTag):
            # A wrong 32-byte key fails the GCM tag check.
            decryptor.decrypt_everything(
                b"\x05" * 32, self.corpus,
                self.root / "lab_keylogic.json", state_path,
            )

    def test_watch_works_without_local_keylog(self):
        """attacker_watch's on-chain-blob path: no victim keylog required.

        Simulates exactly what attacker_watch does now: builds a keylog VIEW
        from attacker_pub + the on-chain sealed blob and recovers victim_priv.
        """
        attacker_keys = json.loads((self.root / "attacker_keys.json").read_text())
        blob_json = json.dumps(self.keylog["victim_priv_sealed"])  # as stored on-chain
        keylog_view = {
            "attacker_pub_pem": attacker_keys["attacker_pub_pem"],
            "victim_priv_sealed": json.loads(blob_json),
        }
        victim_priv_pem = lab_keylogic.attacker_open_victim_priv(
            lab_keylogic.unb64(attacker_keys["attacker_priv_pem"]), keylog_view
        )
        # A different attacker key must be refused.
        other = self.root / "other_keys.json"
        lab_keylogic.create_attacker_keys(other)
        other_keys = json.loads(other.read_text())
        bad_view = dict(keylog_view, attacker_pub_pem=other_keys["attacker_pub_pem"])
        with self.assertRaises(ValueError):
            lab_keylogic.attacker_open_victim_priv(
                lab_keylogic.unb64(other_keys["attacker_priv_pem"]), bad_view
            )

    def test_wnCRY_naming_and_recovery_round_trip(self):
        """The payload leaves <name>.WNCRY envelopes; recovery restores names."""
        for name in lab_keylogic.SAMPLES:
            self.assertFalse((self.corpus / name).exists())
            envelope = (self.corpus / (name + lab_keylogic.ENCRYPTED_SUFFIX)).read_bytes()
            self.assertTrue(envelope.startswith(lab_keylogic.MAGIC))
        state_path = self.root / "participant.json"
        state_path.write_text(json.dumps({
            "original_hashes": {
                name: hashlib.sha256(data).hexdigest()
                for name, data in lab_keylogic.SAMPLES.items()
            }
        }))
        victim_priv_pem = lab_keylogic.attacker_open_victim_priv(
            lab_keylogic.unb64(
                json.loads((self.root / "attacker_keys.json").read_text())["attacker_priv_pem"]
            ),
            self.keylog,
        )
        file_key = lab_keylogic.victim_open_file_key(victim_priv_pem, self.keylog)
        lab_keylogic.recover_samples(
            file_key, self.corpus, "as180-host_0", self.keylog, state_path
        )
        for name in lab_keylogic.SAMPLES:
            self.assertTrue((self.corpus / name).exists())
            self.assertFalse((self.corpus / (name + lab_keylogic.ENCRYPTED_SUFFIX)).exists())
        self.assertEqual(
            (self.corpus / "notes.txt").read_text(),
            "Team handover notes\nPrepare the weekly report on Friday.\n"
            "The next team meeting is on Monday.\n",
        )


if __name__ == "__main__":
    unittest.main()
