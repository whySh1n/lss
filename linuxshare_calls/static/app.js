"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const fragment = new URLSearchParams(location.hash.slice(1));
  // Capabilities never go in HTTP URLs, analytics, persistent storage or referrers.
  history.replaceState(null, "", location.pathname);
  let room = fragment.get("room"), invite = fragment.get("invite");
  let creationKey = fragment.get("create") || "";
  for (const key of [...fragment.keys()]) fragment.delete(key);
  let role = invite ? "guest" : "host", token = null, ws = null, pc = null;
  let ended = false, approved = false, preparing = false, localStreams = [];
  let iceConfig = null, remoteCandidates = [], queue = Promise.resolve();
  let leaseUntil = 0, pingTimer = null, leaseTimer = null, durationTimer = null;
  const show = (id, visible = true) => { $(id).hidden = !visible; };
  const status = text => { $("status").textContent = text; };
  const stopStreams = streams => streams.forEach(s => s.getTracks().forEach(t => t.stop()));
  function transmit(data) {
    if (ended || !ws || ws.readyState !== WebSocket.OPEN) throw new Error("Call disconnected");
    ws.send(JSON.stringify(data));
  }
  function finish(message = "Call ended. The invitation is no longer valid.", notify = true) {
    if (ended) return;
    // Stop media BEFORE making any network request. No acknowledgement is needed.
    ended = true;
    stopStreams(localStreams); localStreams = [];
    if (pc) { pc.close(); pc = null; }
    $("screen").srcObject = null; $("voice").srcObject = null;
    clearInterval(pingTimer); clearInterval(leaseTimer); clearTimeout(durationTimer);
    if (notify && ws?.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: "end"}));
    if (notify && role === "host" && room && token) {
      // Best effort redundancy; the local media already stopped synchronously.
      fetch("/api/end", {method: "POST", headers: {"Content-Type": "application/json"},
        body: JSON.stringify({room, token}), keepalive: true}).catch(() => {});
    }
    ws?.close(); ws = null; token = null; invite = null; creationKey = "";
    $("invite-link").value = ""; $("creation-key").value = "";
    for (const id of ["create-panel", "join-panel", "invite-panel", "approval-panel",
      "guest-code-panel", "controls", "screen", "listen"]) show(id, false);
    show("placeholder"); status(message);
    $("placeholder").querySelector("h2").textContent = "This session is closed";
    $("placeholder").querySelector("p").textContent = "Reload to create a fresh invitation. Old links cannot reconnect.";
  }
  async function api(path, data, key) {
    const response = await fetch(path, {method: "POST", credentials: "omit",
      headers: {"Content-Type": "application/json", ...(key ? {Authorization: `Bearer ${key}`} : {})},
      body: JSON.stringify(data)});
    if (!response.ok) throw new Error("Request denied. The invitation may be used, expired or revoked.");
    return response.json();
  }
  function connect() {
    ws = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`);
    leaseUntil = performance.now() + 10000;
    ws.onopen = () => transmit({room, role, token});
    // Serialize async SDP processing; ICE must not overtake remote descriptions.
    ws.onmessage = event => { queue = queue.then(() => handle(JSON.parse(event.data)))
      .catch(() => finish("Call could not continue. Access has been revoked.")); };
    ws.onerror = () => finish("Connection failed. Create a new invitation.");
    ws.onclose = () => finish("Connection closed. Access has been revoked.", false);
    pingTimer = setInterval(() => {
      if (!ended && ws?.readyState === WebSocket.OPEN) transmit({type: "ping"});
    }, 2000);
    leaseTimer = setInterval(() => {
      if (performance.now() >= leaseUntil) finish("Connection authorization expired. Sharing stopped.");
    }, 500);
    show("controls");
  }
  async function handle(data) {
    if (ended) return;
    switch (data.type) {
      case "hello":
        iceConfig = data.ice; leaseUntil = performance.now() + 10000;
        if (data.development) show("local-warning");
        durationTimer = setTimeout(() => finish("Maximum call duration reached. Access revoked."), data.callSeconds * 1000);
        status(role === "host" ? "Invitation ready. Waiting for one guest." : "Waiting for the host to approve you.");
        break;
      case "lease": leaseUntil = performance.now() + 10000; break;
      case "waiting":
        if (role !== "host") throw new Error("Unexpected role");
        show("invite-panel", false); $("invite-link").value = "";
        $("guest-description").textContent = `${data.name} is requesting access.`;
        $("host-code").textContent = data.code; show("approval-panel");
        status("Verify your guest, then approve or reject this connection."); break;
      case "approved":
        approved = true; show("approval-panel", false); show("guest-code-panel", false);
        $("prepare").textContent = role === "host" ? "Share screen & enable microphone" : "Enable microphone & join";
        show("prepare"); status("Approved. Choose to enable your screen/microphone when ready."); break;
      case "negotiate": {
        if (role !== "host" || !pc) throw new Error("Unexpected offer request");
        const offer = await pc.createOffer();
        if (ended) return;
        await pc.setLocalDescription(offer);
        if (!ended) transmit({type: "offer", sdp: pc.localDescription.sdp});
        break;
      }
      case "offer": {
        if (role !== "guest" || !pc) throw new Error("Unexpected offer");
        await pc.setRemoteDescription({type: "offer", sdp: data.sdp});
        await flushCandidates();
        if (ended) return;
        const answer = await pc.createAnswer();
        if (ended) return;
        await pc.setLocalDescription(answer);
        if (!ended) transmit({type: "answer", sdp: pc.localDescription.sdp});
        break;
      }
      case "answer":
        if (role !== "host" || !pc) throw new Error("Unexpected answer");
        await pc.setRemoteDescription({type: "answer", sdp: data.sdp}); await flushCandidates(); break;
      case "ice":
        if (!pc) throw new Error("Unexpected ICE");
        if (pc.remoteDescription) await pc.addIceCandidate(data.candidate);
        else remoteCandidates.push(data.candidate);
        break;
      case "ended": finish(data.reason, false); break;
      default: throw new Error("Unknown message");
    }
  }
  async function flushCandidates() {
    for (const candidate of remoteCandidates) {
      if (ended) return;
      await pc.addIceCandidate(candidate);
    }
    remoteCandidates = [];
  }
  function adopt(stream) {
    // Permission prompts may complete AFTER revoke/disconnect. Never retain those tracks.
    if (ended) { stopStreams([stream]); throw new Error("Call ended"); }
    localStreams.push(stream);
    stream.getTracks().forEach(track => track.addEventListener("ended", () => finish("Media sharing stopped. Access revoked.")));
    return stream;
  }
  async function prepare() {
    if (!approved || ended || preparing) return;
    preparing = true; $("prepare").disabled = true;
    try {
      let screen = null;
      if (role === "host") {
        // Must be invoked directly from this click handler for browser user activation.
        screen = adopt(await navigator.mediaDevices.getDisplayMedia({video: {frameRate: {ideal: 15, max: 30}}, audio: false}));
      }
      const microphone = adopt(await navigator.mediaDevices.getUserMedia({audio: {
        echoCancellation: true, noiseSuppression: true, autoGainControl: true}, video: false}));
      if (ended) return;
      pc = new RTCPeerConnection(iceConfig);
      pc.onicecandidate = event => { if (event.candidate && !ended) transmit({type: "ice", candidate: event.candidate.toJSON()}); };
      pc.onconnectionstatechange = () => {
        if (ended || !pc) return;
        if (pc.connectionState === "connected") status("Connected · encrypted screen and voice · one guest");
        if (["failed", "disconnected", "closed"].includes(pc.connectionState)) finish("Media connection lost. Start a new call.");
      };
      pc.ontrack = event => {
        const stream = new MediaStream([event.track]);
        if (event.track.kind === "video") {
          $("screen").srcObject = stream; show("screen"); show("placeholder", false);
        } else {
          $("voice").srcObject = stream;
          $("voice").play().catch(() => show("listen"));
        }
      };
      if (screen) {
        screen.getVideoTracks().forEach(track => pc.addTrack(track, screen));
        $("screen").srcObject = screen; show("screen"); show("placeholder", false);
      } else pc.addTransceiver("video", {direction: "recvonly"});
      microphone.getAudioTracks().forEach(track => pc.addTrack(track, microphone));
      show("prepare", false); show("mute");
      status("Media ready. Waiting for the other person…"); transmit({type: "ready"});
    } catch (_) { finish("Screen/microphone permission was cancelled or capture failed. Access revoked."); }
  }
  $("create").onclick = async () => {
    $("create").disabled = true;
    try {
      const key = creationKey || $("creation-key").value;
      creationKey = ""; $("creation-key").value = "";
      const result = await api("/api/create", {}, key);
      if (ended) return;
      room = result.room; token = result.token;
      $("invite-link").value = `${location.origin}/#room=${encodeURIComponent(room)}&invite=${encodeURIComponent(result.invitation)}`;
      $("invite-expiry").textContent = `Expires in ${result.inviteSeconds} seconds. Refreshing or closing this page ends the session.`;
      show("create-panel", false); show("invite-panel"); connect();
    } catch (_) { status("Could not create a call. Check the creation key or try later."); $("create").disabled = false; }
  };
  $("join").onclick = async () => {
    $("join").disabled = true;
    try {
      const result = await api("/api/join", {room, invitation: invite, name: $("guest-name").value});
      invite = null; token = result.token; $("guest-code").textContent = result.code;
      if (ended) return;
      show("join-panel", false); show("guest-code-panel"); connect();
    } catch (_) { finish("This invitation is unavailable, used, or expired. Ask the host for a new link.", false); }
  };
  $("approve").onclick = () => { $("approve").disabled = true; transmit({type: "approve"}); };
  $("reject").onclick = () => finish("Guest rejected. Invitation revoked.");
  $("end").onclick = () => finish();
  $("prepare").onclick = prepare;
  $("mute").onclick = () => {
    const tracks = localStreams.flatMap(stream => stream.getAudioTracks());
    const enable = tracks.some(track => !track.enabled);
    tracks.forEach(track => { track.enabled = enable; });
    $("mute").textContent = enable ? "Mute microphone" : "Unmute microphone";
  };
  $("copy").onclick = () => navigator.clipboard.writeText($("invite-link").value)
    .then(() => { $("copy").textContent = "Copied"; })
    .catch(() => { $("invite-link").focus(); $("invite-link").select(); status("Select and copy the invitation manually."); });
  $("listen").onclick = () => $("voice").play().then(() => show("listen", false)).catch(() => status("Allow audio playback in your browser."));
  window.addEventListener("hashchange", () => {
    finish("A new invitation was opened. Previous access revoked.");
    location.reload();
  });
  window.addEventListener("pagehide", () => finish("Call closed."));
  if (role === "guest") { show("create-panel", false); show("join-panel"); status("Request access to this private call."); }
  else if (creationKey) { show("creation-key", false); document.querySelector('label[for="creation-key"]').hidden = true; }
  if (!window.isSecureContext || !navigator.mediaDevices || !window.RTCPeerConnection) {
    finish("This browser needs HTTPS and WebRTC support. Try a current desktop browser.", false);
  }
})();
