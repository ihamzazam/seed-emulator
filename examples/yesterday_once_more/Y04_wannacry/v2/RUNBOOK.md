# WannaCry Incident Lab — Master Runbook (v2.1)

The operator walkthrough for the full incident, end to end. This is the exact
path proven live on 2026-11-05 (clean build, zero hot-patches). Command-line
purists can find the same actions without the menus in `MANUAL_RUNBOOK.txt`;
this runbook is the primary demo path.

Addresses below are this build's stable assignments — read the node IPs off
the SEED map if they ever differ.

## Environment overview

| Piece | Where | Role |
|---|---|---|
| Docker host + SEED map (localhost:8080) | your machine | build, then open shells into nodes |
| host_0 (10.180.0.71) | AS180 | victim workstation — documents, ransom note, participant menu |
| host_1 (10.180.0.72) | AS180 | attacker machine — all offensive tooling |
| chain0/1/2 (RPC on 10.180.0.83:8545) | AS180 | private Ethereum PoA, chain ID 18000 |
| faucet (10.180.0.90) | AS180 | lab ETH dispenser |
| utility server (10.180.0.95:8080) | AS180 | deploys `RansomExchange` at boot; serves address + attacker account |

Role split: the **victim** is played only through host_0's participant menu;
the **attacker** is played only through host_1's shell. The SEED map gives one
shell per container — that is why the roles live on separate hosts.

## Phase A — build and boot (docker host terminal)

```bash
cd /home/seed/research/seed-emulator/examples/yesterday_once_more/Y04_wannacry/v2
PYTHONPATH=/home/seed/research/chain-seed:/home/seed/research/seed-emulator \
  ~/.local/bin/python3.10 emulator.py --override
cd output && docker compose build && docker compose up -d
```

Compile needs Python <3.11 (python3.10 with the PYTHONPATH above); plain
python3.14 will not work. Wait ~90 seconds, then verify:

```bash
docker compose ps --format '{{.Name}}'
```

Expected: `host_0`, `host_1`, `rnode_180_router0`, three `chain` nodes,
`faucet`, `utility`, plus the internet map.

## Phase B — contract and attacker account (utility shell, via the map)

```text
cat /utility_server/deployed_contracts/contract_address.txt
cat /utility_server/account.json
```

Expected: `{"RansomExchange": "0x..."}` and an account JSON
(`address` + `private_key`). **This account is the attacker's on-chain
identity** — keep it; phase C copies it to host_1.

## Phase C — arm the attacker (host_1 shell)

```bash
cd /opt/wannacry-v2
python3 check_state.py
python3 lab_keylogic.py init-attacker
echo '{"address": "0x...", "private_key": "0x..."}' > attacker_chain_key.json
```

(paste the real account.json contents into the echo)

Expected:
1. `check_state` → contract `code on-chain: 3282 bytes (ALIVE)`; `door: not
   running` is correct on host_1 (the door lives on host_0).
2. `init-attacker` → keypair created; the printed `attacker_pub` PEM needs
   no copying — the delivery step handles it.
3. The echo is silent.

Two identities now exist on host_1: `attacker_keys.json` (crypto identity,
private key never leaves this host) and `attacker_chain_key.json` (payment
identity on-chain). **Re-copy the chain key after every utility-server
rebuild** — a stale one makes `watch` refuse with an `attacker()` mismatch
instead of burning gas on a reverted reply.

## Phase D — deliver the payload (host_1 shell)

```bash
python3 lab_keylogic.py deliver --victim-url http://10.180.0.71:4450
```

Expected:

```json
{
  "status": "infected",
  "participant_id": "as180-host_0",
  "files_encrypted": 5,
  "note": "payload executed on the victim host; ransom note is in place"
}
```

What just happened: the attacker public key traveled over the network to the
victim's delivery inbox (`wormdoor.py`), which dropped it and detonated the
payload in-process. The victim's five documents are now `<name>.WNCRY`
envelopes and the plaintext originals are gone. This is the worm's delivery
played by hand — the courier, not the exploit; real propagation replaces it.

## Phase E — the victim reacts (host_0 shell)

```bash
python3 /opt/wannacry-v2/participant.py
```

1. **[2] Inspect documents** — every file shows
   `ENCRYPTED (.WNCRY) — ransomware envelope present`.
2. **[6] My wallet → c** — create a wallet, pick a password, note the address.
3. **[3] SEED Exchange** — buy lab ETH (presets 1/2/3/5 or a custom amount
   1–5). Expect `Order filled: +N lab ETH` and a balance of `N lab ETH`.
4. **[5] Document recovery** — enter the wallet password. Expected:
   `registered on-chain: request id 0` + `payment transaction: 0x...`, then
   the menu enters its waiting state. **Leave it waiting** and switch to the
   attacker within the 10-minute polling window.

## Phase F — answer the victim (host_1 shell)

```bash
python3 lab_keylogic.py watch --chain-key attacker_chain_key.json \
  --rpc-url http://10.180.0.83:8545 --utility-url http://10.180.0.95:8080
```

Expected:

```json
[
  {
    "id": 0,
    "transaction_hash": "0x..."
  }
]
```

The victim's waiting menu wakes up on its own and prints
`as180-host_0: 5 documents recovered and verified` — decryption succeeded and
every file matched its pre-attack SHA-256 baseline. Original filenames are
restored and the `.WNCRY` envelopes are removed.

## Phase G — collect the ransom (host_1 shell, optional)

```bash
python3 lab_keylogic.py withdraw --chain-key attacker_chain_key.json \
  --rpc-url http://10.180.0.83:8545 --utility-url http://10.180.0.95:8080
python3 -c "import lab_wallet, json; c=lab_wallet.connect(); a=json.load(open('attacker_chain_key.json'))['address']; print(a, lab_wallet.format_ether(lab_wallet.balance_wei(c, a)), 'lab ETH')"
```

Expected: `ransoms swept: 0x...`, then the attacker address at roughly
`10.99 lab ETH` (10 funded − reply gas + 1 ransom).

## Troubleshooting

| Symptom | Meaning | Fix |
|---|---|---|
| `Action unavailable: MAC mismatch` | wrong wallet password, rejected **before** signing | press Enter, choose 5 again with the correct password; no payment was made |
| `no reply posted on-chain in time` | the victim's 10-minute polling window expired | choose 5 again — wait-only mode, **no second payment** (the double-pay guard) |
| `door: not running` in check_state | the delivery inbox service is down | check `cat /opt/wannacry-v2/wormdoor.log` on host_0 |
| watch: `... is not the contract's attacker` | stale `attacker_chain_key.json` from a previous utility rebuild | re-copy the current `account.json` (phase C) |
| contract `code on-chain: 0 bytes (DEAD)` | deployment failed | do not pay into that address; rebuild from source (the deploy-gas fix is baked into `lab_chain.py`) |
| `already_infected` from deliver | this victim was already hit | rebuild (phase A) for a fresh incident |
| host state looks half-wrong | — | run `check_state.py` first, it is read-only |

## Reset rules

- Recreating a host container wipes its writable layer: wallets, keys, keylog,
  documents. Re-run phases C–F after any rebuild (the utility account and
  contract address change on a fresh chain too).
- Full reset: `docker compose down` → phase A again. A plain `up -d` restart
  regenerates documents but keeps the wallet and chain databases.

## What is intentionally not here yet

Real exploit/propagation (replaces the `wormdoor` courier), multiple victims
across networks at scale (the contract and `watch` already support N
requests), and per-request payment gating in the contract.
