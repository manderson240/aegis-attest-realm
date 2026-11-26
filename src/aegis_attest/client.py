"""Deterministic evidence-digest verification and gnomcp JSON-RPC bridge for Aegis Attest."""

from __future__ import annotations

import hashlib
import json
import base64
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable


DEFAULT_ONYX_GNOWEB = "https://onyx.testnets.gno.land/r/g185lernv9lg3c9akmyma2zusur5nrrmfqcfawql/aegis_attest"
DEFAULT_REALM_PATH = "gno.land/r/g185lernv9lg3c9akmyma2zusur5nrrmfqcfawql/aegis_attest"
DEFAULT_RPC = "https://rpc.onyx.testnets.gno.land:443"


def normalize_sha256(digest: str) -> str:
    """Lower-case a SHA-256 hex string, drop a 0x prefix, and reject anything that is not 64 hex chars, as the realm does."""
    cleaned = digest.strip().lower()
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
    if not re.fullmatch(r"[0-9a-f]{64}", cleaned):
        raise ValueError("evidence_sha256 must be exactly 64 hex characters")
    return cleaned


def compute_evidence_digest(receipt_id: str, market_or_task: str, settled_or_payload: str) -> str:
    """SHA-256 of "receipt|task|payload", with the task lower-cased and each part trimmed."""
    canonical = f"{receipt_id.strip()}|{market_or_task.strip().lower()}|{settled_or_payload.strip()}"
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def validate_score_bps(score_bps: int) -> int:
    """Reject scores outside 0 to 10000 basis points, as the realm does."""
    if not isinstance(score_bps, int) or isinstance(score_bps, bool) or score_bps < 0 or score_bps > 10000:
        raise ValueError("score_bps must be an integer between 0 and 10000")
    return score_bps


def validate_handle(handle: str, max_len: int = 48) -> str:
    """Clean a handle the same way the realm does: no newlines, no pipes, at most max_len chars."""
    cleaned = handle.strip().replace("\r", " ").replace("\n", " ").replace("|", "/")
    if not cleaned:
        raise ValueError("handle must be non-empty")
    return cleaned[:max_len]


def compute_next_ema_bps(current_ema_bps: int | None, new_score_bps: int, accepted_count_before: int) -> int:
    """Next score with the realm's integer rule: (score * 7 + new * 3) / 10, or the new score if it is the first."""
    score = validate_score_bps(new_score_bps)
    if accepted_count_before <= 0 or current_ema_bps is None:
        return score
    return (current_ema_bps * 7 + score * 3) // 10


class GnoMcpClient:
    """Stdlib stdio JSON-RPC client for gnomcp read/call/render verification."""

    def __init__(self, binary: str = "gnomcp", profile: str = "testnet") -> None:
        self.binary = binary
        self.profile = profile
        self._proc: subprocess.Popen[str] | None = None
        self._req_id = 0

    def __enter__(self) -> GnoMcpClient:
        self._proc = subprocess.Popen(
            [self.binary],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "aegis-attest-cli", "version": "0.1.0"},
            },
        )
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self._proc.stdin.flush()
        return self

    def __exit__(self, *_: object) -> None:
        if self._proc is not None:
            if self._proc.stdin and not self._proc.stdin.closed:
                self._proc.stdin.close()
            self._proc.wait(timeout=5)
            self._proc = None

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        assert self._proc is not None and self._proc.stdin is not None and self._proc.stdout is not None
        self._req_id += 1
        target_id = self._req_id
        self._proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": target_id, "method": method, "params": params}) + "\n")
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline()
            if not line:
                raise RuntimeError("Unexpected EOF from gnomcp")
            msg = json.loads(line)
            if msg.get("id") == target_id:
                return msg

    def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Invoke a gnomcp tool and return parsed JSON-RPC result."""
        res = self._rpc("tools/call", {"name": name, "arguments": arguments})
        return res.get("result", res)

    def query_summary(self, realm_path: str = DEFAULT_REALM_PATH) -> str:
        """Query zero-gas GetSummary() via gno_eval."""
        res = self.call_tool("gno_eval", {"profile": self.profile, "path": realm_path, "expr": "GetSummary()"})
        return (res.get("content") or [{}])[0].get("text", "")

    def render(self, path: str = "", realm_path: str = DEFAULT_REALM_PATH) -> str:
        """Fetch live rendered markdown from gno_render."""
        res = self.call_tool("gno_render", {"profile": self.profile, "realm": realm_path, "path": path})
        return (res.get("content") or [{}])[0].get("text", "")


def sha256_file(path: str | Path) -> str:
    """SHA-256 of a file's bytes, as 64 lower-case hex characters."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_abci(url: str) -> dict[str, Any]:
    """GET one abci_query URL and parse the JSON body."""
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https RPC
        return json.loads(resp.read())


def qeval(
    expr: str,
    realm_path: str = DEFAULT_REALM_PATH,
    rpc: str = DEFAULT_RPC,
    fetch: Callable[[str], dict[str, Any]] = fetch_abci,
) -> str:
    """Free read: evaluate one expression in the realm with vm/qeval over plain RPC, no gnomcp or key needed."""
    data = f"{realm_path}.{expr}".encode().hex()
    url = f"{rpc}/abci_query?path=%22vm/qeval%22&data=0x{data}"
    base = fetch(url)["result"]["response"]["ResponseBase"]
    if base.get("Error"):
        err = base["Error"]
        raise RuntimeError(f"vm/qeval failed: {err.get('value', err) if isinstance(err, dict) else err}")
    return base64.b64decode(base.get("Data") or "").decode("utf-8")


def clean_task(task: str, max_len: int = 96) -> str:
    """Clean a task id the way the realm does before it builds the lookup key."""
    cleaned = task.replace("\r", " ").replace("\n", " ").replace("|", "/").strip()
    return cleaned[:max_len]


def verify_file(
    path: str | Path,
    subject: str,
    task: str,
    realm_path: str = DEFAULT_REALM_PATH,
    rpc: str = DEFAULT_RPC,
    fetch: Callable[[str], dict[str, Any]] = fetch_abci,
) -> dict[str, Any]:
    """Hash a file locally, then ask the realm if that hash is attested for the subject and task.

    The hash and address are checked here first, because VerifyEvidenceHash on chain panics on a malformed hash.
    """
    digest = normalize_sha256(sha256_file(path))
    if not re.fullmatch(r"g1[0-9a-z]{38}", subject):
        raise ValueError("subject must be a g1 address")
    task = clean_task(task)
    if not task or '"' in task or "\\" in task:
        raise ValueError("task must be non-empty and contain no double quote or backslash")
    raw = qeval(f'VerifyEvidenceHash("{subject}","{task}","{digest}")', realm_path, rpc, fetch)
    return {"sha256": digest, "subject": subject, "task": task, "attested": raw.startswith("(true ")}
