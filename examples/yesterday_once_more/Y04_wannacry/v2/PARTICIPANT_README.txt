WannaCry Incident Lab — Participant Instructions

This host contains five generated sample documents in /home/seed/import_folder.
During the simulated incident their contents change to encrypted lab data.
The files keep their names. This instruction file is available before and after
the incident; its presence alone does not mean the host has been affected.

Open the participant menu inside this host:
    python3 /opt/wannacry-v2/participant.py

Use the menu to inspect the documents and refresh their status. ORIGINAL means
the contents match the generated sample and its recorded baseline. LAB ENVELOPE
means the file has the expected encrypted format; it does not prove integrity.
Recovery authenticates the contents and checks their original hashes.

This milestone has a private chain for wallet exercises, but no propagation or
payment contract yet. The document recovery flow runs the layered key-logic
exchange over the chain transport that will replace the manual copy step.

From the home screen, choose 6 for your wallet. In the wallet screen, c creates
a password-protected wallet, r refreshes its balance, l looks up a pasted
address, and b returns home. Select the displayed full address to copy it with
your terminal's copy shortcut. The "last checked" label tells you when a balance
was read; there is no idle background polling.

Use b to return from a screen and 0 at home to exit. Only one participant menu
can be active per host at a time.

Option 5 drives the blockchain key exchange. Before any payload has run, it
explains how to execute the payload; run that command, then choose option 5
again. It then prints the on-chain exchange request payload and saves it as
/opt/wannacry-v2/exchange_request.json. That sealed blob is useless to anyone
without the attacker private key, which never exists on this host.

The reply step happens on the attacker machine, outside this host. Copy its
output to /opt/wannacry-v2/exchange_reply.json, choose option 5 again, and the
menu accepts the reply, unseals the file key with the recovered victim key,
and decrypts all five documents. After successful recovery, every document
should show ORIGINAL and the recorded state should be RECOVERED. Report any
error rather than assuming success.

Opening the menu, reading these instructions, and refreshing status do not change
the documents. Run one action at a time on this participant.
