# WannaCry payload lab: participant interaction

This independent example is being rebuilt incrementally. The current milestone
creates a router, a participant host, three Ethereum nodes, and a faucet in AS180
on `10.180.0.0/24`. The participant host generates
five dummy documents and a participant record whenever it starts. The container
provides a participant menu for inspecting and recovering those exact samples. Propagation
and blockchain settlement are not implemented yet. Wallet creation, balance queries,
and private-chain faucet funding are available. The layered key logic and its
manual exchange protocol are new; the UI drives them through the recovery menu. Each increment focuses on the
incident scenario; supporting explanations are kept in the personal learning guide.

```text
AS180 / net0 (10.180.0.0/24)
    router0 ----- host_0 ----- chain0, chain1, chain2, faucet
                  /opt/wannacry-v2/file_generator.py
                  /opt/wannacry-v2/prepare_participant.py
                  /opt/wannacry-v2/lab_keylogic.py
                  /opt/wannacry-v2/participant.py
                  /opt/wannacry-v2/lab_wallet.py
                  /opt/wannacry-v2/chain.json
                  /opt/wannacry-v2/PARTICIPANT_README.txt
                  /opt/wannacry-v2/participant.json
                  /home/seed/import_folder/ (five documents and READ_ME.txt)
```

`file_generator.py` prepares the documents. `prepare_participant.py` records
the participant ID, the state `PREPARED`, and a SHA-256 hash for each document.
`lab_keylogic.py` implements the layered ransomware key logic and the exchange.
`participant.py` supplies document inspection and launches `terminal_ui.py`.
The terminal screens provide the learner interface and call local recovery when selected.
`lab_wallet.py` manages an encrypted teaching keystore and communicates with the
RPC node and faucet. `lab_chain.py` defines the example's private chain at compile time.
`emulator.py` defines the network, includes the scripts and instructions in the host image, and
configures startup to generate the documents before recording their hashes.
The router provides the host's local gateway; there is no external network or
inter-AS routing in this milestone.

## Participant record

The record lives at `/opt/wannacry-v2/participant.json`, outside the document
directory. The host's assigned ID is `as180-host_0`; this is a lab label, not
proof of identity. Hashes record the actual files' contents for later recovery
comparison; they do not store copies of those contents.

Only the five filenames defined in `file_generator.py` are read. A missing file
causes preparation to fail before the record is written. Extra files are ignored.
Preparation does not modify the documents. Re-running it replaces the record
with a new `PREPARED` baseline, so it belongs to initial setup, not monitoring.

A future monitor can read these records every few seconds. It is not implemented
yet. The local states are `PREPARED`, `PROCESSING`, `ENCRYPTED`, `RECOVERING`, and
`RECOVERED`. The record is local JSON,
not an authenticated audit log or an on-chain registration.

To try preparation locally, choose a disposable directory and run:

```bash
python file_generator.py --target /tmp/wannacry-participant/corpus
python prepare_participant.py --target /tmp/wannacry-participant/corpus \
  --participant-id as180-host_0 --state-file /tmp/wannacry-participant/participant.json
cat /tmp/wannacry-participant/participant.json
```

Generation and preparation use only Python's standard library. Processing uses
`cryptography`; the emulator installs Ubuntu's `python3-cryptography` package in
the host image. The participant image also installs `eth-account==0.13.7` for
wallet creation. These image dependencies are separate from the host-side
ChainSeed compiler environment. Local menu use needs those packages separately.

## Compile

Use a Python environment with SeedEmu and the sibling ChainSeed package installed
(see [ChainSeed installation](../../../../../chain-seed/README.md)). From this
directory:

```bash
python emulator.py --platform amd
```

Use `--platform arm` on ARM64. The default output directory is `output/` beside
the script, regardless of your working directory. Use `--output PATH` to choose
another location, or `--override` to replace existing generated output.

Compilation writes Docker build contexts and `docker-compose.yml`; it does not
build images or start containers. Source changes require recompilation and an
image rebuild before new containers use them.

## Build, start, and inspect

