"""Deterministic unit tests for Aegis Attest digest, EMA bounds, sanitization, and CLI."""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import pytest

from aegis_attest.cli import main
from aegis_attest.client import (
    DEFAULT_REALM_PATH,
    clean_task,
    compute_evidence_digest,
    compute_next_ema_bps,
    normalize_sha256,
    qeval,
    validate_handle,
    validate_score_bps,
    verify_file,
)


def test_normalize_sha256_accepts_upper_and_0x_prefix() -> None:
    raw = "0x" + ("AB" * 32)
    assert normalize_sha256(raw) == "ab" * 32


@pytest.mark.parametrize("bad", ["short", "0x1234", "z" * 64, "a" * 63, "a_" + "a" * 62, " " + "a" * 63])
def test_normalize_sha256_rejects_invalid(bad: str) -> None:
    with pytest.raises(ValueError):
        normalize_sha256(bad)


def test_compute_evidence_digest_deterministic() -> None:
    d1 = compute_evidence_digest("f59116e6-31f8-48d3-a5ae-ad6a7fc56986", "0x921E3935", "15000000")
    d2 = compute_evidence_digest(" f59116e6-31f8-48d3-a5ae-ad6a7fc56986 ", "0x921e3935", "15000000")
    assert d1 == d2
    assert len(d1) == 64


@pytest.mark.parametrize("bad_score", [-1, 10001, True])
def test_validate_score_bps_rejects_out_of_range(bad_score: object) -> None:
    with pytest.raises(ValueError):
        validate_score_bps(bad_score)  # type: ignore[arg-type]


def test_compute_next_ema_bps_matches_gno_integer_math() -> None:
    first = compute_next_ema_bps(None, 9200, 0)
    assert first == 9200
    second = compute_next_ema_bps(first, 9500, 1)
    assert second == (9200 * 7 + 9500 * 3) // 10 == 9290
    third = compute_next_ema_bps(second, 9400, 2)
    assert third == (9290 * 7 + 9400 * 3) // 10 == 9323
    fourth = compute_next_ema_bps(third, 9600, 3)
    assert fourth == (9323 * 7 + 9600 * 3) // 10 == 9406


def test_validate_handle_sanitizes_markdown_cells() -> None:
    assert validate_handle("my|agent\n01") == "my/agent 01"
    with pytest.raises(ValueError):
        validate_handle("   ")


def test_cli_digest_and_ema(capsys: pytest.CaptureFixture[str]) -> None:
    rc1 = main(["digest", "--receipt", "r1", "--task", "t1", "--payload", "p1"])
    assert rc1 == 0
    out1 = json.loads(capsys.readouterr().out)
    assert len(out1["sha256"]) == 64
    assert DEFAULT_REALM_PATH.endswith("/aegis_attest")

    rc2 = main(["ema", "--current", "9200", "--score", "9500", "--accepted-before", "1"])
    assert rc2 == 0
    out2 = json.loads(capsys.readouterr().out)
    assert out2["next_ema_bps"] == 9290



# Live read: fixtures are unedited RPC replies captured from onyx-1 on 2026-11-26.

FIXTURES = Path(__file__).parent / "fixtures"
SUBJECT = "g1jg8mtutu9khhfwc4nxmuhcpftf0pajdhfvsqf5"


def _replay(name: str, seen: list[str] | None = None):
    def fetch(url: str) -> dict:
        if seen is not None:
            seen.append(url)
        return json.loads((FIXTURES / name).read_text())

    return fetch


def test_qeval_encodes_the_query_and_decodes_the_reply() -> None:
    seen: list[str] = []
    out = qeval("GetSummary()", fetch=_replay("qeval_summary.json", seen))
    assert out.startswith('("agents=0|total_attestations=0|active=0|revoked=0|height=')
    assert seen[0].startswith("https://rpc.onyx.testnets.gno.land:443/abci_query?path=%22vm/qeval%22&data=0x")
    assert bytes.fromhex(seen[0].split("data=0x")[1]).decode() == DEFAULT_REALM_PATH + ".GetSummary()"


def test_qeval_raises_on_a_chain_error() -> None:
    with pytest.raises(RuntimeError, match="64 hex chars"):
        qeval("VerifyEvidenceHash(...)", fetch=_replay("qeval_error.json"))


def test_verify_file_hashes_locally_and_reads_false_from_the_empty_realm(tmp_path: Path) -> None:
    f = tmp_path / "report.txt"
    f.write_bytes(b"hello")
    seen: list[str] = []
    res = verify_file(f, SUBJECT, " task-42 ", fetch=_replay("qeval_verify_false.json", seen))
    assert res == {"sha256": hashlib.sha256(b"hello").hexdigest(), "subject": SUBJECT, "task": "task-42", "attested": False}
    query = bytes.fromhex(seen[0].split("data=0x")[1]).decode()
    assert query.endswith(f'.VerifyEvidenceHash("{SUBJECT}","task-42","{res["sha256"]}")')


def test_verify_file_reads_true_from_a_true_reply(tmp_path: Path) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"x")
    reply = {"result": {"response": {"ResponseBase": {"Error": None, "Data": base64.b64encode(b"(true bool)").decode()}}}}
    assert verify_file(f, SUBJECT, "t", fetch=lambda _u: reply)["attested"] is True


@pytest.mark.parametrize(
    ("subject", "task"),
    [("not-an-address", "t"), (SUBJECT, "   "), (SUBJECT, 'a"b'), (SUBJECT, "a\\b")],
)
def test_verify_file_refuses_bad_input_before_any_network_call(tmp_path: Path, subject: str, task: str) -> None:
    f = tmp_path / "a.bin"
    f.write_bytes(b"x")

    def no_network(_url: str) -> dict:
        raise AssertionError("network must not be called")

    with pytest.raises(ValueError):
        verify_file(f, subject, task, fetch=no_network)


def test_clean_task_matches_the_realm_rules() -> None:
    assert clean_task("a|b\nc ") == "a/b c"
    assert len(clean_task("x" * 200)) == 96


def test_cli_verify_reports_a_missing_file(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["verify", "--file", "/nonexistent/x", "--subject", SUBJECT, "--task", "t"]) == 2
    assert "error:" in capsys.readouterr().err
