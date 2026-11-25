"use strict";

const el = (name) => document.getElementById(name);
const label = (value) => String(value || "").toLowerCase().replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const terminal = new Set(["COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED", "ERROR"]);
const choices = { mode: "aisle", aisles: new Set(["A"]), slots: new Set(), quality: true };
const headings = {
  plan: ["Mission planning", "Choose which locations the drone should inspect."],
  live: ["Live inspection", "Follow the simulator, camera detections and API confirmations."],
  results: ["Inspection results", "Review the selected locations and open the inspection report."],
};
let layout, preview, state, wantedRun, lastRun, lastStage;
let view = "plan";
let dispatching = false;
let version = 0;
let cameraLoading = false;
let overviewLoading = false;

function put(id, value) { el(id).textContent = value; }
function html(id, value) { if (el(id).innerHTML !== value) el(id).innerHTML = value; }
function notice(value = "") { put("notice", value); el("notice").hidden = !value; }

async function api(url, data) {
  const response = await fetch(url, data === undefined ? { cache: "no-store" } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Control service unavailable.");
  return body;
}

function setView(next) {
  view = next;
  el("workspace").dataset.view = next;
  for (const [name, panel] of [["plan", "plan-panel"], ["live", "live-panel"], ["results", "results-panel"]]) {
    el(panel).hidden = name !== next;
  }
  for (const button of document.querySelectorAll(".tab")) {
    const active = button.dataset.view === next;
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  put("page-title", headings[next][0]);
  put("page-description", headings[next][1]);
  draw();
}

function point(x, y) {
  return [62 + (x - layout.floor.x) * 19, 25 + (layout.floor.y + layout.floor.height - y) * 19];
}
function rect(x, y, width, height, style, extras = "") {
  const [px, py] = point(x, y + height);
  return `<rect class="${style}" x="${px}" y="${py}" width="${width * 19}" height="${height * 19}" ${extras}/>`;
}
function text(x, y, value, style) {
  const [px, py] = point(x, y);
  return `<text class="${style}" x="${px}" y="${py}">${safe(value)}</text>`;
}
function mapButton(group, action) {
  group.addEventListener("click", action);
  group.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") { event.preventDefault(); action(); }
  });
}
function drawLayout() {
  const f = layout.floor, p = layout.pad, cross = layout.crossing_x;
  const [cx, cy1] = point(cross, -7.8), [, cy2] = point(cross, 7.8);
  html("floor", rect(f.x, f.y, f.width, f.height, "hall", 'rx="8"')
    + rect(f.x, f.y, f.width, f.height, "mesh", 'rx="8"')
    + `<path class="corridor-axis" d="M${cx} ${cy1}V${cy2}"/>`
    + text(cross + .35, 8.1, "TRANSFER", "corridor")
    + rect(p.x - p.width / 2, p.y - p.height / 2, p.width, p.height, "pad", 'rx="4"')
    + text(p.x, p.y - .28, "H", "pad-letter") + text(p.x - 1.5, p.y - 1.8, "LAUNCH PAD", "pad-caption"));
  html("map-aisles", layout.aisles.map(({ id, y, functional }) => {
    const left = 4.1, right = f.x + f.width - .8;
    const [x1, y1] = point(left, y + 2.3), [x2, y2] = point(right, y - 2.3);
    const attrs = functional ? `role="button" tabindex="0" aria-label="Select aisle ${id}" aria-pressed="false"` : "";
    return `<g id="aisle-${id}" class="aisle aisle-${id.toLowerCase()}" ${attrs}>`
      + rect(left, y - 2.3, right - left, 4.6, "lane", 'rx="4"')
      + `<path class="lane-edge" d="M${x1} ${y1}H${x2}M${x1} ${y2}H${x2}"/>`
      + text(right - 7.6, y + .13, `AISLE ${id}`, "lane-label")
      + text(right - 7.6, y - .78, functional ? "INSPECTION ZONE" : "DECORATIVE", "lane-note")
      + "</g>";
  }).join(""));
  html("racks", layout.racks.map((rack, index) => {
    const step = rack.width / rack.bays;
    return rect(rack.x, rack.y, rack.width, rack.height, "rack", 'rx="2"')
      + Array.from({ length: rack.bays }, (_, bay) => rect(rack.x + bay * step + .13, rack.y + .16, step - .26, rack.height - .32, "rack-bin", 'rx="2"')).join("")
      + text(rack.x - 1.78, rack.y + .44, `R${index + 1}`, "rack-index");
  }).join(""));
  html("positions", Object.entries(layout.slots).map(([slot, item]) => {
    const [x, y] = item.label;
    const [px, py] = point(x + (item.level === 1 ? .12 : 1.02), y - .64);
    return `<g id="slot-${slot}" class="slot" role="button" tabindex="0" aria-label="Select location ${slot}" aria-pressed="false" transform="translate(${px} ${py})">
      <title>${slot} · level ${item.level}</title><circle r="7.6"/><text>${item.level}</text></g>`;
  }).join(""));
  for (const row of layout.aisles.filter((row) => row.functional)) mapButton(el("aisle-" + row.id), () => toggleAisle(row.id));
  for (const slot of Object.keys(layout.slots)) mapButton(el("slot-" + slot), () => toggleSlot(slot));
}

