package aegis_attest

import (
	"strings"
	"testing"

	"gno.land/p/nt/testutils/v0"
	"gno.land/p/nt/uassert/v0"
)

var (
	alice = testutils.TestAddress("alice")
	bob   = testutils.TestAddress("bob")
)

const (
	digest1 = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
	digest2 = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
	digest3 = "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
)

func TestRegisterAndSubmitAttestation(cur realm, t *testing.T) {
	testing.SetRealm(testing.NewUserRealm(alice))
	registered := RegisterAgent(cross(cur), "alice-verifier", "code-review,sha256")
	uassert.Equal(t, alice.String(), registered)

	id1 := SubmitAttestation(cross(cur), alice, "market-0x921e", digest1, 9000, "First verified citation")
	uassert.Equal(t, uint64(1), id1)
	uassert.Equal(t, 9000, GetAgentScoreBps(alice))
	uassert.True(t, VerifyEvidenceHash(alice, "market-0x921e", digest1))

	// Update EMA with second score: (9000*7 + 8000*3) / 10 = 8700
	testing.SetRealm(testing.NewUserRealm(bob))
	id2 := SubmitAttestation(cross(cur), alice, "market-0x6d14", digest2, 8000, "Second independent verification")
	uassert.Equal(t, uint64(2), id2)
	uassert.Equal(t, 8700, GetAgentScoreBps(alice))

	home := Render("")
	uassert.True(t, strings.Contains(home, "Aegis Attest"))
	uassert.True(t, strings.Contains(home, "alice-verifier"))
	uassert.True(t, strings.Contains(home, "market-0x921e"))

	detail := Render("agent/" + alice.String())
	uassert.True(t, strings.Contains(detail, digest1))
	uassert.True(t, strings.Contains(GetSummary(), "active=2"))
}

func TestAuthorOnlyRevocation(cur realm, t *testing.T) {
	testing.SetRealm(testing.NewUserRealm(alice))
	id := SubmitAttestation(cross(cur), bob, "task-rev", digest3, 5000, "Initial tentative score")
	uassert.True(t, VerifyEvidenceHash(bob, "task-rev", digest3))

	RevokeAttestation(cross(cur), id, "Evidence file was replaced")
	uassert.False(t, VerifyEvidenceHash(bob, "task-rev", digest3))
	uassert.True(t, strings.Contains(Render("agent/"+bob.String()), StatusRevoked))
}

func TestSubmitRejectsBadInput(cur realm, t *testing.T) {
	carol := testutils.TestAddress("carol")
	testing.SetRealm(testing.NewUserRealm(alice))

	uassert.AbortsContains(t, cur, "64 hex chars", func() {
		SubmitAttestation(cross(cur), carol, "task-a", "abc", 5000, "short hash")
	})
	uassert.AbortsContains(t, cur, "invalid hex char", func() {
		SubmitAttestation(cross(cur), carol, "task-a", strings.Repeat("g", 64), 5000, "not hex")
	})
	uassert.AbortsContains(t, cur, "out of 0..10000", func() {
		SubmitAttestation(cross(cur), carol, "task-a", digest1, 10001, "too high")
	})
	uassert.AbortsContains(t, cur, "out of 0..10000", func() {
		SubmitAttestation(cross(cur), carol, "task-a", digest1, -1, "negative")
	})
	uassert.AbortsContains(t, cur, "summary must be non-empty", func() {
		SubmitAttestation(cross(cur), carol, "task-a", digest1, 5000, "   ")
	})

	// 0x prefix and upper case normalize to the same digest, so the second call is a duplicate.
	SubmitAttestation(cross(cur), carol, "task-a", digest1, 5000, "first")
	uassert.AbortsContains(t, cur, "duplicate attestation", func() {
		SubmitAttestation(cross(cur), carol, "task-a", "0x"+strings.ToUpper(digest1), 6000, "same evidence again")
	})
	uassert.True(t, VerifyEvidenceHash(carol, "task-a", "0X"+strings.ToUpper(digest1)))
}

func TestRevokeGuards(cur realm, t *testing.T) {
	dave := testutils.TestAddress("dave")
	testing.SetRealm(testing.NewUserRealm(alice))
	id := SubmitAttestation(cross(cur), dave, "task-g", digest2, 7000, "by alice")

	testing.SetRealm(testing.NewUserRealm(bob))
	uassert.AbortsContains(t, cur, "only attestation author may revoke", func() {
		RevokeAttestation(cross(cur), id, "bob tries")
	})
	uassert.AbortsContains(t, cur, "not found", func() {
		RevokeAttestation(cross(cur), 999999, "missing")
	})

	testing.SetRealm(testing.NewUserRealm(alice))
	RevokeAttestation(cross(cur), id, "")
	uassert.AbortsContains(t, cur, "already revoked", func() {
		RevokeAttestation(cross(cur), id, "again")
	})
}

func TestScoreTruncatesTowardZero(cur realm, t *testing.T) {
	erin := testutils.TestAddress("erin")
	testing.SetRealm(testing.NewUserRealm(alice))
	SubmitAttestation(cross(cur), erin, "task-1", digest1, 1, "tiny")
	// (1*7 + 0*3) / 10 = 0 in integer math.
	SubmitAttestation(cross(cur), erin, "task-2", digest2, 0, "zero")
	uassert.Equal(t, 0, GetAgentScoreBps(erin))
	uassert.Equal(t, -1, GetAgentScoreBps(testutils.TestAddress("nobody")))
}

// The tests below pin current behaviour that the README lists under Known limits.

func TestKnownLimits(cur realm, t *testing.T) {
	frank := testutils.TestAddress("frank")
	testing.SetRealm(testing.NewUserRealm(frank))

	// Anyone can attest any address, including their own.
	id := SubmitAttestation(cross(cur), frank, "task-k", digest1, 9000, "self attestation")
	uassert.Equal(t, 9000, GetAgentScoreBps(frank))

	// Revoking leaves the score as it was.
	RevokeAttestation(cross(cur), id, "mistake")
	uassert.Equal(t, 9000, GetAgentScoreBps(frank))

	// With no active attestations left, the next one resets the score instead of blending.
	SubmitAttestation(cross(cur), frank, "task-k2", digest2, 1000, "fresh start")
	uassert.Equal(t, 1000, GetAgentScoreBps(frank))

	// A revoked subject/task/hash can never be submitted again.
	uassert.AbortsContains(t, cur, "duplicate attestation", func() {
		SubmitAttestation(cross(cur), frank, "task-k", digest1, 9000, "try again")
	})

	// VerifyEvidenceHash panics on a malformed hash instead of returning false.
	uassert.PanicsContains(t, cur, "64 hex chars", func() {
		VerifyEvidenceHash(frank, "task-k", "not-a-hash")
	})
}
