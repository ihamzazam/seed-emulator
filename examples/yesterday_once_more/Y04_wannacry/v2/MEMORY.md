# MEMORY — WannaCry ChainSeed Lab (Y04_wannacry/v2)

Last updated: 2026-11-05. Any agent working with the user on this project:
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

Topology (v2.1, 2026-11-05): AS180 has TWO hosts on net0 — host_0 (victim
 workstation) and host_1 (attacker machine). The SEED map gives one shell per
 container, so two hosts = clean side-by-side terminals.
 ROLE CLEAN-SPLIT (user's design, v2.1): host_0 is ONLY the victim
 experience — inspect files, ransom note, participant menu (wallet, SEED
 Exchange funding, pay, recover). All attacker actions live on host_1:
 init-attacker, deliver, watch, withdraw. The payload CODE is baked into
 host_0 at boot; the attacker's `deliver` command sends the attacker PUBLIC
 key to host_0's delivery inbox (wormdoor.py, port 4450), which drops it and
 detonates the payload in-process. wormdoor is a COURIER stand-in, NOT the
 exploit — the user will design the real exploit/worm later (also planning
 one-attacker-to-many-victims across networks at scale; keep everything
 multi-victim-ready — the contract and watch already support N requests).
 Encrypted files are named <original>.WNCRY (plaintext removed); recovery
 restores originals and deletes the envelopes. Funding is themed as the
 "SEED Crypto Exchange" inside the participant menu (presets 1/2/3/5 or
 custom 1-5, fake ticker, short order/settlement animation, faucet
 underneath); manual faucet one-liners remain in MANUAL_RUNBOOK.txt.

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

Compile time (user's machine): `emulator.py` (blueprint: AS180 router0 +
host_0 victim + host_1 attacker; VICTIM_FILES/ATTACKER_FILES lists + two
stage helpers),
`lab_chain.py` (blockchain layer: 3 Geth nodes, faucet, utility server, contract
deployment), `contracts/RansomExchange.sol` + `contracts/compile_contract.py`
(offline solc 0.8.20, evm_version=LONDON, writes .abi/.bin).

Runtime (inside host_0, `/opt/wannacry-v2/`): `file_generator.py` (5 dummies,
runs at boot), `prepare_participant.py` (SHA-256 baseline + PREPARED state →
`participant.json`; used to VERIFY recovery — lab instrument, not attack
infrastructure), `lab_keylogic.py` (THE payload brain: key hierarchy, sealing,
exchange protocol, CLI: init-attacker/deliver/payload/request/reply/accept/
recover/watch/withdraw), `lab_ransom_chain.py` (on-chain transport: calldata via
eth_abi + hand-computed selectors, signing via eth-account, JSON-RPC via
urllib — NO web3 dependency on host), `participant.py`+`terminal_ui.py`
(participant UI: inspect [2], SEED Exchange funding [3], wallet [6],
recovery/exchange [5]), `lab_wallet.py` (keystore, balance, faucet funding),
`wormdoor.py` (victim delivery inbox on :4450 — drops attacker_pub.pem and
detonates the payload in-process; one-shot; GET /status, POST /drop),
`check_state.py` (one-shot read-only status incl. door state —
USE THIS FIRST when debugging), `PARTICIPANT_README.txt` (the READ_ME.txt
ransom note), `MANUAL_RUNBOOK.txt` (repo-level manual-command runbook).

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
   `evm_version="london"` in compile_contract.py. The deploy gas pin was ALSO
   raised 2M→4.5M — but from OUR side: lab_chain.py overrides the
   `UtilityServerFileTemplates['deploy_contract']` template string at import
   time (design principle: the example defines what the chain gets; NO
   chain-seed patch needed, its repo stays clean, no fork required)
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
11. Two-host split (2026-11-05): attacker_watch read the victim's keylog
    from local disk — impossible on host_1 (and would defeat the split).
    Fixed by a PROTOCOL CHANGE, not a file copy: the attacker reply now
    carries ONLY victim_priv (attacker_build_reply lost its file_key arg);
    the victim derives the file key locally via victim_open_file_key
    (victim_accept_reply takes an optional keylog arg and still accepts
    legacy file-key-embedded replies). attacker_watch builds a keylog VIEW
    from attacker_pub + the on-chain sealed blob; the old local keylog
    comparison is replaced by attacker_open_victim_priv's own key check.
    Reply payload shrinks (~2.5KB → ~1.75KB); GAS_REPLY left at 4M. Watch
    CLI no longer requires --keylog.
META-LESSON: all 11 bugs live in the SEAMS with ChainSeed plumbing or in
role-separation seams (gas pins, caps, file lists, RPC response shapes,
which host holds which file), none in the crypto. Verify seams against a
live chain before letting the user run anything. A full autonomous
rehearsal was completed 2026-11-04 (single host); a two-host rehearsal ran
2026-11-05 (see state below).
HOT-PATCH CAVEAT: docker compose cp does NOT affect running Python
processes — after hot-patching, restart participant.py (or the CLI) so the
new module code loads. Symptom seen: victim menu hit `Action unavailable:
'file_key'` until restarted.

## Operational runbook (v2.1 demo path — v2.0 flow proven 2026-11-04/05;
## v2.1 flow built + unit-tested, live rehearsal pending)

Phase A (docker host): `python emulator.py --override` (with the PYTHONPATH
env above) → `cd output && docker compose build && docker compose up -d` →
wait 90s. Phase B (map→utility shell): `cat /utility_server/deployed_contracts/
contract_address.txt` (expect {"RansomExchange": "0x..."}) and `cat
/utility_server/account.json` (this IS the on-chain attacker). Phase C
(host_1 = attacker machine): `cd /opt/wannacry-v2 && python3 check_state.py`
(expect contract ALIVE + door: clean) → `python3 lab_keylogic.py
init-attacker` → save account.json as `attacker_chain_key.json` on host_1
(echo one-liner; MUST be re-copied after every utility rebuild). Phase D
(still host_1): get host_0's IP from the map node, then
`python3 lab_keylogic.py deliver --victim-url http://<host0-ip>:4450` →
expect {"status": "infected", "files_encrypted": 5} — the victim's files are
now <name>.WNCRY envelopes and the ransom note is in place. Phase E (host_0,
participant menu only): `python3 participant.py` → 6 (create wallet) →
3 (SEED Exchange: buy lab ETH — presets or custom) → 5 (pay ransom +
recover; password when prompted) → LEAVE IT WAITING. Phase F (host_1):
`python3 lab_keylogic.py watch --chain-key attacker_chain_key.json --rpc-url
http://10.180.0.83:8545 --utility-url http://10.180.0.95:8080` →
`[{"id": 0, ...}]`; the victim's waiting menu then prints "5 documents
recovered and verified" (original names restored, .WNCRY gone). Phase G
(optional, host_1): `withdraw` → "ransoms swept". Debug anything with
`check_state.py` (runs on either host, read-only; shows door status).

Wallet password: the user chose it; wallets live in the container writable
layer (wiped on container recreate). Note: recreate of host_0 wipes
wallet/keys/keylog — rerun phases C–F after any rebuild.

## State at last update (2026-11-05, v2.1)

- FIRST-DRAFT DEMO DECLARED GOOD by the user after the live v2.1 cycle.
- DOCUMENTATION PASS (same day): architecture.puml (component/flow diagram,
  render on any PlantUML server), RUNBOOK.md (MASTER operator runbook —
  phases A–G with commands, expected outputs, troubleshooting table; the
  primary demo path), README.md rewritten lean for v2.1 (old version
  described the pre-contract milestone). MANUAL_RUNBOOK.txt = no-menu path.
- CLEANUP: removed the superseded v1 prototype in Y04_wannacry/ root
  (8 scripts + old README replaced by a pointer to v2/; files recoverable
  from git history). __pycache__ dirs deleted. RansomExchange.bin stays on
  disk (untracked, consumed at compile time by lab_chain.py, regenerable
  via contracts/compile_contract.py). Uncommitted changes exist across the
  v2 example — user should commit to their fork (wannacry-payload branch).

- V2.1 ROLE-RESHAPE IMPLEMENTED AND LIVE-PROVEN (2026-11-05; 15 tests pass
  AND a clean build → full live cycle with zero hot-patches, every seam
  first-try: contract 0x6B3fc91dc1AF444EE71D519589b9F49995ce2CfD, host_0
  10.180.0.71 / host_1 10.180.0.72, delivery from host_1 infected in one
  command, .WNCRY inspector + auto-recovery restored original names within
  the polling window, withdraw 0x7ece1ba7..., attacker final balance
  10.99683934461400681 lab ETH). Validated behaviors worth knowing:
  wrong wallet password → clean "MAC mismatch" error BEFORE signing (no
  payment, request file reusable — retry option 5 with correct password);
  the deliver step needs host_0's IP, read it off the map node.
  a) .WNCRY: payload writes <name>.WNCRY envelopes + deletes plaintext;
     recovery restores names and deletes envelopes; inspector and
     check_state understand both states.
  b) wormdoor.py delivery inbox on host_0 (:4450, boot-started via emulator);
     lab_keylogic `deliver` runs on host_1 and sends the attacker pub key;
     one-shot (already_infected refused). Explicitly a courier stand-in —
     NOT the exploit; the user will design the real exploit later.
  c) SEED Crypto Exchange screen in terminal_ui (menu option 3): fake
     ticker, presets 1/2/3/5 or custom 1-5, busy() animation for
     order+settlement, lab_wallet.request_funds underneath.
  d) Ransom note (PARTICIPANT_README.txt) rewritten for v2.1 reality;
     MANUAL_RUNBOOK.txt added for command-line purists.
  e) Watch CLI no longer needs --keylog (bug #11 protocol stands).

- TWO-HOST SPLIT APPLIED AND LIVE-TESTED (2026-11-05): emulator.py builds
  host_1 (attacker machine) alongside host_0; lab_keylogic.py `payload` takes
  `--attacker-pub attacker_pub.pem` (worm-drop stand-in) with the old
  attacker_keys.json path kept as fallback. All 13 unit tests pass.
- TWO-HOST FULL CYCLE COMPLETED on a fresh build (build → up → new chain,
  contract 0x1628f3927B73134b5cdCd9754a2EA2ac4DBB201e): payload via dropped
  attacker_pub → paid registration (tx 0x045dcba...) → attacker reply with
  the NEW victim_priv-only protocol (tx 0x97c512...) → victim recovered 5
  docs hash-verified → withdraw (tx 0x2e721a...). That run was hot-patched
  mid-way (bug #11 fix + participant.py restart), so it proved the logic but
  not the source tree.
- CLEAN-SLATE DRESS REHEARSAL COMPLETED 2026-11-05, straight from source,
  ZERO hot-patches, every seam first-try (contract
  0xBeCfd798194206866Aafa9eB0A47Df9f85Ce01f1): check_state ALIVE from host_1
  → init-attacker on host_1 → worm drop (attacker_pub.pem echo) → payload
  --attacker-pub on host_0 → wallet + faucet 5 ETH → option 5 registered
  request id 0 (tx 0xba681ea...) → watch on host_1 replied immediately with
  the keylog-free protocol (tx 0x81fbe4d...) → victim menu recovered all 5
  docs hash-verified WITHIN the 600s polling window → withdraw (tx
  0x0d560891...), attacker final balance 10.996838856123442537 lab ETH.
  THE DEMO PATH IS DEMO-READY. Victim-side note kept: if the 600s
  wait_reply window ever expires, choosing 5 again recovers without a
  second payment — the double-pay guard works exactly as designed.


- Pushed to the user's FORK: `github.com/ihamzazam/seed-emulator`, branch
  `wannacry-payload`, commit 270653e0 (entire v2 example incl. this memory
  duplicated at examples/yesterday_once_more/Y04_wannacry/v2/MEMORY.md).
  upstream (seed-labs) push is disabled — keep it that way.
- IMPORTANT: NO chain-seed patches remain — the deploy-gas override lives in
  lab_chain.py (template replacement at import), evm_version=london lives in
  compile_contract.py, and the faucet cap is our own lab_chain.py knob.
  The local chain-seed repo is clean; nothing to re-apply on fresh machines
  beyond cloning the fork and installing (see bug #3 for rationale).

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

- SCOPE BOUNDARY (violated once, 2026-11-05 — do not repeat): work ONLY
  inside the v2/ directory until the user declares the final version done.
  Do NOT touch, clean up, or reorganize anything outside v2/ — that includes
  the v1 prototype files in Y04_wannacry/ root and other Y* examples — even
  when a request sounds repo-wide ("clean up the repo", "unused files").
  When in doubt, propose the change and wait for explicit confirmation
  before acting outside v2/.

- They run everything through the SEED internet map (localhost:8080) by
  opening shells into containers — do NOT give docker compose exec commands
  unless clearly labeled "docker host terminal".
- They want REAL mechanisms, explicitly no fake crypto; dummy files are fine.
- They are building understanding step by step and ask for a dissection
  session of each component AFTER the demo. Demo deadline was ~2026-11-05.
- They get overwhelmed by long instruction dumps: give ONE step + expected
  output, then wait for their paste.
- They often CANNOT copy/paste from the SEED map terminal: for anything that
  must be copied (long commands, PEM blocks), write a notefile into
  /home/seed/Downloads/ (e.g. wannacry-final-commands.txt) and point them at
  it — they copy from there into the map terminal. Have them report results
  in their own words when copying output out is hard.
- They value honesty about mistakes; keep a running tally rather than hiding
  them (see ledger above).