From this example's directory, enter the generated output folder:

```bash
cd output
docker compose build
docker compose up -d
docker compose logs hnode_180_host_0
docker compose exec hnode_180_host_0 \
  ls -l /home/seed/import_folder
docker compose exec hnode_180_host_0 \
  cat /home/seed/import_folder/notes.txt
docker compose exec hnode_180_host_0 \
  cat /opt/wannacry-v2/participant.json
```

The five filenames are `budget.csv`, `contacts.csv`, `minutes.txt`, `notes.txt`,
and `report.md`. Only the host receives the lab scripts. The router does not.

AS180 avoids the AS150-series networks used by the earlier ChainSeed example.
Other running labs must also avoid overlapping subnets and container names;
a different Compose project name alone does not fix such conflicts.

These commands use Compose's default project naming (normally `output` for this
folder). Run one such lab at a time when other examples also use that default.

## Learner walkthrough: inspect an affected host

After changing the source, update the host image from this example's directory:

```bash
python emulator.py --override
cd output
docker compose build
docker compose up -d
```

Recreating the host resets its documents and participant state. For this first
payload-only milestone, use the development trigger below to model the arrival
of the incident. Propagation is not implemented:

```bash
docker compose exec hnode_180_host_0 \
  python3 /opt/wannacry-v2/lab_keylogic.py payload \
    --target /home/seed/import_folder
```

Then enter the affected host and follow its instructions:

```bash
docker compose exec hnode_180_host_0 bash
ls -l /home/seed/import_folder
cat /home/seed/import_folder/READ_ME.txt
python3 /opt/wannacry-v2/participant.py
```

The home screen offers instructions (1), document inspection (2), the
exchange-driven recovery (5), and the wallet (6). Each screen has explicit
navigation. `b` returns from the wallet, and `0` exits from home. Use `exit`
afterward to leave the container shell. Payment contracts remain unimplemented;
wallet funding does not unlock or gate recovery. Option 5 drives the layered
key-logic exchange: it prints the on-chain request payload, waits for the
attacker-side reply to be copied to `/opt/wannacry-v2/exchange_reply.json`,
then accepts the reply and decrypts the documents.

## Wallet and faucet exercise

The example now has its own private PoA chain, ID `18000`. It is independent of
the standalone learning chain, ID `19000`: balances and deployed contracts are
not transferred between them.

## RansomExchange contract

`contracts/RansomExchange.sol` replaces the original incident's BTC + TOR
manual operations with an enforced on-chain exchange. Compile it offline first
(`python3 contracts/compile_contract.py`, needs py-solc-x); `lab_chain.py`
embeds the resulting ABI and bytecode so a utility node (`10.180.0.95:8080`)
deploys the contract in a real transaction at every `up -d` and serves its
address at `/contracts_info?name=RansomExchange`.

The contract transports only opaque sealed bytes; all key material stays
off-chain. Enforcement happens in the EVM: `registerVictim` is payable and
requires exactly 1 lab ETH (`ransomWei`), so an unpaid request reverts, and
`submitReply` is restricted to the deployer-designated attacker account. The
victim flow is one signed transaction carrying the ephemeral X25519 public key
and the sealed `victim_priv` blob; the attacker watches `VictimRegistered`
events, decrypts offline, and posts the ECDH-sealed reply on-chain.

## On-chain exchange commands

The participant UI (option 5) performs the full victim flow when a wallet
exists: one paid `registerVictim` transaction signed with the wallet key, then
on-chain polling for the reply, then automatic recovery. The manual file-copy
path remains the fallback when no wallet or chain is reachable.

The attacker runs the loop from outside the lab. The on-chain attacker
account is the utility server's deploy account, so first copy its key out:

```bash
docker compose exec hnode_180_utility cat /utility_server/account.json \
  > attacker_chain_key.json
```

Then watch for paid requests and answer them (RSA offline crypto plus one
`submitReply` transaction per request):

