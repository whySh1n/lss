"""Real Chromium/WebRTC integration with synthetic screen and microphone.

Run with: python tests/calls/browser_smoke.py
Requires playwright and Chromium (CHROMIUM_PATH or /usr/bin/chromium).
Uses two independent browser contexts and an isolated loopback service.
Only screen selection is replaced by a test canvas; no personal media is read.
"""

import asyncio
import os
from pathlib import Path
import secrets
import socket
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from aiohttp import web
from playwright.async_api import async_playwright
from linuxshare_calls.server import Config, make_app, ROOMS

INSTRUMENT = """(() => {
  window.__pcs = []; window.__tracks = []; window.__delayScreen = false;
  const NativePC = window.RTCPeerConnection;
  window.RTCPeerConnection = class extends NativePC {
    constructor(...args) { super(...args); window.__pcs.push(this); }
  };
  const mic = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
  navigator.mediaDevices.getUserMedia = async (...args) => {
    const stream = await mic(...args); window.__tracks.push(...stream.getTracks()); return stream;
  };
  navigator.mediaDevices.getDisplayMedia = async () => {
    const canvas = document.createElement('canvas'); canvas.width = 640; canvas.height = 360;
    const ctx = canvas.getContext('2d'); let n = 0;
    const draw = () => { ctx.fillStyle = n++ % 2 ? '#224466' : '#446622';
      ctx.fillRect(0, 0, 640, 360); ctx.fillStyle = 'white';
      ctx.fillText('Synthetic test', 30, 30); };
    draw(); window.__drawTimer = setInterval(draw, 50);
    const stream = canvas.captureStream(15);
    window.__tracks.push(...stream.getTracks());
    if (window.__delayScreen) await new Promise(resolve => { window.__releaseScreen = resolve; });
    return stream;
  };
})();"""


async def wait_for(page, expression):
    for _ in range(200):
        if await page.evaluate(expression):
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        "Browser condition failed: "
        + expression
        + " status="
        + await page.locator("#status").text_content()
    )


async def create_pair(browser, origin, key):
    host_context = await browser.new_context(permissions=["microphone"])
    guest_context = await browser.new_context(permissions=["microphone"])
    for context in (host_context, guest_context):
        await context.add_init_script(INSTRUMENT)
    host, guest = await host_context.new_page(), await guest_context.new_page()
    errors = []
    host.on("pageerror", lambda exc: errors.append(str(exc)))
    guest.on("pageerror", lambda exc: errors.append(str(exc)))
    await host.goto(origin)
    await host.locator("#creation-key").fill(key)
    await host.locator("#create").click()
    await host.locator("#invite-panel").wait_for(state="visible")
    invitation = await host.locator("#invite-link").input_value()
    assert "#room=" in invitation
    await guest.goto(invitation)
    assert "#" not in guest.url  # Credentials erased from visible history.
    await guest.locator("#guest-name").fill("Test guest")
    await guest.locator("#join").click()
    await host.locator("#approval-panel").wait_for(state="visible")
    assert (
        await host.locator("#host-code").text_content()
        == await guest.locator("#guest-code").text_content()
    )
    assert await host.evaluate("__tracks.length") == 0
    assert await guest.evaluate("__tracks.length") == 0
    await host.locator("#approve").click()
    await guest.locator("#prepare").wait_for(state="visible")
    return host_context, guest_context, host, guest, invitation, errors


async def assert_media_stopped(page):
    await wait_for(page, "__tracks.every(t => t.readyState === 'ended')")
    assert await page.evaluate("__pcs.every(p => p.connectionState === 'closed')")


async def run():
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.setblocking(False)
    origin = f"http://127.0.0.1:{listener.getsockname()[1]}"
    key = secrets.token_urlsafe(32)
    app = make_app(Config(origin, key, development=True))
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    await web.SockSite(runner, listener).start()
    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=os.environ.get("CHROMIUM_PATH", "/usr/bin/chromium"),
                headless=True,
                args=[
                    "--use-fake-device-for-media-stream",
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                ],
            )
            try:
                hc, gc, host, guest, invitation, errors = await create_pair(
                    browser, origin, key
                )
                await host.locator("#prepare").click()
                await guest.locator("#prepare").click()
                await wait_for(
                    host, "__pcs.some(p => p.connectionState === 'connected')"
                )
                await wait_for(
                    guest, "document.querySelector('#screen').videoWidth === 640"
                )
                # Real ICE/DTLS/SRTP connection; verify incoming audio at BOTH endpoints.
                for page in (host, guest):
                    await wait_for(
                        page,
                        """async () => {
                      const stats = await __pcs[0].getStats();
                      return [...stats.values()].some(s => s.type === 'inbound-rtp' &&
                        s.kind === 'audio' && s.packetsReceived > 0);
                    }""",
                    )
                    assert await page.evaluate("""async () => {
                      const stats = await __pcs[0].getStats();
                      return [...stats.values()].some(s =>
                        s.type === 'transport' && s.dtlsState === 'connected');
                    }""")
                if os.environ.get("LINUXSHARE_TEST_SCREENSHOT"):
                    await host.screenshot(path=os.environ["LINUXSHARE_TEST_SCREENSHOT"])
                await host.locator("#mute").click()
                assert await host.evaluate(
                    "__tracks.filter(t => t.kind === 'audio').every(t => !t.enabled)"
                )
                await host.locator("#mute").click()
                await host.locator("#end").click()
                await wait_for(guest, "document.querySelector('#controls').hidden")
                await assert_media_stopped(host)
                await assert_media_stopped(guest)
                assert not app[ROOMS].items
                replay = await gc.new_page()
                await replay.goto(invitation)
                await replay.locator("#guest-name").fill("Replay")
                await replay.locator("#join").click()
                await wait_for(
                    replay,
                    "document.querySelector('#status').textContent.includes('unavailable')",
                )
                assert not errors, errors
                await hc.close()
                await gc.close()
                print(
                    "PASS: approval, encrypted WebRTC screen + two-way audio, "
                    "mute, revoke, replay denial"
                )

                hc, gc, host, guest, _, errors = await create_pair(browser, origin, key)
                await host.evaluate("__delayScreen = true")
                await host.locator("#prepare").click()
                await wait_for(host, "typeof __releaseScreen === 'function'")
                await host.locator("#end").click()
                await host.evaluate("__releaseScreen()")
                await assert_media_stopped(host)
                assert await host.evaluate("__pcs.length") == 0
                assert not errors, errors
                await hc.close()
                await gc.close()
                print(
                    "PASS: revocation while screen permission is pending stops late tracks"
                )

                hc, gc, host, guest, _, errors = await create_pair(browser, origin, key)
                await host.locator("#prepare").click()
                await guest.locator("#prepare").click()
                await wait_for(
                    guest, "__pcs.some(p => p.connectionState === 'connected')"
                )
                await runner.shutdown()
                await wait_for(host, "document.querySelector('#controls').hidden")
                await wait_for(guest, "document.querySelector('#controls').hidden")
                await assert_media_stopped(host)
                await assert_media_stopped(guest)
                assert not errors, errors
                print(
                    "PASS: signaling shutdown closes both peer connections and stops all tracks"
                )
                await hc.close()
                await gc.close()
            finally:
                await browser.close()
    finally:
        await runner.cleanup()
        listener.close()


if __name__ == "__main__":
    asyncio.run(run())
