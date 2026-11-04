# MEMORY — WannaCry ChainSeed Lab (Y04_wannacry/v2)

Last updated: 2026-11-04. Any agent working with the user on this project:
read this first, and **update this file after any significant change**.

## Project location

- Example: `/home/seed/research/seed-emulator/examples/yesterday_once_more/Y04_wannacry/v2/`
- ChainSeed package: `/home/seed/research/chain-seed/` (also installed in uv cache — patched copies exist in BOTH, see bug #2/#3 below)
- SEED emulator: `/home/seed/research/seed-emulator/`
- Compile env: `~/.local/bin/python3.10` with
  `PYTHONPATH=/home/seed/research/chain-seed:/home/seed/research/seed-emulator`
  (default python3.14 does NOT work — chainseed needs <3.11)

## What this lab is

A WannaCry-style ransomware scenario on SEED Emulator where every mechanism is
REAL: real RSA-2048 + AES-256-GCM file encryption, real Ethereum PoA private
chain (Geth, chain ID 18000), a real deployed smart contract, real signed
transactions. The original incident's BTC+TOR manual operations are replaced by
an enforced smart contract. Humans play attacker/victim manually. Dummy files
are the 5 generated fixtures (`file_generator.py`); they may be garbage files,
but the crypto must never be fake.

## Key hierarchy (the core design — never change without the user)

```
attacker_priv/attacker_pub  — created on "attacker machine" (in practice:
                              init-attacker on host_0, file copied "out")
  worm carries attacker_pub to victims
victim_priv/victim_pub     — generated per victim at payload execution
  victim_priv SEALED under attacker_pub (hybrid AES-GCM + RSA-OAEP)
file key (one AES-256-GCM key) — encrypts all 5 files, sealed under victim_pub
Recovery chain: attacker_priv -> victim_priv -> file key -> files
Reply channel: per-request EPHEMERAL X25519 keypair (session key, not a
  third persistent key). Request needs no transfer key (the sealed blob is
  already self-protecting). Wallet (Ethereum) key is for SIGNING only —
  never reuse it for content crypto (user explicitly rejected that).
```

Encrypted file format: `Y04LAB1\n | nonce(12) | ciphertext | tag(16)`,
participant id + filename authenticated as AES-GCM associated data.

## File map (lean set — sample_processing.py and lab_exchange.py were DELETED)

Compile time (user's machine): `emulator.py` (blueprint: AS180 router0+host_0),
`lab_chain.py` (blockchain layer: 3 Geth nodes, faucet, utility server, contract
deployment), `contracts/RansomExchange.sol` + `contracts/compile_contract.py`
(offline solc 0.8.20, evm_version=LONDON, writes .abi/.bin).

Runtime (inside host_0, `/opt/wannacry-v2/`): `file_generator.py` (5 dummies,
runs at boot), `prepare_participant.py` (SHA-256 baseline + PREPARED state →
`participant.json`; used to VERIFY recovery — lab instrument, not attack
infrastructure), `lab_keylogic.py` (THE payload brain: key hierarchy, sealing,
exchange protocol, CLI: init-attacker/payload/request/reply/accept/recover/
watch/withdraw), `lab_ransom_chain.py` (on-chain transport: calldata via
eth_abi + hand-computed selectors, signing via eth-account, JSON-RPC via
urllib — NO web3 dependency on host), `participant.py`+`terminal_ui.py`
(ransom-note UI; option 5 = the exchange flow), `lab_wallet.py` (keystore,
balance, faucet funding), `check_state.py` (one-shot read-only status —
USE THIS FIRST when debugging), `PARTICIPANT_README.txt` (the READ_ME.txt
ransom note).

## The contract (RansomExchange)

- `registerVictim(bytes ephemeralPub, bytes sealedBlob)` payable, ENFORCED:
  reverts unless msg.value == RANSOM_WEI (1 ether constant — constructor has
  NO arguments because ChainSeed's deploy script can't pass any)
- `submitReply(uint256 id, bytes sealedReply)` — only the contract `attacker`
  (set at deploy = msg.sender = the utility server's deploy account)
- `getReply(id)` view — reverts NoReplyYet() (selector 0x70fe9626) until
  answered; the client must TOLERATE this revert while polling
- `withdraw()` — attacker sweeps contract balance
- Contract transports only OPAQUE sealed bytes; all crypto stays off-chain
- Deployed automatically at `up -d` by ChainSeed's utility server
  (10.180.0.95:8080, address served at `/contracts_info?name=RansomExchange`
  — NOTE: returns the address as a plain JSON STRING, not a dict)

## KNOWN-HARD BUG LEDGER (all fixed; do not re-introduce)

1. Contract constructor arg → deploy script crashed; fixed by making
   RANSOM_WEI a contract constant
2. Faucet `max_fund_amount=5` vs deploy script requesting 10 ETH → infinite
   retry recursion; fixed: cap raised to 10 in lab_chain.py
3. solc default EVM version (Shanghai) emits PUSH0 → older SEED Geth doesn't
   support it → deploy burns ALL gas and "succeeds" with a DEAD address
   (ChainSeed's deploy script never checks receipt status!). Fix:
   `evm_version="london"` in compile_contract.py + gas raised 2M→4.5M in
   ChainSeed's deploy template (patched in repo AND uv-cache copies)
4. `lab_ransom_chain.py` / `check_state.py` missing from emulator.py file
   list → ModuleNotFoundError in container; fixed, now in image
5. `discover_contract()` called .get() on the plain-string response
6. GAS_REGISTER 600k → too low (~1.4KB blob storage ≈ 1M gas SSTORE);
   now 3,000,000
7. GAS_REPLY 1.5M → too low (reply ≈ 2.5KB ≈ 1.8M); now 4,000,000
   (block gas limit is 5,278,701 — keep caps below it)
8. `NoReplyYet` revert crashed the poll instead of meaning "keep waiting"
9. Option 5 could double-pay if request already registered; fixed: request
   file stores request_id → wait-only path, and UI skips password prompt
10. Stale attacker_chain_key.json (from a previous utility rebuild) →
    submitReply reverts OnlyAttacker; fixed: attacker_watch now verifies
    contract `attacker()` locally BEFORE sending
META-LESSON: all 10 bugs live in the SEAMS with ChainSeed plumbing (gas pins,
caps, file lists, RPC response shapes), none in the crypto. Verify seams
against a live chain before letting the user run anything. A full autonomous
rehearsal was completed 2026-11-04 (see state below).

## Operational runbook (the demo path — PROVEN 2026-11-04)

Phase A (docker host): `python emulator.py --override` (with the PYTHONPATH
env above) → `cd output && docker compose build && docker compose up -d` →
wait 90s. Phase B (map→utility shell): `cat /utility_server/deployed_contracts/
contract_address.txt` (expect {"RansomExchange": "0x..."}) and `cat
/utility_server/account.json` (this IS the on-chain attacker; copy it). On
host_0 run `check_state.py` — expect "code on-chain: 3200+ bytes (ALIVE)".
Phase C (host_0): `cd /opt/wannacry-v2 && python3 lab_keylogic.py init-attacker`
then save account.json as `attacker_chain_key.json` (echo one-liner; MUST be
re-copied after every utility rebuild). Phase D: `python3 lab_keylogic.py
payload` → files become Y04LAB1 ciphertext. Phase E: `participant.py` → 6 → c
(create wallet, note address) → 0; fund via faucet one-liner
(`lab_wallet.request_funds(lab_wallet.connect(), '0xADDR', 5)`); expect
"balance: 5 lab ETH". Phase F: `participant.py` → 5 → wallet password →
"registered on-chain: request id 0" → LEAVE IT WAITING. Phase G (second
host_0 shell): `python3 lab_keylogic.py watch --chain-key
attacker_chain_key.json --rpc-url http://10.180.0.83:8545 --utility-url
http://10.180.0.95:8080` → `[{"id": 0, ...}]`; the waiting menu then prints
"5 documents recovered and verified". Phase H (optional): `withdraw` →
"ransoms swept". Debug anything with `check_state.py` (read-only).

Wallet password: the user chose it; wallets live in the container writable
layer (wiped on container recreate). Note: recreate of host_0 wipes
wallet/keys/keylog — rerun phases C–F after any rebuild.

## State at last update (2026-11-04)

- FULL CYCLE COMPLETED AND VERIFIED: payload → paid registration (tx 0xb59b...)
  → attacker reply (0x4c84...) → victim recovered 5 docs (hash-verified) →
  withdraw (0x4244...). This was done as a live repair/rehearsal of the user's
  in-progress session; containers hot-patched via docker compose cp.
- Source tree on disk is now the truth and reproduces the success on a clean
  rebuild (all fixes baked in: london bytecode, gas 4.5M deploy template,
  faucet cap 10, complete file list).
- NOT yet done: a clean-slate full rehearsal (down → build → up → whole run)
  as final demo dress rehearsal; the `.WNCRY` file-extension fidelity change
  (user wants encrypted files named like `notes.txt.WNCRY` — deferred, must
  touch lab_keylogic payload/recover + participant inspector); payment
  contract could later gate release per-request (currently ransom is global
  msg.value, one payment per registration — that IS enforced).

## User context (how to work with them)

- They run everything through the SEED internet map (localhost:8080) by
  opening shells into containers — do NOT give docker compose exec commands
  unless clearly labeled "docker host terminal".
- They want REAL mechanisms, explicitly no fake crypto; dummy files are fine.
- They are building understanding step by step and ask for a dissection
  session of each component AFTER the demo. Demo deadline was ~2026-11-05.
- They get overwhelmed by long instruction dumps: give ONE step + expected
  output, then wait for their paste.
- They value honesty about mistakes; keep a running tally rather than hiding
  them (see ledger above).
