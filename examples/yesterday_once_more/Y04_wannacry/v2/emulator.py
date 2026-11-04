#!/usr/bin/env python3
"""Compile a small SEED network with one host holding dummy documents."""

import argparse
import json
from pathlib import Path
import sys


# Use this checkout when the example is launched directly from any directory.
SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parents[3]
sys.path.insert(0, str(REPO_ROOT))

from chainseed.compiler import ChainSeedDocker  # noqa: E402
from seedemu.compiler import Platform  # noqa: E402
from seedemu.core import Emulator  # noqa: E402
from seedemu.layers import Base, Routing  # noqa: E402
from lab_chain import add_chain  # noqa: E402


LAB_DIR = "/opt/wannacry-v2"
CORPUS_DIR = "/home/seed/import_folder"


def build_emulator():
    """Define the network and the sample host's startup behavior."""
    emu = Emulator()
    base = Base()

    # AS180 keeps this small example separate from the earlier chain topology.
    lab_as = base.createAutonomousSystem(180)
    lab_as.createNetwork("net0", prefix="10.180.0.0/24")
    lab_as.createRouter("router0").joinNetwork("net0")
    victim = lab_as.createHost("host_0").joinNetwork("net0")

    victim.addSoftware("python3 python3-cryptography python3-pip")
    victim.addBuildCommand("pip3 install --break-system-packages eth-account==0.13.7")
    for name in (
        "file_generator.py",
        "prepare_participant.py",
        "lab_keylogic.py",
        "lab_ransom_chain.py",
        "check_state.py",
        "participant.py",
        "lab_wallet.py",
        "terminal_ui.py",
        "PARTICIPANT_README.txt",
    ):
        source = (SCRIPT_DIR / name).read_text(encoding="utf-8")
        victim.setFile(f"{LAB_DIR}/{name}", source)
    victim.setFile(
        f"{CORPUS_DIR}/READ_ME.txt",
        (SCRIPT_DIR / "PARTICIPANT_README.txt").read_text(encoding="utf-8"),
    )
    victim.appendStartCommand(
        f"python3 {LAB_DIR}/file_generator.py --target {CORPUS_DIR} && "
        f"python3 {LAB_DIR}/prepare_participant.py --target {CORPUS_DIR} "
        f"--participant-id as180-host_0 --state-file {LAB_DIR}/participant.json"
    )

    emu.addLayer(base)
    emu.addLayer(Routing())
    config = add_chain(emu, lab_as)
    victim.setFile(f"{LAB_DIR}/chain.json", json.dumps(config, indent=2) + "\n")

    contracts_dir = Path(f"{LAB_DIR}/contracts")
    victim.setFile(
        f"{contracts_dir}/RansomExchange.abi",
        (SCRIPT_DIR / "contracts" / "RansomExchange.abi").read_text(encoding="utf-8"),
    )
    return emu


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--platform", choices=["amd", "arm"], default="amd")
    parser.add_argument("--output", type=Path, default=SCRIPT_DIR / "output")
    parser.add_argument(
        "--override", action="store_true", help="replace an existing output directory"
    )
    args = parser.parse_args()

    platform = Platform.AMD64 if args.platform == "amd" else Platform.ARM64
    output = args.output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)

    emu = build_emulator()
    emu.render()
    compiler = ChainSeedDocker(platform=platform, internetMapEnabled=True)
    emu.compile(compiler, str(output), override=args.override)
    print(f"Docker configuration written to {output}")


if __name__ == "__main__":
    main()