```bash
python3 lab_keylogic.py watch \
  --attacker-keys attacker_keys.json --keylog lab_keylogic.json \
  --chain-key attacker_chain_key.json \
  --rpc-url http://10.180.0.83:8545 \
  --utility-url http://10.180.0.95:8080
```

Sweep the collected ransoms:

```bash
python3 lab_keylogic.py withdraw \
  --chain-key attacker_chain_key.json \
  --rpc-url http://10.180.0.83:8545 \
  --utility-url http://10.180.0.95:8080
```

| Host | Address | Role |
|---|---|---|
| host_0 | 10.180.0.71 | Participant application; no Geth process |
| chain0 | 10.180.0.81 | Ethereum node, signer, discovery bootnode |
| chain1 | 10.180.0.82 | Ethereum node and signer |
| chain2 | 10.180.0.83 | Ethereum node exposing RPC on port 8545 |
| faucet | 10.180.0.90 | Funding service on HTTP port 80 |
| utility | 10.180.0.95 | Deploys `RansomExchange` at start; serves the deployed address on port 8080 |

Enter the participant host and open its menu:

```bash
docker compose exec -it hnode_180_host_0 /bin/bash
python3 /opt/wannacry-v2/participant.py
```

Choose **6** to open the wallet screen. Use **c** to create a wallet and enter a
password twice; an existing wallet is preserved. Use **r** to refresh its balance,
or **l** to look up a manually pasted address. The full wallet address is displayed
for copying through your terminal's normal selection/copy shortcut.

The purchase/exchange demo screens were removed in the key-logic cleanup.
The wallet screen keeps wallet creation, balance refresh, and address lookup.

The per-participant UI lock still prevents two copies of the menu from running.
## Inspecting document state

Recorded state and file observations are displayed separately. `ORIGINAL` means
the file matches both the known sample bytes and the recorded hash. `LAB ENVELOPE`
means its size and marker match the lab format; authentication is checked during
recovery. Missing, modified, or unreadable files are reported, not counted as
successful recovery. Merely opening the menu does not change the files.

The readable `READ_ME.txt` is installed with the image and exists even before the
incident. It is not one of the five samples and is never processed. After recovery,
the five samples should show `ORIGINAL` and the recorded state `RECOVERED`.

## Development commands: process and recover the samples

From `output/`, after rebuilding the host image and starting the updated host:

```bash
docker compose exec hnode_180_host_0 \
  python3 /opt/wannacry-v2/lab_keylogic.py payload \
    --target /home/seed/import_folder
docker compose exec hnode_180_host_0 \
  cat /opt/wannacry-v2/participant.json
docker compose exec hnode_180_host_0 \
  od -An -tx1 -N48 /home/seed/import_folder/notes.txt
```

The filenames stay the same, but their contents become lab-format ciphertext.
No original-document copies are retained. The script accepts only the exact
five generated documents and a matching baseline; it refuses arbitrary changed
content, missing files, and symbolic-link samples. Extra filenames are untouched.
This is a fixed-fixture demonstration, not a general file encryptor.

Recover them with:

```bash
docker compose exec hnode_180_host_0 \
  python3 /opt/wannacry-v2/lab_keylogic.py request \
    --keylog /opt/wannacry-v2/lab_keylogic.json
# then, on the attacker machine:
python3 lab_keylogic.py reply --attacker-keys attacker_keys.json \
  --in request.json > reply.json
# copy reply.json back to /opt/wannacry-v2/exchange_reply.json, then:
docker compose exec hnode_180_host_0 \
  python3 lab_keylogic.py accept --keylog /opt/wannacry-v2/lab_keylogic.json \
    --in /opt/wannacry-v2/exchange_reply.json --out /opt/wannacry-v2/accepted.json
docker compose exec hnode_180_host_0 \
  python3 /opt/wannacry-v2/lab_keylogic.py recover \
    --in /opt/wannacry-v2/accepted.json --target /home/seed/import_folder
docker compose exec hnode_180_host_0 \
  cat /home/seed/import_folder/notes.txt
docker compose exec hnode_180_host_0 \
  cat /opt/wannacry-v2/participant.json
```

