# Private screen and voice calls

LinuxShare 0.2 adds one-to-one calls with screen sharing and two-way microphone
audio. The host opens a call from the GTK application or `linuxshare-call`.
Both participants use the call page in a browser; the guest installs nothing
and needs no Teams account. The virtual-camera mode remains separate.

## Local demonstration

Install using `./install.sh`, which includes the `calls` extra. For development:

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/pip install -e '.[calls,dev]'
.venv/bin/linuxshare-call
```

A loopback-only service opens your browser with a temporary creation key.
Click **Create private invitation**, copy its link into another browser/profile
on the **same computer**, and request to join. The host compares the displayed
connection code with the guest through a separate trusted channel, then
approves them. Both explicitly enable their media. The host selects a screen
or window; the guest enables only their microphone. No media starts before
approval and browser consent. The host can mute or end the call; either party
can leave. Rejecting a guest ends the session and burns the invitation.

**Loopback invitations cannot work on another computer.** Do not expose the
HTTP demonstration on your LAN or through a public tunnel. For internet calls,
deploy the HTTPS signaling service and private TURN infrastructure below.

The call lives in the host's browser tab. Ending/closing/reloading that tab
revokes access. In local demonstration mode, closing LinuxShare also terminates
its child service. With a remote service, closing the GTK launcher does **not**
close an already-open host browser tab: use **End call & revoke access** there.
Browser microphone/screen permissions may remain saved by the browser, but
media tracks are stopped; permission storage does not grant access to a future
LinuxShare session. Desktop Chromium is the automated-test target; manually
validate Firefox/Safari/mobile browser support before relying on it.

## Internet deployment (operator setup required)

No server, domain, TURN subscription or public deployment has been provisioned.
The repository contains templates, not live hosting credentials.

1. Use a trusted Linux server, a domain you control, valid HTTPS certificates,
   and a private coturn or compatible TURN service. The production server
   refuses insecure origins and missing TURN configuration. TURN relay mode
   is the default, avoiding direct peer-IP disclosure to the other participant.
2. Install this trusted checkout into `/opt/linuxshare/venv` with the `calls`
   extra. A version-pinned runtime dependency file is supplied as
   `deployment/requirements-calls.txt`; install it before the package for
   reproducible versions. Keep the application and dependencies patched.
3. Copy `deployment/environment.example` to `/etc/linuxshare-calls.env`, fill
   in the actual origin/TURN URLs, and use two independent random secrets.
   Generate each with `python3 -c 'import secrets; print(secrets.token_urlsafe(32))'`.
   Use root ownership and mode 0600. Never paste secrets into tickets or Git.
   The creation key allows creation of host sessions; share it only with trusted
   hosts. Guests need only their invitation. Rotate keys after suspected exposure.
4. Install the supplied systemd service and Caddy configuration, replacing the
   example domain. Caddy terminates HTTPS and forwards WebSockets to
   `127.0.0.1:8787`. Keep that backend port inaccessible externally. Preserve
   the original Host and Origin headers; the application checks exact origin
   and does not trust forwarded headers. Use **one process/worker**, since
   authorization state is deliberately in-memory; multiple workers are unsupported.
5. Configure private TURN using the example as a starting point, including
   TLS certificates, authentication, quotas, internal-address restrictions,
   and firewall ports. Coturn's REST shared secret must match the server's
   `LINUXSHARE_TURN_SECRET`. Open 3478 UDP/TCP, 5349 TCP, and the configured UDP
   relay range as appropriate; port 443 TURN/TLS on a separate endpoint may be
   needed for restrictive corporate networks. Do not weaken encryption or
   authentication to work around a blocked network.
6. On the host desktop, set `LINUXSHARE_CALL_URL=https://calls.example.org`
   before starting LinuxShare or `linuxshare-call`. The call page asks for the
   creation key and never persists it. The guest link contains only the
   single-use invitation, not the creation or host key.
7. Test on two real networks, including a forced TURN path and revoked invites,
   before inviting someone to view private content. See the security checklist.

Example foreground deployment command (environment already loaded securely):

```bash
/opt/linuxshare/venv/bin/linuxshare-call-server --port 8787
```

Do not disable certificate validation or loosen the origin checks. Configure
health checks through the local loopback address with the correct Host header.
The service serves no third-party scripts, fonts or analytics. Logging is off
for HTTP access by default; proxy/TURN/hosting-provider logs also need review.

## Access lifetime and revocation

- Invitations have 256 bits of randomness, expire after two minutes, and are
  consumed on the first valid join request, even if the host later rejects it.
- A host approves one connected guest. A displayed name is not identity proof;
  compare the connection code through your existing trusted contact channel.
- Host and guest receive different role-scoped capabilities, kept only in
  memory. Server storage contains SHA-256 digests, not raw invitation/session keys.
- Authenticated WebSocket connections are single-use. No automatic reconnect,
  refresh recovery, second guest, or restoration after server restart exists.
- Ending/revoking stops the local tracks and peer connection before any network
  request. The server invalidates the room before notifying/closing peers.
- WebSocket loss ends the call; an application lease watchdog stops the client
  after ten seconds without server acknowledgements. Server leases expire after
  twelve seconds, checked every second. Browser suspension/timer throttling can
  delay client timers, so these are designed bounds, not hard real-time guarantees.
- The session has a one-hour maximum. Heartbeats never extend the invitation or
  maximum call duration. A new call requires a new invitation and fresh consent.
- Service shutdown/restart destroys sessions. It does not store SDP, ICE
  candidates, screen frames, audio, or room credentials on disk.

## Honest security limits

WebRTC encrypts media using DTLS-SRTP; HTTPS/WSS protects signaling. A standard
TURN relay transports encrypted packets and does not terminate media encryption.
The HTTPS/signaling service and delivered JavaScript remain trusted: compromise
of either endpoint or the application server can compromise a call. This is
not independently authenticated end-to-end encryption against a malicious
signaling operator, and it is not a promise of perfect security.

Anyone receiving your media can make their own recording. Revocation stops
future sharing; it cannot delete copies or buffered frames already received.
There is no built-in recording. No camera video or system-audio sharing is
requested. The browser may reveal device/network metadata to the service.

TURN credentials expire at the session deadline plus 30 seconds. Ending a call
revokes its signaling/media session, but does not immediately invalidate a
previously issued coturn credential or force-delete TURN allocations. Quotas
limit that residual relay-resource exposure; the credential alone cannot
restart an ended call or obtain more screen/audio from the host.

Internet operation, restrictive-network TURN behavior, mobile browsers, and a
third-party security audit remain deployment validation tasks. Validate access
controls after any change; do not market the application as “100% secure.”

## Verification checklist

- Wrong origin, missing creation key, guest-to-host privilege substitution,
  reused invitations and second guests must all fail.
- Approval alone must not activate devices; browser consent and an explicit
  media button are also required.
- Confirm screen frames and voice arrive in both directions as appropriate.
- Test mute, reject, end, closing either tab, server shutdown, invitation expiry,
  network interruption and permission prompts completed after revocation.
- Confirm expired/revoked host and guest capabilities cannot reconnect, even
  with saved tokens; inspect the browser's media indicator after ending.
- Verify forced TURN traffic across separate networks, certificates, origin
  restrictions, firewall, quotas, log policy and secret rotation.

Automated protocol tests: `python -m pytest tests/calls -q`.
Synthetic media/browser integration: `python tests/calls/browser_smoke.py`
(requires Playwright and Chromium; does not access your real screen or mic).
