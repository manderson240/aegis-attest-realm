# Aegis Attest: DoraHacks BUIDL submission

**Hackathon**: Gnome Tavern Hackathon (#2470)
**Track**: Default Track
**Repository**: https://github.com/manderson240/aegis-attest-realm

This is the text I paste into the DoraHacks build form, kept in the repo so it stays in step with the code.

## Form fields

### Name
```text
Aegis Attest
```

### Brief description (106 characters)
```text
Gno realm where anyone pins an AI agent's evidence hash to a task, with a score and an author-only revoke.
```

### Tags
```text
Gno.land, Realm, AI Agents, Attestations, Reputation
```

### Team
```text
Mike Anderson
```

### Links
- GitHub: https://github.com/manderson240/aegis-attest-realm
- Live realm on onyx-1: https://onyx.testnets.gno.land/r/g185lernv9lg3c9akmyma2zusur5nrrmfqcfawql/aegis_attest
- Demo video: https://raw.githubusercontent.com/manderson240/aegis-attest-realm/main/docs/aegis_attest_demo.mp4 (120 s, 2560x1440)

### Contact
- Telegram: `manderson240`
- Discord: `miked238725`

## Description

### Why I built this

AI agents are starting to do real work, but once a task is done there is rarely a shared record of what the agent produced or how good it was. I wanted a small public ledger where that evidence can be pinned down and checked later by anyone, without trusting the agent or me.

### How it works

Aegis Attest is a realm on the Gno.land onyx-1 testnet at `gno.land/r/g185lernv9lg3c9akmyma2zusur5nrrmfqcfawql/aegis_attest`. An agent can register a handle and a short list of capabilities. After a task, anyone can submit an attestation with the agent address, a task ID, the SHA-256 hash of the evidence, a score from 0 to 10000 basis points, and a one line note.

The realm checks that the hash is 64 hex characters and refuses a second attestation for the same agent, task and hash. The first attestation sets an agent's score, and each later one moves it 30 percent of the way toward the new value. Only the author of an attestation can revoke it. Revoked entries stay on the page marked REVOKED.

Reading costs nothing. The gnoweb page shows totals, agents and recent attestations. `VerifyEvidenceHash` answers whether a hash was attested for an agent and task. The Python command `aegis-attest verify --file report.pdf --subject <g1 address> --task task-42` hashes the file, checks the input, and asks the live realm over plain RPC, with no key.

### Verification

- The deployed `aegis_attest.gno` and `realm/aegis_attest.gno` are identical. I fetched the deployed file with `vm/qfile` on 2026-11-26 and compared it with `cmp`. Both are 11639 bytes with SHA-256 `ef5e3393655f8dea349ef29f91abff0135d470d8a298b3751773ab1a62e2e520`.

  The check needs no key:

  ```bash
  P=gno.land/r/g185lernv9lg3c9akmyma2zusur5nrrmfqcfawql/aegis_attest/aegis_attest.gno
  curl -s "https://rpc.onyx.testnets.gno.land:443/abci_query?path=%22vm/qfile%22&data=0x$(printf %s "$P" | xxd -p | tr -d '\n')" \
    | python3 -c "import sys,json,base64;print(base64.b64decode(json.load(sys.stdin)['result']['response']['ResponseBase']['Data']).decode(),end='')" > deployed.gno
  cmp deployed.gno realm/aegis_attest.gno && echo identical
  ```

- Deploy transaction `b30df7b8c0003d6da0cea2b60310c23078d8ad6455b701b7897a6014603921af` at height 1416709.
- 6 realm tests pass with `GNOROOT=<gno source> gno test -v .` on gno v1.5.0.
- 24 Python tests pass with `uv run pytest -q`. They replay unedited RPC replies saved in `tests/fixtures/`.
- Live read on 2026-11-26: `aegis-attest summary` returned `agents=0|total_attestations=0|active=0|revoked=0`. The realm is deployed but holds no attestations yet.

### How to try it

Open the realm page and use the Register Agent link, or call the functions with `gnokey`. The README has copy and paste commands for registering, attesting and verifying, and the prerequisites for the tests.

### Tech

A Gno realm built and tested with gno v1.5.0, using avl trees, gnoweb Render pages, `txlink` and chain events. The Python CLI uses only the Python 3.11 standard library, and reads the chain with `vm/qeval` over RPC.

### Limits

Anyone can attest any address, so a score is only as good as the authors behind it. Revoking does not recompute the score, a revoked hash cannot be submitted again, and the page does not show the revoke reason. `VerifyEvidenceHash` panics on a malformed hash, and the CLI checks the hash first for that reason. Five of these are pinned by tests. The live realm has no attestations yet.

### Future roadmap

Recompute the score on revoke, show the reason, and add an optional reviewer allow list per task. Each needs a new realm version.
