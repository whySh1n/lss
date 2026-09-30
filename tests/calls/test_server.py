import asyncio
import pytest
import pytest_asyncio
from aiohttp import WSMsgType
from linuxshare_calls.server import Config, make_app, ROOMS, end

pytestmark = pytest.mark.asyncio
KEY = "test-creation-key-" + "x" * 32


@pytest_asyncio.fixture
async def service(aiohttp_client):
    config = Config("http://127.0.0.1:1", KEY, development=True)
    app = make_app(config)
    client = await aiohttp_client(app)
    config.origin = str(client.make_url("/")).rstrip("/")
    client.session.headers["Origin"] = config.origin
    yield client, app


async def create(client):
    response = await client.post(
        "/api/create", headers={"Authorization": "Bearer " + KEY}, json={}
    )
    assert response.status == 200
    return await response.json()


async def attach(client, data, role, token=None):
    ws = await client.ws_connect("/ws")
    await ws.send_json(
        {"room": data["room"], "role": role, "token": token or data["token"]}
    )
    hello = await ws.receive_json(timeout=2)
    assert hello["type"] == "hello"
    return ws


async def pair(client):
    data = await create(client)
    host = await attach(client, data, "host")
    response = await client.post(
        "/api/join",
        json={
            "room": data["room"],
            "invitation": data["invitation"],
            "name": "<script>not markup</script>",
        },
    )
    guest_data = await response.json()
    guest = await attach(client, guest_data, "guest")
    assert (await host.receive_json(timeout=2))["type"] == "waiting"
    return data, host, guest, guest_data


async def approve(host, guest):
    await host.send_json({"type": "approve"})
    assert (await host.receive_json(timeout=2))["type"] == "approved"
    assert (await guest.receive_json(timeout=2))["type"] == "approved"
    await host.send_json({"type": "ready"})
    await guest.send_json({"type": "ready"})
    assert (await host.receive_json(timeout=2))["type"] == "negotiate"


async def test_no_creation_without_key_or_with_bad_origin(service):
    client, _ = service
    assert (await client.post("/api/create", json={})).status == 403
    assert (
        await client.post(
            "/api/create",
            headers={
                "Origin": "https://evil.example",
                "Authorization": "Bearer " + KEY,
            },
            json={},
        )
    ).status == 403
    assert (await client.get("/", headers={"Host": "evil.example"})).status == 403


async def test_headers_assets_and_no_remote_scripts(service):
    client, _ = service
    response = await client.get("/")
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert (await client.get("/assets/server.py")).status == 404
    assert (await client.get("/assets/app.js")).status == 200


async def test_two_roles_signal_only_after_approval_and_readiness(service):
    client, _ = service
    data, host, guest, _ = await pair(client)
    await approve(host, guest)
    await host.send_json({"type": "offer", "sdp": "test-offer", "ignored": "secret"})
    assert await guest.receive_json(timeout=2) == {"type": "offer", "sdp": "test-offer"}
    await guest.send_json({"type": "answer", "sdp": "test-answer"})
    assert await host.receive_json(timeout=2) == {
        "type": "answer",
        "sdp": "test-answer",
    }
    await host.send_json({"type": "end"})
    assert (await guest.receive_json(timeout=2))["type"] == "ended"


async def test_unapproved_guest_cannot_signal(service):
    client, app = service
    data, host, guest, _ = await pair(client)
    await guest.send_json({"type": "offer", "sdp": "attack"})
    await guest.receive(timeout=2)
    await asyncio.sleep(0.05)
    assert data["room"] not in app[ROOMS].items
    await host.close()


async def test_guest_cannot_approve_themselves(service):
    client, app = service
    data, host, guest, _ = await pair(client)
    await guest.send_json({"type": "approve"})
    await guest.receive(timeout=2)
    await asyncio.sleep(0.05)
    assert data["room"] not in app[ROOMS].items
    await host.close()


async def test_end_revokes_tokens_and_link_before_closing_sockets(service):
    client, app = service
    data, host, guest, guest_data = await pair(client)
    response = await client.post(
        "/api/end", json={"room": data["room"], "token": data["token"]}
    )
    assert response.status == 200
    assert data["room"] not in app[ROOMS].items
    replay = await client.post(
        "/api/join",
        json={"room": data["room"], "invitation": data["invitation"], "name": "Replay"},
    )
    assert replay.status == 403
    retry = await client.ws_connect("/ws")
    await retry.send_json(
        {"room": data["room"], "role": "guest", "token": guest_data["token"]}
    )
    assert (await retry.receive(timeout=2)).type == WSMsgType.CLOSE
    await host.close()
    await guest.close()


async def test_duplicate_host_cannot_kick_original(service):
    client, app = service
    data = await create(client)
    host = await attach(client, data, "host")
    second = await client.ws_connect("/ws")
    await second.send_json(
        {"room": data["room"], "role": "host", "token": data["token"]}
    )
    assert (await second.receive(timeout=2)).type == WSMsgType.CLOSE
    assert data["room"] in app[ROOMS].items
    await host.send_json({"type": "ping"})
    assert (await host.receive_json(timeout=2))["type"] == "lease"
    await host.close()


async def test_host_disconnect_ends_guest_and_prevents_reconnect(service):
    client, app = service
    data, host, guest, _ = await pair(client)
    await host.close()
    assert (await guest.receive_json(timeout=2))["type"] == "ended"
    assert data["room"] not in app[ROOMS].items


async def test_invalid_guest_end_token_cannot_revoke_host(service):
    client, app = service
    data, host, guest, guest_data = await pair(client)
    response = await client.post(
        "/api/end", json={"room": data["room"], "token": guest_data["token"]}
    )
    assert response.status == 403
    assert data["room"] in app[ROOMS].items
    await host.close()
    await guest.close()


async def test_expiry_closes_existing_sockets(service):
    client, app = service
    data, host, guest, _ = await pair(client)
    room = app[ROOMS].items[data["room"]]
    room.end_at = 0
    assert (await guest.receive_json(timeout=3))["type"] == "ended"
    assert data["room"] not in app[ROOMS].items
    await host.close()


async def test_restart_cleanup_invalidates_rooms(service):
    client, app = service
    data = await create(client)
    host = await attach(client, data, "host")
    await end(app, app[ROOMS].items[data["room"]], "Service stopping")
    assert (await host.receive_json(timeout=2))["type"] == "ended"
    assert not app[ROOMS].items
