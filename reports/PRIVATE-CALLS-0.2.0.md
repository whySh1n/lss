# LinuxShare 0.2.0 implementation and validation report

30 September 2026

## Delivered

Direct-link, one-to-one browser calls launched from LinuxShare, with host screen sharing and two-way microphone audio. Guests need a browser, not Teams. Existing virtual-camera functionality remains available separately.

Calls require explicit host approval and explicit media permission. Invites contain 256 bits of randomness, expire after two minutes, and are consumed once. Host and guest credentials are separate; duplicate attachments and reconnects are denied. Ending or revoking removes server authorization before notifying peers, stops browser media tracks and closes connections. Calls also expire after one hour; disconnects, missing heartbeats and service shutdown trigger cleanup. No built-in recording or persistent call store is implemented.

Production configuration requires HTTPS and TURN, with relay-only WebRTC by default. Media uses WebRTC DTLS-SRTP. Signaling and the served browser application remain trusted components. Origin checks, restrictive browser headers, bounded requests, rate limits and short-lived TURN credentials reduce exposure.

## Validation

- Python suite: 115 tests passed, including existing virtual-camera tests and new consent, authorization, replay, expiry, revocation, reconnect-denial and cleanup coverage.
- Chromium integration: real WebRTC connections between independent browser contexts; received screen video and two-way audio RTP with connected DTLS; mute, end/revoke, replay denial, delayed-permission cleanup and signaling shutdown passed.
- Browser media was synthetic canvas video and Chromium fake microphone input. This did not capture a person's desktop or microphone.
- Fresh installation in a temporary prefix succeeded; installed CLI and private-call commands worked. Installed GTK main window, picker, settings and private-call launcher callback smoke tests passed.
- Python lint, JavaScript syntax, shell syntax and package build passed. Static assets are packaged with the application.
- Bandit reported no medium/high findings (29 low-severity findings across the application).
- Pinned runtime dependency audit reported no known vulnerabilities. This is a point-in-time dependency check, not an independent security certification.

GitHub Actions also runs Python 3.10/3.12/3.14 checks, portal protocol tests, Chromium integration and the dependency audit. Its result is reported separately with the pushed commit.

## Deployment and remaining limits

No public server, domain or TURN service has been purchased or deployed. The included local demonstration uses loopback HTTP, which browsers treat as a secure local context; its invite is not usable by a remote person. Deployment templates and instructions are in `deployment/` and `docs/private-calls.md`.

Real screen/microphone calls across two devices and networks, TURN relay connectivity, TLS configuration and production operational controls still need validation after hosting is selected. Revocation cannot remove media a recipient already received or recorded independently. Browser scheduling or a frozen process can delay local cleanup; the server removes authorization on its own expiry checks. Previously issued TURN credentials remain usable until their short expiry, but do not restore the removed call.

No system can promise perfect security. An independent security review is advisable before sensitive production use. The existing installed application and local installation report were preserved; the new version was validated through an isolated installation.
