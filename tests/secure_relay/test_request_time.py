"""Deterministic service clock checks against guarded, real QA PostgreSQL.

These calls exercise service authorization and durable receipts, not HTTP timing.
"""

import pytest
from researchhub_relay.models import RequestReceipt
from researchhub_relay.service import execute
from sqlalchemy.orm import Session

from packages.secure_wire.canonical import strict_loads
from packages.secure_wire.envelope import b64decode

NOW = 1_800_000_000


def test_future_request_crosses_into_valid_window_after_one_second(project):
    prepared = project.prepare("POST", "/v1/hello", {}, issued_at=NOW + 6)
    proof = strict_loads(b64decode(prepared["headers"]["x-rh-proof"]))
    engine = project.network["engine"]
    args = (engine, proof, "POST", "/v1/hello", {}, b"{}")
    receipt_key = (project.id, project.owner.device_id, proof["request_id"])

    with pytest.raises(ValueError, match="^AUTH_REJECTED$"):
        execute(*args, now=NOW)
    with Session(engine) as db:
        assert db.get(RequestReceipt, receipt_key) is None

    # The same signature is now exactly +5 seconds ahead and therefore valid.
    response = execute(*args, now=NOW + 1)
    assert strict_loads(response)["ok"] is True
    with Session(engine) as db:
        assert db.get(RequestReceipt, receipt_key).response == response
    assert execute(*args, now=NOW + 1) == response

    # Existing durable cache must never bypass either time boundary. The past
    # timestamp becomes expired at issued_at + 61; the original T is too early.
    for invalid_now in (NOW, NOW + 67):
        with pytest.raises(ValueError, match="^AUTH_REJECTED$"):
            execute(*args, now=invalid_now)
        with Session(engine) as db:
            assert db.get(RequestReceipt, receipt_key).response == response


@pytest.mark.parametrize(
    ("offset", "accepted"), [(-61, False), (-60, True), (5, True), (6, False)]
)
def test_service_request_time_boundaries_and_receipts(project, offset, accepted):
    prepared = project.prepare("POST", "/v1/hello", {}, issued_at=NOW + offset)
    proof = strict_loads(b64decode(prepared["headers"]["x-rh-proof"]))
    engine = project.network["engine"]
    args = (engine, proof, "POST", "/v1/hello", {}, b"{}")
    receipt_key = (project.id, project.owner.device_id, proof["request_id"])
    if accepted:
        response = execute(*args, now=NOW)
        assert strict_loads(response)["ok"] is True
        with Session(engine) as db:
            assert db.get(RequestReceipt, receipt_key).response == response
    else:
        with pytest.raises(ValueError, match="^AUTH_REJECTED$"):
            execute(*args, now=NOW)
        with Session(engine) as db:
            assert db.get(RequestReceipt, receipt_key) is None
