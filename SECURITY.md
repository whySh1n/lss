# Security model and reporting

LinuxShare's private-call mode is a small, single-process service intended for
one approved guest per host session. See [the full access model and deployment
checklist](docs/private-calls.md). No claim of perfect security is made.

## Trust boundaries

- The host grants screen/microphone permission in their browser, then explicitly
  approves one guest. Guest media needs their own explicit microphone consent.
- Invite, host and guest capabilities are distinct. Only the host may approve or
  use the host-revocation endpoint. Either connected participant may end/leave.
- The signaling service is the authority for admission, expiry and single-use
  connections. HTTPS, strict Origin/Host checks, CSP, no persistent browser
  storage, bounded messages/rooms/rates and hashed server capabilities reduce
  exposure. They do not replace a deployment review or host authentication policy.
- Creation-key holders may create sessions. A single shared operator key is not
  a multi-tenant identity system. Do not deploy as a public anonymous service.
- WebRTC encrypts media to the peer. Private TURN relays ciphertext, with expiring
  credentials and production relay-only mode. The browser, delivered JavaScript,
  HTTPS server/operator and endpoint operating systems must be trusted.
- End/revoke stops local tracks before attempting signaling. Server authority is
  removed before awaiting peer notification. Disconnects and missed heartbeats
  fail closed; timer scheduling and buffered frames prevent hard real-time claims.
- Server restart invalidates everything. No server-side recording or media
  storage exists. Recipient-made recordings cannot be revoked or erased.

## Deployment responsibilities

Use valid HTTPS, a private authenticated TURN service, restrictive firewalls,
least-privilege service accounts, patched dependencies and secret rotation.
Keep proxy/provider/TURN logs from collecting tokens, SDP, ICE or unnecessary
metadata. Monitor aggregate failures without recording participant content.
Review native virtual-camera and desktop security separately from browser calls.
Do not expose the local HTTP demonstration publicly. Production must run one
worker and use the documented HTTPS reverse proxy. A public deployment and an
independent penetration test have not been performed by this code change.

## Reporting

For a suspected vulnerability, use the repository's private vulnerability
reporting feature if enabled, or arrange a private channel with its maintainer.
Do not post live invitation links, credentials, private screen content or an
active exploit against another user's session in a public issue. If no private
channel is configured, first request one without disclosing exploit details.
