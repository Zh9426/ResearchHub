"""Fixed RH-C14N-1 identity and protocol rejection vectors (no services)."""
import copy
import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))


class WireTests(unittest.TestCase):
    def test_shared_nesting_limit_for_decoder_and_encoder(self):
        from researchhub.sync.canonical import canonical_bytes, strict_loads
        cases = json.loads((ROOT / "fixtures/sync/v1/nesting.json").read_text(encoding="utf-8"))
        for case in cases:
            value = 0
            for _ in range(case["depth"]):
                value = [value]
            with self.subTest(case=case["name"]):
                if case["valid"]:
                    self.assertEqual(canonical_bytes(strict_loads(case["raw"])).decode(), case["raw"])
                    self.assertEqual(canonical_bytes(value).decode(), case["raw"])
                else:
                    with self.assertRaises(ValueError):
                        canonical_bytes(value)
                    with self.assertRaises(ValueError):
                        strict_loads(case["raw"])

    def test_wire_engine_exists(self):
        self.assertIsNotNone(importlib.util.find_spec("researchhub.sync"), "RH-C14N-1 encoder is absent")

    def test_fixed_vectors(self):
        from researchhub.sync.canonical import canonical_bytes, digest
        for vector in json.loads((ROOT / "fixtures/sync/v1/canonical.json").read_text(encoding="utf-8")):
            with self.subTest(vector=vector["name"]):
                actual = canonical_bytes(vector["input"])
                self.assertEqual(actual.decode(), vector["canonical"])
                self.assertEqual(actual.hex(), vector["hex"])
                self.assertEqual(digest(vector["input"]), vector["sha256"])

    def test_protocol_fixtures(self):
        from researchhub.sync.canonical import strict_loads
        from researchhub.sync.protocol import (
            revision,
            transaction_digest,
            validate_transaction,
        )
        fixtures = json.loads((ROOT / "fixtures/sync/v1/protocol.json").read_text(encoding="utf-8"))
        for case in fixtures:
            with self.subTest(case=case["name"]):
                if case["valid"]:
                    tx = strict_loads(case["raw"])
                    validate_transaction(tx, case.get("context"))
                    self.assertEqual(transaction_digest(tx), case["digest"])
                    self.assertEqual([revision(c) for c in tx["changes"]], case["revisions"])
                else:
                    with self.assertRaises(ValueError):
                        validate_transaction(strict_loads(case["raw"]), case.get("context"))

    def test_numeric_precision_is_separate_from_identity(self):
        from researchhub.sync.canonical import digest, scientific_equal
        for a, b in [("1", "1.00"), ("1e0", "1.0"), ("1.60", "1.600"), ("-0", "0e99"), ("9e18", "9000000000000000000")]:
            self.assertTrue(scientific_equal(a, b))
            self.assertNotEqual(digest({"value_type": "decimal", "value": a}), digest({"value_type": "decimal", "value": b}))
        self.assertFalse(scientific_equal("9007199254740992", "9007199254740993"))

    def test_invalid_native_values_and_decimal_limits(self):
        from researchhub.sync.canonical import (
            canonical_bytes,
            scientific_equal,
            strict_loads,
        )
        for value in [1.0, -0.0, float("nan"), 9007199254740992, "\ud800", {1: "x"}]:
            with self.subTest(value=repr(value)), self.assertRaises(ValueError):
                canonical_bytes(value)
        for raw in ['{"x":1,"\\u0078":2}', '1.0', '1e0', '-0', '9007199254740992', 'NaN', '"\\ud800"', '[] trailing']:
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                strict_loads(raw)
        for value in ["1e100001", "1" * 1025, "+1", "01", "1."]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                scientific_equal(value, "1")
        self.assertTrue(scientific_equal("1e100000", "10e99999"))
        with self.assertRaises(ValueError):
            strict_loads(b'"\xff"')

    def test_every_semantic_change_field_binds_revision(self):
        from researchhub.sync.protocol import revision
        fixture = json.loads((ROOT / "fixtures/sync/v1/protocol.json").read_text(encoding="utf-8"))[0]
        change = json.loads(fixture["raw"])["changes"][0]
        changes = {key: "ffffffff-ffff-4fff-8fff-ffffffffffff" for key in ["change_id", "audit_id", "transaction_id", "project_id", "device_id", "actor_id", "object_id"]}
        changes.update(actor_type="system", object_type="Metric", operation="update", payload={"name":"pressure", "value_type":"decimal", "value":"1.600"}, module_snapshot_hash="b"*64, created_at="2026-10-07T01:02:03.005Z")
        for key, value in changes.items():
            altered = copy.deepcopy(change)
            altered[key] = value
            if key == "operation":
                altered["parents"] = ["a" * 64]
            with self.subTest(field=key):
                self.assertNotEqual(revision(change), revision(altered))
        updated = copy.deepcopy(change)
        updated.update(operation="update", parents=["a"*64])
        other_parent = copy.deepcopy(updated)
        other_parent["parents"] = ["b"*64]
        self.assertNotEqual(revision(updated), revision(other_parent))


if __name__ == "__main__":
    unittest.main()
