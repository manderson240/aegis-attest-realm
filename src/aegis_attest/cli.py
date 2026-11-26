"""CLI entrypoint for Aegis Attest verification and live Gno.land onyx-1 queries."""

from __future__ import annotations

import argparse
import json
import sys

from aegis_attest.client import (
    DEFAULT_ONYX_GNOWEB,
    DEFAULT_REALM_PATH,
    GnoMcpClient,
    compute_evidence_digest,
    compute_next_ema_bps,
    normalize_sha256,
    qeval,
    verify_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="aegis-attest", description="Aegis Attest Gno.land verifier CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    dig = sub.add_parser("digest", help="Compute canonical SHA-256 attestation digest")
    dig.add_argument("--receipt", required=True)
    dig.add_argument("--task", required=True)
    dig.add_argument("--payload", required=True)

    ema = sub.add_parser("ema", help="Next agent score after one attestation, same integer math as the realm")
    ema.add_argument("--current", type=int, default=None)
    ema.add_argument("--score", type=int, required=True)
    ema.add_argument("--accepted-before", type=int, default=0)

    stat = sub.add_parser("status", help="Query live onyx-1 realm state via gnomcp")
    stat.add_argument("--realm", default=DEFAULT_REALM_PATH)
    stat.add_argument("--profile", default="testnet")
    stat.add_argument("--binary", default="gnomcp")

    rnd = sub.add_parser("render", help="Render live gnoweb markdown page via gnomcp")
    rnd.add_argument("--realm", default=DEFAULT_REALM_PATH)
    rnd.add_argument("--path", default="")
    rnd.add_argument("--profile", default="testnet")
    rnd.add_argument("--binary", default="gnomcp")

    ver = sub.add_parser("verify", help="Hash a file and ask the live realm if it was attested for an agent and task")
    ver.add_argument("--file", required=True)
    ver.add_argument("--subject", required=True, help="agent g1 address")
    ver.add_argument("--task", required=True)

    summ = sub.add_parser("summary", help="Live GetSummary() over plain RPC, no gnomcp needed")
    summ.add_argument("--realm", default=DEFAULT_REALM_PATH)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "digest":
        d = compute_evidence_digest(args.receipt, args.task, args.payload)
        print(json.dumps({"sha256": normalize_sha256(d), "realm_url": DEFAULT_ONYX_GNOWEB}))
        return 0
    if args.command == "ema":
        nxt = compute_next_ema_bps(args.current, args.score, args.accepted_before)
        print(json.dumps({"next_ema_bps": nxt}))
        return 0
    if args.command == "verify":
        try:
            print(json.dumps(verify_file(args.file, args.subject, args.task)))
        except (OSError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        return 0
    if args.command == "summary":
        print(qeval("GetSummary()", realm_path=args.realm))
        return 0
    if args.command == "status":
        with GnoMcpClient(binary=args.binary, profile=args.profile) as client:
            print(client.query_summary(realm_path=args.realm))
        return 0
    if args.command == "render":
        with GnoMcpClient(binary=args.binary, profile=args.profile) as client:
            print(client.render(path=args.path, realm_path=args.realm))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