function toggleAisle(id) {
  if (view !== "plan") return;
  choices.mode = "aisle";
  choices.aisles.has(id) ? choices.aisles.delete(id) : choices.aisles.add(id);
  changePlan();
}
function toggleSlot(slot) {
  if (view !== "plan") return;
  if (choices.mode !== "custom") choices.slots.clear();
  choices.mode = "custom";
  choices.slots.has(slot) ? choices.slots.delete(slot) : choices.slots.add(slot);
  changePlan();
}
function selection() {
  return { mode: choices.mode, aisles: [...choices.aisles], slots: [...choices.slots], quality: choices.quality };
}
function changePlan() {
  notice();
  for (const radio of document.querySelectorAll("input[name='mode']")) radio.checked = radio.value === choices.mode;
  el("quality").checked = choices.quality;
  el("aisle-options").hidden = choices.mode !== "aisle";
  el("slot-options").hidden = choices.mode !== "custom";
  html("aisle-options", layout.aisles.map((row) => `<button class="chip" type="button" data-aisle="${row.id}"
    aria-pressed="${choices.aisles.has(row.id)}" ${row.functional ? "" : "disabled"}>Aisle ${row.id}${row.functional ? "" : " · decorative"}</button>`).join(""));
  html("slot-options", Object.keys(layout.slots).map((slot) => `<button class="chip" type="button" data-slot="${slot}"
    aria-pressed="${choices.slots.has(slot)}">${slot}</button>`).join(""));
  const revision = ++version;
  preview = null;
  draw();
  const chosen = selection();
  if ((chosen.mode === "aisle" && !chosen.aisles.length) || (chosen.mode === "custom" && !chosen.slots.length)) return;
  api("/api/plan", chosen).then((plan) => {
    if (version === revision) { preview = plan; draw(); }
  }).catch((error) => notice(error.message));
}

function drawMap(job) {
  const drawing = view === "plan" ? preview : job;
  const selected = new Set(drawing?.slots || []);
  const selectedAisles = new Set([...selected].map((slot) => layout.slots[slot].aisle));
  const status = view === "plan" ? {} : job?.status || {};
  const current = status.stage === "INSPECT" ? status.target : null;
  for (const row of layout.aisles) {
    const item = el("aisle-" + row.id);
    item.classList.toggle("selected", selectedAisles.has(row.id));
    if (row.functional) item.setAttribute("aria-pressed", String(selectedAisles.has(row.id)));
  }
  if (layout.safety_fields) {
    const zones = state?.safety?.zones || {};
    html("safety-fields", Object.entries(layout.safety_fields).map(([id, [x, y, endX, endY]]) =>
      rect(x, y, endX - x, endY - y, `safety-field access-${(zones[id]?.state || "FAULT").toLowerCase()}`,
        'rx="4"')).join(""));
  }
  for (const slot of Object.keys(layout.slots)) {
    const item = el("slot-" + slot);
    item.classList.toggle("selected", selected.has(slot));
    item.classList.toggle("confirmed", !!status.confirmed?.[slot]);
    item.classList.toggle("missed", !!status.missed?.includes(slot));
    item.classList.toggle("active", slot === current);
    item.setAttribute("aria-pressed", String(selected.has(slot)));
  }
  const line = (points) => (points || []).map(([x, y]) => point(x, y).join(",")).join(" ");
  el("plan-line").setAttribute("points", line(view === "plan" ? preview?.points : job?.planned));
  el("flown-line").setAttribute("points", view === "plan" ? "" : line(job?.flown));
  const drone = el("drone");
  const position = state?.robot && state.position;
  drone.setAttribute("visibility", position ? "visible" : "hidden");
  if (position) {
    const [px, py] = point(position[0], position[1]);
    drone.style.transform = `translate(${px}px,${py}px) rotate(${-position[3] * 180 / Math.PI}deg)`;
  }
}

