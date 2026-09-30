"""Single-process HTTPS-proxied signaling; never receives screen/audio media."""

import argparse
import asyncio
import base64
from collections import defaultdict, deque
from dataclasses import dataclass
import hashlib
import hmac
from importlib.resources import files
import json
import os
import time
from urllib.parse import urlsplit

from aiohttp import web, WSMsgType

from .state import Denied, Rooms, digest, matches


@dataclass
class Config:
    origin: str
    create_key: str
    development: bool = False
    invite_seconds: int = 120
    call_seconds: int = 3600
    turn_urls: tuple = ()
    turn_secret: str = ""
    relay_only: bool = True

    def validate(self):
        parsed = urlsplit(self.origin)
        if (
            parsed.path
            or parsed.query
            or parsed.fragment
            or parsed.username
            or not parsed.hostname
            or parsed.password
        ):
            raise ValueError("Origin must contain only scheme, host and optional port")
        local = parsed.hostname in ("127.0.0.1", "localhost", "::1")
        if parsed.scheme != "https" and not (
            self.development and local and parsed.scheme == "http"
        ):
            raise ValueError("HTTPS is required; HTTP development is loopback-only")
        if len(self.create_key) < 32 or len(self.create_key) > 128:
            raise ValueError(
                "Set a randomly generated creation key of 32–128 characters"
            )
        if not 10 <= self.invite_seconds <= 600 or not 30 <= self.call_seconds <= 14400:
            raise ValueError("Invite/session lifetime out of range")
        if not self.development and (not self.turn_urls or len(self.turn_secret) < 32):
            raise ValueError(
                "Production requires private TURN URLs and a strong shared secret"
            )
        if any(not url.startswith(("turn:", "turns:")) for url in self.turn_urls):
            raise ValueError("Only TURN URLs are supported")
        if self.turn_urls and len(self.turn_secret) < 32:
            raise ValueError("TURN secret is required")
        return self

    def ice(self, room, role):
        if not self.turn_urls:
            return {"iceServers": [], "iceTransportPolicy": "all"}
        # coturn REST credentials expire at the maximum remaining session lifetime.
        remaining = max(1, int(room.end_at - time.monotonic()))
        username = f"{int(time.time()) + remaining + 30}:{room.id}:{role}"
        credential = base64.b64encode(
            hmac.new(
                self.turn_secret.encode(), username.encode(), hashlib.sha1
            ).digest()
        ).decode()
        return {
            "iceServers": [
                {
                    "urls": list(self.turn_urls),
                    "username": username,
                    "credential": credential,
                }
            ],
            "iceTransportPolicy": "relay" if self.relay_only else "all",
        }


class Limit:
    def __init__(self):
        self.hits = defaultdict(deque)

    def allow(self, key, maximum=60, window=60):
        now = time.monotonic()
        # Bound buckets as well as requests. Do not retain IP addresses indefinitely.
        for old in list(self.hits):
            if not self.hits[old] or self.hits[old][-1] < now - 60:
                del self.hits[old]
        if key not in self.hits and len(self.hits) >= 1024:
            return False
        queue = self.hits[key]
        while queue and queue[0] <= now - window:
            queue.popleft()
        if len(queue) >= maximum:
            return False
        queue.append(now)
        return True


CONFIG = web.AppKey("config", Config)
ROOMS = web.AppKey("rooms", Rooms)
LIMIT = web.AppKey("limit", Limit)
AUTH = web.AppKey("create_digest", bytes)
CLOSERS = web.AppKey("closing_tasks", set)


@web.middleware
async def security(request, handler):
    config = request.app[CONFIG]
    if request.host != urlsplit(config.origin).netloc:
        raise web.HTTPForbidden(text="Invalid host")
    if request.path.startswith(("/api/", "/ws")):
        if request.headers.get("Origin") != config.origin:
            raise web.HTTPForbidden(text="Invalid origin")
        if not request.app[LIMIT].allow(request.remote or "unknown"):
            raise web.HTTPTooManyRequests(text="Try again later")
    try:
        response = await handler(request)
    except Denied:
        response = web.json_response(
            {"error": "Session unavailable or request denied"}, status=403
        )
    except (json.JSONDecodeError, TypeError, KeyError, ValueError):
        response = web.json_response({"error": "Invalid request"}, status=400)
    return response


