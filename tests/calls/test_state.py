import pytest
from linuxshare_calls.state import Denied, Rooms, digest, matches
from linuxshare_calls.server import Config, Limit
from linuxshare_calls.launcher import service_url


def make():
    now = [100.0]
    store = Rooms(clock=lambda: now[0])
    room, host, invite = store.create()
    store.attach(room.id, "host", host, object())
    return now, store, room, host, invite


def test_tokens_are_random_separate_and_stored_as_digests():
    _, store, room, host, invite = make()
    assert host != invite and len(host) >= 43
    assert room.host.key == digest(host) and room.host.key != host
    assert room.invitation == digest(invite)
    assert store.create()[0].id != room.id


def test_single_use_invite_and_one_guest():
    _, store, room, _, invite = make()
    _, key = store.join(room.id, invite, "Guest")
    assert room.invitation is None and matches(key, room.guest.key)
    with pytest.raises(Denied):
        store.join(room.id, invite, "Another guest")


def test_role_keys_cannot_be_substituted():
    _, store, room, host, invite = make()
    _, guest = store.join(room.id, invite, "Guest")
    for role, key in [("host", guest), ("host", invite), ("guest", host)]:
        with pytest.raises(Denied):
            store.authenticate(room.id, role, key)


def test_duplicate_connections_cannot_replace_host():
    _, store, room, host, _ = make()
    original = room.host.socket
    with pytest.raises(Denied):
        store.attach(room.id, "host", host, object())
    assert room.host.socket is original


def test_revocation_invalidates_every_capability():
    _, store, room, host, invite = make()
    _, guest = store.join(room.id, invite, "Guest")
    store.remove(room)
    for role, key in [("host", host), ("guest", guest)]:
        with pytest.raises(Denied):
            store.authenticate(room.id, role, key)
    with pytest.raises(Denied):
        store.join(room.id, invite, "Guest")


def test_invite_expires_and_heartbeat_does_not_extend_it():
    now, store, room, _, invite = make()
    now[0] += 121
    room.host.last_seen = now[0]
    with pytest.raises(Denied):
        store.join(room.id, invite, "Guest")


def test_host_approval_and_both_ready_required():
    _, store, room, _, invite = make()
    _, key = store.join(room.id, invite, "Guest")
    with pytest.raises(Denied):
        store.ready(room, "host")
    with pytest.raises(Denied):
        store.approve(room)
    store.attach(room.id, "guest", key, object())
    store.approve(room)
    assert not store.ready(room, "host")
    assert store.ready(room, "guest")
    with pytest.raises(Denied):
        store.ready(room, "guest")


@pytest.mark.parametrize("reason", ["lease", "duration", "guest-connect"])
def test_fail_closed_deadlines(reason):
    now, store, room, _, invite = make()
    if reason == "guest-connect":
        store.join(room.id, invite, "Guest")
        now[0] += 16
        room.host.last_seen = now[0]
    elif reason == "duration":
        now[0] = room.end_at
        room.host.last_seen = now[0]
    else:
        now[0] += 13
    with pytest.raises(Denied):
        store.get(room.id)


def test_new_server_cannot_restore_old_tokens():
    _, _, room, host, _ = make()
    with pytest.raises(Denied):
        Rooms().authenticate(room.id, "host", host)


@pytest.mark.parametrize("name", ["", "a" * 61, "bad\nname", [], None])
def test_invalid_guest_names(name):
    _, store, room, _, invite = make()
    with pytest.raises(Denied):
        store.join(room.id, invite, name)
    assert room.invitation is not None


@pytest.mark.parametrize(
    "url",
    [
        "http://calls.example.org",
        "https://a@b",
        "https://x/#token",
        "https://x/path",
        "file:///tmp/call",
        "javascript:alert(1)",
    ],
)
def test_launcher_rejects_unsafe_origins(url):
    with pytest.raises(ValueError):
        service_url(url)


def test_production_requires_https_and_private_turn():
    with pytest.raises(ValueError):
        Config("http://example.org", "x" * 43, development=True).validate()
    with pytest.raises(ValueError):
        Config("https://example.org", "x" * 43).validate()
    Config(
        "https://example.org",
        "x" * 43,
        turn_urls=("turns:turn.example.org:5349",),
        turn_secret="y" * 43,
    ).validate()


def test_rate_limit():
    limiter = Limit()
    assert limiter.allow("client", maximum=1)
    assert not limiter.allow("client", maximum=1)