function drawResults(job) {
  const status = job?.status || {};
  const result = job?.result;
  const finished = job && terminal.has(job.stage);
  const reports = job?.evidence || [];
  put("completion-id", job?.inspection_id || "No inspection selected");
  put("completion-text", job?.error || (finished ? (status.landed ? "Touchdown confirmed. " : "Touchdown unconfirmed. ")
    + (result ? `${Object.keys(status.confirmed || {}).length} stops confirmed · ${result.events} API events.` : "Preparing report.")
    : job ? "The mission is still in progress." : "Run an inspection to see its report."));
  const reportLink = el("report-link");
  reportLink.hidden = !result;
  if (result) reportLink.href = result.url;
  const review = reviewSlots(job);
  el("review-stops").hidden = !(finished && review.length);
  el("review-stops").disabled = !state?.at_pad || !!state?.busy;
  el("next-inspection").disabled = !!state?.busy;
  html("history", state?.history?.length ? state.history.map((item) => `<div class="history-item"><a target="_blank"
    rel="noopener" href="${safe(item.url)}">${safe(item.run)}</a><span>${item.confirmed}/${item.total}</span></div>`).join("")
    : '<p class="footnote">Completed reports will appear here.</p>');
  el("review").hidden = view !== "results" || !job;
  if (view !== "results" || !job) return;
  put("results-note", result ? "Inventory results as returned by the API." : "Waiting for the final API snapshot.");
  const selected = new Set(job.slots);
  const rows = new Map((result?.rows || []).map((row) => [row.slot_id, row]));
  const captures = new Map(reports.map((report) => [report.slot_id, report]));
  html("result-rows", Object.keys(layout.slots).map((slot) => {
    const observed = status.confirmed?.[slot];
    const row = rows.get(slot);
    const evidence = captures.get(slot);
    const stopped = status.missed?.includes(slot);
    const progress = !selected.has(slot) ? "Outside scope" : observed ? "Confirmed" : stopped ? "Missed"
      : status.visited?.includes(slot) ? "Visited" : "Planned";
    const outcome = row?.outcome;
    const reading = observed ? `${label(observed.occupancy)} · ${label(observed.label_status)}` : "—";
    return `<tr><th scope="row">${slot}</th><td><span class="label ${observed ? "good" : stopped ? "warn" : ""}">${progress}</span></td>
      <td>${safe(observed?.pallet_id || "—")}</td><td>${safe(reading)}</td>
      <td>${safe(outcome === "pending" ? "Pending comparison" : label(outcome) || "—")}</td>
      <td>${evidence ? `<span class="label ${evidence.status === "DAMAGED" ? "bad" : "good"}">${safe(evidence.status)}</span>` : "—"}</td></tr>`;
  }).join(""));
  html("findings", reports.filter((report) => report.status === "DAMAGED").map((report) => {
    const photo = `/evidence/${encodeURIComponent(job.inspection_id)}/${encodeURIComponent(report.quality_id)}/annotated.png`;
    return `<a class="finding" target="_blank" rel="noopener" href="${photo}">
      <img src="${photo}" alt="Damage evidence for ${safe(report.slot_id)}">
      <strong>${safe(report.slot_id)} · ${safe(report.pallet_id || "Unreadable pallet")}</strong><small>${safe(report.reason)}</small></a>`;
  }).join(""));
}

function reviewSlots(job) {
  if (!job) return [];
  const status = job.status;
  const problems = Object.values(status.confirmed || {}).filter((event) =>
    event.occupancy === "uncertain" || event.label_status === "unreadable").map((event) => event.slot_id);
  return [...new Set([...(status.missed || []), ...problems, ...(job.result?.discrepancies || []).map((row) => row.slot_id)])];
}

