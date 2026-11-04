"""Lightweight terminal screens; no web server or idle background polling."""

from contextlib import contextmanager
from datetime import datetime
import fcntl
from getpass import getpass
import json
import os
from pathlib import Path
import shutil
import sys
from threading import Event, Thread

from cryptography.exceptions import InvalidTag

import lab_wallet
import lab_keylogic


ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, RuntimeError)
INSTRUCTIONS = Path(__file__).with_name("PARTICIPANT_README.txt")


def interactive_terminal():
    return sys.stdout.isatty() and os.environ.get("TERM", "") != "dumb"


def heading(title: str, subtitle: str):
    """Redraw real terminals; keep redirected output plain and readable."""
    width = min(78, max(42, shutil.get_terminal_size().columns))
    if interactive_terminal():
        print("\033[2J\033[H", end="")
    color = interactive_terminal() and "NO_COLOR" not in os.environ
    print("=" * width)
    print(f"\033[1;36m{title}\033[0m" if color else title)
    print(subtitle)
    print("=" * width)


def field(label, value):
    print(f"  {label:<16} {value}")


def pause():
    input("\nPress Enter to continue...")


@contextmanager
def busy(message: str):
    """Animate during an operation; stop the animation on exceptions."""
    print(f"\n{message}", flush=True)
    done = Event()

    def animate():
        frames = "|/-\\"
        index = 0
        while not done.wait(0.15):
            print(f"\r  {frames[index % 4]} Working...", end="", flush=True)
            index += 1

    thread = Thread(target=animate, daemon=True) if interactive_terminal() else None
    if thread:
        thread.start()
    try:
        yield
    finally:
        done.set()
        if thread:
            thread.join()
            print("\r\033[K", end="", flush=True)


def wallet_screen(wallet_file):
    balance = "Not checked"
    checked = "Use r to refresh"
    while True:
        heading("PARTICIPANT WALLET", "Private chain 18000 / local password-protected keystore")
        exists = wallet_file.exists() or wallet_file.is_symlink()
        address = lab_wallet.wallet_address(wallet_file) if exists else None
        field("Address", address or "No wallet yet")
        field("Balance", balance)
        field("Last checked", checked)
        if address:
            print("\nSelect the full address above to copy using your terminal's copy shortcut.")
        print("\n[c] Create wallet   [r] Refresh balance   [l] Look up an address")
        print("[b] Back")
        choice = input("\nWallet > ").strip().lower()
        if choice == "b":
            return
        try:
            if choice == "c":
                if exists:
                    raise ValueError("your wallet already exists; its address is shown above")
                password = getpass("Choose a lab wallet password: ")
                if password != getpass("Repeat password: "):
                    raise ValueError("passwords do not match")
                with busy("Creating your encrypted wallet locally..."):
                    lab_wallet.create_wallet(wallet_file, password)
                del password
                balance, checked = "Not checked", "Wallet created; use r to refresh"
            elif choice == "r":
                if not address:
                    raise ValueError("create a wallet first")
                with busy("Reading balance from chain 18000..."):
                    config = lab_wallet.connect()
                    value = lab_wallet.balance_wei(config, address)
                balance = f"{lab_wallet.format_ether(value)} lab ETH"
                checked = datetime.now().astimezone().isoformat(timespec="seconds")
            elif choice == "l":
                lookup = lab_wallet.validate_address(input("Paste an address to look up: "))
                with busy("Querying the pasted address..."):
                    value = lab_wallet.balance_wei(lab_wallet.connect(), lookup)
                field("Address", lookup)
                field("Balance", f"{lab_wallet.format_ether(value)} lab ETH")
                pause()
            else:
                print("Choose one of the displayed actions.")
                pause()
        except ERRORS as error:
            if choice == "r":
                balance, checked = "Unavailable", "Refresh failed; check chain connectivity"
            print(f"\nWallet: {error}")
            pause()


def run_interface(target, state_file, inspect_documents):
    """Allow one active UI per participant to avoid overlapping actions."""
    wallet_file = state_file.parent / "wallet.json"
    lab_dir = state_file.parent
    try:
        with (state_file.parent / ".participant-ui.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            while True:
                heading(
                    "SEED INCIDENT LAB", "Participant workspace / wallet and document exercises"
                )
                try:
                    record = json.loads(state_file.read_text(encoding="utf-8"))
                    field("Participant", record["participant_id"])
                    field("Recorded state", record["state"])
                except ERRORS as error:
                    print(f"Participant record unavailable: {error}")
                field("Wallet", "Available" if wallet_file.exists() else "Not created")
                print("\n  DOCUMENTS                      WALLET & FUNDING")
                print("  [1] Instructions               [6] My wallet")
                print("  [2] Inspect documents")
                print("  [5] Document recovery (exchange)")
                print("\n  [0] Exit")
                print("\nPayment contracts are not implemented; wallet funding does not gate recovery.")
                choice = input("\nHome > ").strip()
                try:
                    if choice == "0":
                        return
                    if choice == "1":
                        heading("INCIDENT INSTRUCTIONS", "Participant guide")
                        print(INSTRUCTIONS.read_text(encoding="utf-8"))
                        pause()
                    elif choice == "2":
                        heading("DOCUMENT INSPECTION", "Current observations / no files changed")
                        record = json.loads(state_file.read_text(encoding="utf-8"))
                        for name, status in inspect_documents(target, record).items():
                            field(name, status)
                        pause()
                    elif choice == "5":
                        heading(
                            "DOCUMENT RECOVERY",
                            "Blockchain key exchange / enforced ransom payment",
                        )
                        lab_dir = state_file.parent
                        wallet_file = lab_dir / "wallet.json"
                        chain_config = lab_dir / "chain.json"
                        password = None
                        request_file = lab_dir / "exchange_request.json"
                        already_registered = (
                            request_file.exists()
                            and json.loads(request_file.read_text(encoding="utf-8"))
                            .get("request_id")
                            is not None
                        )
                        if (
                            wallet_file.exists()
                            and chain_config.exists()
                            and not already_registered
                            and not (lab_dir / "exchange_reply.json").exists()
                        ):
                            password = getpass(
                                "Wallet password (to sign the paid registration): "
                            )
                        lab_keylogic.run_recovery_step(
                            target, state_file, lab_dir, password=password
                        )
                        pause()
                    elif choice in ("6", "7"):
                        wallet_screen(wallet_file)
                    else:
                        print("Choose one of the displayed actions.")
                        pause()
                except InvalidTag:
                    print("Sample authentication failed; this attempt restored no files.")
                    pause()
                except ERRORS as error:
                    print(f"Action unavailable: {error}")
                    pause()
    except BlockingIOError:
        print("Another participant menu is already open. Close it before opening a new one.")
    except (EOFError, KeyboardInterrupt):
        print("\nLeaving participant workspace.")
