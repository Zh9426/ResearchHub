"""Mature property testing of strict canonical Unicode/numbers (no service fake)."""

import sys
from pathlib import Path

from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "apps/api"))
from researchhub.sync.canonical import (
    canonical_bytes,
    digest,
    scientific_equal,
    strict_loads,
)

SCALARS = st.text(alphabet=st.characters(blacklist_categories=("Cs",)), max_size=50)
VALUES = st.recursive(st.one_of(st.none(), st.booleans(), st.integers(-9007199254740991, 9007199254740991), SCALARS),
                      lambda children: st.one_of(st.lists(children, max_size=5),
                                                 st.dictionaries(SCALARS, children, max_size=5)), max_leaves=20)


@settings(max_examples=100, deadline=None)
@given(VALUES)
def test_canonical_roundtrip_preserves_supported_values(value):
    encoded = canonical_bytes(value)
    assert strict_loads(encoded) == value
    assert canonical_bytes(strict_loads(encoded)) == encoded


@settings(max_examples=100, deadline=None)
@given(st.dictionaries(SCALARS, VALUES, max_size=5))
def test_object_insertion_permutation_does_not_change_digest(value):
    assert digest(value) == digest(dict(reversed(list(value.items()))))


@settings(max_examples=100, deadline=None)
@given(st.integers(1, 100000), st.integers(1, 8))
def test_equal_decimal_precision_stays_distinct_wire(value, zero_count):
    raw = str(value)
    precise = raw + "." + "0" * zero_count
    assert scientific_equal(raw, precise)
    assert digest({"value": raw}) != digest({"value": precise})
