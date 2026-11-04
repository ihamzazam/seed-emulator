WannaCry Incident Lab — Participant Instructions

This host contains five generated sample documents in /home/seed/import_folder.
During the simulated incident they were encrypted: each document was replaced
by a ransomware envelope named <original-name>.WNCRY (for example notes.txt.WNCRY),
and the plaintext original is gone. This instruction file is available before
and after the incident; its presence alone does not mean the host has been
affected.

Open the participant menu inside this host:
    python3 /opt/wannacry-v2/participant.py

From the home screen:

  [2] Inspect documents shows the current state of every sample. ORIGINAL
      means the plaintext contents match the recorded baseline. ENCRYPTED
      (.WNCRY) means the ransomware envelope is present. Recovery is the only
      step that changes files.

  [6] My wallet creates and checks your lab wallet. c creates a
      password-protected wallet, r refreshes its balance, l looks up a pasted
      address, and b returns home.

  [3] SEED Exchange is where you buy lab ETH to pay the ransom. Choose a
      preset amount or a custom amount (1-5 lab ETH); the order is settled on
      private chain 18000. Command-line users can fund manually — see the lab
      runbook instead of this menu.

  [5] Document recovery runs the enforced exchange: it registers your request
      on-chain with the exact ransom payment (the RansomExchange contract
      rejects any other amount), waits for the attacker's reply, unseals your
      file key with your recovered private key, decrypts all documents, and
      removes the .WNCRY envelopes. After success every document shows
      ORIGINAL again and the recorded state becomes RECOVERED. Report any
      error rather than assuming success.

The encrypted envelope of your private key was sent to the attacker through
the blockchain. It is useless to anyone without the attacker's private key,
which never exists on this host. The attacker replies on-chain; only your
host can open that reply.

Use b to return from a screen and 0 at home to exit. Only one participant
menu can be active per host at a time. Reading instructions, inspecting
documents, and refreshing balances do not change the documents. Run one
action at a time on this participant.
