"""PUBLIC QA application request signatures; deliberately not RFC 9421."""

import hashlib
import re

from .canonical import canonical_bytes, strict_loads
from .envelope import b64decode, hex_bytes, safe_int, uuid
from .membership import fields, verify_signed

AUDIENCE = "ResearchHub/SecureRelay/QA/v1"
PROOF_FIELDS = frozenset(
    (
        "version",
        "audience",
        "method",
        "path",
        "query",
        "opaque_project_id",
        "device_id",
        "membership_epoch",
        "key_epoch",
        "manifest_digest",
        "body_digest",
        "request_id",
        "issued_at",
        "signature",
    )
)
GET_QUERIES = {
    "/v1/messages": {"cursor": "int", "limit": "limit"},
    "/v1/membership": {},
    "/v1/membership/receipt": {"candidate_digest": "digest"},
    "/v1/grants": {"session_id": "uuid"},
    "/v1/pairing/challenge": {"session_id": "uuid"},
    "/v1/pairing/receipt": {"session_id": "uuid"},
    "/v1/checkpoints": {},
    "/v1/chunks": {"opaque_locator": "uuid", "index": "index"},
}
POST_PATHS = frozenset(
    (
        "/v1/hello",
        "/v1/messages",
        "/v1/ack",
        "/v1/membership",
        "/v1/membership/recovery",
        "/v1/grants",
        "/v1/pairing/challenge",
        "/v1/pairing/submit",
        "/v1/pairing/complete",
        "/v1/checkpoints",
        "/v1/chunks",
    )
)


def validate_query(path, raw):
    if path not in GET_QUERIES or type(raw) is not bytes or len(raw) > 512:
        raise ValueError("INVALID_QUERY")
    spec, result = GET_QUERIES[path], {}
    try:
        for part in raw.decode("ascii").split("&") if raw else ():
            key, value = part.split("=", 1)
            if key in result or key not in spec:
                raise ValueError("INVALID_QUERY")
            kind = spec[key]
            if kind in ("int", "limit", "index"):
                if not re.fullmatch("0|[1-9][0-9]{0,15}", value):
                    raise ValueError("INVALID_QUERY")
                value = int(value)
                safe_int(
                    value,
                    1 if kind == "limit" else 0,
                    100
                    if kind == "limit"
                    else 15
                    if kind == "index"
                    else 9007199254740991,
                )
            elif kind == "uuid":
                uuid(value)
            else:
                hex_bytes(value, 32)
            result[key] = value
        if set(result) != set(spec):
            raise ValueError("INVALID_QUERY")
        # No percent encoding, plus encoding, duplicate or alternate number spellings.
        expected = "&".join(f"{k}={result[k]}" for k in sorted(result)).encode()
        if expected != raw:
            raise ValueError("INVALID_QUERY")
    except (UnicodeError, TypeError, ValueError):
        raise ValueError("INVALID_QUERY") from None
    return result


def decode_proof(encoded):
    if type(encoded) is not str or len(encoded) > 8192:
        raise ValueError("AUTH_REJECTED")
    raw = b64decode(encoded)
    proof = strict_loads(raw)
    fields(proof, PROOF_FIELDS)
    if canonical_bytes(proof) != raw:
        raise ValueError("AUTH_REJECTED")
    safe_int(proof["version"], 1, 1)
    if proof["audience"] != AUDIENCE:
        raise ValueError("AUTH_REJECTED")
    for field in ("opaque_project_id", "device_id", "request_id"):
        uuid(proof[field])
    for field in ("membership_epoch", "key_epoch"):
        safe_int(proof[field], 1)
    for field in ("manifest_digest", "body_digest"):
        hex_bytes(proof[field], 32)
    safe_int(proof["issued_at"])
    b64decode(proof["signature"], 64)
    return proof


def verify_request(proof, public, method, path, query, body, now):
    safe_int(now, 1)
    if not now - 60 <= proof["issued_at"] <= now + 5:
        raise ValueError("AUTH_REJECTED")
    if (
        proof["method"] != method
        or proof["path"] != path
        # Python considers False == 0 and True == 1. Signed wire identity must
        # preserve JSON types as well as values for every endpoint query.
        or canonical_bytes(proof["query"]) != canonical_bytes(query)
        or proof["body_digest"] != hashlib.sha256(body).hexdigest()
    ):
        raise ValueError("AUTH_REJECTED")
    verify_signed("RelayRequest", proof, public)
