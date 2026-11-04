#!/usr/bin/env python3
"""Inspect this host's lab samples and use independent local recovery."""

import argparse
import hashlib
from pathlib import Path

from lab_keylogic import ENCRYPTED_SUFFIX, MAGIC, NONCE_SIZE, SAMPLES, TAG_SIZE
from terminal_ui import run_interface


def inspect_documents(target: Path, record: dict):
    """Observe known samples without changing files or trusting state alone."""
    if target.is_symlink() or not target.is_dir():
        raise ValueError("sample directory must be a real directory")
    observations = {}
    for name, original in sorted(SAMPLES.items()):
        plain_path = target / name
        cipher_path = target / (name + ENCRYPTED_SUFFIX)
        envelope_size = len(MAGIC) + NONCE_SIZE + len(original) + TAG_SIZE
        try:
            plain_present = not plain_path.is_symlink() and plain_path.is_file()
            cipher_present = not cipher_path.is_symlink() and cipher_path.is_file()
            if plain_present and cipher_present:
                status = "INCONSISTENT — both plaintext and .WNCRY envelope exist"
            elif cipher_present:
                data = cipher_path.read_bytes()
                if len(data) == envelope_size and data.startswith(MAGIC):
                    status = "ENCRYPTED (.WNCRY) — ransomware envelope present"
                else:
                    status = "ENCRYPTED (.WNCRY) — UNEXPECTED FORMAT"
            elif plain_present:
                data = plain_path.read_bytes()
                baseline = record.get("original_hashes", {}).get(name)
                if data == original and hashlib.sha256(data).hexdigest() == baseline:
                    status = "ORIGINAL — baseline matches"
                else:
                    status = "CHANGED OR BASELINE MISMATCH"
            else:
                status = "MISSING"
        except OSError as error:
            status = f"UNREADABLE — {error}"
        observations[name] = status
    return observations


def interact(target: Path, state_file: Path):
    """Open the workspace with the existing read-only sample inspector."""
    run_interface(target, state_file, inspect_documents)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, default=Path("/home/seed/import_folder"))
    parser.add_argument(
        "--state-file", type=Path, default=Path("/opt/wannacry-v2/participant.json")
    )
    args = parser.parse_args()
    interact(args.target.expanduser(), args.state_file.expanduser())


if __name__ == "__main__":
    main()
