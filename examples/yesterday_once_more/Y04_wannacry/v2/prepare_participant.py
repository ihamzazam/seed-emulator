#!/usr/bin/env python3
"""Record a lab participant's identity and original sample-document hashes."""

import argparse
import hashlib
import json
from pathlib import Path

from file_generator import FILES


def prepare(target: Path, participant_id: str, state_file: Path):
    """Write a PREPARED record after reading all five generated documents."""
    if not participant_id.strip():
        raise ValueError("participant ID must not be empty")
    if state_file.resolve() in {(target / name).resolve() for name in FILES}:
        raise ValueError("state file must not overwrite a sample document")

    original_hashes = {}
    for name in sorted(FILES):
        data = (target / name).read_bytes()
        original_hashes[name] = hashlib.sha256(data).hexdigest()

    record = {
        "participant_id": participant_id,
        "state": "PREPARED",
        "original_hashes": original_hashes,
    }
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(f"{participant_id}: PREPARED ({len(original_hashes)} documents)")
    print(f"Record: {state_file}")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, type=Path)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--state-file", required=True, type=Path)
    args = parser.parse_args()
    prepare(
        args.target.expanduser(),
        args.participant_id,
        args.state_file.expanduser(),
    )


if __name__ == "__main__":
    main()