async def headers(request, response):
    response.headers.update(
        {
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Permissions-Policy": "camera=(), microphone=(self), display-capture=(self)",
            "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; media-src 'self' blob:; img-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
        }
    )
    if not request.app[CONFIG].development:
        response.headers["Strict-Transport-Security"] = "max-age=31536000"


async def page(request):
    name = request.match_info.get("name", "index.html")
    mime = {
        "index.html": "text/html",
        "app.js": "application/javascript",
        "style.css": "text/css",
    }
    if name not in mime:
        raise web.HTTPNotFound()
    return web.Response(
        body=files("linuxshare_calls").joinpath("static", name).read_bytes(),
        content_type=mime[name],
    )


async def create(request):
    token = request.headers.get("Authorization", "").removeprefix("Bearer ")
    if not matches(token, request.app[AUTH]):
        raise Denied("Unavailable")
    if not request.app[LIMIT].allow("create", maximum=10):
        raise web.HTTPTooManyRequests()
    room, host, invite = request.app[ROOMS].create()
    return web.json_response(
        {
            "room": room.id,
            "token": host,
            "invitation": invite,
            "inviteSeconds": request.app[CONFIG].invite_seconds,
        }
    )


async def join(request):
    data = await request.json()
    room, key = request.app[ROOMS].join(data["room"], data["invitation"], data["name"])
    return web.json_response({"room": room.id, "token": key, "code": room.check_code})


async def end(app, room, reason="Call ended; invitation revoked"):
    if app[ROOMS].items.get(room.id) is not room:
        return
    app[ROOMS].remove(room)  # Revoke authority before awaiting network I/O.

    async def close(peer):
        if peer and peer.socket is not None:
            try:
                await asyncio.wait_for(
                    peer.socket.send_json({"type": "ended", "reason": reason}), 1
                )
                await asyncio.wait_for(peer.socket.close(), 1)
            except (ConnectionError, RuntimeError, asyncio.TimeoutError):
                pass  # Already disconnected; room credentials are revoked.

    async def notify_all():
        await asyncio.gather(close(room.host), close(room.guest))

    # The disconnected request task can be cancelled by aiohttp. Closing the
    # OTHER peer must survive that cancellation, with a strong task reference.
    task = asyncio.create_task(notify_all())
    app[CLOSERS].add(task)
    task.add_done_callback(app[CLOSERS].discard)
    await asyncio.shield(task)


async def revoke(request):
    data = await request.json()
    room, _ = request.app[ROOMS].authenticate(data["room"], "host", data["token"])
    await end(request.app, room)
    return web.json_response({"ended": True})


async def send(peer, data):
    if peer and peer.socket is not None and not peer.socket.closed:
        await peer.socket.send_json(data)


async def handle(app, room, role, message):
    store = app[ROOMS]
    store.get(room.id)
    peer = room.peer(role)
    kind = message.get("type")
    if kind == "ping":
        peer.last_seen = store.clock()
        await send(peer, {"type": "lease", "seconds": 10})
    elif kind == "end":
        await end(app, room)
    elif kind == "approve" and role == "host":
        store.approve(room)
        for target in (room.host, room.guest):
            await send(target, {"type": "approved"})
    elif kind == "ready":
        if store.ready(room, role):
            await send(room.host, {"type": "negotiate"})
    elif kind in ("offer", "answer", "ice"):
        if not room.approved or not room.negotiating:
            raise Denied("Not approved")
        if kind == "offer":
            if role != "host" or room.offered:
                raise Denied("Invalid offer")
            validate_sdp(message)
            room.offered = True
        elif kind == "answer":
            if role != "guest" or not room.offered or room.answered:
                raise Denied("Invalid answer")
            validate_sdp(message)
            room.answered = True
        else:
            room.candidates[role] += 1
            candidate = message.get("candidate")
            if (
                room.candidates[role] > 256
                or not isinstance(candidate, dict)
                or len(json.dumps(candidate)) > 4096
            ):
                raise Denied("Invalid candidate")
        other = room.guest if role == "host" else room.host
        # Forward only protocol fields, never arbitrary message properties.
        data = {"type": kind}
        data["candidate" if kind == "ice" else "sdp"] = message[
            "candidate" if kind == "ice" else "sdp"
        ]
        await send(other, data)
    else:
        raise Denied("Invalid message")


