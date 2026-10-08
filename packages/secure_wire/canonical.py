"""RH-C14N-1: scalar Unicode, UTF-16 key order and exact scientific numbers."""

import hashlib
import json
import re

SAFE_INTEGER = 9007199254740991
MAX_NESTING = 64
DECIMAL = re.compile(r"-?(0|[1-9][0-9]*)(\.[0-9]+)?([eE][+-]?[0-9]+)?\Z")
INTEGER = re.compile(r"(?:0|-?[1-9][0-9]*)\Z")


def _string(value):
    if any(0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError("invalid Unicode scalar")
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def canonical_bytes(value):
    """Encode supported JSON values without normalization or numeric coercion."""

    def encode(item, depth=0):
        if depth > MAX_NESTING:
            raise ValueError("wire nesting exceeds 64 value edges")
        if item is None:
            return "null"
        if type(item) is bool:
            return "true" if item else "false"
        if type(item) is int and abs(item) <= SAFE_INTEGER:
            return str(item)
        if type(item) is str:
            return _string(item)
        if type(item) is list:
            return "[" + ",".join(encode(v, depth + 1) for v in item) + "]"
        if type(item) is dict:
            if any(type(k) is not str for k in item):
                raise ValueError("object keys must be strings")
            for key in item:
                _string(key)
            keys = sorted(item, key=lambda k: k.encode("utf-16-be"))
            return (
                "{"
                + ",".join(_string(k) + ":" + encode(item[k], depth + 1) for k in keys)
                + "}"
            )
        raise ValueError("unsupported wire value; numbers must be safe native integers")

    try:
        return encode(value).encode("utf-8")
    except RecursionError as exc:
        raise ValueError("wire nesting too deep") from exc


def strict_loads(raw):
    """Reject duplicate decoded keys and disallowed numeric lexemes before coercion."""

    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate decoded object key")
            result[key] = value
        return result

    def integer(token):
        if token == "-0" or len(token.lstrip("-")) > 16:
            raise ValueError("disallowed integer lexeme")
        value = int(token)
        if abs(value) > SAFE_INTEGER:
            raise ValueError("unsafe native integer")
        return value

    def forbidden(token):
        raise ValueError("disallowed native numeric lexeme: " + token)

    if not isinstance(raw, (str, bytes, bytearray)):
        # All invalid wire inputs share ValueError so ingress can quarantine them.
        raise ValueError("wire input must be UTF-8 bytes or text")  # noqa: TRY004
    try:
        if not isinstance(raw, str):
            raw = bytes(raw).decode("utf-8", errors="strict")
        value = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_int=integer,
            parse_float=forbidden,
            parse_constant=forbidden,
        )
        canonical_bytes(value)
        return value
    except (UnicodeError, json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("invalid strict JSON") from exc


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def validate_decimal(value):
    if type(value) is not str or len(value) > 1024 or not DECIMAL.fullmatch(value):
        raise ValueError("invalid decimal string")
    parts = re.split("[eE]", value)
    exponent_text = parts[1] if len(parts) == 2 else "0"
    # Avoid constructing an unbounded integer even for a long exponent lexeme.
    significant_exponent = exponent_text.lstrip("+-").lstrip("0") or "0"
    if len(significant_exponent) > 6 or abs(int(exponent_text)) > 100000:
        raise ValueError("decimal exponent exceeds limit")
    return value


def validate_integer(value):
    if type(value) is not str or not INTEGER.fullmatch(value):
        raise ValueError("invalid tagged integer")
    return value


def _scientific_key(value):
    validate_decimal(value)
    parts = re.split("[eE]", value)
    coefficient = parts[0]
    exponent = int(parts[1]) if len(parts) == 2 else 0
    negative = coefficient.startswith("-")
    coefficient = coefficient.lstrip("-")
    if "." in coefficient:
        exponent -= len(coefficient.split(".")[1])
    digits = coefficient.replace(".", "").lstrip("0")
    if not digits:
        return (False, "0", 0)
    stripped = digits.rstrip("0")
    exponent += len(digits) - len(stripped)
    return (negative, stripped, exponent)


def scientific_equal(a, b):
    """Exact decimal equality; never rewrites wire precision or authorizes a merge."""
    return _scientific_key(a) == _scientific_key(b)
