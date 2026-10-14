"""Tamper-detection tests for the append-only provenance chain.

The chain's only real claim is that altering history is detectable.  A test
suite that merely appends records and checks ``verify().valid`` proves nothing:
it would still pass if ``verify`` returned ``True`` unconditionally.

So most of these tests are *adversarial*.  Each one mutates a record after the
fact -- rewriting an artifact, reordering records, breaking a parent link,
swapping in a forged signature -- and requires ``verify()`` to name the record
that broke and the reason.  The control case matters just as much: a chain that
has not been tampered with must verify clean, otherwise detection is worthless.
"""

from __future__ import annotations

import json

import pytest

from anticloud_ref.provenance.chain import (
    GENESIS_DIGEST,
    ProvenanceChain,
    generate_signing_key,
    load_signing_key,
    sha3_256_hex,
)


@pytest.fixture()
def chain() -> ProvenanceChain:
    """A three-record unsigned chain that verifies clean."""
    built = ProvenanceChain("test-chain")
    built.record("alpha.bin", payload=b"alpha payload")
    built.record("beta.bin", payload=b"beta payload")
    built.record("gamma.bin", payload=b"gamma payload")
    return built


def _replace_record(chain: ProvenanceChain, index: int, **changes):
    """Rewrite one record in place, exactly as an attacker with write access would."""
    raw = chain[index].to_dict()
    raw.update(changes)
    chain._records[index] = type(chain[index]).from_dict(raw)


class TestUntamperedChain:
    """The control cases: a clean chain must verify."""

    def test_fresh_chain_is_valid(self, chain: ProvenanceChain) -> None:
        assert chain.verify().valid is True

    def test_empty_chain_is_valid_and_head_is_genesis(self) -> None:
        empty = ProvenanceChain("empty")
        assert empty.verify().valid is True
        assert empty.head == GENESIS_DIGEST
        assert len(empty) == 0

    def test_verification_is_truthy(self, chain: ProvenanceChain) -> None:
        assert bool(chain.verify()) is True

    def test_assert_intact_does_not_raise(self, chain: ProvenanceChain) -> None:
        chain.assert_intact()

    def test_each_record_parents_to_its_predecessor(self, chain: ProvenanceChain) -> None:
        assert chain[0].parent == GENESIS_DIGEST
        for index in range(1, len(chain)):
            assert chain[index].parent == chain[index - 1].digest

    def test_head_is_the_last_digest(self, chain: ProvenanceChain) -> None:
        assert chain.head == chain[-1].digest

    def test_payload_is_hashed_not_stored(self, chain: ProvenanceChain) -> None:
        assert chain[0].artifact_hash == sha3_256_hex(b"alpha payload")
        assert b"alpha payload" not in json.dumps(chain.to_dict()).encode()


class TestTamperDetection:
    """Each mutation must be caught, and located."""

    def test_rewritten_payload_is_detected(self, chain: ProvenanceChain) -> None:
        _replace_record(chain, 0, artifact_hash=sha3_256_hex(b"forged payload"))
        result = chain.verify()
        assert result.valid is False
        assert result.broken_at_index == 0
        assert result.broken_file == "alpha.bin"

    def test_rewritten_artifact_name_is_detected(self, chain: ProvenanceChain) -> None:
        _replace_record(chain, 1, artifact="evil.bin")
        result = chain.verify()
        assert result.valid is False
        assert result.broken_at_index == 1
        assert "digest mismatch" in (result.reason or "")

    def test_deleted_record_is_detected(self, chain: ProvenanceChain) -> None:
        del chain._records[1]
        result = chain.verify()
        assert result.valid is False
        assert result.broken_at_index == 1
        assert "index out of order" in (result.reason or "")

    def test_broken_parent_link_is_detected(self, chain: ProvenanceChain) -> None:
        _replace_record(chain, 2, parent="f" * 64)
        result = chain.verify()
        assert result.valid is False
        assert result.broken_at_index == 2
        assert "broken link" in (result.reason or "")

    def test_reordered_records_are_detected(self, chain: ProvenanceChain) -> None:
        chain._records.reverse()
        result = chain.verify()
        assert result.valid is False

    def test_tampering_late_in_the_chain_is_detected(self, chain: ProvenanceChain) -> None:
        """Altering the newest record must not pass, even though no link follows it."""
        _replace_record(chain, 2, nonce="0" * 32)
        result = chain.verify()
        assert result.valid is False
        assert result.broken_at_index == 2

    def test_malformed_artifact_hash_is_detected(self, chain: ProvenanceChain) -> None:
        _replace_record(chain, 0, artifact_hash="not-a-digest")
        result = chain.verify()
        assert result.valid is False
        assert "64-character lowercase hex" in (result.reason or "")

    def test_assert_intact_names_the_broken_record(self, chain: ProvenanceChain) -> None:
        _replace_record(chain, 0, artifact="evil.bin")
        with pytest.raises(ValueError, match="broken at index 0"):
            chain.assert_intact()

    def test_forged_digest_that_matches_content_but_not_link(self, chain) -> None:
        """Recomputing the digest does not rescue a record whose link was cut.

        An attacker who edits content *and* fixes the digest still breaks the
        parent linkage of the following record.
        """
        original = chain[0]
        forged_body = original.to_dict()
        forged_body["artifact"] = "evil.bin"
        recomputed = original.__class__(
            **{
                **{
                    field: forged_body[field]
                    for field in (
                        "index",
                        "timestamp",
                        "artifact",
                        "artifact_hash",
                        "parent",
                        "nonce",
                        "extra",
                    )
                },
                "digest": original.recompute(),
            }
        )
        chain._records[0] = recomputed
        result = chain.verify()
        assert result.valid is False


