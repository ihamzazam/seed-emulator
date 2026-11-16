#!/usr/bin/env python3
"""WannaCry-style manual decryptor: paste the granted key, get your files.

The attacker's exchange granted a decryption key after the ransom was paid
(option 5 in the participant menu printed it). This tool is the victim's
hands-on recovery step, like the decryptors real ransomware victims ran:

  1. Paste the AES-256 file key you were granted.
  2. Each .WNCRY envelope is decrypted with that key (AES-256-GCM),
     verified against the recorded SHA-256 baseline, restored under its
     original name, and the envelope is deleted.

Nothing is automatic: without the key pasted here, no file comes back.
"""

import argparse
import base64
import json
from pathlib import Path

import lab_keylogic


DEFAULT_KEYLOG = lab_keylogic.DEFAULT_KEYLOG


def decrypt_everything(file_key: bytes, target: Path, keylog_path: Path, state_file: Path):
    keylog = json.loads(keylog_path.read_text(encoding="utf-8"))
    participant_id = keylog["participant_id"]
    print()
    print("Decrypting with the pasted key:")
    lab_keylogic.recover_samples(file_key, target, participant_id, keylog, state_file)
    print()
    print("All ransomware envelopes removed. Your documents are back.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("/home/seed/import_folder"))
    parser.add_argument("--keylog", type=Path, default=DEFAULT_KEYLOG)
    parser.add_argument("--state-file", type=Path,
                        default=Path("/opt/wannacry-v2/participant.json"))
    parser.add_argument("--key", default=None,
                        help="the decryption key you were granted (b64); "
                             "omitted = prompt for it")
    args = parser.parse_args()

    print("=" * 60)
    print("  WANNACRY LAB DECRYPTOR")
    print("  Paste the decryption key the attacker granted you.")
    print("=" * 60)

    pasted = args.key or input("Paste your decryption key: ").strip()
    try:
        file_key = base64.b64decode(pasted.encode("ascii"))
    except Exception:
        raise SystemExit("that is not valid base64; copy the key exactly as printed")
    if len(file_key) != 32:
        raise SystemExit(
            f"expected a 32-byte AES-256 key (got {len(file_key)} bytes); "
            "copy the full key exactly as printed"
        )

    decrypt_everything(file_key, args.target.expanduser(), args.keylog.expanduser(),
                       args.state_file.expanduser())


if __name__ == "__main__":
    main()