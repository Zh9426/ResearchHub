"""Bound hostile transport input before JSON parsing and trusted PG access."""

import time

from packages.secure_wire.canonical import canonical_bytes

MAX_RESPONSE = 524288


def bounded_canonical(value):
    # Cheap lower bound limits traversed nodes/strings before canonical encoding.
    # Exact encoded budget is checked afterward (escaping/UTF-8 can expand it).
    remaining = MAX_RESPONSE

    def visit(item, depth=0):
        nonlocal remaining
        if depth > 64:
            raise ValueError("INVALID_PAGE_DEPTH")
        remaining -= len(item) if type(item) is str else 1
        if remaining < 0:
            raise ValueError("RESPONSE_TOO_LARGE")
        if type(item) is dict:
            for key, child in item.items():
                visit(key, depth + 1)
                visit(child, depth + 1)
        elif type(item) is list:
            for child in item:
                visit(child, depth + 1)

    visit(value)
    raw = canonical_bytes(value)
    if len(raw) > MAX_RESPONSE:
        raise ValueError("RESPONSE_TOO_LARGE")
    return raw


def read_response(response):
    if response.headers.get("content-encoding", "identity") != "identity":
        raise ValueError("UNSUPPORTED_CONTENT_ENCODING")
    raw = bytearray()
    deadline = time.monotonic() + 15
    # Do not request a chunk_size: httpx would aggregate slow tiny reads before
    # yielding, preventing our deadline check from seeing their elapsed time.
    for chunk in response.iter_raw():
        if time.monotonic() > deadline:
            raise ValueError("RESPONSE_TIMEOUT")
        if len(raw) + len(chunk) > MAX_RESPONSE:
            raise ValueError("RESPONSE_TOO_LARGE")
        raw.extend(chunk)
    if time.monotonic() > deadline:
        raise ValueError("RESPONSE_TIMEOUT")
    return bytes(raw)
