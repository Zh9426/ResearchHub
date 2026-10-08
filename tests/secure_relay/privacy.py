"""Client-side terminal audit. Private search patterns never enter containers."""

import ast
import base64
import io
import json
import tarfile

from sqlalchemy import LargeBinary, MetaData, Table, inspect, select, text


def audit(network, private_material, canaries):
    q, state, config = (network[k] for k in ("lifecycle", "state", "config"))
    q.guard_state(state, config)
    sources = set(canaries) | {
        b"SYNTHETIC_PRIVATE_NOTE",
        b"SYNTHETIC_SECRET_PRESSURE_1_600",
        b"SYNTHETIC_SECRET_FILENAME_MAT",
    }
    for secret in private_material:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise RuntimeError("PRIVACY_INVENTORY_INVALID")
        sources.add(secret)
    markers = set()
    for source in sources:
        if not isinstance(source, bytes) or not source:
            raise RuntimeError("PRIVACY_INVENTORY_INVALID")
        markers.update(
            (
                source,
                source.hex().encode(),
                source.hex().upper().encode(),
                base64.b64encode(source),
                base64.b64encode(source).rstrip(b"="),
                base64.urlsafe_b64encode(source),
                base64.urlsafe_b64encode(source).rstrip(b"="),
            )
        )
    hits = 0
    scanned = 0

    def scan(data):
        nonlocal hits, scanned
        scanned += len(data)
        # Native bounded substring scans avoid an alternation regex trying
        # every random key prefix at every byte of a large hexadecimal dump.
        hits += sum(data.count(marker) for marker in markers)

    scan(
        q.docker(
            "exec",
            state["pg"]["id"],
            "pg_dump",
            "-U",
            q.USER,
            "-d",
            q.DB,
            "--no-owner",
            "--no-privileges",
        )
    )
    # pg_dump hex-encodes bytea; an encoded secret in bytea has another outer
    # encoding layer. Read every actual bytea column through the guarded driver
    # as well, so no guessed number of textual encoding layers is required.
    bytea_values = 0
    bytea_bytes = 0
    bytea_columns = 0
    with network["engine"].connect() as db:
        if tuple(db.execute(text("SELECT current_database(), current_user")).one()) != (
            q.DB,
            q.USER,
        ):
            raise RuntimeError("PRIVACY_DATABASE_BOUNDARY")
        inspector = inspect(db)
        for name in inspector.get_table_names(schema="public"):
            if not name.startswith("relay_qa_"):
                raise RuntimeError("PRIVACY_SCHEMA_BOUNDARY")
            table = Table(name, MetaData(), schema="public", autoload_with=db)
            for column in table.columns:
                if not isinstance(column.type, LargeBinary):
                    continue
                bytea_columns += 1
                with db.execute(
                    select(column).execution_options(yield_per=100)
                ) as rows:
                    for row in rows:
                        if row[0] is None:
                            continue
                        value = bytes(row[0])
                        scan(value)
                        bytea_values += 1
                        bytea_bytes += len(value)
    if hits:
        # Positive controls intentionally exercise this real failure path.
        # Never include the matching value, dump, markers or SQL parameters.
        raise RuntimeError("PRIVACY_NONZERO_HITS values suppressed")
    names = {}
    for name, id_ in state["containers"].items():
        scan(q.docker("logs", id_))
        # Read-only rootfs cannot persist newly received material elsewhere.
        # All writable mounts are separately checked by guard_state and scanned.
        changes = set(q.docker("diff", id_).splitlines())
        # Docker records creation of mountpoint directories in the container
        # diff even with readonly rootfs; their entire mounted contents follow.
        assert changes <= ({b"A /tls", b"A /fault"} if name == q.RELAY else set()), (
            "Unexpected writable rootfs content"
        )
        paths = ["/srv", "/fault", "/tls"] if name == q.RELAY else ["/srv"]
        archive = q.docker("exec", id_, "tar", "-c", *paths)
        files = []
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            for item in tar:
                if not item.isfile():
                    continue
                data = tar.extractfile(item).read()
                scan(data)
                files.append(item.name)
                if item.name.endswith(".py") and item.name.startswith("srv/"):
                    tree = ast.parse(data)
                    imports = [
                        node.module or ""
                        for node in ast.walk(tree)
                        if isinstance(node, ast.ImportFrom)
                    ] + [
                        a.name
                        for node in ast.walk(tree)
                        if isinstance(node, ast.Import)
                        for a in node.names
                    ]
                    assert not any(
                        any(
                            bad in value
                            for bad in (
                                "researchhub.sync",
                                "secure.crypto",
                                ".keys",
                                "domain",
                                "aead",
                            )
                        )
                        for value in imports
                    )
        names[name] = len(files)
        assert not any(
            any(part in f for part in ("fixtures/", "tests/", "vault", "apps/api/"))
            for f in files
        )
    # Docker logs --stderr must also be captured: docker() only returns stdout.
    import subprocess

    for id_ in [state["pg"]["id"], *state["containers"].values()]:
        result = subprocess.run(
            ["docker", "logs", id_], capture_output=True, timeout=30, check=True
        )
        scan(result.stdout)
        scan(result.stderr)
    result = {
        "audit_version": 2,
        "scope": "SYNTHETIC_LOOPBACK_ONLY",
        "run": state["run"],
        "private_material_count": len(private_material),
        "canary_count": len(canaries),
        "unique_pattern_count": len(markers),
        "scanned_bytes": scanned,
        "bytea_column_count": bytea_columns,
        "bytea_value_count": bytea_values,
        "bytea_decoded_bytes": bytea_bytes,
        "database_scan": "direct pg_dump plus driver-decoded actual public bytea columns",
        "files_by_service": names,
        "hits": hits,
        "exceptions": [
            "TLS server key in /tls only",
            "dedicated QA PG service password in guarded service environment",
        ],
        "boundary": "readonly image; only Docker-created /tls,/fault mountpoint directories in diff; all mounted contents scanned; exact env + public application AST",
    }
    # Only aggregate evidence is persisted. No keys, dumps or log bodies.
    (q.ROOT / "storage/runtime/secure-relay-privacy-result.json").write_text(
        json.dumps(result), encoding="utf-8"
    )
    if hits:
        raise RuntimeError("PRIVACY_NONZERO_HITS values suppressed")
    print("RELAY_PRIVACY", json.dumps(result))
