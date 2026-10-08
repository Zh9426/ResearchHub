"""Real HTTPS/container/PG fixtures; all private material stays client-side."""

import hashlib
import importlib.util
import json
import os
import ssl
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "apps/api"), str(ROOT / "apps/relay")]
from researchhub.sync.secure import keys
from researchhub.sync.secure.envelope import seal_record
from researchhub.sync.secure.nonce import NonceVault
from researchhub_relay.models import Base, Budget, Project
from researchhub_relay.qa import connect
from researchhub_relay.service import initialize, pin_bootstrap

from packages.secure_wire.canonical import canonical_bytes, digest
from packages.secure_wire.envelope import b64encode
from packages.secure_wire.request import AUDIENCE


class SecretBytes(bytes):
    def __repr__(self):
        return "SecretBytes(<redacted>)"


class SecretInventory(list):
    def append(self, value):
        super().append(SecretBytes(value))

    def extend(self, values):
        for value in values:
            self.append(value)

    def __repr__(self):
        return "SecretInventory(<redacted>)"


PRIVATE_MATERIAL = SecretInventory()
CANARIES = [
    b"SYNTHETIC_RESEARCH_PROJECT_4ae93b",
    b"SYNTHETIC_RUN_TITLE_b9c7df",
    b"SYNTHETIC_PARAMETER_a6e841",
    b"SYNTHETIC_METRIC_f3981a",
    b"SYNTHETIC_ARTIFACT_FILE_3ea954.mat",
    b"SYNTHETIC_CATEGORY_a2d6c0",
    b"SYNTHETIC_HUMAN_CONCLUSION_d8ef31",
]


def qa_module():
    spec = importlib.util.spec_from_file_location(
        "secure_relay_lifecycle", ROOT / "scripts/secure-relay-qa.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def network():
    assert os.environ.get("HUB_RELAY_QA") == "1", (
        "Explicit real-network QA opt-in required"
    )
    lifecycle = qa_module()
    config = lifecycle.config()
    assert lifecycle.STATE.exists(), "Run secure-relay-qa.py --init first"
    state = json.loads(lifecycle.STATE.read_text())
    lifecycle.guard_state(state, config)
    lifecycle.wait_tls(state)
    engine = connect(lifecycle.url(config), profile="host")
    # Only guarded dedicated Relay QA tables; no production migration.
    initialize(engine)
    with Session(engine) as db, db.begin():
        old_projects = list(db.scalars(select(Project.id)))
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
        db.add(Budget(id="global", events=b"[]"))
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Project)) == 0
        assert all(db.get(Project, identity) is None for identity in old_projects)
    context = ssl.create_default_context(
        cafile=str(Path(state["tls_directory"]) / "ca.crt")
    )
    with httpx.Client(
        base_url="https://127.0.0.1:38001", verify=context, trust_env=False, timeout=12
    ) as client:
        # No previous run's authority remains in the registry. Every retired
        # opaque project is checked over HTTP with a fresh, signed request.
        if old_projects:
            outsider = device()
            for identity in old_projects:
                proof = keys.signed_object(
                    "RelayRequest",
                    {
                        "version": 1,
                        "audience": AUDIENCE,
                        "method": "POST",
                        "path": "/v1/hello",
                        "query": {},
                        "opaque_project_id": identity,
                        "device_id": outsider.device_id,
                        "membership_epoch": 1,
                        "key_epoch": 1,
                        "manifest_digest": "0" * 64,
                        "body_digest": hashlib.sha256(b"{}").hexdigest(),
                        "request_id": str(uuid4()),
                        "issued_at": int(time.time()),
                    },
                    outsider.signing_seed,
                )
                response = client.post(
                    "/v1/hello",
                    content=b"{}",
                    headers={
                        "content-type": "application/json",
                        "x-rh-proof": b64encode(canonical_bytes(proof)),
                    },
                )
                assert response.status_code == 401
        value = {
            "client": client,
            "engine": engine,
            "lifecycle": lifecycle,
            "state": state,
            "config": config,
            "tls": context,
            "retired_project_count": len(old_projects),
            "audit_context": {
                "trial": os.environ.get("HUB_QA_TRIAL", str(uuid4())),
                "cohort": os.environ.get("HUB_QA_COHORT", "direct"),
                "invocation": os.environ.get("HUB_QA_INVOCATION", str(uuid4())),
            },
        }
        yield value
        from privacy import audit

        audit(value, PRIVATE_MATERIAL, CANARIES)
    engine.dispose()


def device():
    value = keys.Device.generate()
    PRIVATE_MATERIAL.extend((value.signing_seed, value.recipient_seed))
    return value


