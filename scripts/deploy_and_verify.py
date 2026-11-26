"""One-command deploy, call, eval, and render verifier for Aegis Attest on Gno.land onyx-1."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from aegis_attest.client import DEFAULT_ONYX_GNOWEB, DEFAULT_REALM_PATH, GnoMcpClient


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or deploy Aegis Attest via gnomcp")
    parser.add_argument("--profile", default="testnet")
    parser.add_argument("--realm", default=DEFAULT_REALM_PATH)
    parser.add_argument("--deploy", action="store_true", help="Broadcast AddPackage if realm is not yet deployed")
    args = parser.parse_args()

    with GnoMcpClient(profile=args.profile) as client:
        if args.deploy:
            root = Path(__file__).resolve().parents[1] / "realm"
            files = [
                {"name": "gnomod.toml", "body": (root / "gnomod.toml").read_text(encoding="utf-8")},
                {"name": "aegis_attest.gno", "body": (root / "aegis_attest.gno").read_text(encoding="utf-8")},
            ]
            dep = client.call_tool("gno_addpkg", {"profile": args.profile, "deploy_path": args.realm, "files": files})
            print("ADD_PKG:", json.dumps(dep, indent=2))
            return 0

        summary = client.query_summary(realm_path=args.realm)
        rendered = client.render(path="", realm_path=args.realm)
        sample_digest = hashlib.sha256(b"f59116e6-31f8-48d3-a5ae-ad6a7fc56986|0x921e3935|15000000").hexdigest()
        print("REALM_URL:", DEFAULT_ONYX_GNOWEB)
        print("SUMMARY:", summary)
        print("RENDER_PREVIEW:", rendered[:400])
        print("SAMPLE_SHA256:", sample_digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
