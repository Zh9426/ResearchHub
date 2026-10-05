"""Bound request bodies before the framework parses/spools multipart files."""

import os
import tempfile

from starlette.responses import JSONResponse


class BodyLimitMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PATCH", "PUT"):
            return await self.app(scope, receive, send)
        upload = scope["path"].endswith("/artifacts") and scope["method"] == "POST"
        limit = (
            int(os.getenv("MAX_UPLOAD_BYTES", "52428800")) + 1048576
            if upload
            else 1048576
        )
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse(
                {"detail": "Invalid content length"}, status_code=400
            )(scope, receive, send)
        if length > limit:
            return await JSONResponse(
                {"detail": "Request body exceeds configured limit"}, status_code=413
            )(scope, receive, send)
        with tempfile.SpooledTemporaryFile(max_size=1048576) as stream:
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                data = message.get("body", b"")
                size += len(data)
                if size > limit:
                    return await JSONResponse(
                        {"detail": "Request body exceeds configured limit"},
                        status_code=413,
                    )(scope, receive, send)
                stream.write(data)
                if not message.get("more_body", False):
                    break
            stream.seek(0)

            async def replay():
                chunk = stream.read(65536)
                return {
                    "type": "http.request",
                    "body": chunk,
                    "more_body": stream.tell() < size,
                }

            await self.app(scope, replay, send)