class ProjectClient:
    def __init__(self, network, directory):
        self.network, self.directory = network, directory
        self.owner = device()
        self.kit = keys.RecoveryKit.generate()
        PRIVATE_MATERIAL.extend((self.kit.signing_seed, self.kit.recipient_seed))
        self.manifest = keys.bootstrap(str(uuid4()), self.owner, self.kit)
        pin_bootstrap(
            network["engine"],
            self.manifest,
            self.owner.signing_public,
            self.kit.signing_public,
        )
        self.key = os.urandom(32)
        PRIVATE_MATERIAL.append(self.key)
        self.vault = NonceVault(directory / "nonce.sqlite")
        self.vault.register_new(self.key, 0)

    @property
    def id(self):
        return self.manifest["opaque_project_id"]

    def prepare(
        self,
        method,
        path,
        body=None,
        query=None,
        *,
        signer=None,
        manifest=None,
        request_id=None,
        issued_at=None,
    ):
        signer, manifest = signer or self.owner, manifest or self.manifest
        query = query or {}
        raw = canonical_bytes(body) if method == "POST" else b""
        proof = keys.signed_object(
            "RelayRequest",
            {
                "version": 1,
                "audience": AUDIENCE,
                "method": method,
                "path": path,
                "query": query,
                "opaque_project_id": self.id,
                "device_id": signer.device_id,
                "membership_epoch": manifest["membership_epoch"],
                "key_epoch": manifest["key_epoch"],
                "manifest_digest": digest(manifest),
                "body_digest": hashlib.sha256(raw).hexdigest(),
                "request_id": request_id or str(uuid4()),
                "issued_at": int(time.time()) if issued_at is None else issued_at,
            },
            signer.signing_seed,
        )
        suffix = (
            "?" + "&".join(f"{k}={query[k]}" for k in sorted(query)) if query else ""
        )
        return {
            "method": method,
            "url": path + suffix,
            "content": raw,
            "headers": {
                "x-rh-proof": b64encode(canonical_bytes(proof)),
                **({"content-type": "application/json"} if method == "POST" else {}),
            },
        }

    def send(self, prepared):
        return self.network["client"].request(**prepared)

    def request(self, method, path, body=None, query=None, **kwargs):
        return self.send(self.prepare(method, path, body, query, **kwargs))

    def envelope(self, record=None, *, signer=None, manifest=None):
        signer, manifest = signer or self.owner, manifest or self.manifest
        member = next(
            m for m in manifest["members"] if m["device_id"] == signer.device_id
        )
        if member["nonce_prefix"] != 0:
            try:
                self.vault.register_new(self.key, member["nonce_prefix"])
            except ValueError:
                pass
        return seal_record(
            record or {"synthetic": [c.decode() for c in CANARIES]},
            self.key,
            signer.signing_seed,
            self.vault,
            member["nonce_prefix"],
            opaque_project_id=self.id,
            sender_device_id=signer.device_id,
            membership_epoch=manifest["membership_epoch"],
            key_epoch=manifest["key_epoch"],
            message_id=str(uuid4()),
        )

    def push(self, envelopes, **kwargs):
        return self.request("POST", "/v1/messages", {"envelopes": envelopes}, **kwargs)

    def pull(self, cursor=0, limit=100, **kwargs):
        return self.request(
            "GET", "/v1/messages", query={"cursor": cursor, "limit": limit}, **kwargs
        )

    def add(self, role="reader", status="ACTIVE"):
        value = device()
        candidate = keys.transition(
            self.manifest,
            self.owner,
            add=value.member(
                role,
                max(m["nonce_prefix"] for m in self.manifest["members"]) + 1,
                status=status,
            ),
        )
        result = self.request("POST", "/v1/membership", {"manifest": candidate})
        assert result.status_code == 200, result.json().get("code")
        self.manifest = candidate
        return value


@pytest.fixture
def project(network, tmp_path):
    return ProjectClient(network, tmp_path)


@pytest.fixture
def trusted(project):
    from researchhub.sync.authority import register_principal
    from researchhub.sync.kernel import register_project
    from researchhub.sync.secure.transport import SecureTransport
    from researchhub.sync.secure.transport_pg import client_engine, initialize, pin

    engine = client_engine()
    initialize(engine)
    semantic = str(uuid4())
    person = {
        k: str(uuid4()) for k in ("principal_id", "user_id", "session_id", "actor_id")
    }
    person.update(
        project_id=semantic, device_id=project.owner.device_id, actor_type="codex"
    )
    with Session(engine) as db, db.begin():
        register_project(db, semantic, "a" * 64)
        register_principal(db, **person)
    pin(
        engine,
        project.manifest,
        project.owner.signing_public,
        project.kit.signing_public,
        semantic,
        {project.owner.device_id: person["principal_id"]},
    )
    client = SecureTransport(
        engine,
        project.id,
        project.owner,
        project.network["state"]["tls_directory"] + "/ca.crt",
        {1: project.key},
    )
    yield client, person
    client.close()
    engine.dispose()