def validate_sdp(message):
    value = message.get("sdp")
    if not isinstance(value, str) or not 1 <= len(value) <= 60000:
        raise Denied("Invalid SDP")


async def socket(request):
    if not request.app[LIMIT].allow("websocket-global", maximum=120):
        raise web.HTTPTooManyRequests()
    ws = web.WebSocketResponse(
        heartbeat=5, max_msg_size=65536, compress=False, timeout=1
    )
    await ws.prepare(request)
    room = None
    try:
        data = await ws.receive_json(timeout=5)
        room, peer = request.app[ROOMS].attach(
            data["room"], data["role"], data["token"], ws
        )
        role = data["role"]
        await ws.send_json(
            {
                "type": "hello",
                "role": role,
                "development": request.app[CONFIG].development,
                "ice": request.app[CONFIG].ice(room, role),
                "leaseSeconds": 10,
                "callSeconds": max(1, int(room.end_at - time.monotonic())),
            }
        )
        if role == "guest" or room.guest:
            await send(
                room.host,
                {"type": "waiting", "name": room.guest_name, "code": room.check_code},
            )
        async for message in ws:
            if message.type != WSMsgType.TEXT:
                break
            if not request.app[LIMIT].allow(
                f"{room.id}:{role}", maximum=300, window=60
            ):
                raise Denied("Rate limited")
            data = json.loads(message.data)
            if not isinstance(data, dict):
                raise Denied("Invalid message")
            await handle(request.app, room, role, data)
    except (
        Denied,
        ValueError,
        TypeError,
        KeyError,
        asyncio.TimeoutError,
        ConnectionError,
    ):
        await ws.close(code=1008, message=b"Session unavailable")
    finally:
        if room is not None:
            await end(request.app, room, "Connection ended; start a new call")
    return ws


async def shutdown(app):
    await asyncio.gather(
        *(
            end(app, room, "Service stopped; access revoked")
            for room in list(app[ROOMS].items.values())
        )
    )
    if app[CLOSERS]:
        await asyncio.gather(*list(app[CLOSERS]), return_exceptions=True)


async def lifecycle(app):
    async def sweep():
        while True:
            await asyncio.sleep(1)
            for room in list(app[ROOMS].items.values()):
                if app[ROOMS].expired(room):
                    await end(app, room, "Session expired; invitation revoked")

    task = asyncio.create_task(sweep())
    yield
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await asyncio.gather(*(end(app, room) for room in list(app[ROOMS].items.values())))


def make_app(config):
    config.validate()
    app = web.Application(middlewares=[security], client_max_size=8192)
    app[CONFIG], app[AUTH] = config, digest(config.create_key)
    app[ROOMS], app[LIMIT] = Rooms(config.invite_seconds, config.call_seconds), Limit()
    app[CLOSERS] = set()
    app.router.add_get("/", page)
    app.router.add_get("/assets/{name}", page)
    app.router.add_post("/api/create", create)
    app.router.add_post("/api/join", join)
    app.router.add_post("/api/end", revoke)
    app.router.add_get("/ws", socket)
    app.on_response_prepare.append(headers)
    app.on_shutdown.append(shutdown)
    app.cleanup_ctx.append(lifecycle)
    return app


def main():
    parser = argparse.ArgumentParser(
        description="LinuxShare private-call signaling service"
    )
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument(
        "--dev", action="store_true", help="loopback-only local testing"
    )
    args = parser.parse_args()
    origin = os.environ.get(
        "LINUXSHARE_ORIGIN", f"http://127.0.0.1:{args.port}" if args.dev else ""
    )
    key = os.environ.get("LINUXSHARE_CREATE_KEY", "")
    config = Config(
        origin,
        key,
        development=args.dev,
        turn_urls=tuple(
            filter(None, os.environ.get("LINUXSHARE_TURN_URLS", "").split(","))
        ),
        turn_secret=os.environ.get("LINUXSHARE_TURN_SECRET", ""),
    )
    try:
        app = make_app(config)
    except ValueError as exc:
        parser.error(str(exc))
    web.run_app(app, host="127.0.0.1", port=args.port, access_log=None, print=None)


if __name__ == "__main__":
    main()
