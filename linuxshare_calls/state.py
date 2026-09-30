"""In-memory authority. Credentials are capabilities, never user identities.

All transitions run synchronously on the server's single asyncio event loop.
Restarting the service destroys every session and invalidates all invitations.
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import secrets
import time


class Denied(ValueError):
    """Invalid, consumed, expired or unauthorized capability."""


def digest(token):
    if not isinstance(token, str) or not 20 <= len(token) <= 128:
        raise Denied("Unavailable")
    return hashlib.sha256(token.encode()).digest()


def matches(token, expected):
    try:
        return expected is not None and hmac.compare_digest(digest(token), expected)
    except Denied:
        return False


@dataclass
class Peer:
    key: bytes
    socket: object = None
    attached: bool = False
    ready: bool = False
    last_seen: float = 0


@dataclass
class Room:
    id: str
    host: Peer
    invitation: bytes | None
    invite_until: float
    end_at: float
    guest: Peer | None = None
    guest_name: str = ""
    check_code: str = ""
    approved: bool = False
    negotiating: bool = False
    offered: bool = False
    answered: bool = False
    created: float = 0
    guest_connect_until: float = 0
    candidates: dict = field(default_factory=lambda: {"host": 0, "guest": 0})

    def peer(self, role):
        if role not in ("host", "guest"):
            raise Denied("Unavailable")
        peer = getattr(self, role)
        if peer is None:
            raise Denied("Unavailable")
        return peer


class Rooms:
    def __init__(self, invite_seconds=120, call_seconds=3600, clock=time.monotonic):
        self.items = {}
        self.invite_seconds, self.call_seconds = invite_seconds, call_seconds
        self.clock = clock

    def create(self):
        if len(self.items) >= 32:
            raise Denied("Capacity reached")
        now = self.clock()
        room_id, host, invite = (secrets.token_urlsafe(n) for n in (18, 32, 32))
        room = Room(
            room_id,
            Peer(digest(host)),
            digest(invite),
            now + self.invite_seconds,
            now + self.call_seconds,
            created=now,
        )
        self.items[room_id] = room
        return room, host, invite

    def get(self, room_id):
        room = self.items.get(room_id) if isinstance(room_id, str) else None
        if room is None or self.expired(room):
            raise Denied("Unavailable")
        return room

    def expired(self, room):
        now = self.clock()
        return (
            now >= room.end_at
            or (not room.host.attached and now >= room.created + 15)
            or (not room.approved and now >= room.invite_until)
            or (
                room.guest is not None
                and not room.guest.attached
                and now >= room.guest_connect_until
            )
            or any(
                p and p.attached and now - p.last_seen > 12
                for p in (room.host, room.guest)
            )
        )

    def join(self, room_id, invitation, name):
        room = self.get(room_id)
        if (
            room.guest is not None
            or self.clock() >= room.invite_until
            or not matches(invitation, room.invitation)
        ):
            raise Denied("Unavailable")
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60:
            raise Denied("Enter a name (1–60 characters)")
        if any(not c.isprintable() for c in name):
            raise Denied("Invalid name")
        guest_key = secrets.token_urlsafe(32)
        room.guest = Peer(digest(guest_key))
        room.invitation = None  # Single-use consumption, even before host approval.
        room.guest_name = name.strip()
        room.check_code = f"{secrets.randbelow(1000000):06d}"
        room.guest_connect_until = self.clock() + 15
        return room, guest_key

    def authenticate(self, room_id, role, key):
        room = self.get(room_id)
        peer = room.peer(role)
        if not matches(key, peer.key):
            raise Denied("Unavailable")
        return room, peer

    def attach(self, room_id, role, key, socket):
        room, peer = self.authenticate(room_id, role, key)
        if peer.attached:
            raise Denied("Connection already used")
        peer.attached, peer.socket, peer.last_seen = True, socket, self.clock()
        return room, peer

    def approve(self, room):
        if room.guest is None or not room.guest.attached or room.approved:
            raise Denied("No guest waiting")
        room.approved = True

    def ready(self, room, role):
        if not room.approved or room.negotiating:
            raise Denied("Not ready")
        room.peer(role).ready = True
        if room.host.ready and room.guest.ready:
            room.negotiating = True
            return True
        return False

    def remove(self, room):
        self.items.pop(room.id, None)
        room.invitation = None
        room.host.key = b""
        if room.guest:
            room.guest.key = b""
