"""
The MIT License (MIT)

Copyright (c) 2021-present Village

Permission is hereby granted, free of charge, to any person obtaining a
copy of this software and associated documentation files (the "Software"),
to deal in the Software without restriction, including without limitation
the rights to use, copy, modify, merge, publish, distribute, sublicense,
and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS
OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
DEALINGS IN THE SOFTWARE.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import pathlib
import ssl
import traceback
from typing import Any, Callable, Coroutine, Set

import aiohttp
from aiohttp import web
from socket_ import Socket

__all__ = ("Server",)

_log = logging.getLogger(__name__)


def wrap_send(
    coro: Callable[..., Coroutine[Any, Any, Any]]
) -> Callable[..., Coroutine[Any, Any, Any]]:
    async def predicate(data: Any):
        try:
            await coro(data)
        except ConnectionResetError:
            pass

    return predicate


class Server:
    def __init__(self, secret: str, loop: asyncio.AbstractEventLoop, port: int = 9093):
        self.secret: str = secret
        self.websockets: Set[web.WebSocketResponse] = set()
        self.sockets: Set[Socket] = set()
        self.loop: asyncio.AbstractEventLoop = loop
        self.port: int = port
        self.server: web.Application
        self.runner: web.AppRunner
        self.site: web.TCPSite

    async def ws_handler(self, req: web.Request) -> None:
        websocket = web.WebSocketResponse(max_msg_size=0, timeout=300)
        await websocket.prepare(req)
        socket = None
        self.websockets.add(websocket)
        async for message in websocket:
            try:
                if message.type == aiohttp.WSMsgType.CLOSE:  # type: ignore
                    if socket is not None:
                        self.sockets.remove(socket)
                    return
                elif message.type == aiohttp.WSMsgType.TEXT:  # type: ignore
                    try:
                        data = message.json()
                    except json.JSONDecodeError:
                        await websocket.send_json(
                            {"success": False, "error": "Invalid JSON."}
                        )
                        continue
                    channels = data.get("channels", [])
                    channels_set = set(channels)
                    if not channels:
                        await websocket.send_json(
                            {"success": False, "error": "No channels provided."}
                        )
                        continue
                    if not isinstance(channels, list):
                        await websocket.send_json(
                            {"success": False, "error": "Channels must be an array."}
                        )
                        continue
                    if socket is None:
                        socket = Socket.from_websocket(websocket, channels_set)
                        self.sockets.add(socket)
                    else:
                        socket.channels = channels_set
                    await websocket.send_json(
                        {"success": True, "channels": list(set(channels_set))}
                    )
            except Exception as error:
                f = io.StringIO()
                f.write("Ignoring exception in websocket:\n")
                traceback.print_exception(
                    type(error), error, error.__traceback__, file=f
                )
                _log.warning(f.getvalue())

    async def send_handler(self, req: web.Request) -> web.Response:
        if req.headers.get("Authorization") != self.secret:
            raise web.HTTPUnauthorized()
        data = await req.json()
        if "channels" not in data or "event" not in data:
            raise web.HTTPBadRequest()
        if not data["channels"] or not data["event"]:
            raise web.HTTPBadRequest()
        self.loop.create_task(self.send_channels(set(data["channels"]), data["event"]))
        raise web.HTTPCreated()

    async def start_coro(self) -> None:
        self.runner = web.AppRunner(self.server)
        await self.runner.setup()
        cert_path = pathlib.Path(__file__).parent.parent / "cert.pem"
        key_path = pathlib.Path(__file__).parent.parent / "key.pem"
        if cert_path.is_file() and key_path.is_file():
            ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
            ssl_context.load_cert_chain(cert_path, key_path)
        else:
            ssl_context = None
        self.site = web.TCPSite(
            self.runner,
            port=self.port,
            ssl_context=ssl_context,
        )
        await self.site.start()

    def start(self) -> None:
        self.server = web.Application()
        self.server.add_routes(
            [web.post("/v1/send", self.send_handler), web.get("/v1/ws", self.ws_handler)]  # type: ignore
        )
        self.loop.create_task(self.start_coro())

    async def send_channels(self, channels: Set[str], event: dict[str, Any]) -> None:
        coros = [
            socket.send(event) for socket in self.sockets if channels & socket.channels
        ]
        await asyncio.gather(*coros, return_exceptions=True)
