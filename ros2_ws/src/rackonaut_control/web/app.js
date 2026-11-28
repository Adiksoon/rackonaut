import { createIntelligence } from "/business.js";
import { createService } from "/service.js";
import { createManual } from "/manual.js";
import { createTeaching } from "/teaching.js";
import { createRouteReview } from "/route.js";
import { activeMission, activeSafetyAlarm, batteryPercent, droneProfile, missionPhase, operatorState,
  percentagePoints, returnEnergy, terminal } from "/operator.js";

"use strict";

const el = (name) => document.getElementById(name);
const label = (value) => String(value || "").toLowerCase().replaceAll("_", " ").replace(/^./, (c) => c.toUpperCase());
const safe = (value) => String(value ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const choices = { mode: "aisle", aisles: new Set(["A"]), slots: new Set(), quality: true, adaptive: false };
const inspectionStages = ["INSPECT", "REINSPECT", "QUALITY_CLOSEUP", "REPOSITION", "RECENTER"];
const retryReasons = { initial: "Reference view", unreadable: "Unreadable label",
  uncertain: "Uncertain occupancy", missing: "No reading", damage: "Damage close-up",
  damage_closeup_unconfirmed: "Close-up unconfirmed" };
const headings = {
  plan: ["Plan inspection", ""],
  live: ["Live flight", ""],
  manual: ["Manual Control", ""],
  results: ["Inspection results", ""],
  diagnostics: ["Diagnostics", "Check live telemetry, safety zones and simulator controls."],
  service: ["Service", ""],
  route: ["Learned Flight Route", "Review the measured route from dock to inspection and back."],
  configuration: ["Warehouse preview", ""],
};
const service = createService({
  openWarehouse(configuration) {
    previewSource = {kind: "warehouse", id: configuration.manifest.configuration_id};
    setView("route", true);
    routeReview.openArchive(configuration);
  },
  openPreview(configuration) {
    previewSource = {kind: "warehouse", id: configuration.configuration_id};
    put("configuration-preview-name", configuration.name);
    setView("configuration", true);
  },
  openPlan() { setView("plan", true); },
  sessionChanged() {
    warehouseRequest = null;
    warehouseConfiguration = null;
    for (const key of visualCache.keys()) if (key.startsWith("/api/service/")) visualCache.delete(key);
    if (layout?.learned_warehouse) changePlan();
  },
});
const manual = createManual(api, terminal, notice);
const teaching = createTeaching(() => drawTwin(state?.mission), focusTaughtLocation);
const routeReview = createRouteReview(api, (event) => {
  if (event === "approved" && previewSource?.kind === "calibration") {
    visualCache.delete("/api/service/visualization/calibration/" + previewSource.id);
    loadTwin("model");
  }
  drawTwin(state?.mission);
});
let layout, preview, state, wantedRun, lastRun, lastStage, intelligence;
let view = "plan";
let serviceTab = "management", lastPose = null;
let resultsMap = false;
let locatedReport = null;
let stopping = false;
let dispatching = false;
let version = 0;
let previewPending = false, previewError = "";
let cameraLoading = false;
let overviewLoading = false;
let twin = null, twinLoading = false, show3D = false, focusedLocation = null;
let mapMode = "2d", mapIntent = "2d";
let warehouseConfiguration = null, warehouseRequest = null, warehouseError = "", warehouseLocked = false;
let learnedStops = new Set();
const learnedGroups = new Map();
let replanLocations = null;
let emergencyTarget = null, connectionLost = false;
let previewSource = null, businessRun = null, businessOutcomes = {}, fittedFocus = null;
let showFittedDetails = false;
const visualCache = new Map();

function put(id, value) {
  const element = el(id);
  if (element.textContent !== String(value)) element.textContent = value;
}
function html(id, value) { if (el(id).innerHTML !== value) el(id).innerHTML = value; }
function notice(value = "") { put("notice", value); el("notice").hidden = !value; }
function connectionStatus(value = "") {
  put("connection-status", value);
  el("connection-status").hidden = !value;
}

function chooseMap(mode) {
  mapMode = mapIntent = mode;
  const unavailable = mode === "scan" && layout.localization?.mode !== "sensor_based"
    && !visualRequest(state?.mission).archiveScan;
  show3D = mode !== "2d" && !unavailable;
  el("workspace").dataset.mapMode = mode;
  el("scan-window-actions").hidden = mode === "2d" || unavailable;
  el("warehouse-map").toggleAttribute("hidden", mode !== "2d");
  el("map-legend").hidden = mode !== "2d";
  el("twin-panel").hidden = !show3D;
  el("twin-error").hidden = !unavailable;
  if (unavailable) put("twin-error", "3D Scan is unavailable in this profile. Run Full Robotics with sensor-based localization.");
  for (const [id, key] of [["map-2d", "2d"], ["map-3d", "model"], ["map-scan", "scan"]]) {
    el(id).setAttribute("aria-pressed", String(key === mode));
  }
  put("map-title", mode === "scan" ? "LiDAR Scan" : mode === "model" ? "Warehouse Digital Twin" : "Warehouse floor");
  twin?.setMode(mode);
  drawWorkspace();
  twin?.setVisible(show3D && !el("warehouse-panel").hidden);
  drawTwin(state?.mission);
}
function twinError(message) {
  if (visualRequest(state?.mission).required) message = "The 3D view is unavailable. Reload Control Center to try again.";
  else chooseMap("2d");
  el("visual-status").hidden = true;
  put("twin-error", message);
  el("twin-error").hidden = false;
}
async function loadTwin(mode = "model") {
  mapIntent = mode;
  if (mode === "scan" && layout.localization?.mode !== "sensor_based"
      && !visualRequest(state?.mission).archiveScan) { chooseMap(mode); return; }
  el("twin-error").hidden = true;
  if (twin) { chooseMap(mode); return; }
  if (visualRequest(state?.mission).required) {
    chooseMap(mode);
    put("visual-status", "Loading the surveyed warehouse…");
    el("visual-status").hidden = false;
  }
  if (twinLoading) return;
  twinLoading = true;
  el("map-3d").disabled = el("map-scan").disabled = true;
  try {
    const { createTwin } = await import("/twin.js");
    twin = createTwin(layout, {
      onAisle: toggleAisle,
      onSlot: toggleSlot,
      onTaughtLocation: async id => {
        if (view === "route") {
          if (scanFullscreen()) await leaveScanFullscreen();
          const record = routeReview.select(id);
          if (record) twin?.focusTaughtLocation(record.position_m);
        } else teaching.select(id);
      },
      onFittedLocation: selectFittedLocation,
      onReinspect: id => planLocations([id]),
      onError: (message) => { twinError(message); twin = null; el("map-3d").disabled = true; },
    });
    if (focusedLocation) twin.focusSlot(focusedLocation);
    chooseMap(mapIntent);
  } catch (error) {
    twinError("3D view could not start. Use the 2D Warehouse Map.");
    console.warn(error);
  } finally {
    twinLoading = false;
    el("map-3d").disabled = !layout.scene;
    el("map-scan").disabled = false;
  }
}
function visualRequest(job) {
  if (["route", "configuration"].includes(view) && previewSource) {
    const {kind, id} = previewSource;
    return {required: true, url: `/api/service/visualization/${kind}/${id}`, archiveScan: view === "configuration"};
  }
  if (view === "manual" && (job?.mapping_id || state?.localization?.mapping_id)
      && state?.service_mode !== "PRODUCTION") return {};
  const run = view === "results" ? businessRun || locatedReport || (job?.mode !== "manual" ? job?.inspection_id : null)
    : view === "live" && job?.mode === "learned" ? job.inspection_id : null;
  const archivedLearned = view === "results" && state?.history.some(row => row.run === run && row.warehouse_configuration_id);
  const currentLearned = job?.inspection_id === run && job?.mode === "learned";
  if (run && (currentLearned || archivedLearned)) {
    return {required: true, url: `/api/visualization/run/${run}`, archiveScan: true, showFlight: view === "live"};
  }
  if (!layout?.learned_warehouse || view === "results") return {};
  const identifier = state?.warehouse?.active_id;
  return {required: true, url: identifier ? "/api/visualization/active" : null,
    identity: identifier, archiveScan: true, showFlight: ["live", "manual"].includes(view)};
}

function readVisualization(visual) {
  if (!visual.url) return {status: "Activate a saved warehouse to see its Digital Twin."};
  const key = visual.url;
  let entry = visualCache.get(key);
  if (!entry || entry.identity !== visual.identity) {
    entry = {identity: visual.identity, retry: 0, status: "Preparing the surveyed warehouse…"};
    visualCache.set(key, entry);
    if (visualCache.size > 8) visualCache.delete(visualCache.keys().next().value);
  }
  if (!entry.pending && !entry.packet && Date.now() >= entry.retry) {
    entry.pending = true;
    fetch(key, {cache: "no-store", signal: AbortSignal.timeout(6000)})
      .then(async response => {
        if (response.status === 202) { entry.retry = Date.now() + 1700; return; }
        if (!response.ok) {
          entry.status = response.status === 401 ? "Unlock Service to view this calibration."
            : response.status === 404 ? "No surveyed model is available for this warehouse revision."
            : "The surveyed warehouse could not be loaded.";
          entry.retry = Date.now() + 10000;
          return;
        }
        const packet = await response.json();
        if (visual.identity && packet.binding.configuration_id !== visual.identity) {
          entry.retry = Date.now() + 1700;
          return;
        }
        entry.packet = packet;
      }).catch(() => {
        entry.retry = Date.now() + 3000;
        entry.status = "Waiting for the warehouse visualization service…";
      }).finally(() => {
        entry.pending = false;
        if (visualCache.get(key) === entry) drawTwin(state?.mission);
      });
  }
  return entry;
}

function selectFittedLocation(id) {
  if (view === "plan") {
    const record = warehouseConfiguration?.locations.find(row => row.storage_location_id === id);
    if (record) toggleLearned(record.record_id);
    return;
  }
  fittedFocus = id;
  showFittedDetails = true;
  if (view === "results") intelligence.selectLocation(id);
  drawTwin(state?.mission);
}

function showVisualizationDetails(visual, entry) {
  const packet = entry.packet;
  if (view === "plan" && layout.learned_warehouse) drawLearnedGroups(packet);
  const locations = packet?.enhanced.locations || [];
  const pending = el("visual-status");
  const partialRows = packet?.enhanced.rows.filter(row => row.partial).length || 0;
  const coverage = mapMode === "model" && partialRows
    ? `${partialRows} partially observed rack ${partialRows === 1 ? "row" : "rows"} · Showing measured shelf levels` : "";
  pending.hidden = !coverage && (!visual.required || !!packet || (mapMode === "scan" && !visual.archiveScan));
  put("visual-status", coverage || entry.status || "");
  el("visual-locations").hidden = !locations.some(location => location.status === "unplaced");
  html("unplaced-options", locations.filter(row => row.status === "unplaced").map(row =>
    `<button class="chip" type="button" data-location="${safe(row.id)}"
    ${view === "plan" && !visual.interactive ? "disabled" : ""}
    aria-pressed="${visual.selected.has(row.id)}">${safe(row.id)}</button>`).join(""));
  const item = showFittedDetails && locations.find(location => location.id === fittedFocus);
  el("visual-location-detail").hidden = !item;
  if (!item) return;
  const outcome = view === "results" ? visual.outcomes[item.id] : null;
  put("visual-location-title", item.id);
  put("visual-location-caption", [outcome?.label, item.status === "unplaced" ? "Shelf location unconfirmed"
    : item.status === "estimated" ? "Estimated rack face" : "Measured rack face",
  item.rack_id, item.level ? "Level " + item.level : ""].filter(Boolean).join(" · "));
  const photo = el("visual-location-photo");
  photo.hidden = !item.photo_jpeg;
  if (item.photo_jpeg) {
    const source = "data:image/jpeg;base64," + item.photo_jpeg;
    if (photo.getAttribute("src") !== source) photo.src = source;
  } else photo.removeAttribute("src");
}

function flightTarget(job) {
  const status = job?.status;
  if (job?.mode !== "learned" || terminal.has(job.stage) || inspectionStages.includes(status?.stage)
      || (status?.stage === "LEARNED_INSPECTION" && job.slots.includes(status.target))) return status?.target;
  return job.slots.find(id => !status?.visited?.includes(id) && !status?.confirmed?.[id]
    && !status?.missed?.includes(id)) || "PAD";
}

function drawTwin(job) {
  if (!twin || !show3D || el("warehouse-panel").hidden) return;
  const visual = visualRequest(job);
  const specimen = visual.required ? readVisualization(visual) : {};
  const selectedLearned = new Set(warehouseConfiguration?.locations.filter(row => learnedStops.has(row.record_id))
    .map(row => row.storage_location_id) || []);
  const visualization = {...visual, packet: specimen.packet, selected: selectedLearned,
    interactive: !!warehouseConfiguration && state?.warehouse?.ready,
    outcomes: view === "results" ? businessOutcomes : {}, focus: fittedFocus, target: flightTarget(job)};
  showVisualizationDetails(visualization, specimen);
  drawMapCaption();
  if (view === "results" && locatedReport && job?.inspection_id !== locatedReport) job = null;
  const selected = layout.learned_warehouse ? [] : Object.keys(layout.slots).filter((slot) => choices.mode === "full"
    || (choices.mode === "custom" ? choices.slots.has(slot) : choices.aisles.has(layout.slots[slot].aisle)));
  const review = view === "route" ? routeReview.display() : null;
  twin.update({ state, lastPose, view, preview, job, activeFlight: activeMission(job), selection: new Set(selected),
    visualization, review, taught: review ? review.locations : view === "manual" ? teaching.locations() : [],
    taughtSelection: review ? review.selectedLocation : teaching.selection() });
}

async function focusTaughtLocation(record) {
  if (scanFullscreen()) await leaveScanFullscreen();
  await loadTwin("scan");
  twin?.focusTaughtLocation(record.position_m);
  el("teaching-details").scrollIntoView({ block: "nearest" });
}

async function api(url, data) {
  const response = await fetch(url, data === undefined ? {
    cache: "no-store", ...(url === "/api/state" ? {signal: AbortSignal.timeout(3000)} : {}),
  } : {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
  });
  const body = await response.json();
  if (!response.ok) throw new Error(body.error || "Control service unavailable.");
  return body;
}

function drawWorkspace() {
  const showMap = ["plan", "live", "route", "configuration"].includes(view) ||
    (view === "manual" && el("camera-expand").getAttribute("aria-pressed") !== "true") ||
    (view === "results" && resultsMap);
  const warehouse = el("warehouse-panel");
  if (warehouse.hidden === showMap) {
    warehouse.hidden = !showMap;
    twin?.setVisible(showMap && show3D);
  }
  if ((!showMap || view === "service" || view === "diagnostics") && scanFullscreen()) leaveScanFullscreen();
  el("workspace").classList.toggle("with-map", showMap);
  el("workspace").dataset.surveyed = String(visualRequest(state?.mission).required);
  el("operator-map-legend").hidden = !showMap || mapMode !== "model" ||
    (view === "plan" ? !preview?.points.length : view !== "live" || !activeMission(state?.mission));
  el("operator-flown-key").hidden = view !== "live";
  el("results-map").setAttribute("aria-expanded", String(resultsMap));
  el("business-map").setAttribute("aria-expanded", String(resultsMap));
  put("results-map", resultsMap ? "Back to findings" : "Warehouse map");
  el("results-close-map").hidden = view !== "results" || !resultsMap;
  drawMapCaption();
}

function openServiceTab(tab) {
  serviceTab = tab;
  setView(tab === "manual" ? "manual" : "service", true);
}

function drawMapCaption() {
  const visual = visualRequest(state?.mission);
  if (visual.required && (mapMode !== "scan" || visual.archiveScan)) {
    const artifact = visualCache.get(visual.url)?.packet;
    put("map-caption", (artifact ? `${artifact.name} · Revision ${artifact.binding.revision} · ` : "")
      + (mapMode === "scan" ? "Saved LiDAR measurements" : "Surveyed positions · Fitted rack templates"));
    return;
  }
  const scanSource = view === "route" || state?.localization?.source === "learned_map" ? "Saved measured map"
    : state?.localization?.state === "TRACKING" ? "Accumulated LiDAR measurements" : "Last measured snapshot";
  put("map-caption", mapMode === "scan" ? scanSource : mapMode === "model" ? "Reference model of the warehouse"
    : view === "plan" ? (layout?.learned_warehouse ? "Reference floor plan · measured location markers" : "Reference floor plan · select aisles or locations")
    : view === "results" ? (locatedReport && state?.mission?.inspection_id !== locatedReport ? "Reference floor plan · selected location" : "Reference floor plan · planned and flown route")
    : "Reference floor plan · drone and flight path");
}

function scanFullscreen() { return document.fullscreenElement === el("warehouse-panel"); }

async function leaveScanFullscreen() {
  try { await document.exitFullscreen(); }
  catch (error) { notice(`Could not exit full screen. ${error.message}`); }
}

function setView(next, focus = false) {
  if (next === "results" && view !== next) {
    resultsMap = false;
    locatedReport = null;
    businessRun = null;
    businessOutcomes = {};
  }
  showFittedDetails = false;
  fittedFocus = null;
  view = next;
  if (next === "manual") serviceTab = state?.service_mode !== "PRODUCTION" && state?.localization?.mapping_id
    ? "calibration" : "manual";
  el("workspace").dataset.view = next;
  el("workspace").hidden = next === "diagnostics" || next === "service";
  el("system-details").hidden = next !== "diagnostics";
  el("route-panel").hidden = next !== "route";
  el("configuration-preview").hidden = next !== "configuration";
  el("service-nav").hidden = !["service", "manual", "route", "configuration"].includes(next);
  for (const button of el("service-nav").querySelectorAll("button")) {
    if (button.dataset.serviceView === serviceTab) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  service.show(next === "service", serviceTab);
  manual.show(next === "manual");
  drawWorkspace();
  for (const [name, panel] of [["plan", "plan-panel"], ["live", "live-panel"], ["results", "results-panel"]]) {
    el(panel).hidden = name !== next && !(name === "live" && next === "manual");
  }
  for (const button of document.querySelectorAll(".tab")) {
    const active = button.dataset.view === next || (["route", "manual", "configuration"].includes(next) && button.dataset.view === "service");
    button.classList.toggle("active", active);
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  const serviceTitles = {management:"Drone Management", calibration:"Warehouse Calibration", configuration:"Warehouse Configuration"};
  put("page-title", next === "service" ? serviceTitles[serviceTab] : headings[next][0]);
  put("page-description", headings[next][1]);
  el("page-description").hidden = !headings[next][1];
  if (next === "plan" && layout.learned_warehouse) {
    warehouseRequest = null;
    syncLearnedPlan();
  }
  if (next === "route" || (next === "manual" && state?.localization?.mapping_id
    && state?.service_mode !== "PRODUCTION")) loadTwin("scan");
  else if (["configuration", "live", "manual"].includes(next) || (next === "plan" && layout.learned_warehouse)
    || next === "results" && resultsMap) loadTwin("model");
  draw();
  if (next === "results") intelligence.update(state, canReinspect);
  if (focus) el("page-title").focus();
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
    + text(p.x, p.y - .28, "H", "pad-letter") + text(p.x - 1.5, p.y - 1.8, layout.dock ? "CHARGING DOCK" : "LAUNCH PAD", "pad-caption"));
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
  if (layout.laser_fields) {
    html("laser-fields", Object.entries(layout.laser_fields).map(([id, scanner]) => {
      const [left, bottom, right, top] = scanner.field;
      const [x, y] = scanner.pose;
      const [px, py] = point(x, y);
      return rect(left, bottom, right - left, top - bottom, "laser-outline")
        + `<circle class="laser-mount" cx="${px}" cy="${py}" r="5"/>`
        + text(x - .60, y - .30, id, "laser-label");
    }).join(""));
  }
}

function drawScans() {
  if (!layout.laser_fields) return;
  const scans = state?.safety?.scans || {};
  html("laser-returns", Object.entries(scans).map(([zone, scan]) => {
    const [originX, originY] = point(...layout.laser_fields[zone].pose);
    const rays = scan.points.filter((_, index) => index % 5 === 0).map(([x, y]) => {
      const [px, py] = point(x, y);
      return `M${originX} ${originY}L${px} ${py}`;
    }).join("");
    const dots = (points, radius, style) => points.map(([x, y]) => {
      const [px, py] = point(x, y);
      return `<circle class="${style}" cx="${px}" cy="${py}" r="${radius}"/>`;
    }).join("");
    return `<path class="laser-beams" d="${rays}"/>`
      + dots(scan.points, 1.12, "laser-return") + dots(scan.hits, 2.4, "laser-hit");
  }).join(""));
}

function toggleAisle(id) {
  if (view !== "plan" || layout.learned_warehouse) return;
  choices.mode = "aisle";
  choices.aisles.has(id) ? choices.aisles.delete(id) : choices.aisles.add(id);
  changePlan();
}
function toggleSlot(slot) {
  focusedLocation = slot;
  twin?.focusSlot(slot);
  if (view !== "plan" || layout.learned_warehouse) return;
  if (choices.mode !== "custom") choices.slots.clear();
  choices.mode = "custom";
  choices.slots.has(slot) ? choices.slots.delete(slot) : choices.slots.add(slot);
  changePlan();
}
function selection() {
  if (layout.learned_warehouse) return {mode: "learned", configuration_id: warehouseConfiguration?.manifest.configuration_id,
    revision: warehouseConfiguration?.manifest.revision, record_ids: [...learnedStops]};
  return { mode: choices.mode, aisles: [...choices.aisles], slots: [...choices.slots],
    quality: choices.quality, adaptive: choices.adaptive };
}

function toggleLearned(id) {
  learnedStops.has(id) ? learnedStops.delete(id) : learnedStops.add(id);
  changePlan();
}

function drawLearnedGroups(packet = visualCache.get("/api/visualization/active")?.packet) {
  learnedGroups.clear();
  const add = (name, id) => {
    if (!learnedGroups.has(name)) learnedGroups.set(name, new Set());
    learnedGroups.get(name).add(id);
  };
  const placed = new Map((packet?.enhanced.locations || []).filter(item => item.status === "projected" && item.rack_id)
    .map(item => [item.id, item.rack_id]));
  for (const row of warehouseConfiguration?.locations || []) {
    const aisle = layout.slots[row.storage_location_id]?.aisle;
    if (aisle) add("Aisle " + aisle, row.record_id);
    const rack = placed.get(row.storage_location_id);
    if (rack) add("Rack row " + rack, row.record_id);
  }
  html("learned-groups", [...learnedGroups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([name, ids]) => {
    const count = [...ids].filter(id => learnedStops.has(id)).length;
    return `<button type="button" class="chip" data-group="${safe(name)}"
      aria-pressed="${count === ids.size ? "true" : count ? "mixed" : "false"}">${safe(name)} <small>${ids.size}</small></button>`;
  }).join(""));
}

function canReinspect(id) {
  if (!id) return false;
  if (!layout.learned_warehouse) return !!layout.slots[id];
  if (!state?.warehouse?.active_id) return false;
  if (warehouseConfiguration?.manifest.configuration_id !== state.warehouse.active_id) return true;
  return warehouseConfiguration.locations.some(row => row.storage_location_id === id);
}

async function reinspectLocation(id) {
  if (layout.learned_warehouse) {
    const active = state?.warehouse?.active_id;
    if (!active) throw new Error("Activate a saved warehouse before planning a reinspection.");
    if (warehouseConfiguration?.manifest.configuration_id !== active) {
      const config = await service.planConfiguration(active);
      if (!config) throw new Error("Unlock Service before planning a reinspection in the learned warehouse.");
      if (active !== state?.warehouse?.active_id) throw new Error("The active warehouse changed. Select the location again.");
      warehouseConfiguration = config;
    }
    if (!canReinspect(id)) throw new Error("This location has not been taught in the active warehouse.");
  }
  planLocations([id]);
}

function planLocations(ids) {
  notice();
  if (layout.learned_warehouse) {
    if (warehouseConfiguration) {
      learnedStops = new Set(warehouseConfiguration.locations.filter(row => ids.includes(row.storage_location_id)).map(row => row.record_id));
    } else replanLocations = ids;
  } else {
    choices.mode = ids.length ? "custom" : "aisle";
    choices.slots = new Set(ids);
    choices.aisles.clear();
  }
  setView("plan", true);
  changePlan();
  if (layout.learned_warehouse && warehouseConfiguration && ids.length && learnedStops.size !== new Set(ids).size)
    notice("Only locations taught in the active warehouse can be selected for reinspection.");
}

async function syncLearnedPlan() {
  const identifier = state?.localization?.warehouse_id;
  if (view !== "plan" || !layout.learned_warehouse || !identifier || !state.localization.warehouse_ready) return;
  if (warehouseRequest?.id === identifier && Date.now() < warehouseRequest.until) return;
  const request = {id: identifier, until: Date.now() + 60000};
  warehouseRequest = request;
  try {
    const config = await service.planConfiguration(identifier);
    if (warehouseRequest !== request) return;
    const changed = config?.manifest.configuration_id !== warehouseConfiguration?.manifest.configuration_id;
    warehouseLocked = !config;
    warehouseError = "";
    warehouseConfiguration = config;
    if (config && (changed || replanLocations)) {
      learnedStops = new Set(config.locations.filter(row => !replanLocations || replanLocations.includes(row.storage_location_id))
        .map(row => row.record_id));
      replanLocations = null;
    } else if (!config) learnedStops.clear();
    if (changed || warehouseLocked || config && !preview && learnedStops.size) changePlan();
  } catch (error) {
    if (warehouseRequest !== request) return;
    warehouseConfiguration = null;
    warehouseError = error.message;
    warehouseLocked = false;
    changePlan();
  }
}

function changePlan() {
  notice();
  if (layout.learned_warehouse) {
    const locations = warehouseConfiguration?.locations || [];
    el("learned-options").hidden = !locations.length;
    el("learned-all").checked = !!locations.length && learnedStops.size === locations.length;
    el("learned-all").indeterminate = learnedStops.size > 0 && learnedStops.size < locations.length;
    html("learned-locations", '<legend class="sr-only">Registered locations</legend>' + locations.map(row =>
      `<label class="learned-choice"><input type="checkbox" value="${safe(row.record_id)}" ${learnedStops.has(row.record_id) ? "checked" : ""}>${safe(row.storage_location_id)}</label>`).join(""));
    drawLearnedGroups();
  } else {
  for (const radio of document.querySelectorAll("input[name='mode']")) radio.checked = radio.value === choices.mode;
  el("quality").checked = choices.quality;
  el("adaptive").checked = choices.adaptive;
  el("aisle-options").hidden = choices.mode !== "aisle";
  el("slot-options").hidden = choices.mode !== "custom";
  html("aisle-options", layout.aisles.map((row) => `<button class="chip" type="button" data-aisle="${row.id}"
    aria-pressed="${choices.aisles.has(row.id)}" ${row.functional ? "" : "disabled"}>Aisle ${row.id}${row.functional ? "" : " · decorative"}</button>`).join(""));
  html("slot-options", Object.keys(layout.slots).map((slot) => `<button class="chip" type="button" data-slot="${slot}"
    aria-pressed="${choices.slots.has(slot)}">${slot}</button>`).join(""));
  }
  const revision = ++version;
  preview = null;
  previewError = "";
  const chosen = selection();
  previewPending = chosen.mode === "full" || (chosen.mode === "aisle" && !!chosen.aisles.length) ||
    (chosen.mode === "custom" && !!chosen.slots.length) || (chosen.mode === "learned" &&
    !!chosen.configuration_id && !!chosen.record_ids.length);
  draw();
  if (!previewPending) return;
  api("/api/plan", chosen).then((plan) => {
    if (version === revision) { preview = {...plan, points: plan.display_points || plan.points}; previewPending = false; draw(); }
  }).catch((error) => {
    if (version === revision) { previewError = error.message; previewPending = false; draw(); }
  });
}

function drawMap(job) {
  if (view === "results" && locatedReport && job?.inspection_id !== locatedReport) job = null;
  const drawing = view === "plan" ? preview : job;
  const selected = new Set(drawing?.slots || []);
  const selectedAisles = new Set([...selected].map((slot) => layout.slots[slot]?.aisle).filter(Boolean));
  const status = view === "plan" ? {} : job?.status || {};
  const learned = view === "plan" && layout.learned_warehouse;
  el("warehouse-map").classList.toggle("learned-plan", learned);
  const locations = learned ? warehouseConfiguration?.locations || [] : [];
  html("learned-map-locations", locations.map(row => {
    const [x,y] = point(...row.position_m);
    return `<g class="learned-map-location ${learnedStops.has(row.record_id) ? "selected" : ""}" data-record="${safe(row.record_id)}" role="button" tabindex="0" aria-label="${safe(row.storage_location_id)}" aria-pressed="${learnedStops.has(row.record_id)}"><circle cx="${x}" cy="${y}" r="10"/><title>${safe(row.storage_location_id)}</title></g>`;
  }).join(""));
  const current = inspectionStages.includes(status.stage) ? status.target : null;
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
  if (layout.aerial) {
    const { nodes, edges, gates } = layout.aerial;
    const descents = state?.safety?.aerial?.descents || {};
    const overhead = edges.filter(([, , kind]) => kind === "tunnel").map(([from, to]) =>
      `<polyline class="aerial-axis" points="${[nodes[from], nodes[to]].map(([x, y]) => point(x, y).join(",")).join(" ")}"/>`);
    const access = Object.entries(gates).map(([id, [x, y, endX, endY]]) =>
      rect(x, y, endX - x, endY - y, `aerial-gate ${descents[id]?.cleared ? "clear" : ""}`, 'rx="3"')
      + text(x + .25, y - .32, `DESCENT ${id}`, "aerial-caption"));
    html("aerial-map", overhead.join("") + access.join(""));
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
  const returnPath = status.energy?.return_path;
  el("plan-line").setAttribute("points", line(view === "plan" ? preview?.points : returnPath?.length ? returnPath : job?.planned));
  el("flown-line").setAttribute("points", view === "plan" ? "" : line(job?.flown));
  const moves = status.adaptive?.moves || [];
  html("adaptive-lines", moves.map((move) =>
    `<polyline class="adaptive-line ${move.actual ? "" : "seeking"}" points="${line([move.from, move.actual || move.target])}"/>`
  ).join(""));
  el("adaptive-key").hidden = !moves.length;
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
  const confirmed = Object.keys(status.confirmed || {}).length;
  const reports = job?.evidence || [];
  const damage = reports.filter(report => report.status === "DAMAGED");
  const interrupted = job?.stage === "ABORTED";
  const calibrated = job?.stage === "INTERRUPTED_FOR_CALIBRATION";
  el("completion-id").hidden = !job;
  put("completion-id", job?.inspection_id || "");
  el("completion-text").classList.toggle("warning", interrupted || calibrated || !!job?.error || (!!finished && !status.landed));
  const interruption = status.detail === "Safety Manager heartbeat stopped"
    ? "The flight controller lost contact with the Safety Manager."
    : status.detail;
  const nextStep = layout.recovery ? "Open Emergency & Recovery to return to the dock."
    : "Restart the Rackonaut simulator before starting a new inspection.";
  put("completion-text", job?.error || (finished ? (interrupted
    ? ["Flight stopped.", interruption, !status.landed && nextStep].filter(Boolean).join(" ") + " "
    : calibrated ? "Inspection interrupted for calibration. Physical dock confirmed. "
    : status.landed ? "The drone landed safely. " : "Landing is unconfirmed. ")
    + (result ? "" : "Preparing the report.")
    : job ? "The inspection is in progress." : "Completed inspections and reports will appear here."));
  const reportLink = el("report-link");
  reportLink.hidden = !result;
  if (result) reportLink.href = result.url;
  el("damage-link").hidden = !damage.length;
  put("damage-link", `View ${damage.length} damage ${damage.length === 1 ? "photo" : "photos"} ↓`);
  const review = reviewSlots(job);
  el("result-counts").hidden = !finished;
  put("result-confirmed", `${confirmed} / ${job?.slots?.length || 0}`);
  put("result-review-count", review.length);
  put("result-damage-count", job?.quality ? damage.length : "—");
  el("result-attention").hidden = !finished || !review.length;
  put("result-attention", review.length ? `Check ${review.slice(0, 4).join(", ")}${review.length > 4 ? ` and ${review.length - 4} more` : ""}.` : "");
  el("results-map").hidden = !job;
  el("review-stops").hidden = !(finished && review.length);
  const recoveryPending = layout.recovery && state?.safety?.phase === "RECOVERY";
  const servicePending = state?.service_mode && state.service_mode !== "PRODUCTION";
  el("review-stops").disabled = !state?.at_pad || !!state?.busy || recoveryPending || servicePending;
  el("next-inspection").disabled = !!state?.busy || recoveryPending || servicePending;
  el("history-panel").hidden = !state?.history?.length;
  html("history", state?.history?.length ? state.history.map((item) => `<div class="history-item"><a target="_blank"
    rel="noopener" href="${safe(item.url)}">${safe(item.warehouse_name || "Inspection")} · ${safe(item.planned_slots?.join(" → ") || item.run)}</a>
    <span>${item.confirmed}/${item.total}</span></div>`).join("")
    : '<p class="footnote">Completed reports will appear here.</p>');
  const recoveries = state?.recovery_history || [];
  el("recovery-history").hidden = !recoveries.length;
  html("recovery-history-rows", recoveries.map((item) => `<div class="history-item"><a target="_blank"
    rel="noopener" href="${safe(item.url)}">${safe(item.recovery_id)}</a>
    <span>${safe(item.inspection_id)} · ${safe(item.result.replaceAll("_", " "))}</span></div>`).join(""));
  el("review").hidden = view !== "results" || !job;
  if (view !== "results" || !job) return;
  put("results-note", result ? "Inventory results as returned by the API." : "Waiting for the final API snapshot.");
  const rows = new Map((result?.rows || []).map((row) => [row.slot_id, row]));
  const captures = new Map(reports.map((report) => [report.slot_id, report]));
  html("result-rows", job.slots.map((slot) => {
    const observed = status.confirmed?.[slot];
    const row = rows.get(slot);
    const evidence = captures.get(slot);
    const stopped = status.missed?.includes(slot);
    const manual = status.adaptive?.manual_review?.[slot];
    const progress = manual ? "Manual verification" : observed ? "Confirmed" : stopped ? "Missed"
      : status.visited?.includes(slot) ? "Visited" : "Planned";
    const outcome = row?.outcome;
    const reading = observed ? `${label(observed.occupancy)} · ${label(observed.label_status)}` : "—";
    return `<tr><th scope="row">${slot}</th><td><span class="label ${stopped || manual ? "warn" : observed ? "good" : ""}">${progress}</span></td>
      <td>${safe(observed?.pallet_id || "—")}</td><td>${safe(reading)}</td>
      <td>${safe(outcome === "pending" ? "Pending comparison" : label(outcome) || "—")}</td>
      <td>${evidence ? `<span class="label ${evidence.status === "DAMAGED" ? "bad" : "good"}">${safe(evidence.status)}</span>` : "—"}</td></tr>`;
  }).join(""));
  html("findings", damage.map((report) => {
    const photo = `/evidence/${encodeURIComponent(job.inspection_id)}/${encodeURIComponent(report.quality_id)}/annotated.png`;
    const attempt = status.adaptive?.attempts.find((item) => item.quality_id === report.quality_id);
    const angle = attempt ? ` · ${retryReasons[attempt.reason]}` : "";
    return `<a class="finding" target="_blank" rel="noopener" href="${photo}">
      <img src="${photo}" alt="Damage evidence for ${safe(report.slot_id + angle)}">
      <strong>${safe(report.slot_id)} · ${safe((report.pallet_id || "Unreadable pallet") + angle)}</strong><small>${safe(report.reason)}</small></a>`;
  }).join(""));
}

function reviewSlots(job) {
  if (!job) return [];
  const status = job.status || {};
  const problems = Object.values(status.confirmed || {}).filter((event) =>
    event.occupancy === "uncertain" || event.label_status === "unreadable").map((event) => event.slot_id);
  return [...new Set([...(status.missed || []), ...problems, ...Object.keys(status.adaptive?.manual_review || {}),
    ...(job.result?.discrepancies || []).map((row) => row.slot_id)])];
}

function drawAdaptive(job) {
  const adaptive = job?.status?.adaptive;
  el("adaptive-summary").hidden = !adaptive || view !== "results";
  el("adaptive-progress").hidden = !adaptive || view !== "live" || !inspectionStages.includes(job.status.stage);
  if (!adaptive) return;
  const move = adaptive.moves.at(-1);
  const moving = move && ["REPOSITION", "RECENTER"].includes(job.status.stage);
  const waypoint = moving ? ` · Target ${move.target.map((value) => value.toFixed(2)).join(" / ")} m` : "";
  put("adaptive-attempt", `Attempt ${adaptive.attempt} of 3 · ${retryReasons[adaptive.reason] || "Reference view"}${waypoint}`);
  put("adaptive-outcome", moving && job.status.stage === "REPOSITION" ? "" : adaptive.outcome);
  const manual = Object.entries(adaptive.manual_review);
  const observed = adaptive.attempts.filter((attempt) => attempt.observation_id).length;
  put("adaptive-totals", `${observed} observations · ${adaptive.retries} additional attempts · ${adaptive.resolved.length} resolved · ${manual.length} manual checks`);
  put("adaptive-review", manual.map(([slot, reason]) => `${slot} · ${retryReasons[reason] || reason}`).join("  |  "));
}

function drawEnergy(job) {
  el("energy-panel").hidden = !layout.dock;
  if (!layout.dock) return;
  const telemetry = state?.energy;
  const forecast = view === "plan" ? preview?.energy : null;
  const mission = view !== "plan" ? job?.status?.energy : null;
  const stage = job?.stage;
  const remaining = mission?.remaining || preview?.slots;
  const percent = value => Number.isFinite(value) ? `${value.toFixed(1)}%` : "—";
  const battery = telemetry?.fresh ? telemetry.percent : null;
  const dock = telemetry?.dock || "FAULT";
  put("battery-value", percent(battery));
  el("battery-meter").value = battery ?? 0;
  el("battery-meter").classList.toggle("low", battery != null && battery < 30);
  put("dock-state", `Dock · ${label(dock)}`);
  el("dock-state").dataset.tone = !telemetry?.fresh ? "neutral"
    : ["READY", "CHARGING", "AVAILABLE"].includes(dock) ? "ready" : dock === "FAULT" ? "danger" : "active";
  el("energy-panel").dataset.dock = dock.toLowerCase();
  put("energy-cycles", telemetry?.cycles ?? "—");
  put("energy-need", percent(mission?.required_percent ?? forecast?.estimated_percent ?? forecast?.percent));
  put("energy-budget", !forecast ? "" : Number.isFinite(forecast.seconds) ? `${forecast.seconds} s sim · estimated inspection`
    : `${forecast.flight_seconds} sim s flight · ${forecast.inspection_seconds} sim s scan · up to ${forecast.adaptive_percent.toFixed(1)}% adaptive allowance`);
  const balance = returnEnergy(telemetry, activeMission(job) ? mission : null);
  put("energy-return", batteryPercent(balance.atDock));
  put("energy-reserve", batteryPercent(balance.reserve));
  put("energy-margin", percentagePoints(balance.margin));
  el("energy-margin").dataset.tone = balance.margin == null ? "neutral" : balance.margin >= 0 ? "ready" : "warning";
  put("energy-remaining", remaining?.length ?? "—");
  put("energy-remaining-ids", remaining ? remaining.slice(0, 5).join(" · ") + (remaining.length > 5 ? " …" : "") : "");
  const messages = {
    RETURN_TO_DOCK: mission?.return_reason === "CALIBRATION_REQUESTED" ? "Returning to dock for calibration" : mission?.return_reason,
    DOCKING: "Aligning and landing on the dock",
    CHARGING: "Docking confirmed · Accelerated simulated charging",
    READY_TO_RESUME: "Battery ready — requesting departure clearance",
    RESUMING: "Resuming unfinished inspection", COMPLETE: "Inspection completed",
    COMPLETE_WITH_MISSES: "Inspection completed with unconfirmed stops",
    INTERRUPTED_FOR_CALIBRATION: "Inspection interrupted for calibration · Physical dock confirmed",
    ABORTED: "Inspection stopped · Automatic departure disabled",
  };
  let message = "Waiting for simulated battery data";
  if (battery != null) {
    message = mission ? messages[stage] || (telemetry.charging ? "Simulated charging" : "") || "Tracking live simulated energy"
      : forecast && battery < forecast.minimum_percent ? "Insufficient energy for the first stop and safe return"
      : forecast && (forecast.single_cycle || (layout.learned_warehouse && forecast.can_start))
        ? "Battery sufficient for planned inspection"
        : forecast ? "The route may require a charging stop" : "Select an inspection scope for an energy estimate";
  }
  if (el("energy-message").textContent !== message) put("energy-message", message);
}

function drawAvoidance(job) {
  if (!layout.avoidance) return;
  const safetyAlarm = activeSafetyAlarm(state?.safety);
  const a = activeMission(job) || safetyAlarm ? job?.status?.avoidance : null;
  const mode = safetyAlarm && job?.stage === "ABORTED" && a?.state === "ABORTED"
    ? "SAFETY_ABORT" : a?.state || "WAITING";
  el("avoidance-panel").dataset.state = mode.toLowerCase();
  put("avoidance-state", label(mode));
  el("avoidance-state").dataset.tone = mode === "CLEAR" ? "ready" : mode === "WAITING" ? "neutral"
    : ["SAFETY_ABORT", "ABORTED", "FAULT", "BLOCKED"].includes(mode) ? "danger" : "warning";
  put("avoidance-reason", mode === "SAFETY_ABORT" ? safetyAlarm.message
    : a?.reason || "Awaiting the first scan from an active inspection.");
  put("avoidance-range", a?.obstacle_distance == null ? mode === "CLEAR" ? "None detected" : "Unavailable"
    : `${a.obstacle_distance.toFixed(2)} m`);
  put("avoidance-returns", a?.obstacle_returns ? `${a.obstacles} obstacle cluster(s) · ${a.obstacle_returns} returns` : "");
  put("avoidance-age", a?.scan_age_ms == null ? "—" : `${a.scan_age_ms} ms`);
  put("avoidance-coverage", a ? `${a.verified_distance.toFixed(2)} m checked along the active leg` : "");
  put("avoidance-direction", a?.direction ? a.direction.map(value => value.toFixed(2)).join(" / ") : "—");
  put("avoidance-maneuver", a?.maneuver?.length ? `${a.maneuver.length - 1} verified leg(s)` : "—");
  const distance = a?.extra_distance == null ? "—" : `+${a.extra_distance.toFixed(2)} m`;
  const energy = a?.extra_percent == null ? "—" : `+${a.extra_percent.toFixed(1)} pp`;
  put("avoidance-cost", `${distance} / ${energy}`);
}

function drawLocalization() {
  if (!layout.localization) return;
  const loc = state?.localization;
  const validation = state?.localization_validation;
  const quality = loc?.state || "DEGRADED";
  el("localization-panel").dataset.state = quality.toLowerCase();
  put("localization-status", quality);
  el("localization-status").dataset.tone = !loc ? "neutral" : quality === "TRACKING" ? "ready"
    : quality === "LOST" ? "danger" : "warning";
  put("localization-source", layout.localization.mode === "shadow" ? "Gazebo · shadow comparison" : "LiDAR + IMU");
  put("localization-reason", loc?.reason || "Waiting for a synchronized scan.");
  put("localization-pose", loc?.position ? `${loc.position.map(x => x.toFixed(3)).join(" / ")} m` : "—");
  put("localization-sigma", loc?.sigma ? `Fit σ up to ${(Math.max(...loc.sigma)*100).toFixed(1)} cm` : "");
  put("localization-fit", loc?.rms == null ? "—" : `${(loc.rms*100).toFixed(1)} cm`);
  put("localization-overlap", loc?.overlap == null ? "" : `${Math.round(loc.overlap*100)}% correspondences`);
  put("localization-rate", loc?.scan_age_ms == null ? "—" : `${loc.scan_age_ms} ms / ${loc.update_hz.toFixed(1)} Hz`);
  put("localization-map-size", loc?.map_voxels ? `${loc.map_voxels.toLocaleString()} cells` : "—");
  put("localization-validation", validation ? `Validation RMSE ${(validation.rmse*100).toFixed(1)} cm` : "");
}

const recoveryChecks = {
  stable_tracking: "Stable sensor localization", onboard_lidar: "Fresh onboard LiDAR",
  safety_heartbeat_and_zones: "Safety heartbeat and reserved zones", stationary: "Drone stationary for approval",
  zone_sensors: "Fresh zone sensors", fields_clear: "Required zones clear", red_signals: "Reserved signals confirmed",
  in_flight_envelope: "Pose inside flight envelope", connected_return: "Connected return route",
  first_leg_observed: "Onboard clearance for first leg", energy_telemetry: "Verified battery budget",
  return_budget: "Sufficient energy and reserve", command_ownership: "Exclusive flight control",
  flight_enable_bridge: "Flight controller bridge ready",
};

function drawRecovery() {
  if (!layout.recovery) return;
  const r = state?.recovery;
  const panel = el("emergency-panel");
  panel.hidden = !r || (r.phase === "RECOVERY_COMPLETE" && !["live", "results", "diagnostics"].includes(view));
  if (!r) return;
  const phase = r.phase;
  const complete = phase === "RECOVERY_COMPLETE";
  const active = ["RECOVERY_AUTHORIZED", "RETURNING_TO_DOCK", "EMERGENCY_DOCKING"].includes(phase);
  panel.dataset.phase = phase;
  put("recovery-phase", phase.replaceAll("_", " "));
  const trigger = r.stopped?.detail;
  const noRoute = phase === "RECOVERY_BLOCKED" && r.conditions?.in_flight_envelope && !r.conditions.connected_return;
  const explanation = r.detail || (noRoute ? "No connected route in the reservation. Physical recovery required." : trigger);
  put("recovery-detail", [r.cause?.replaceAll("_", " "), explanation].filter(Boolean).join(" · "));
  put("recovery-position", state.robot && state.localization?.state === "TRACKING" && state.position ? state.position.slice(0, 3).map(x => x.toFixed(2)).join(" / ") + " m" : "Estimate unavailable");
  put("recovery-localization", state.localization?.state || "No localization heartbeat");
  put("recovery-zones", (state.safety?.required || state.last_reservation || []).join(" · ") || "Released");
  const permit = state.safety?.recovery?.permit;
  put("recovery-permit", permit ? `Safety permit ${permit}` : r.recovery_id || "Waiting for evaluation");
  const pct = value => value == null ? "—" : `${value.toFixed(1)}%`;
  put("recovery-energy", r.energy_verified ? [state.energy?.percent, r.return_cost, r.reserve].map(pct).join(" / ") : "Unverified");
  const energyBlocked = r.conditions?.energy_telemetry && r.return_cost != null && r.conditions.return_budget === false;
  const nextStep = complete ? "The drone is docked. You can plan another inspection."
    : active ? "Return in progress. Keep the reserved zones clear."
    : energyBlocked ? "Battery too low for a verified return. In this simulator, restart the demo to place the drone back at its dock."
    : phase === "WAITING_FOR_OPERATOR_APPROVAL" ? "Review the proposed route, then select Authorize return to dock."
    : phase === "RECOVERY_PLANNING" ? "Checking whether a safe return is possible."
    : phase === "WAITING_FOR_LOCALIZATION" ? "Waiting for reliable localization. The drone will hold position."
    : phase === "WAITING_FOR_ZONE_CLEARANCE" ? "Keep the reserved zones clear. Recovery is waiting for Safety."
    : phase === "RECOVERY_BLOCKED" ? "Return blocked. Review the failed checks below and clear the cause before reevaluating."
    : "The inspection has stopped. Select Evaluate recovery to check whether the drone can return to the dock.";
  put("recovery-next-step", nextStep);
  put("recovery-wait", energyBlocked ? "Return budget insufficient · physical recovery required" :
      r.wait_per_sim_s != null && !complete ? `${state.energy?.fresh ? "Hover" : "Conservative draw"} ${r.wait_per_sim_s.toFixed(2)} pp per simulation second` : complete ? "Physical contact confirmed" : "");
  const legs = Math.max(0, (r.planned?.length || 0)-1);
  put("recovery-route", complete ? "Docked" : active ? `Leg ${Math.min(legs,r.leg + 1)} of ${legs}` :
      legs ? `${legs} planned corridor legs` : "Awaiting verified route");
  put("recovery-retry", complete && r.retry_slots?.length ? `Remaining ${r.retry_slots.join(", ")}` : "");
  const visible = Object.entries(r.conditions || {}).filter(([key]) => !active || !["stationary", "first_leg_observed"].includes(key));
  const list = el("recovery-checks");
  const signature = JSON.stringify(visible);
  if (list.dataset.signature !== signature) {
    list.replaceChildren(...visible.map(([key, ok]) => {
      const row = document.createElement("li");
      row.dataset.ok = String(ok);
      row.textContent = `${ok ? "✓" : "×"} ${recoveryChecks[key] || key}`;
      return row;
    }));
    list.dataset.signature = signature;
  }
  el("recovery-evaluate").disabled = !["RECOVERY_REQUIRED","RECOVERY_FAILED"].includes(phase) || state.safety?.phase !== "RECOVERY" || !trigger;
  el("recovery-authorize").disabled = phase !== "WAITING_FOR_OPERATOR_APPROVAL";
  el("recovery-abort").disabled = !r.recovery_id || complete || phase === "RECOVERY_FAILED";
  el("recovery-replan").disabled = !complete || state.safety?.phase !== "RELEASED" || !state.energy?.contact || state.busy;
}

function drawSafety() {
  const enabled = !!layout.safety_fields;
  el("safety-banner").hidden = el("warehouse-safety").hidden = !enabled;
  if (!enabled) return;
  const status = state?.safety;
  const laser = !!layout.laser_fields;
  const alarm = activeSafetyAlarm(status);
  const zones = status?.zones || {};
  const awaiting = status?.phase === "PREPARING";
  const selected = (preview?.required_zones || []).map(id => zones[id]).filter(Boolean);
  const checked = selected.length ? selected : Object.values(zones);
  const unavailable = !status || !status.signals_online || checked.some(zone => zone.sensor !== "FRESH");
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
  } else if (!status) {
    title = "Safety Manager offline";
    message = "Access is unverified. Dispatch is blocked.";
    style = "fault";
  } else if (unavailable || occupied.length) {
    title = "Hold · Selected scope unavailable";
    message = unavailable ? "Waiting for verified sensor and signal data."
      : `${laser ? "Obstacle detected" : "Worker present"} · ${occupied.join(", ")}`;
    style = "fault";
  } else if (status.phase === "RELEASED") {
    title = "Inspection completed · Access restored";
    message = status.message;
  } else if (!selected.length) {
    title = "Choose an inspection scope";
    message = "Required zones follow the planned flight path.";
  }
  el("safety-banner").hidden = !["fault", "preparing"].includes(style) || !!alarm;
  el("safety-banner").dataset.access = style;
  put("safety-headline", title);
  put("safety-message", message);
  if (view !== "diagnostics") return;
  const source = laser ? "Laser scan" : "Presence feed";
  put("sensor-state", source + (status?.sensor === "FRESH" ? " live" : status?.sensor === "STALE" ? " stale" : " unknown"));
  el("sensor-state").classList.toggle("good", status?.sensor === "FRESH");
  const byName = { A: "Aisle A", B: "Aisle B", T: layout.aerial ? "Ground transfer" : "Transfer corridor & pad",
                   C: "Aisle C", D: "Technical dock & shaft" };
  html("safety-zones", (layout.aerial ? ["D", "A", "B", "T", "C"] : ["A", "B", "T", "C"]).map(id => {
    const zone = zones[id];
    const state = zone?.state || (id === "C" ? "UNMONITORED" : "UNAVAILABLE");
    const detected = zone?.occupied === true ? (laser && id !== "D" ? "Obstacle detected" : "Worker present")
      : zone?.occupied === false ? "Clear field" : "Unknown presence";
    const age = status?.scans?.[id]?.age_ms;
    const scanner = id === "D" && zone ? ` · Virtual presence · ${label(zone.sensor)}`
      : laser && zone ? ` · ${label(zone.sensor)}${age == null ? "" : ` ${age} ms`}` : "";
    const tone = zone?.occupied === true || state === "FAULT" || state === "INTRUSION" ? "danger"
      : state === "RESERVED" || state === "PREPARING" ? "active" : state === "OPEN" && zone?.sensor === "FRESH" ? "ready" : "neutral";
    return `<div class="safety-zone access-${state.toLowerCase()}" data-tone="${tone}">
      <strong>${byName[id]}</strong><span class="access-label"><i></i>${label(state)}</span>
      <small>${id === "C" ? "Decorative aisle" : detected + scanner + (zone?.signals_acknowledged ? " · lights confirmed" : " · awaiting lights")}</small></div>`;
  }).join(""));
  const reservations = (status?.required || state?.last_reservation || []).map(id => byName[id]);
  put("zone-reservations", status
    ? (reservations.length ? `Restricted scope · ${reservations.join(", ")}` : "No active reservation.")
    : (reservations.length ? `Access unverified · Last reservation · ${reservations.join(", ")}` : "Reservation status unverified."));
  html("safety-history", (status?.events || []).slice(0, 12).map(event =>
    `<li><time datetime="${safe(event.time)}">${safe(new Date(event.time).toLocaleTimeString())}</time>
      <div><b>${safe(label(event.event))}</b><span>${safe(event.message)}</span>
      <small>${safe(event.inspection_id || "")}</small></div></li>`).join(""));
  el("safety-overview").hidden = !state?.overview;
  el("overview-unavailable").hidden = !!state?.overview;
}

function flightAlert(job, active, returnBalance, reserve) {
  if (connectionLost) return "Connection lost. Live readings are unavailable. Reconnecting…";
  const incident = activeSafetyAlarm(state?.safety);
  if (incident) return incident.message;
  const status = job?.status || {};
  if (job?.stage === "ABORTED" && state?.recovery?.phase !== "RECOVERY_COMPLETE" &&
      !state?.physical_dock && !status.landed) return status.detail || "Flight stopped.";
  if (!active) return "";
  const manual = status.manual;
  if (["LINK_LOST", "ENERGY_LIMIT", "LOCALIZATION_LOST", "BLOCKED", "LIMITED", "FAULT"].includes(manual?.state)) return manual.detail;
  if (layout.safety_fields && !state.safety) return "Safety connection lost. Flight clearance is unverified.";
  if (layout.localization?.mode === "sensor_based" && state.localization?.state !== "TRACKING") {
    return "Drone position is uncertain. Check the flight status.";
  }
  if (["BLOCKED", "FAULT", "ABORTED"].includes(status.avoidance?.state)) return status.avoidance.reason || status.detail;
  if (["RETURN_TO_DOCK", "DOCKING"].includes(job?.stage) && /low battery|energy/i.test(status.energy?.return_reason || "")) {
    return "Battery limit reached. The drone will charge before resuming this inspection.";
  }
  if (layout.dock && !state.energy?.fresh) return "Battery reading unavailable. Return capacity is unverified.";
  if (["CHARGING", "READY_TO_RESUME"].includes(job?.stage)) return "";
  if ((returnBalance != null && returnBalance < reserve) || state.energy?.percent < state.energy?.model?.reserve) {
    return "Battery warning. Verified return reserve is low.";
  }
  return "";
}

function draw() {
  if (!layout) return;
  const job = state?.mission;
  const status = job?.status || {};
  const stage = job?.stage;
  const mapping = view === "manual" && !!state?.localization?.mapping_id && state?.service_mode !== "PRODUCTION";
  const surveyed = visualRequest(job).required;
  el("workspace").dataset.surveyed = String(surveyed);
  el("map-2d").hidden = mapping || surveyed;
  el("map-3d").hidden = mapping;
  const businessResults = state?.backend?.mode === "mock_sap" || !!state?.history.some(row => row.business);
  el("business-results").hidden = view !== "results" || !businessResults || resultsMap;
  el("results-panel").hidden = view !== "results" || businessResults;
  if (view !== "results") el("review").hidden = true;
  const robot = el("robot-state"), backend = el("api-state");
  const target = flightTarget(job);
  const operator = operatorState(state, target, connectionLost);
  put("robot-state", operator.label);
  robot.dataset.tone = operator.tone;
  put("api-state", state?.backend?.online ? (state.backend.mode === "mock_sap" ? "Mock SAP online" : "Warehouse API online") : "Inventory API offline");
  backend.dataset.tone = state?.backend?.online ? "ready" : "neutral";
  el("run-state").hidden = true;
  const forecast = preview?.energy;
  const learned = !!layout.learned_warehouse;
  const learnedReady = state?.localization?.warehouse_ready && warehouseConfiguration &&
    state.localization.warehouse_id === warehouseConfiguration.manifest.configuration_id;
  el("reference-scope").hidden = learned;
  el("learned-scope").hidden = !learned;
  el("learned-service").hidden = !learned || (!!learnedReady && !warehouseLocked);
  const activeModel = visualCache.get("/api/visualization/active")?.packet;
  const manifest = warehouseConfiguration?.manifest;
  const name = manifest?.name || activeModel?.name || "Learned warehouse";
  const revision = manifest?.revision ?? activeModel?.binding.revision;
  put("active-warehouse-name", learned ? name + (revision == null ? "" : " · Revision " + revision) : "Reference warehouse");
  put("planned-total", preview?.slots.length ?? (learned ? learnedStops.size : "—"));
  put("plan-distance", Number.isFinite(preview?.distance) ? `${preview.distance.toFixed(1)} m planned` : "");
  const duration = forecast?.seconds ?? (forecast ? forecast.flight_seconds + forecast.inspection_seconds : null);
  put("plan-duration", Number.isFinite(duration) ? `~${Math.max(1, Math.ceil(duration/60))} min sim` : layout.dock ? "—" : "Not estimated");
  put("plan-battery", Number.isFinite(forecast?.minimum_percent) ? `${Math.ceil(forecast.minimum_percent)}% min.` : layout.dock ? "—" : "Not tracked");
  put("plan-battery-now", state?.energy?.fresh ? batteryPercent(state.energy.percent) : "Unavailable");
  const missing = preview?.slots.filter((slot) => !state?.backend?.slots?.includes(slot)) || [];
  const selectedZones = (preview?.required_zones || []).map(id => state?.safety?.zones?.[id]);
  let reason = "";
  if (!state) reason = "Connecting to the Control Center.";
  else if (layout.mapping_only && !learned) reason = "Open Service to start a mapping session.";
  else if (state.safety?.phase === "RECOVERY") reason = "Recovery required. Open Emergency & Recovery before takeoff.";
  else if (state.service_mode && state.service_mode !== "PRODUCTION") reason = "Warehouse calibration is active. New inspections are locked.";
  else if (state.busy || dispatching || wantedRun) reason = job?.mode === "manual"
    ? "Return the active manual flight to the dock before dispatch."
    : "An inspection is in progress or its report is being prepared.";
  else if (learned && state.localization?.warehouse_error) reason = state.localization.warehouse_error;
  else if (learned && !state.localization?.warehouse_id) reason = "Activate a saved warehouse in Service before planning.";
  else if (learned && warehouseLocked) reason = "Unlock Service to load the registered locations for this warehouse.";
  else if (learned && warehouseError) reason = warehouseError;
  else if (learned && !learnedReady) reason = "Waiting for the drone at the dock to match the verified saved map.";
  else if (previewError) reason = previewError;
  else if (previewPending) reason = "Calculating the route and checking departure conditions…";
  else if (!preview) reason = "Select at least one functional location.";
  else if (preview.requires_multiple_sorties)
    reason = `Verified plan for ${preview.sorties.length} sorties. Select the locations for one sortie to dispatch.`;
  else if (layout.localization?.mode === "sensor_based" && state?.localization?.state !== "TRACKING")
    reason = "The drone’s position is unverified. Wait until it can locate itself.";
  else if (!state?.robot) reason = "Waiting for the drone connection.";
  else if (!state.at_pad) reason = layout.recovery ? "Use the Recovery Center to return the drone to the dock." :
    "Drone is away from the pad. After an abort, restart the simulator before dispatch.";
  else if (layout.safety_fields && !state.safety) reason = "Waiting for the Safety Manager.";
  else if (layout.safety_fields && (!state.safety.signals_online || selectedZones.some(zone => zone?.sensor !== "FRESH")))
    reason = "Waiting for verified safety sensors and signals.";
  else if (selectedZones.some(zone => zone?.occupied)) reason = "A required zone is occupied. Clear it or choose another scope.";
  else if (layout.dock && !state.energy?.contact) reason = "Wait for physical dock confirmation before takeoff.";
  else if (layout.dock && (!state.energy?.fresh || !preview.energy)) reason = "Waiting for a current battery reading and departure estimate.";
  else if (layout.dock && (state.energy.percent < forecast.minimum_percent || (learned && !state.energy.budget_verified)))
    reason = "Waiting for enough verified battery capacity for the inspection and safe return.";
  else if (!state.backend.online) reason = "Waiting for the inventory API.";
  else if (missing.length) reason = "Inventory API profile lacks locations in this plan.";
  el("start").disabled = !!reason;
  put("start", dispatching || wantedRun ? "Starting inspection…" : "Start inspection");
  put("dispatch-help", reason || (forecast?.single_cycle === false
    ? "Ready for simulated takeoff. The inspection may require a charging stop."
    : "Ready for simulated takeoff."));
  el("dispatch-help").dataset.tone = reason ? "warning" : "ready";
  el("camera").hidden = !state?.camera;
  el("no-camera").hidden = !!state?.camera;
  const visited = new Set(status.visited || []);
  const recorded = new Set(Object.keys(status.confirmed || {}));
  const total = job?.slots?.length || 0;
  el("flight-progress").hidden = !job || job.mode === "manual" || view === "manual";
  put("active-target", target === "PAD" ? "Dock" : target === "CORRIDOR" ? "Transfer corridor" : target || "Unavailable");
  put("progress-count", `${recorded.size} of ${total}`);
  el("progress-bar").max = total || 1;
  el("progress-bar").value = recorded.size;
  html("flight-stops", (job?.slots || []).map(id => {
    const progress = recorded.has(id) ? "Observation recorded" : status.missed?.includes(id) ? "Missed"
      : id === target && visited.has(id) ? "Reached · awaiting observation"
      : id === target ? "Current target" : visited.has(id) ? "Reached · no observation" : "Awaiting visit";
    return `<li data-tone="${recorded.has(id) ? "ready" : progress === "Missed" ? "warning" : id === target ? "active" : "neutral"}">
      <strong>${safe(id)}</strong><span>${progress}</span></li>`;
  }).join(""));
  put("position-value", state?.robot && state.position ? state.position.slice(0, 3).map((p) => p.toFixed(2)).join(" / ") : "—");
  put("live-detail", job?.error || "");
  el("live-detail").hidden = !job?.error;
  el("flight-battery").hidden = !layout.dock;
  const canStop = activeMission(job);
  const budget = returnEnergy(state?.energy, canStop ? status.energy : null);
  put("flight-battery-level", batteryPercent(budget.now));
  put("flight-finish", batteryPercent(budget.atDock));
  put("flight-reserve", batteryPercent(budget.reserve));
  put("flight-margin", percentagePoints(budget.margin));
  el("flight-margin").dataset.tone = budget.margin == null ? "neutral" : budget.margin >= 0 ? "ready" : "warning";
  el("abort").hidden = !canStop;
  el("abort").disabled = !canStop || stopping;
  put("abort", stopping ? "Stopping flight…" : job?.mode === "manual" ? "Stop flight" : "Stop inspection");
  const recoveryInMotion = state?.recovery?.permit_request === true;
  if (state) emergencyTarget = canStop || recoveryInMotion ? {inspection_id: job?.inspection_id,
    recovery: recoveryInMotion ? state.recovery : null} : null;
  el("global-stop").hidden = !emergencyTarget;
  el("global-stop").disabled = stopping;
  el("calibration-emergency-stop").hidden = !emergencyTarget;
  el("calibration-emergency-stop").disabled = stopping;
  el("scan-stop").hidden = !scanFullscreen() || el("global-stop").hidden;
  el("scan-stop").disabled = stopping;
  el("manual-stop").hidden = !canStop;
  el("manual-stop").disabled = stopping;
  el("live-plan").hidden = !!job || view === "manual";
  put("flight-time", job ? `${(status.elapsed_seconds || 0).toFixed(1)} s` : "—");
  drawWorkspace();
  if (mapMode === "2d" && !el("warehouse-panel").hidden) {
    drawMap(job);
    drawScans();
  }
  drawSafety();
  const concern = flightAlert(job, canStop, budget.atDock, budget.reserve);
  put("live-phase", canStop && view === "live" && job.mode !== "manual" ? missionPhase(job, target) : operator.label);
  el("live-phase").dataset.tone = operator.tone;
  const missionAction = {
    CHARGING: "Automatically charging for the next sortie. The inspection remains active.",
    READY_TO_RESUME: "Charged and waiting for departure clearance. The inspection remains active.",
    RESUMING: "Continuing with the unfinished inspection locations.",
  }[stage];
  put("live-operator-action", concern || (view === "manual" && canStop ? "Hold a control to move. Release it to stop."
    : canStop ? missionAction || "Autonomous flight · monitoring only." : state?.robot && view !== "manual" ? "Start an inspection from Plan inspection."
    : state?.robot ? "" : "Waiting for the simulated drone."));
  el("live-operator-action").dataset.tone = concern ? "warning" : "neutral";
  el("camera-expand").hidden = view !== "manual" || mapping;
  for (const id of ["critical-alert", "fullscreen-alert"]) {
    el(id).hidden = !concern || (id === "fullscreen-alert") !== scanFullscreen() || (view === "manual" && id === "critical-alert");
    put(id, concern);
  }
  el("critical-action").hidden = state?.safety?.phase !== "RECOVERY" || view === "diagnostics" || !layout.recovery;
  if (view === "results" || view === "diagnostics") drawResults(job);
  if (businessResults) el("review").hidden = true;
  drawAdaptive(job);
  if (view === "diagnostics") {
    put("diagnostic-drone-model", droneProfile(state?.drone_model));
    put("diagnostic-phase", operator.label);
    el("diagnostic-phase").dataset.tone = operator.tone;
    const liveSummary = canStop ? [target && "Target " + (target === "PAD" ? "dock" : target),
      status.avoidance?.state === "CLEAR" ? "Path clear" : "",
      budget.margin != null ? percentagePoints(budget.margin) + " relative to reserve if returning now" : ""].filter(Boolean).join(" · ") : "";
    put("diagnostic-action", concern || liveSummary ||
      (state?.robot ? "Monitoring flight and warehouse systems." : "Start the simulator to receive live telemetry."));
    put("diagnostic-pose", state?.position_fresh ? "Live position" : state?.position || lastPose ? "Last known position" : "Position unavailable");
    el("diagnostic-pose").dataset.tone = state?.position_fresh ? "ready" : "neutral";
    drawEnergy(job);
    drawAvoidance(job);
    drawLocalization();
  }
  drawRecovery();
  manual.update(state);
  teaching.update(state, view);
  drawTwin(job);
}

async function poll() {
  try {
    state = await api("/api/state");
    if (state.position_fresh && state.position && (!layout.localization || state.localization?.state === "TRACKING"))
      lastPose = {position:state.position, orientation:state.orientation};
    connectionLost = false;
    connectionStatus();
    syncLearnedPlan();
    if (layout.dock && preview && !preview.energy && state.energy?.fresh && view === "plan") changePlan();
    const job = state.mission;
    if (job && (!wantedRun || job.inspection_id === wantedRun)) {
      if (job.inspection_id !== lastRun) {
        lastRun = job.inspection_id;
        lastStage = null;
        wantedRun = null;
        if (!terminal.has(job.stage) && view === "plan") setView(job.mode === "manual" ? "manual" : "live");
      }
      if (terminal.has(job.stage) && lastStage !== job.stage) {
        if (stopping) { stopping = false; notice(); }
        if (view === "live" && !scanFullscreen()) setView("results", true);
      }
      lastStage = job.stage;
    }
    draw();
    service.refresh();
    if (view === "results") intelligence.update(state, canReinspect);
  } catch (error) {
    connectionLost = true;
    state = null;
    draw();
  }
  setTimeout(poll, 350);
}

async function init() {
  try {
    layout = await api("/api/layout");
    connectionStatus();
  } catch (error) {
    connectionStatus("Waiting for Control Center. Start Rackonaut in the terminal. Reconnecting…");
    setTimeout(init, 1500);
    return;
  }
  intelligence = createIntelligence(api, async (slot, inspectionId) => {
    focusedLocation = slot;
    locatedReport = inspectionId;
    resultsMap = true;
    fittedFocus = slot;
    showFittedDetails = true;
    drawWorkspace();
    await loadTwin();
    if (visualRequest(state?.mission).required) twin?.focusFittedLocation(slot);
    else twin?.focusSlot(slot);
    draw();
    el("results-close-map").focus();
  }, reinspectLocation, safe, label, (run, outcomes) => {
    if (businessRun !== run) {
      fittedFocus = null;
      showFittedDetails = false;
    }
    businessRun = run;
    businessOutcomes = outcomes;
    if (view === "results") drawTwin(state?.mission);
  });
  el("localization-panel").hidden = !layout.localization;
  if (layout.avoidance) {
    el("avoidance-panel").hidden = false;
    el("flight-obstacle-controls").hidden = false;
  }
  el("adaptive-option").hidden = !layout.adaptive_world;
  if (layout.laser_fields) {
    for (const id of ["laser-field-key", "laser-hit-key", "obstacle-controls"]) el(id).hidden = false;
    put("sensor-source", "3 simulated GPU LiDARs · Live LaserScan · Dashed fields show measured scope");
  }
  if (layout.aerial) {
    for (const id of ["aerial-key", "worker-descent-a", "worker-descent-b"]) el(id).hidden = false;
    if (layout.laser_fields) put("sensor-source", "3 simulated GPU LiDARs · Technical dock uses virtual worker presence");
  }
  el("warehouse-map").classList.toggle("has-safety", !!layout.safety_fields);
  drawWorkspace();
  drawLayout();
  el("map-2d").addEventListener("click", () => chooseMap("2d"));
  el("map-3d").addEventListener("click", () => loadTwin("model"));
  el("map-scan").addEventListener("click", () => loadTwin("scan"));
  el("calibration-fly").addEventListener("click", () => {
    setView("manual", true);
    loadTwin("scan");
  });
  el("service-review-route").addEventListener("click", () => {
    previewSource = {kind: "calibration", id: el("service-review-route").dataset.session};
    setView("route", true);
    routeReview.open(previewSource.id, layout.learned_warehouse);
  });
  el("service-preview-calibration").addEventListener("click", () => {
    previewSource = {kind: "calibration", id: el("service-review-route").dataset.session};
    put("configuration-preview-name", "Completed calibration");
    setView("configuration", true);
  });
  el("configuration-back").addEventListener("click", () => setView("service", true));
  el("unplaced-options").addEventListener("click", event => {
    const button = event.target.closest("button[data-location]");
    if (button) selectFittedLocation(button.dataset.location);
  });
  el("route-back").addEventListener("click", () => setView("service", true));
  el("scan-expand").disabled = !document.fullscreenEnabled;
  el("scan-expand").addEventListener("click", async () => {
    if (scanFullscreen()) { await leaveScanFullscreen(); return; }
    try { await el("warehouse-panel").requestFullscreen(); }
    catch (error) { notice(`Could not expand the map. ${error.message}`); }
  });
  el("scan-stop").addEventListener("click", () => el("global-stop").click());
  document.addEventListener("fullscreenchange", () => {
    const expanded = scanFullscreen();
    el("scan-expand").setAttribute("aria-pressed", String(expanded));
    put("scan-expand", expanded ? "Exit full screen" : "Expand map");
    draw();
  });
  el("map-3d").disabled = !layout.scene;
  el("focus-dock").addEventListener("click", async () => {
    setView("plan", true);
    if (mapMode !== "model") await loadTwin();
    if (show3D) {
      twin?.focusDock();
      el("map-title").scrollIntoView({block: "start"});
    }
  });
  for (const tab of document.querySelectorAll(".tab")) tab.addEventListener("click", () => {
    if (tab.dataset.view === "service") openServiceTab("management");
    else setView(tab.dataset.view);
  });
  for (const tab of el("service-nav").querySelectorAll("button")) {
    tab.addEventListener("click", () => openServiceTab(tab.dataset.serviceView));
    if (tab.dataset.serviceView === "manual") tab.hidden = !layout.manual_flight || layout.mapping_only && !layout.learned_warehouse;
  }
  el("diagnostics-tab").hidden = false;
  el("learned-service").addEventListener("click", () => openServiceTab("configuration"));
  el("learned-all").addEventListener("change", (event) => {
    learnedStops = new Set(event.target.checked ? warehouseConfiguration.locations.map(row => row.record_id) : []);
    changePlan();
  });
  el("learned-groups").addEventListener("click", (event) => {
    const name = event.target.closest("button[data-group]")?.dataset.group;
    const group = learnedGroups.get(name);
    if (!group) return;
    const selected = [...group].every(id => learnedStops.has(id));
    for (const id of group) {
      if (selected) learnedStops.delete(id);
      else learnedStops.add(id);
    }
    changePlan();
    el("learned-groups").querySelector(`[data-group="${CSS.escape(name)}"]`)?.focus();
  });
  el("learned-locations").addEventListener("change", (event) => {
    const id = event.target.value;
    toggleLearned(id);
    el("learned-locations").querySelector(`input[value="${CSS.escape(id)}"]`)?.focus();
  });
  const chooseLearnedMarker = (event) => {
    const marker = event.target.closest("[data-record]");
    if (!marker || (event.type === "keydown" && ![" ", "Enter"].includes(event.key))) return;
    event.preventDefault();
    toggleLearned(marker.dataset.record);
    el("learned-map-locations").querySelector(`[data-record="${CSS.escape(marker.dataset.record)}"]`)?.focus();
  };
  el("learned-map-locations").addEventListener("click", chooseLearnedMarker);
  el("learned-map-locations").addEventListener("keydown", chooseLearnedMarker);
  el("safety-details-link").addEventListener("click", (event) => {
    event.preventDefault();
    setView("diagnostics", true);
  });
  el("critical-action").addEventListener("click", () => {
    setView("diagnostics", true);
    el("emergency-panel").scrollIntoView({block:"start"});
  });
  el("live-plan").addEventListener("click", () => setView("plan", true));
  async function toggleResultsMap() {
    resultsMap = !resultsMap;
    locatedReport = resultsMap ? intelligence.currentRun() : null;
    drawWorkspace();
    if (resultsMap) await loadTwin("model");
    draw();
    (resultsMap ? el("results-close-map") : el("business-map")).focus();
  }
  for (const id of ["results-map", "business-map", "results-close-map"])
    el(id).addEventListener("click", toggleResultsMap);
  el("camera-expand").addEventListener("click", () => {
    const button = el("camera-expand");
    const focus = button.getAttribute("aria-pressed") !== "true";
    button.setAttribute("aria-pressed", String(focus));
    put("camera-expand", focus ? "Show map" : "Focus camera");
    drawWorkspace();
    draw();
  });
  el("damage-link").addEventListener("click", () => { el("review").open = true; });
  el("mode-options").addEventListener("change", (event) => { choices.mode = event.target.value; changePlan(); });
  el("quality").addEventListener("change", (event) => { choices.quality = event.target.checked; changePlan(); });
  el("adaptive").addEventListener("change", (event) => { choices.adaptive = event.target.checked; changePlan(); });
  el("aisle-options").addEventListener("click", (event) => {
    if (event.target.dataset.aisle && !event.target.disabled) toggleAisle(event.target.dataset.aisle);
  });
  el("slot-options").addEventListener("click", (event) => {
    if (event.target.dataset.slot) toggleSlot(event.target.dataset.slot);
  });
  el("start").addEventListener("click", async () => {
    dispatching = true; notice(); draw();
    try {
      const run = (await api("/api/start", selection())).inspection_id;
      wantedRun = run === lastRun ? null : run;
      setView("live", true);
    } catch (error) { notice(error.message); }
    finally { dispatching = false; draw(); }
  });
  async function stopInspection() {
    if (!emergencyTarget?.inspection_id) return;
    stopping = true;
    draw();
    try {
      await api("/api/abort", { inspection_id: emergencyTarget.inspection_id });
      notice("Stop requested. Waiting for the drone to respond.");
    } catch (error) {
      stopping = false;
      draw();
      notice(error.message);
    }
  }
  el("abort").addEventListener("click", stopInspection);
  el("manual-stop").addEventListener("click", () => el("global-stop").click());
  el("calibration-emergency-stop").addEventListener("click", () => {
    el("calibration-confirm").close("cancel");
    el("global-stop").click();
  });
  el("global-stop").addEventListener("click", () => {
    if (emergencyTarget?.recovery) {
      const {inspection_id, recovery_id, proposal} = emergencyTarget.recovery;
      api("/api/recovery/abort", {inspection_id,recovery_id,proposal}).catch(error => notice(error.message));
    }
    else stopInspection();
  });
  for (const action of ["evaluate", "authorize", "abort"]) {
    el(`recovery-${action}`).addEventListener("click", async () => {
      const r = state?.recovery;
      if (!r) return;
      try {
        await api(`/api/recovery/${action}`, {
          inspection_id: r.inspection_id, recovery_id: r.recovery_id, proposal: r.proposal,
        });
        put("recovery-action-message", "Request sent to the flight controller.");
      } catch (error) { put("recovery-action-message", error.message); }
    });
  }
  el("recovery-replan").addEventListener("click", () => {
    planLocations(state?.recovery?.retry_slots || []);
  });
  el("service-return").addEventListener("click", () => {
    if (state?.safety?.phase === "RECOVERY") el("emergency-panel").scrollIntoView({block: "start"});
    else setView("manual", true);
  });
  el("review-stops").addEventListener("click", () => {
    planLocations(reviewSlots(state.mission));
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
  for (const id of ["obstacle-controls", "flight-obstacle-controls"]) {
    el(id).addEventListener("click", async (event) => {
      const target = event.target.dataset.obstacle;
      if (!target) return;
      try {
        await api("/api/simulation/obstacle", { target });
        put("worker-message", "Gazebo movement requested. Watch the live returns.");
      } catch (error) {
        put("worker-message", error.message);
      }
    });
  }
  const camera = el("camera");
  camera.onload = camera.onerror = () => { cameraLoading = false; };
  setInterval(() => {
    if (!document.hidden && (view === "live" || view === "manual") && state?.camera && !cameraLoading) {
      cameraLoading = true;
      camera.src = "/api/frame.jpg?t=" + Date.now();
    }
  }, 155);
  if (layout.safety_fields) {
    const overview = el("safety-overview");
    overview.onload = overview.onerror = () => { overviewLoading = false; };
    setInterval(() => {
      if (!document.hidden && view === "diagnostics" && state?.overview && !overviewLoading) {
        overviewLoading = true;
        overview.src = "/api/overview.jpg?t=" + Date.now();
      }
    }, 225);
  }
  setView("plan");
  changePlan();
  poll();
}
init().catch((error) => notice(error.message));
