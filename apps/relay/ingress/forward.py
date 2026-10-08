"""Fixed-target TLS TCP passthrough; no credentials or dynamic target."""

import asyncio
import json
import time

MAX_CONNECTIONS = 64
BUFFER = 16384
active = 0


async def copy(reader, writer, direction, evidence):
    while True:
        evidence[direction + "_phase"] = "read"
        data = await asyncio.wait_for(reader.read(BUFFER), timeout=5)
        if not data:
            evidence[direction + "_phase"] = "read_eof"
            return
        evidence[direction + "_bytes"] += len(data)
        evidence[direction + "_phase"] = "write"
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=5)


def report(reason, evidence, started):
    # Fixed fields only. Never serialize exceptions, addresses or stream bytes.
    print(
        json.dumps(
            {
                "event": "ingress_close",
                "reason": reason,
                "elapsed_ms": int((time.monotonic() - started) * 1000),
                "time_ms": time.time_ns() // 1000000,
                "active": active,
                "client_to_upstream_bytes": evidence["client_to_upstream_bytes"],
                "upstream_to_client_bytes": evidence["upstream_to_client_bytes"],
            }
        ),
        flush=True,
    )


async def connection(reader, writer):
    global active
    started = time.monotonic()
    evidence = {"client_to_upstream_bytes": 0, "upstream_to_client_bytes": 0}
    if active >= MAX_CONNECTIONS:
        writer.close()
        report("capacity_rejected", evidence, started)
        return
    active += 1
    upstream = None
    phase, reason = "upstream_connect", "connection_cancelled"
    try:
        async with asyncio.timeout(30):
            remote, upstream = await asyncio.wait_for(
                asyncio.open_connection("researchhub-secure-relay", 8443, limit=BUFFER),
                timeout=3,
            )
            tasks = [
                asyncio.create_task(
                    copy(reader, upstream, "client_to_upstream", evidence)
                ),
                asyncio.create_task(
                    copy(remote, writer, "upstream_to_client", evidence)
                ),
            ]
            phase = "connection_lifetime"
            try:
                done, _pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for index, task in enumerate(tasks):
                    if task not in done:
                        continue
                    direction = ("client_to_upstream", "upstream_to_client")[index]
                    phase = direction + "_" + evidence[direction + "_phase"]
                    task.result()
                    reason = phase
                if len(done) > 1:
                    # Both EOFs observed in one wakeup; do not invent causal order.
                    reason = "multiple_directions_eof"
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except TimeoutError:
        reason = phase + "_timeout"
        return
    except Exception:  # noqa: BLE001 -- close failed connection; never retry or log contents
        reason = phase + "_error"
        return
    finally:
        active -= 1
        writer.close()
        if upstream:
            upstream.close()
        report(reason, evidence, started)


async def main():
    server = await asyncio.start_server(
        connection, "0.0.0.0", 8443, limit=BUFFER, backlog=64
    )
    async with server:
        await server.serve_forever()


asyncio.run(main())