function drawSafety() {
  const enabled = !!layout.safety_fields;
  el("safety-banner").hidden = el("warehouse-safety").hidden = !enabled;
  if (!enabled) return;
  const status = state?.safety;
  const alarm = status?.alarm;
  const zones = status?.zones || {};
  const awaiting = status?.phase === "PREPARING";
  const selected = (preview?.required_zones || []).map(id => zones[id]).filter(Boolean);
  const unavailable = !status || status.sensor !== "FRESH" || !status.signals_online;
  const occupied = selected.filter(zone => zone.occupied).map(zone => zone.label);
  let title = "Ready to request inspection";
  let message = "Selected zones clear • Verify access before dispatch.";
  let style = "open";
  if (alarm) {
    title = alarm.event === "intrusion" ? "Safety alert · Intrusion detected" : "Safety alert · Access restricted";
    message = alarm.message + " " + status.message;
    style = alarm.event === "intrusion" ? "intrusion" : "fault";
  } else if (awaiting) {
    title = `Preparing inspection · ${status.countdown.toFixed(1)} s`;
    message = status.message;
    style = "preparing";
  } else if (status?.phase === "RESERVED") {
    title = "Drone inspection · Zones reserved";
    message = status.message;
    style = "reserved";
  } else if (status?.phase === "REJECTED") {
    title = "Inspection blocked";
    message = status.message;
    if (!unavailable && !occupied.length) message += " Clear now. Request a new inspection when ready.";
    style = "fault";
  } else if (unavailable || occupied.length) {
    title = "Hold · Selected scope unavailable";
    message = unavailable ? "Waiting for verified sensor and signal data." : `Worker present · ${occupied.join(", ")}`;
    style = "fault";
  } else if (status.phase === "RELEASED") {
    title = "Inspection completed · Access restored";
    message = status.message;
  } else if (!selected.length) {
    title = "Choose an inspection scope";
    message = "Required zones follow the planned flight path.";
  }
  el("safety-banner").dataset.access = style;
  put("safety-headline", title);
  put("safety-message", message);
  put("sensor-state", status?.sensor === "FRESH" ? "Presence feed live" : status?.sensor === "STALE" ? "Presence feed stale" : "Presence unknown");
  el("sensor-state").classList.toggle("good", status?.sensor === "FRESH");
  const byName = { A: "Aisle A", B: "Aisle B", T: "Transfer corridor & pad", C: "Aisle C" };
  html("safety-zones", ["A", "B", "T", "C"].map(id => {
    const zone = zones[id];
    const state = zone?.state || (id === "C" ? "UNMONITORED" : "FAULT");
    const detected = zone?.occupied === true ? "Worker present" : zone?.occupied === false ? "Clear field" : "Unknown presence";
    return `<div class="safety-zone access-${state.toLowerCase()}">
      <strong>${byName[id]}</strong><span class="access-label"><i></i>${label(state)}</span>
      <small>${id === "C" ? "Decorative aisle" : detected + (zone?.signals_acknowledged ? " · lights confirmed" : " · awaiting lights")}</small></div>`;
  }).join(""));
  const reservations = (status?.required || []).map(id => zones[id]?.label).filter(Boolean);
  put("zone-reservations", reservations.length ? `Restricted scope · ${reservations.join(", ")}` : "No active reservation.");
  html("safety-history", (status?.events || []).slice(0, 12).map(event =>
    `<li><time datetime="${safe(event.time)}">${safe(new Date(event.time).toLocaleTimeString())}</time>
      <div><b>${safe(label(event.event))}</b><span>${safe(event.message)}</span>
      <small>${safe(event.inspection_id || "")}</small></div></li>`).join(""));
  el("safety-overview").hidden = !state?.overview;
  el("overview-unavailable").hidden = !!state?.overview;
}

function draw() {
  if (!layout) return;
  const job = state?.mission;
  const status = job?.status || {};
  const stage = job?.stage;
  const robot = el("robot-state"), backend = el("api-state");
  robot.textContent = state?.robot ? (state.at_pad ? "Drone at pad" : "Drone connected") : "Drone offline";
  robot.classList.toggle("good", !!state?.robot);
  backend.textContent = state?.backend.online ? (state.backend.mode === "fixture" ? "Mock API online" : "Warehouse API online") : "Inventory API offline";
  backend.classList.toggle("good", !!state?.backend.online);
  put("run-state", stage ? stage.replaceAll("_", " ") : "AWAITING DISPATCH");
  el("run-state").classList.toggle("active", !!stage && !terminal.has(stage));
  put("planned-total", preview?.slots.length ?? "—");
  put("plan-distance", preview ? `${preview.distance.toFixed(1)} m planned` : "—");
  const missing = preview?.slots.filter((slot) => !state?.backend.slots.includes(slot)) || [];
  let reason = "";
  if (state?.busy || dispatching) reason = "An inspection is in progress or its report is being prepared.";
  else if (!preview) reason = "Select at least one functional location.";
  else if (!state?.robot) reason = "Waiting for drone odometry.";
  else if (!state.at_pad) reason = "Drone is away from the pad. After an abort, restart the simulator before dispatch.";
  else if (layout.safety_fields && !state.safety) reason = "Waiting for the Safety Manager.";
  else if (state?.safety?.phase === "RECOVERY") reason = "Operator recovery required before dispatch.";
  else if (!state.backend.online) reason = "Waiting for the inventory API.";
  else if (missing.length) reason = "Inventory API profile lacks locations in this plan.";
  el("start").disabled = !!reason;
  put("dispatch-help", reason || "Drone ready on launch pad.");
  put("camera-caption", state?.camera ? (state.camera_type === "annotated" ? "Live perception overlay" : "Live reference camera") : "Waiting for a live frame");
  put("camera-kind", state?.camera_type === "annotated" ? "DETECTIONS" : "ROS 2");
  el("camera").hidden = !state?.camera;
  el("no-camera").hidden = !!state?.camera;
  put("active-target", status.target || "—");
  put("position-value", state?.robot && state.position ? state.position.slice(0, 3).map((p) => p.toFixed(2)).join(" / ") : "—");
  put("live-detail", job?.error || status.detail || "Start an inspection to monitor progress.");
  el("abort").disabled = !job || terminal.has(stage);
  put("metric-planned", (view === "plan" ? preview?.slots.length : job?.slots.length) ?? "—");
  put("metric-visited", job ? (status.visited || []).length : "—");
  put("metric-confirmed", job ? Object.keys(status.confirmed || {}).length : "—");
  put("metric-damaged", job?.quality ? new Set(job.evidence.filter((r) => r.status === "DAMAGED").map((r) => r.slot_id + "/" + r.pallet_id)).size : "—");
  put("metric-time", job ? `${(status.elapsed_seconds || 0).toFixed(1)} s` : "—");
  drawMap(job);
  drawSafety();
  drawResults(job);
}

