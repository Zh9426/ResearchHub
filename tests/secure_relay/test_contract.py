"""Task3A public request and QA boundary RED tests (no fake service)."""

import importlib.util


def test_relay_has_strict_qa_database_boundary():
    assert importlib.util.find_spec("researchhub_relay"), "Relay QA service is missing"
    import pytest
    from researchhub_relay.qa import validate_url

    for url in (
        "sqlite://",
        "postgresql+psycopg://x:y@127.0.0.1:55432/researchhub",
        "postgresql+psycopg://researchhub_relay_qa:x@127.0.0.1:35434/researchhub_secure_relay_qa",
    ):
        with pytest.raises(ValueError):
            validate_url(url, opt_in="0", profile="host")


def test_public_request_proof_has_exact_http_binding():
    assert importlib.util.find_spec("packages.secure_wire.request"), (
        "Public HTTP proof validator is missing"
    )
    import pytest

    from packages.secure_wire.request import validate_query

    assert validate_query("/v1/messages", b"cursor=0&limit=100") == {
        "cursor": 0,
        "limit": 100,
    }
    for query in (
        b"cursor=00",
        b"cursor=0&cursor=1",
        b"%63ursor=0",
        b"cursor=0&extra=1",
        b"cursor=-1",
    ):
        with pytest.raises(ValueError):
            validate_query("/v1/messages", query)


def test_runtime_private_inventory_and_qa_config_have_redacted_repr():
    from conftest import SecretInventory, qa_module

    values = SecretInventory()
    values.extend([b"PUBLIC_SYNTHETIC_REPR_CHECK_ONLY_" * 2])
    assert repr(values) == "SecretInventory(<redacted>)"
    assert repr(values[0]) == "SecretBytes(<redacted>)"
    assert (
        repr(qa_module().QAConfig(password="PUBLIC_TEST_ONLY"))
        == "QAConfig(<service credentials redacted>)"
    )
