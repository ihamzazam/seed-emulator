"""The victim delivery inbox: one drop detonates the payload exactly once."""

import json
import sys
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import file_generator
import lab_keylogic
import wormdoor


class WormDoorTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)
        self.corpus = self.root / "corpus"
        self.corpus.mkdir()
        file_generator.generate(self.corpus)
        # Re-point the door's constants at the temporary lab.
        wormdoor.LAB_DIR = self.root
        wormdoor.DEFAULT_TARGET = self.corpus
        wormdoor.STATE_FILE = self.root / "participant.json"
        wormdoor.KEYLOG_PATH = self.root / "lab_keylogic.json"
        wormdoor.PUB_PATH = self.root / "attacker_pub.pem"
        lab_keylogic.create_attacker_keys(self.root / "attacker_keys.json")
        self.pub = json.loads(
            (self.root / "attacker_keys.json").read_text()
        )["attacker_pub_pem"]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), wormdoor.DoorHandler)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def _post(self, path: str, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        return Request(
            f"{self.base}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
        )

    def test_drop_rejects_garbage_detonates_once_then_reports_infected(self):
        with urlopen(f"{self.base}/status", timeout=5) as response:
            self.assertEqual(json.load(response)["status"], "clean")

        # A non-PEM payload is rejected before anything is written.
        with self.assertRaises(HTTPError) as caught:
            urlopen(self._post("/drop", {"attacker_pub_pem": "garbage"}), timeout=10)
        self.assertEqual(caught.exception.code, 400)
        self.assertEqual(json.load(caught.exception)["status"], "rejected")
        self.assertFalse(wormdoor.PUB_PATH.exists())

        # The real delivery: pub key persisted, payload detonated in-process.
        with urlopen(self._post("/drop", {"attacker_pub_pem": self.pub}), timeout=30) as response:
            result = json.load(response)
        self.assertEqual(result["status"], "infected")
        self.assertEqual(result["files_encrypted"], len(lab_keylogic.SAMPLES))
        self.assertTrue(wormdoor.PUB_PATH.exists())
        for name in lab_keylogic.SAMPLES:
            self.assertFalse((self.corpus / name).exists())
            self.assertTrue((self.corpus / (name + lab_keylogic.ENCRYPTED_SUFFIX)).exists())

        # The inbox is one-shot: a second delivery is refused, nothing changes.
        with urlopen(self._post("/drop", {"attacker_pub_pem": self.pub}), timeout=10) as response:
            again = json.load(response)
        self.assertEqual(again["status"], "already_infected")

        with urlopen(f"{self.base}/status", timeout=5) as response:
            self.assertEqual(json.load(response)["status"], "infected")


if __name__ == "__main__":
    unittest.main()