async function poll() {
  try {
    state = await api("/api/state");
    const job = state.mission;
    if (job && (!wantedRun || job.inspection_id === wantedRun)) {
      if (job.inspection_id !== lastRun) {
        lastRun = job.inspection_id;
        lastStage = null;
        wantedRun = null;
        if (!terminal.has(job.stage)) setView("live");
      }
      if (terminal.has(job.stage) && lastStage !== job.stage && view === "live") setView("results");
      lastStage = job.stage;
    }
    draw();
  } catch (error) {
    notice(error.message);
    state = null;
    draw();
  }
  setTimeout(poll, 350);
}

async function init() {
  layout = await api("/api/layout");
  el("warehouse-map").classList.toggle("has-safety", !!layout.safety_fields);
  drawLayout();
  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => setView(tab.dataset.view));
  el("mode-options").addEventListener("change", (event) => { choices.mode = event.target.value; changePlan(); });
  el("quality").addEventListener("change", (event) => { choices.quality = event.target.checked; changePlan(); });
  el("aisle-options").addEventListener("click", (event) => {
    if (event.target.dataset.aisle && !event.target.disabled) toggleAisle(event.target.dataset.aisle);
  });
  el("slot-options").addEventListener("click", (event) => {
    if (event.target.dataset.slot) toggleSlot(event.target.dataset.slot);
  });
  el("start").addEventListener("click", async () => {
    dispatching = true; notice(); draw();
    try {
      wantedRun = (await api("/api/start", selection())).inspection_id;
      setView("live");
    } catch (error) { notice(error.message); }
    finally { dispatching = false; draw(); }
  });
  el("abort").addEventListener("click", async () => {
    try {
      await api("/api/abort", { inspection_id: state.mission.inspection_id });
      notice("Abort sent to Mission Manager. Waiting for acknowledgement.");
    } catch (error) { notice(error.message); }
  });
  el("review-stops").addEventListener("click", () => {
    choices.mode = "custom"; choices.slots = new Set(reviewSlots(state.mission)); setView("plan"); changePlan();
  });
  el("next-inspection").addEventListener("click", () => {
    choices.mode = "aisle"; choices.aisles.clear(); choices.slots.clear(); setView("plan"); changePlan();
  });
  el("worker-controls").addEventListener("click", async (event) => {
    const target = event.target.dataset.worker;
    if (!target) return;
    try {
      await api("/api/simulation/worker", { target });
      put("worker-message", "Movement requested. Watch the live model and presence status.");
    } catch (error) {
      put("worker-message", error.message);
    }
  });
  const camera = el("camera");
  camera.onload = camera.onerror = () => { cameraLoading = false; };
  setInterval(() => {
    if (view === "live" && state?.camera && !cameraLoading) {
      cameraLoading = true;
      camera.src = "/api/frame.jpg?t=" + Date.now();
    }
  }, 155);
  if (layout.safety_fields) {
    const overview = el("safety-overview");
    overview.onload = overview.onerror = () => { overviewLoading = false; };
    setInterval(() => {
      if (state?.overview && !overviewLoading) {
        overviewLoading = true;
        overview.src = "/api/overview.jpg?t=" + Date.now();
      }
    }, 225);
  }
  changePlan();
  poll();
}
init().catch((error) => notice(error.message));
