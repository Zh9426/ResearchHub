"""Unit boundary inputs only; actual TLS service evidence lives in transport tests."""

import httpx
import pytest


def test_stream_reader_rejects_overflow_without_consuming_remainder():
    from researchhub.sync.secure import transport

    assert callable(getattr(transport, "read_response", None)), (
        "bounded response reader missing"
    )
    consumed = []

    class Input(httpx.SyncByteStream):
        def __iter__(self):
            for i in range(10):
                consumed.append(i)
                yield b"x" * 65536

    response = httpx.Response(200, stream=Input())
    try:
        with pytest.raises(ValueError, match="RESPONSE_TOO_LARGE"):
            transport.read_response(response)
    finally:
        response.close()
    assert len(consumed) == 9


def test_direct_page_bound_precedes_database_access():
    from researchhub.sync.secure.receiver import receive

    page = {
        "rows": [{"envelope": "x" * 524289}],
        "cursor": 1,
        "chain_digest": "0" * 64,
        "has_more": False,
    }
    with pytest.raises(ValueError, match="RESPONSE_TOO_LARGE"):
        receive(None, "unused", None, {}, page, 0)


def test_stream_reader_ignores_lying_length_and_rejects_compression():
    from researchhub.sync.secure import transport

    assert callable(getattr(transport, "read_response", None)), (
        "bounded response reader missing"
    )

    class Input(httpx.SyncByteStream):
        def __iter__(self):
            yield b"x" * 524289

    response = httpx.Response(200, headers={"content-length": "1"}, stream=Input())
    try:
        with pytest.raises(ValueError, match="RESPONSE_TOO_LARGE"):
            transport.read_response(response)
    finally:
        response.close()
    compressed = httpx.Response(
        200, headers={"content-encoding": "gzip"}, stream=Input()
    )
    try:
        with pytest.raises(ValueError, match="UNSUPPORTED_CONTENT_ENCODING"):
            transport.read_response(compressed)
    finally:
        compressed.close()


def test_real_httpx_slow_drip_checks_each_raw_transport_read(monkeypatch):
    from researchhub.sync.secure import transport_bounds

    clock, consumed = [0.0], []

    class Drip(httpx.SyncByteStream):
        def __iter__(self):
            for n in range(100):
                clock[0] += 6
                consumed.append(n)
                yield b"x"

    monkeypatch.setattr(transport_bounds.time, "monotonic", lambda: clock[0])
    response = httpx.Response(200, stream=Drip())
    try:
        with pytest.raises(ValueError, match="RESPONSE_TIMEOUT"):
            transport_bounds.read_response(response)
        assert len(consumed) == 3
        assert clock[0] == 18
    finally:
        response.close()


def test_real_httpx_delayed_empty_eof_also_checks_deadline(monkeypatch):
    from researchhub.sync.secure import transport_bounds

    clock = [0.0]

    class Empty(httpx.SyncByteStream):
        def __iter__(self):
            clock[0] = 16
            yield from ()

    monkeypatch.setattr(transport_bounds.time, "monotonic", lambda: clock[0])
    response = httpx.Response(200, stream=Empty())
    try:
        with pytest.raises(ValueError, match="RESPONSE_TIMEOUT"):
            transport_bounds.read_response(response)
    finally:
        response.close()
