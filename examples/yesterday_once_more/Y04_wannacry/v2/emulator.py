#!/usr/bin/env python3
"""Compile a small SEED network: one victim host (host_0) and one attacker
host (host_1). Propagation is not simulated yet; the worm's key-delivery step
is performed manually by copying attacker_pub.pem from host_1 to host_0."""

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


# The victim host holds the infected endpoint tooling (payload, ransom-note UI,
# baseline verification). The attacker host holds only the attacker-side
# tooling; attacker_priv is born there and never leaves it.
VICTIM_FILES = (
    "file_generator.py",
    "prepare_participant.py",
    "lab_keylogic.py",
    "lab_ransom_chain.py",
    "check_state.py",
    "participant.py",
    "lab_wallet.py",
    "terminal_ui.py",
    "wormdoor.py",
    "PARTICIPANT_README.txt",
)
ATTACKER_FILES = (
    "file_generator.py",
    "lab_keylogic.py",
    "lab_ransom_chain.py",
    "lab_wallet.py",
    "check_state.py",
)


def stage_lab_files(host, names):
    """Install common runtime deps and copy the given lab files into a host."""
    host.addSoftware("python3 python3-cryptography python3-pip")
    host.addBuildCommand("pip3 install --break-system-packages eth-account==0.13.7")
    for name in names:
        source = (SCRIPT_DIR / name).read_text(encoding="utf-8")
        host.setFile(f"{LAB_DIR}/{name}", source)


def stage_chain_files(host, config):
    """Give a host the chain config and the contract ABI."""
    host.setFile(f"{LAB_DIR}/chain.json", json.dumps(config, indent=2) + "\n")
    host.setFile(
        f"{LAB_DIR}/contracts/RansomExchange.abi",
        (SCRIPT_DIR / "contracts" / "RansomExchange.abi").read_text(encoding="utf-8"),
    )


def build_emulator():
    """Define the network and both hosts' startup behavior."""
    emu = Emulator()
    base = Base()

    # AS180 keeps this small example separate from the earlier chain topology.
    lab_as = base.createAutonomousSystem(180)
    lab_as.createNetwork("net0", prefix="10.180.0.0/24")
    lab_as.createRouter("router0").joinNetwork("net0")
    victim = lab_as.createHost("host_0").joinNetwork("net0")
    attacker = lab_as.createHost("host_1").joinNetwork("net0")

    stage_lab_files(victim, VICTIM_FILES)
    victim.setFile(
        f"{CORPUS_DIR}/READ_ME.txt",
        (SCRIPT_DIR / "PARTICIPANT_README.txt").read_text(encoding="utf-8"),
    )
    victim.appendStartCommand(
        f"python3 {LAB_DIR}/file_generator.py --target {CORPUS_DIR} && "
        f"python3 {LAB_DIR}/prepare_participant.py --target {CORPUS_DIR} "
        f"--participant-id as180-host_0 --state-file {LAB_DIR}/participant.json"
    )
    # The delivery inbox stands in for the worm's drop point: it accepts the
    # attacker public key over HTTP and detonates the already-present payload.
    victim.appendStartCommand(
        f"nohup python3 {LAB_DIR}/wormdoor.py --port 4450 --target {CORPUS_DIR} "
        f"> {LAB_DIR}/wormdoor.log 2>&1 &"
    )

    stage_lab_files(attacker, ATTACKER_FILES)

    emu.addLayer(base)
    emu.addLayer(Routing())
    config = add_chain(emu, lab_as)
    stage_chain_files(victim, config)
    stage_chain_files(attacker, config)
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
