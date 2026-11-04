"""Exercise participant-lock behavior and wallet input validation."""

import contextlib
import fcntl
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import lab_keylogic  # noqa: E402
import lab_wallet as wallet  # noqa: E402
import terminal_ui as ui  # noqa: E402

ADDRESS = "0x1111111111111111111111111111111111111111"
CONFIG = {"chain_id": 18000, "rpc_url": "http://unused", "faucet_url": "http://unused"}


class WalletValidationTests(unittest.TestCase):
    def test_invalid_input_never_reaches_faucet(self):
        with patch.object(wallet, "request_json") as request:
            for address, amount in [
                ("wrong", 1),
                ("0x" + "0" * 40, 1),
                (ADDRESS, 6),
                (ADDRESS, True),
                (ADDRESS, 0),
            ]:
                with self.subTest(address=address, amount=amount), self.assertRaises(ValueError):
                    wallet.request_funds(CONFIG, address, amount)
            request.assert_not_called()
        with self.assertRaises(ValueError):
            wallet.validate_address("0x52908400098527886e0F7030069857D2E4169EE7")

    def test_recovery_step_refuses_before_payload(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        with self.assertRaises(ValueError):
            lab_keylogic.run_recovery_step(root / "corpus", root / "participant.json", root)


class NavigationTests(unittest.TestCase):
    def test_second_menu_is_blocked_by_participant_lock(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        with (root / ".participant-ui.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch("builtins.input") as prompt:
                with contextlib.redirect_stdout(io.StringIO()) as output:
                    ui.run_interface(root, root / "participant.json", None)
                prompt.assert_not_called()
        self.assertIn("already open", output.getvalue())


if __name__ == "__main__":
    unittest.main()