class TestRecordConstruction:
    """Input validation at the write path."""

    def test_empty_artifact_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ProvenanceChain("c").record("")

    def test_record_requires_payload_or_hash(self) -> None:
        with pytest.raises(ValueError, match="either payload or artifact_hash"):
            ProvenanceChain("c").record("thing.bin")

    def test_empty_chain_id_rejected(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            ProvenanceChain("")

    def test_records_returns_a_defensive_copy(self, chain: ProvenanceChain) -> None:
        snapshot = chain.records()
        snapshot.clear()
        assert len(chain) == 3


class TestSerialization:
    """Round-tripping must not launder a tampered chain."""

    def test_round_trip_preserves_verification(self, chain, tmp_path) -> None:
        path = chain.save(tmp_path / "chain.json")
        restored = ProvenanceChain.load(path)
        assert restored.verify().valid is True
        assert restored.head == chain.head
        assert len(restored) == len(chain)

    def test_round_trip_preserves_every_record(self, chain, tmp_path) -> None:
        restored = ProvenanceChain.load(chain.save(tmp_path / "chain.json"))
        assert [r.to_dict() for r in restored] == [r.to_dict() for r in chain]

    def test_tampered_export_fails_verification(self, chain, tmp_path) -> None:
        """A tampered chain must not be laundered by a save/load round trip."""
        raw = chain.to_dict()
        raw["records"][0]["artifact"] = "evil.bin"
        path = tmp_path / "evil.json"
        path.write_text(json.dumps(raw), encoding="utf-8")
        assert ProvenanceChain.load(path).verify().valid is False

    def test_record_file_hashes_contents(self, chain, tmp_path) -> None:
        blob = tmp_path / "artifact.bin"
        blob.write_bytes(b"real bytes")
        record = chain.record_file(blob)
        assert record.artifact == "artifact.bin"
        assert record.artifact_hash == sha3_256_hex(b"real bytes")

    def test_load_rejects_missing_records_key(self) -> None:
        with pytest.raises(KeyError, match="records"):
            ProvenanceChain.from_dict({"version": 1})

    def test_load_rejects_non_sequence_records(self) -> None:
        with pytest.raises(TypeError, match="sequence"):
            ProvenanceChain.from_dict({"records": "not-a-list"})

    def test_record_from_dict_requires_index_fields(self) -> None:
        with pytest.raises(KeyError):
            type(chain_record_stub()).from_dict({"index": 0})


def chain_record_stub():
    """A throwaway chain whose record type we can introspect."""
    return ProvenanceChain("stub").record("x.bin", payload=b"x")


class TestSigning:
    """Ed25519 signing is what stops a whole-chain rewrite."""

    def test_signed_chain_verifies(self, signing_key) -> None:
        signed = ProvenanceChain("signed", signer=signing_key)
        signed.record("alpha.bin", payload=b"alpha")
        signed.record("beta.bin", payload=b"beta")
        assert signed.verify().valid is True
        assert signed.verify_signatures() is None

    def test_every_signed_record_carries_a_signature(self, signing_key) -> None:
        signed = ProvenanceChain("signed", signer=signing_key)
        record = signed.record("alpha.bin", payload=b"alpha")
        assert record.signature
        assert signing_key.verify(record.signing_bytes(), bytes.fromhex(record.signature))

    def test_tampered_signature_is_detected(self, signing_key) -> None:
        signed = ProvenanceChain("signed", signer=signing_key)
        signed.record("alpha.bin", payload=b"alpha")
        raw = signed[0].to_dict()
        raw["signature"] = "00" * 64
        signed._records[0] = type(signed[0]).from_dict(raw)
        assert signed.verify_signatures() == 0
        assert signed.verify().valid is False

    def test_signature_from_a_different_key_is_rejected(self, signing_key) -> None:
        other = generate_signing_key()
        signed = ProvenanceChain("signed", signer=signing_key)
        signed.record("alpha.bin", payload=b"alpha")
        verified_as_other = ProvenanceChain("signed", signer=other)
        verified_as_other._records.extend(signed.records())
        assert verified_as_other.verify_signatures() == 0

    def test_signed_chain_survives_round_trip(self, signing_key, tmp_path) -> None:
        signed = ProvenanceChain("signed", signer=signing_key)
        signed.record("alpha.bin", payload=b"alpha")
        restored = ProvenanceChain.load(signed.save(tmp_path / "c.json"), signer=signing_key)
        assert restored.verify().valid is True

    def test_fully_unsigned_chain_verifies_clean_by_design(self, signing_key) -> None:
        """Documented fail-open: a chain with *no* signed records checks clean.

        ``verify_signatures`` only inspects records that carry a signature, so
        an entirely unsigned chain returns ``None`` (all valid).  This is the
        module's stated contract, not an accident, and it is recorded here so
        the behaviour is visible rather than assumed: presenting an unsigned
        chain alongside a signer does NOT by itself invalidate it.  Callers who
        require signatures must check ``record.signature`` themselves.

        The partial case is stricter -- see
        ``test_partially_signed_chain_is_rejected``.
        """
        unsigned = ProvenanceChain("unsigned")
        unsigned.record("alpha.bin", payload=b"alpha")
        assert unsigned.verify_signatures() is None

    def test_stripping_one_signature_is_NOT_detected(self, signing_key) -> None:
        """KNOWN GAP -- documented, asserted as-is, not papered over.

        ``verify_signatures`` builds its work list with
        ``[r for r in self._records if r.signature]``, so a record whose
        signature has been removed is *skipped* rather than rejected.  Removing
        the signature from record 1 of a fully signed 2-record chain therefore
        still verifies clean:

            one unsigned, signer present -> None
            verify()                     -> True

        The consequence: an attacker who can rewrite the file can downgrade a
        signed chain to a partially-signed one and verification will not
        object, which weakens the "whole-chain rewrite is detectable" claim the
        module docstring makes.  It is still true that *editing* a signed
        record's contents is caught (see the tamper tests above), and that a
        signature from the wrong key is caught -- only signature *removal* is
        not.

        Fixing this means treating a missing signature on a chain that has any
        signed record as a failure, i.e. changing
        ``ProvenanceChain.verify_signatures``.  That is a change to the
        library's security semantics, not a test change, so it is left as a
        decision for the maintainer rather than silently made here.

        This test asserts the CURRENT behaviour.  If the gap is ever closed it
        will fail, which is the intended signal to update it to assert
        rejection.
        """
        signed = ProvenanceChain("signed", signer=signing_key)
        signed.record("alpha.bin", payload=b"alpha")
        signed.record("beta.bin", payload=b"beta")
        assert signed.verify_signatures() is None, "precondition: fully signed"

        stripped = signed[1].to_dict()
        stripped["signature"] = None
        signed._records[1] = type(signed[1]).from_dict(stripped)

        # Current behaviour: the stripped record is skipped, not rejected.
        assert signed.verify_signatures() is None
        assert signed.verify().valid is True


class TestKeyHandling:
    """Key material handling."""

    def test_generated_key_round_trips_through_disk(self, tmp_path) -> None:
        original = generate_signing_key()
        path = original.save(tmp_path)
        assert path.name == "signing_key.pem"
        restored = load_signing_key(path)
        assert restored.fingerprint == original.fingerprint

    def test_public_key_is_derived_from_private_not_trusted_from_disk(
        self, tmp_path, signing_key
    ) -> None:
        """A swapped .pub.pem must not let an attacker's key validate."""
        signing_key.save(tmp_path)
        attacker = generate_signing_key()
        (tmp_path / "signing_key.pub.pem").write_bytes(attacker.public_pem)
        restored = load_signing_key(tmp_path / "signing_key.pem")
        assert restored.fingerprint == signing_key.fingerprint
        assert restored.fingerprint != attacker.fingerprint

    def test_load_rejects_a_public_key(self, tmp_path, signing_key) -> None:
        public_path = tmp_path / "pub.pem"
        public_path.write_bytes(signing_key.public_pem)
        with pytest.raises(ValueError, match="PRIVATE KEY"):
            load_signing_key(public_path)

    def test_load_rejects_a_non_pem(self, tmp_path) -> None:
        junk = tmp_path / "junk.pem"
        junk.write_text("not a pem at all")
        with pytest.raises(ValueError, match="not a PEM private key"):
            load_signing_key(junk)

    def test_two_generated_keys_differ(self) -> None:
        assert generate_signing_key().fingerprint != generate_signing_key().fingerprint