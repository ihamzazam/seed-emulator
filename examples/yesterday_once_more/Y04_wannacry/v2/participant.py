#!/usr/bin/env python3
"""Inspect this host's lab samples and use independent local recovery."""

import argparse
import hashlib
from pathlib import Path

from lab_keylogic import MAGIC, NONCE_SIZE, SAMPLES, TAG_SIZE
from terminal_ui import run_interface


def inspect_documents(target: Path, record: dict):
    """Observe known samples without changing files or trusting state alone."""
    if target.is_symlink() or not target.is_dir():
        raise ValueError("sample directory must be a real directory")
    observations = {}
    for name, original in sorted(SAMPLES.items()):
        path = target / name
        envelope_size = len(MAGIC) + NONCE_SIZE + len(original) + TAG_SIZE
        try:
            if path.is_symlink() or not path.is_file():
                status = "MISSING OR NOT A REGULAR FILE"
            elif path.stat().st_size not in (len(original), envelope_size):
                status = "UNEXPECTED SIZE"
            else:
                data = path.read_bytes()
                baseline = record.get("original_hashes", {}).get(name)
                if data == original and hashlib.sha256(data).hexdigest() == baseline:
                    status = "ORIGINAL — baseline matches"
                elif len(data) == envelope_size and data.startswith(MAGIC):
                    status = "LAB ENVELOPE — integrity not checked"
                else:
                    status = "CHANGED OR BASELINE MISMATCH"
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
