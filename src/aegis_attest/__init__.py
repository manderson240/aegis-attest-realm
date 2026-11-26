"""Aegis Attest helpers: evidence digests, score math and a small gnomcp client."""

from aegis_attest.client import (
    DEFAULT_ONYX_GNOWEB,
    DEFAULT_REALM_PATH,
    GnoMcpClient,
    compute_evidence_digest,
    compute_next_ema_bps,
    normalize_sha256,
    validate_handle,
    validate_score_bps,
)

__all__ = [
    "DEFAULT_ONYX_GNOWEB",
    "DEFAULT_REALM_PATH",
    "GnoMcpClient",
    "compute_evidence_digest",
    "compute_next_ema_bps",
    "normalize_sha256",
    "validate_handle",
    "validate_score_bps",
]
