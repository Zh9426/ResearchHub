"""Fixed-target TLS TCP passthrough; no credentials or dynamic target."""

import asyncio

MAX_CONNECTIONS = 64
BUFFER = 16384
active = 0


async def copy(reader, writer):
    while True:
        data = await asyncio.wait_for(reader.read(BUFFER), timeout=5)
        if not data:
            return
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=5)


async def connection(reader, writer):
    global active
    if active >= MAX_CONNECTIONS:
        writer.close()
        return
    active += 1
    upstream = None
    try:
        async with asyncio.timeout(30):
            remote, upstream = await asyncio.wait_for(
                asyncio.open_connection("researchhub-secure-relay", 8443, limit=BUFFER),
                timeout=3,
            )
            tasks = [
                asyncio.create_task(copy(reader, upstream)),
                asyncio.create_task(copy(remote, writer)),
            ]
            try:
                done, _pending = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    task.result()
            finally:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
    except Exception:  # noqa: BLE001 -- network boundary never logs stream contents
        return
    finally:
        active -= 1
        writer.close()
        if upstream:
            upstream.close()


async def main():
    server = await asyncio.start_server(
        connection, "0.0.0.0", 8443, limit=BUFFER, backlog=64
    )
    async with server:
        await server.serve_forever()


asyncio.run(main())
