"""HTTPS-only container entrypoint, bounded ingress and allowlist errors."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool

from packages.secure_wire.canonical import canonical_bytes, strict_loads
from packages.secure_wire.request import POST_PATHS, decode_proof, validate_query

from .qa import connect
from .service import charge, error_code, execute, initialize

logging.getLogger("sqlalchemy.engine").disabled = True


@asynccontextmanager
async def lifespan(app):
    app.state.engine = connect()
    initialize(app.state.engine)
    yield
    app.state.engine.dispose()


app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
    redirect_slashes=False,
)


def failure(code, status=400):
    return Response(
        canonical_bytes({"ok": False, "code": code}),
        status_code=status,
        media_type="application/json",
    )


@app.middleware("http")
async def browser_cors(request, call_next):
    """Only the isolated browser. Preflight has no access to business state."""
    origins = [v for k, v in request.scope["headers"] if k.lower() == b"origin"]
    allowed = origins == [b"http://127.0.0.1:3314"]
    if origins and not allowed:
        return failure("ORIGIN_REJECTED", 403)
    if request.method == "OPTIONS":
        method = request.headers.get("access-control-request-method")
        headers = {h.strip().lower() for h in request.headers.get("access-control-request-headers", "").split(",") if h.strip()}
        if not allowed or method not in ("GET", "POST") or not headers <= {"content-type", "x-rh-proof"}:
            return failure("ORIGIN_REJECTED", 403)
        response = Response(status_code=204, headers={
            "Access-Control-Allow-Methods": "GET, POST",
            "Access-Control-Allow-Headers": "content-type, x-rh-proof",
        })
    else:
        response = await call_next(request)
    if allowed:
        response.headers["Access-Control-Allow-Origin"] = "http://127.0.0.1:3314"
        response.headers["Vary"] = "Origin"
    return response


@app.api_route(
    "/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"]
)
async def endpoint(request: Request, path: str):
    proof = None
    try:
        # A single global persistent bucket is charged even for unknown identity.
        headers = request.scope["headers"]
        if sum(len(k) + len(v) for k, v in headers) > 16384:
            await run_in_threadpool(charge, request.app.state.engine)
            return failure("AUTH_REJECTED", 401)
        proofs = [v for k, v in headers if k.lower() == b"x-rh-proof"]
        try:
            if len(proofs) != 1:
                raise ValueError()
            proof = decode_proof(proofs[0].decode("ascii"))
        except (ValueError, UnicodeError):
            await run_in_threadpool(charge, request.app.state.engine)
            return failure("AUTH_REJECTED", 401)
        await run_in_threadpool(charge, request.app.state.engine, proof)
        raw_path = request.scope["raw_path"]
        path = "/" + path
        method = request.method
        if raw_path != path.encode("ascii"):
            return failure("AUTH_REJECTED", 401)
        if method == "GET":
            query = validate_query(path, request.scope["query_string"])
        elif (
            method == "POST"
            and path in POST_PATHS
            and not request.scope["query_string"]
        ):
            query = {}
        else:
            return failure("AUTH_REJECTED", 401)
        for header in (b"content-length", b"content-type", b"transfer-encoding"):
            if sum(k.lower() == header for k, v in headers) > 1:
                return failure("AUTH_REJECTED", 401)
        raw = bytearray()
        async with asyncio.timeout(8):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > 524288:
                    return failure("REQUEST_TOO_LARGE", 413)
                raw.extend(chunk)
        body = bytes(raw)
        if method == "GET" and body:
            return failure("AUTH_REJECTED", 401)
        if method == "POST" and (
            request.headers.get("content-type") != "application/json"
            or not body
            or canonical_bytes(strict_loads(body)) != body
        ):
            return failure("AUTH_REJECTED", 401)
        result = await run_in_threadpool(
            execute, request.app.state.engine, proof, method, path, query, body
        )
        value = strict_loads(result)
        return Response(
            result,
            status_code=200 if value["ok"] else 400,
            media_type="application/json",
        )
    except TimeoutError:
        return failure("TIMEOUT", 408)
    except ValueError as exc:
        code = error_code(exc)
        if code in ("INVALID_REQUEST", "INVALID_QUERY", "INVALID_SIGNATURE"):
            code = "AUTH_REJECTED"
        return failure(
            code,
            429 if code == "RATE_LIMITED" else 401 if code == "AUTH_REJECTED" else 400,
        )
    except Exception:  # noqa: BLE001 -- external API boundary deliberately sanitizes all failures
        # No body, stack, SQL, key, URL or exception message leaves this boundary.
        return failure("SERVICE_UNAVAILABLE", 503)
