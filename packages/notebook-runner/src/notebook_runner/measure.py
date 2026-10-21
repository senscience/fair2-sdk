"""The data a notebook downloads, counted by a local proxy, per host.

The kernel gets HTTP_PROXY and HTTPS_PROXY pointing to a proxy on 127.0.0.1, and the processes it
starts inherit them: Python's HTTP clients (urllib, requests: mlcroissant, pandas...), DuckDB, pip,
curl and wget go through it. HTTPS goes through as an encrypted tunnel (CONNECT), so the proxy
counts the bytes received, TLS included, without reading them; plain HTTP is forwarded.

Clients that ignore the proxy variables aren't counted: aiohttp, without `trust_env=True` (so
fsspec's HTTP file system), and programs with their own network settings. If the environment
already has a proxy (HTTPS_PROXY...), the counting proxy goes through it.
"""

from __future__ import annotations

import asyncio
import collections
import dataclasses
import os
import threading
from urllib.parse import urlsplit

PROXY_VARIABLES = ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")
# Seconds to reach a host: a connection that never opens fails (502) instead of blocking a cell
# until its timeout.
CONNECT_TIMEOUT = 30


@dataclasses.dataclass(frozen=True)
class Downloads:
    total_bytes: int
    """Received through the proxy: the responses, TLS included for HTTPS."""
    by_host: dict[str, int]
    """Host -> bytes, the largest first: e.g. the data host, and pypi.org for the packages."""


class CountingProxy:
    """An HTTP proxy on 127.0.0.1, in a thread, counting the bytes received from each host."""

    def __init__(self):
        self._received: collections.Counter[str] = collections.Counter()
        self._lock = threading.Lock()
        self._upstream = _upstream_proxy()
        self._loop = asyncio.new_event_loop()
        started = threading.Event()

        def serve():
            asyncio.set_event_loop(self._loop)
            self._server = self._loop.run_until_complete(
                asyncio.start_server(self._handle, "127.0.0.1", 0)
            )
            self.port = self._server.sockets[0].getsockname()[1]
            started.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=serve, daemon=True)
        self._thread.start()
        started.wait()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def environment(self) -> dict[str, str]:
        """The environment variables that send a process's HTTP(S) traffic through the proxy."""
        return dict.fromkeys(PROXY_VARIABLES, self.url)

    def downloads(self) -> Downloads:
        with self._lock:
            by_host = dict(self._received.most_common())
        return Downloads(sum(by_host.values()), by_host)

    def close(self) -> None:
        def stop():
            self._server.close()
            self._loop.stop()

        self._loop.call_soon_threadsafe(stop)
        self._thread.join(timeout=5)

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            head = await reader.readuntil(b"\r\n\r\n")
            method, target, _ = head.split(b"\r\n", 1)[0].decode("latin-1").split(" ", 2)
            if method == "CONNECT":  # HTTPS: a tunnel to host:port
                host, port = target.rsplit(":", 1)
                upstream = await self._open(host, int(port), head)
                writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
                await writer.drain()
            else:  # plain HTTP: the request line has the absolute URL
                url = urlsplit(target)
                host = url.hostname or ""
                upstream = await self._open(host, url.port or 80, None)
                if self._upstream:  # the upstream proxy takes the absolute URL
                    upstream[1].write(head)
                else:
                    path = (url.path or "/") + (f"?{url.query}" if url.query else "")
                    upstream[1].write(head.replace(target.encode(), path.encode(), 1))
                await upstream[1].drain()
        except (
            OSError,
            ValueError,
            TimeoutError,
            asyncio.IncompleteReadError,
            asyncio.LimitOverrunError,
        ):
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            writer.close()
            return
        up_reader, up_writer = upstream
        await asyncio.gather(self._pipe(reader, up_writer), self._pipe(up_reader, writer, host))

    async def _open(self, host: str, port: int, connect: bytes | None):
        """A connection to host:port, through the upstream proxy if there is one."""
        async with asyncio.timeout(CONNECT_TIMEOUT):
            return await self._connect(host, port, connect)

    async def _connect(self, host: str, port: int, connect: bytes | None):
        if not self._upstream:
            return await asyncio.open_connection(host, port)
        reader, writer = await asyncio.open_connection(*self._upstream)
        if connect:  # tunnel through the upstream proxy
            writer.write(connect)
            await writer.drain()
            status = await reader.readuntil(b"\r\n\r\n")
            if b" 200 " not in status.split(b"\r\n", 1)[0]:
                raise OSError(f"upstream proxy refused {host}:{port}")
        return reader, writer

    async def _pipe(self, reader, writer, host: str | None = None) -> None:
        try:
            while data := await reader.read(65536):
                if host is not None:
                    with self._lock:
                        self._received[host] += len(data)
                writer.write(data)
                await writer.drain()
        except (OSError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()


def _upstream_proxy() -> tuple[str, int] | None:
    """The proxy the environment already uses, if any: (host, port)."""
    for variable in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        if value := os.environ.get(variable):
            url = urlsplit(value if "://" in value else f"http://{value}")
            if url.hostname:
                return url.hostname, url.port or 80
    return None
