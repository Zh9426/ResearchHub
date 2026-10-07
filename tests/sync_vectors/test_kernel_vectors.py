"""Shared transcript wire expectations. Kernel states are a separate PG layer."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "apps/api"))
from researchhub.sync.canonical import canonical_bytes, digest, strict_loads
from researchhub.sync.protocol import ProtocolError, validate_transaction

CASES = json.loads((ROOT / "fixtures/sync/v1/kernel_cases.json").read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_kernel_transcript_wire(case):
    for step in case["steps"]:
        tx = strict_loads(step["raw"])
        assert canonical_bytes(tx).hex() == step["canonical_hex"]
        assert digest(tx) == step["digest"]
        assert [digest(c) for c in tx["changes"]] == step["revisions"]
        if step["wire_valid"]:
            validate_transaction(tx, step.get("context"))
        else:
            with pytest.raises(ProtocolError) as caught:
                validate_transaction(tx, step.get("context"))
            assert caught.value.code == step["wire_error"]
