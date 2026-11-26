const directions = {
  w: [0, 1], s: [0, -1], a: [1, 1], d: [1, -1],
  r: [2, 1], f: [2, -1], q: [3, 1], e: [3, -1],
};

export function createManual(api, terminal, onError) {
  const el = id => document.getElementById(id);
  const keys = new Set(), pointers = new Map();
  let session = null, state = null, active = false, visible = false, starting = false, returning = false, sequence = 0;
  const motionUrl = "/api/manual/movement";
  const put = (id, value) => { if (el(id).textContent !== value) el(id).textContent = value; };

  function envelope(axes) {
    return { ...session, sequence: ++sequence, issued_ms: Date.now(), axes,
      speed: el("manual-speed").valueAsNumber / 100 };
  }
  function controlsAvailable() {
    return visible && session && active && !returning && !document.hidden && document.hasFocus();
  }
  function axes() {
    const result = [0, 0, 0, 0];
    for (const key of new Set([...keys, ...pointers.values()])) {
      const [axis, sign] = directions[key];
      result[axis] += sign;
    }
    return result;
  }
  function heartbeat() {
    if (!controlsAvailable()) return;
    api(motionUrl, envelope(axes())).catch(error => {
      if (controlsAvailable() && !error.message.includes("updated movement request")) release();
    });
  }
  function release() {
    keys.clear();
    pointers.clear();
    if (!session || !active || returning) return;
    const data = envelope([0, 0, 0, 0]);
    const blob = new Blob([JSON.stringify(data)], { type: "application/json" });
    if (!navigator.sendBeacon(motionUrl, blob)) {
      fetch(motionUrl, { method: "POST", headers: { "Content-Type": "application/json" }, body: blob, keepalive: true })
        .catch(() => {});
    }
  }

  function render() {
    const job = state?.mission;
    const manual = job?.mode === "manual" ? job : null;
    const status = manual?.status.manual;
    const owned = !!session && active;
    const flying = owned && manual?.stage === "MANUAL_FLIGHT" && !returning && status?.state !== "RETURNING";
    el("manual-aisles").disabled = starting || !!state?.busy;
    el("manual-start").disabled = !state || starting || !!state.busy || !state.at_pad
      || state.safety?.phase === "RECOVERY" || state.service_mode !== "PRODUCTION";
    el("manual-return").disabled = !flying;
    el("manual-motion").disabled = !flying;
    const current = status?.state || (owned ? "Preparing" : "Ready at dock");
    put("manual-status", current.toLowerCase().replaceAll("_", " "));
    el("manual-status").dataset.state = current;
    put("manual-detail", status?.detail || (owned ? "Waiting for the Safety reservation and takeoff." :
      state?.safety?.phase === "RECOVERY" ? "Resolve the Safety incident in the Recovery Center." :
      "Use the camera and LiDAR to guide the drone inside the reserved aisle."));
    if (active && !owned && !status) put("manual-detail", "The active manual flight belongs to another browser session.");
    const display = values => values ? values.map(value => value.toFixed(2)).join(" / ") : "—";
    put("manual-requested", display(status?.requested));
    put("manual-permitted", display(status?.permitted));
    put("manual-clearance", status?.clearance != null ? `${status.clearance.toFixed(2)} m` : "—");
  }

  el("manual-start").addEventListener("click", async () => {
    starting = true;
    render();
    try {
      session = await api("/api/manual/start", { aisles: el("manual-aisles").value.split(",") });
      sequence = 0;
      active = true;
      returning = false;
      heartbeat();
    } catch (error) { onError(error.message); }
    finally { starting = false; render(); }
  });
  el("manual-return").addEventListener("click", async () => {
    if (!session || !active) return;
    release();
    returning = true;
    render();
    try { await api("/api/manual/return", envelope([0, 0, 0, 0])); }
    catch (error) { returning = false; onError(error.message); render(); }
  });
  el("manual-hold").addEventListener("click", release);
  el("manual-speed").addEventListener("input", () => {
    put("manual-speed-value", `${el("manual-speed").value}%`);
    heartbeat();
  });
  document.querySelectorAll("[data-move]").forEach(button => {
    button.addEventListener("pointerdown", event => {
      if (event.button !== 0 || !controlsAvailable() || el("manual-motion").disabled) return;
      event.preventDefault();
      button.setPointerCapture(event.pointerId);
      pointers.set(event.pointerId, button.dataset.move);
      heartbeat();
    });
    for (const type of ["pointerup", "pointercancel", "lostpointercapture"]) {
      button.addEventListener(type, event => {
        if (pointers.delete(event.pointerId)) heartbeat();
      });
    }
  });
  document.addEventListener("keydown", event => {
    if (!controlsAvailable() || event.target.closest("input, select, textarea, [contenteditable]")) return;
    const key = event.key.toLowerCase();
    if (key === " ") { event.preventDefault(); release(); return; }
    if (!directions[key] || el("manual-motion").disabled) return;
    event.preventDefault();
    if (!event.repeat) { keys.add(key); heartbeat(); }
  });
  document.addEventListener("keyup", event => { if (keys.delete(event.key.toLowerCase())) heartbeat(); });
  window.addEventListener("blur", release);
  window.addEventListener("pagehide", release);
  document.addEventListener("visibilitychange", () => { if (document.hidden) release(); });
  setInterval(heartbeat, 120);

  return {
    show(value) {
      if (visible && !value) release();
      visible = value;
      el("manual-controls").hidden = !visible;
    },
    update(data) {
      state = data;
      const job = data?.mission;
      if (!data) { release(); render(); return; }
      if (session && job?.inspection_id === session.inspection_id && terminal.has(job.stage)) {
        active = false;
        session = null;
        release();
      } else if (!session) active = job?.mode === "manual" && !terminal.has(job.stage);
      render();
    },
  };
}