Expected state progression:

```text
PREPARED -> PROCESSING -> ENCRYPTED -> RECOVERING -> RECOVERED
```

Recovery verifies the original hashes before writing, then reads back the
written files before recording `RECOVERED`. Processing can be repeated from
`RECOVERED`. Run one action at a time for each participant.

### Keys, format, and scope

Each sample uses an independent AES-256-GCM key. Its stored bytes are:

```text
Y04LAB1\n (8 bytes) | nonce (12 bytes) | ciphertext | tag (16 bytes)
```

The participant ID and filename are authenticated as associated data. The format
is specific to this lab, not compatible with historical `.WNCRY` files. Historical
WannaCry used AES-128-CBC and RSA key protection; neither the historical RSA
hierarchy nor payment-dependent delivery is implemented here.

`/opt/wannacry-v2/lab_keylogic.json` holds the layered key material locally,
with owner-only file permissions: the sealed `victim_priv`, the sealed file key,
and per-file ciphertext/nonce records. No plaintext private key material is
written to disk. The generator's known sample text is also still available;
this lab demonstrates a reversible transition, not loss of every recovery route.

Each file is replaced atomically, and the payload writes the keylog before
touching any document. The five-file operation is not one atomic transaction.
An interruption can leave an intermediate state and a mix of plain and
encrypted samples; `payload` refuses to run twice on one keylog. If
authentication or baseline validation fails, recovery stops before writing any
sample. An I/O failure during writes can still leave a partial result. Inspect
the error and state rather than treating a running container as proof of
success.

The format and controls are intentionally limited to the generated fixture.
The path checks are not a general sandbox against concurrent filesystem changes.

## Internet Map

Open [the topology map](http://localhost:8080/) in a browser on the Docker
host. If Docker runs inside a VM or remote machine, use its reachable address or
forward port 8080 to your browser machine.

`Docker(..., internetMapEnabled=True)` includes the built-in
`seedemu_internet_map` service. It reads SEED's Docker metadata to discover the
host, router, and network. A mini Internet topology is not required.

The topology map is separate from the planned participant-state monitor: it does
not read `participant.json` or display our scenario's protocol states.

For troubleshooting, from `output/`:

```bash
docker compose ps
docker compose logs seedemu_internet_map
```

## Reset this milestone

From `output/`:

```bash
docker compose down
docker compose up -d
```

There are no persistent document/state mounts in this example. The map service
mounts the Docker socket to inspect and interact with the emulation. Recreating the lab containers
discards their writable files, and the host regenerates the documents at startup.
A simple restart also regenerates the documents and their `PREPARED` record,
but does not remove unrelated files from the existing container. This startup
behavior will need revisiting when the example supports resuming later states.
After processing, prefer `down` followed by `up -d` for a fresh exercise: a simple
restart regenerates the documents but retains the previous local recovery file.
Use `recover` before another `process`, or recreate the containers to reset both.
The wallet and chain databases also live in container writable layers. A full
`down`/`up -d` reset removes the wallet and returns the chain to genesis. A simple
restart retains the wallet and chain databases, while the participant startup
still regenerates its dummy files and baseline. Both signer nodes must be running
for this two-signer chain to keep producing blocks.

## Repository references

- [Contribution guidelines](../../../../CONTRIBUTING.md)
- [Node customization](../../../basic/A09_node_customization/README.md)
- [Simple autonomous systems](../../../basic/A00_simple_as/README.md)
- [Docker compiler](../../../../docs/user_manual/compiler.md)

The personal line-by-line learning guide is maintained separately in Downloads.

## UI checks and updating an existing container

Run the focused checkout tests from this example directory:

```bash
python -m unittest discover -s tests -v
```

Rebuilding an image does not update a running container. For this UI-only update,
copying the updated Python modules and instruction text into the existing host
preserves its wallet, chain state, documents, and account balances. Close and
reopen the participant program to load the new UI. Normal full builds install
these files through emulator.py. The initial update was applied this way rather
than recreating the existing wallet-bearing host.
