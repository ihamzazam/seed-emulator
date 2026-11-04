#!/usr/bin/env python3
"""Create five deterministic dummy documents for the classroom exercise.

Running again overwrites these five filenames with their original contents.
Other files in the target directory are left alone.
"""

import argparse
from pathlib import Path


# All names and contents are fictional sample data.
FILES = {
    "notes.txt": (
        "Team handover notes\n"
        "Prepare the weekly report on Friday.\n"
        "The next team meeting is on Monday.\n"
    ),
    "budget.csv": (
        "department,allocated,spent\n"
        "operations,12000,9500\n"
        "it,8000,6200\n"
    ),
    "report.md": (
        "# Monthly report\n"
        "\n"
        "The team completed three training sessions this month.\n"
    ),
    "contacts.csv": (
        "name,team,extension\n"
        "Alex,Operations,4101\n"
        "Sam,IT,4102\n"
    ),
    "minutes.txt": (
        "Meeting minutes\n"
        "1. Review the training schedule.\n"
        "2. Prepare next month's equipment list.\n"
    ),
}


def generate(target: Path) -> int:
    """Write the sample documents and return the number written."""
    target.mkdir(parents=True, exist_ok=True)

    for name in sorted(FILES):
        path = target / name
        data = FILES[name].encode("utf-8")
        path.write_bytes(data)
        print(f"wrote {path} ({len(data)} bytes)")

    return len(FILES)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--target",
        required=True,
        type=Path,
        help="directory for the generated dummy documents",
    )
    args = parser.parse_args()
    count = generate(args.target.expanduser())
    print(f"Corpus ready: {count} files")


if __name__ == "__main__":
    main()
