import * as T from "three";
import { OrbitControls } from "./vendor/OrbitControls.js";
import { accessColors, at, makeAircraft, makeWarehouse, slotColors, tint } from "./twin-scene.js";
import { createMeasuredScene } from "./scan.js";

const byId = (id) => document.getElementById(id);
const stages = new Set(["INSPECT", "REPOSITION", "REINSPECT", "QUALITY_CLOSEUP", "RECENTER"]);
const statusNames = {
  uninspected: "Uninspected", outside: "Outside scope", planned: "Planned", inspecting: "Inspecting",
  observed: "Observed", pending: "Pending SAP comparison", match: "Match", discrepancy: "Discrepancy",
  manual: "Manual review required", missed: "Missed",
};
function node(tag, className, content) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (content !== undefined) element.textContent = content;
  return element;
}
function fill(id, value) {
  const item = byId(id);
  if (item.textContent !== value) item.textContent = value;
}

function slotRecord(id, scope, job) {
  const status = job?.status;
  const reading = status?.confirmed?.[id];
  const result = job?.result?.rows?.find((row) => row.slot_id === id);
  const outcome = result?.outcome;
  const photos = (job?.evidence || []).filter((photo) => photo.slot_id === id)
    .sort((first, second) => first.timestamp.localeCompare(second.timestamp));
  const damage = photos.some((photo) => photo.status === "DAMAGED");
  const uncertainty = job?.quality_uncertain?.[id];
  const uncertain = uncertainty && reading?.observation_id === uncertainty.observation_id;
  const manual = status?.adaptive?.manual_review?.[id];
  let state = "uninspected";
  if (scope && !scope.has(id)) state = "outside";
  else if (status?.target === id && stages.has(status.stage)) state = "inspecting";
  else if (manual) state = "manual";
  else if (status?.missed?.includes(id)) state = "missed";
  else if (outcome === "pending" || outcome === "match") state = outcome;
  else if (outcome && outcome !== "uninspected") state = "discrepancy";
  else if (reading) state = "observed";
  else if (scope?.has(id)) state = "planned";
  const latestPhotos = photos.filter((photo) => photo.observation_id === reading?.observation_id);
  const quality = damage ? "Damaged" : latestPhotos.some((photo) => photo.status === "OK") ? "Intact"
    : uncertain ? "Uncertain" : "Not assessed";
  return { state, reading, outcome, quality, manual, photos,
    qualityReason: uncertain ? uncertainty.reason : null,
    attempts: (status?.adaptive?.attempts || []).filter((attempt) => attempt.slot_id === id) };
}
function showSlot(focused, record, job, busy) {
  byId("twin-slot-actions").hidden = !focused;
  byId("twin-slot-record").hidden = !focused;
  if (!focused) return;
  byId("twin-slot-title").textContent = focused;
  byId("twin-slot-summary").textContent = statusNames[record.state];
  byId("twin-reinspect").disabled = busy;
  const labelText = (value) => value ? value.replaceAll("_", " ") : "—";
  const facts = node("dl", "twin-facts");
  for (const [term, definition] of [
    ["Pallet ID", record.reading?.pallet_id || "—"],
    ["Occupancy", labelText(record.reading?.occupancy)],
    ["Label", labelText(record.reading?.label_status)],
    ["SAP comparison", record.outcome === "pending" ? "Pending" : labelText(record.outcome)],
    ["Package quality", record.quality],
  ]) {
    const fact = node("div");
    fact.append(node("dt", "", term), node("dd", "", definition));
    facts.append(fact);
  }
  const contents = [facts];
  if (record.manual) contents.push(node("p", "twin-reading-note", "Manual verification · " + labelText(record.manual)));
  if (record.quality === "Uncertain" && record.qualityReason) contents.push(node("p", "twin-reading-note", record.qualityReason));
  if (record.attempts.length) {
    const attempts = node("ol", "twin-attempts");
    for (const event of record.attempts) {
      const reading = event.reading?.filter(Boolean).map(labelText).join(" / ");
      const attempt = node("li", "", `Attempt ${event.attempt} · ${event.outcome}${reading ? " · " + reading : ""}`);
      if (event.observation_id) attempt.title = event.observation_id;
      attempts.append(attempt);
    }
    contents.push(attempts);
  }
  if (record.photos.length) {
    const gallery = node("div", "twin-photos");
    for (const photo of record.photos) {
      const source = `/evidence/${encodeURIComponent(job.inspection_id)}/${encodeURIComponent(photo.quality_id)}/annotated.png`;
      const link = node("a");
      link.href = source;
      link.target = "_blank";
      link.rel = "noopener";
      link.setAttribute("aria-label", `Open quality photo for ${focused}`);
      const image = node("img");
      image.src = source;
      image.loading = "lazy";
      image.alt = `Camera evidence for ${focused}`;
      const shot = record.attempts.find((attempt) => attempt.quality_id === photo.quality_id);
      link.append(image, node("span", "", shot?.reason === "damage" ? "Damage close-up" : photo.status === "DAMAGED" ? "Damage evidence" : "Intact package"));
      gallery.append(link);
    }
    contents.push(gallery);
  }
  byId("twin-slot-record").replaceChildren(...contents);
}

function path(scene, color, dashed = false, segments = false) {
  const mat = dashed
    ? new T.LineDashedMaterial({ color, dashSize: .29, gapSize: .18, depthTest: false })
    : new T.LineBasicMaterial({ color, depthTest: false });
  const line = segments ? new T.LineSegments(new T.BufferGeometry(), mat) : new T.Line(new T.BufferGeometry(), mat);
  line.frustumCulled = false;
  line.renderOrder = 4;
  line.visible = false;
  scene.add(line);
  return line;
}
function setPath(line, points, lift = 0) {
  const signature = JSON.stringify(points);
  if (signature === line.userData.signature) return;
  line.userData.signature = signature;
  line.visible = points.length > 1;
  line.geometry.dispose();
  line.geometry = new T.BufferGeometry().setFromPoints(points.map(([x, y, z]) => at([x, y, z + lift])));
  if (line.material.isLineDashedMaterial) line.computeLineDistances();
}
function samples(scene, limit, color, size, alpha) {
  const geometry = new T.BufferGeometry();
  const position = new T.BufferAttribute(new Float32Array(limit * 3), 3).setUsage(T.DynamicDrawUsage);
  geometry.setAttribute("position", position);
  geometry.setDrawRange(0, 0);
  const points = new T.Points(geometry, new T.PointsMaterial({ color, size, transparent: true, opacity: alpha, depthWrite: false }));
  points.frustumCulled = false;
  scene.add(points);
  return (vectors) => {
    const length = Math.min(limit, vectors.length);
    for (let result = 0; result < length; result++) position.setXYZ(result, ...vectors[result]);
    position.needsUpdate = true;
    geometry.setDrawRange(0, length);
  };
}

export function createTwin(layout, callbacks) {
  if (!layout.scene) throw new Error("Warehouse scene data is unavailable");
  const viewport = byId("twin-viewport");
  const overlay = byId("twin-markers");
  const renderer = new T.WebGLRenderer({ antialias: true, powerPreference: "low-power" });
  renderer.domElement.setAttribute("aria-label", "3D warehouse scene");
  viewport.prepend(renderer.domElement);
  renderer.domElement.addEventListener("webglcontextlost", (event) => {
    event.preventDefault();
    callbacks.onError("WebGL context lost. The 2D map is available.");
  });
  const camera = new T.PerspectiveCamera(42, 1, .1, 155);
  const controls = new OrbitControls(camera, renderer.domElement);
  controls.minDistance = 5;
  controls.maxDistance = 96;
  controls.maxPolarAngle = Math.PI / 2 - .12;
  controls.enableDamping = true;
  controls.dampingFactor = .18;
  controls.zoomToCursor = true;
  const scene = new T.Scene();
  scene.background = new T.Color(0xedf3fa);
  scene.add(new T.HemisphereLight(0xe9f3ff, 0x9cabc0, 1.55));
  const sun = new T.DirectionalLight(0xffeed6, 1.65);
  sun.position.set(-14, 27, 18);
  scene.add(sun);
  const rim = new T.DirectionalLight(0xb2dafc, .58);
  rim.position.set(22, 19, -25);
  scene.add(rim);
  scene.fog = new T.Fog(scene.background, 79, 140);
  const warehouseModel = new T.Group();
  scene.add(warehouseModel);
  const warehouse = makeWarehouse(layout, warehouseModel);
  const { drone, body, edge } = makeAircraft(scene, layout.avoidance);
  const scanHeading = new T.ArrowHelper(new T.Vector3(1, 0, 0), new T.Vector3(0, .26, 0), .96, 0x9bdbff, .24, .16);
  scanHeading.visible = false;
  for (const tip of scanHeading.children) {
    tip.material.depthTest = false;
    tip.material.depthWrite = false;
    tip.renderOrder = 6;
  }
  drone.add(scanHeading);
  const corridor = warehouse.aerial ? path(scene, 0x8a5cb8, true, true) : null;
  if (corridor) setPath(corridor, layout.aerial.edges.flatMap(([a, b]) =>
    [layout.aerial.nodes[a], layout.aerial.nodes[b]]));
  const planLine = path(scene, 0x4b78a8, true);
  const recoveryPlan = layout.recovery ? path(scene, 0xa85b14, true) : null;
  const recoveryFlown = layout.recovery ? path(scene, 0xa23287) : null;
  const stopped = layout.recovery ? samples(scene, 1, 0xbd3e57, .48, .95) : null;
  if (layout.recovery) {
    recoveryPlan.renderOrder = 7;
    recoveryFlown.renderOrder = 8;
    for (const id of ["twin-recovery-key", "twin-recovery-flown", "twin-recovery-stop"]) byId(id).hidden = false;
  }
  const flownLine = path(scene, 0x214b80);
  const extraLine = path(scene, 0xa85b14, false, true);
  const pendingLine = path(scene, 0xa85b14, true, true);
  const beams = path(scene, 0x4e94bf, false, true);
  beams.material.transparent = true;
  beams.material.opacity = .30;
  beams.material.depthTest = true;
  beams.renderOrder = 2;
  const lidarReturns = samples(scene, 450, 0x3587aa, .08, .79);
  const lidarHits = samples(scene, 300, 0xba3a4d, .15, 1);
  const onboard = new T.Group();
  scene.add(onboard);
  const onboardPoints = layout.avoidance ? samples(onboard, 240, 0x267caa, .070, .76) : null;
  const onboardHazards = layout.avoidance ? samples(onboard, 60, 0xbd3e57, .16, 1) : null;
  const bypass = layout.avoidance ? path(onboard, 0x7c51ac) : null;
  const field = layout.avoidance ? path(onboard, 0x4f9cc0, true, true) : null;
  const direction = layout.avoidance ? path(onboard, 0x9d6c22) : null;
  const mapLayer = new T.Group();
  scene.add(mapLayer);
  const measuredMap = layout.localization ? samples(mapLayer, 2200, 0x408bb0, .088, .82) : null;
  const unmatched = layout.localization ? samples(mapLayer, 120, 0xa26124, .105, .90) : null;
  const estimatedPath = layout.localization ? path(scene, 0x24835f) : null;
  const referencePath = layout.localization?.diagnostics ? path(scene, 0xa26124, true) : null;
  if (referencePath) referencePath.visible = false;

  let width = 1, height = 1, raf = 0, lastDraw = 0, visible = false, eco = false;
  let focus = null, detailSignature = "", sampleSignature = "", startedAt = 0, moving = false, transition = null;
  let sourceSnapshot = null;
  let renderData = null;
  let preset = "iso";
  let following = false;
  let scanMode = false;
  let autoFrameScan = true, framedSpan = 0;
  let modelPreset = "iso", scanPreset = "iso";
  const framedCenter = new T.Vector3();
  const scanOffset = new T.Vector3();
  const scan = layout.localization?.mode === "sensor_based"
    ? createMeasuredScene(byId("twin-panel"), queue, frameMeasuredCloud)
    : null;
  const projected = new T.Vector3();
  const followAnchor = new T.Vector3(), followDelta = new T.Vector3();
  const startPosition = new T.Vector3(), endPosition = new T.Vector3();
  const startRotation = new T.Quaternion(), endRotation = new T.Quaternion();

  const labels = [];
  const taughtLabels = new Map();
  let taughtSignature = "";
  function drawTaughtLocations(records, selected) {
    const signature = JSON.stringify([selected, records]);
    if (signature === taughtSignature) return;
    taughtSignature = signature;
    const present = new Set(records.map(record => record.record_id));
    for (const [id, item] of taughtLabels) {
      if (present.has(id)) continue;
      item.element.remove();
      item.arrow.removeFromParent();
      item.arrow.line.material.dispose();
      item.arrow.cone.material.dispose();
      labels.splice(labels.indexOf(item), 1);
      taughtLabels.delete(id);
    }
    for (const record of records) {
      const id = record.record_id;
      let item = taughtLabels.get(id);
      if (!item) {
        const element = addMarker(record.storage_location_id, "taught-marker", record.position_m, () => callbacks.onTaughtLocation(id));
        item = labels[labels.length - 1];
        item.arrow = new T.ArrowHelper(new T.Vector3(1, 0, 0), item.anchor, .8, 0x7edcff, .18, .15);
        for (const child of item.arrow.children) {
          child.material.depthTest = false;
          child.renderOrder = 9;
        }
        scan.scene.add(item.arrow);
        taughtLabels.set(id, item);
      }
      const status = record.status === "approved" ? "Approved" : record.status;
      const focused = id === selected;
      item.element.textContent = record.storage_location_id;
      item.element.title = `${record.storage_location_id} · ${status} · camera viewpoint`;
      item.element.setAttribute("aria-label", `View taught location ${record.storage_location_id}`);
      item.element.setAttribute("aria-pressed", String(focused));
      item.arrow.position.copy(at(record.position_m));
      item.arrow.setDirection(at(record.camera_direction).normalize());
      item.arrow.setColor(focused ? 0xffffff : 0x7edcff);
      item.anchor.copy(item.arrow.position).add(new T.Vector3(0, .32, 0));
    }
  }
  function addMarker(value, kind, coords, action) {
    const element = node(action ? "button" : "span", "twin-marker " + kind, value);
    if (action) {
      element.type = "button";
      element.addEventListener("click", action);
    }
    overlay.append(element);
    const anchor = at(coords);
    labels.push({ element, anchor, kind });
    return element;
  }
  const markerForSlot = {};
  const markerForAisle = {};
  for (const aisle of layout.aisles) {
    const text = aisle.functional ? `Aisle ${aisle.id}` : `Aisle ${aisle.id} · Scenery`;
    const action = aisle.functional ? () => callbacks.onAisle(aisle.id) : null;
    const marker = addMarker(text, "aisle-marker", [layout.racks[0].x + layout.racks[0].width + 2.3, aisle.y, .18], action);
    if (action) marker.setAttribute("aria-label", `Select aisle ${aisle.id} in 3D`);
    markerForAisle[aisle.id] = marker;
  }
  for (const [id, slot] of Object.entries(layout.slots)) {
    const coords = [slot.bay_center[0], slot.label[1] - .12, slot.bay_center[2] + .47];
    const marker = addMarker(id, "slot-marker", coords, () => selectSlot(id));
    marker.setAttribute("aria-label", `Select location ${id} in 3D`);
    marker.dataset.slot = id;
    markerForSlot[id] = marker;
  }
  const dockLabel = layout.dock
    ? addMarker("Charging dock", "dock-marker", layout.dock.locator, null)
    : null;
  if (!dockLabel) addMarker("H · Launch pad", "pad-marker", [layout.pad.x - .45, layout.pad.y, .12], null);
  const gateLabels = {};
  if (warehouse.aerial) {
    addMarker("Launch shaft", "aerial-marker", layout.aerial.nodes.shaft, null);
    for (const id of Object.keys(layout.aerial.gates)) {
      const entry = at(layout.aerial.nodes["entry_" + id]);
      gateLabels[id] = addMarker(`Descent ${id}`, "aerial-marker", layout.aerial.nodes["entry_" + id], () => {
        setFollow(false);
        const aim = entry.clone().add(new T.Vector3(0, -2.3, 0));
        cameraTo(aim.clone().add(new T.Vector3(-6.7, 5.6, 6.2)), aim);
      });
    }
  }
  if (layout.avoidance) {
    const button = byId("twin-onboard");
    for (const id of ["twin-onboard", "twin-onboard-key", "twin-hazard-key", "twin-bypass-key"]) byId(id).hidden = false;
    button.addEventListener("click", () => {
      onboard.visible = !onboard.visible;
      button.setAttribute("aria-pressed", String(onboard.visible));
      queue();
    });
  }
  addMarker("Transfer", "pad-marker", [layout.crossing_x, layout.aisles.at(-1).y, .12], null);
  const flightLabel = addMarker("", "aircraft-marker", [0, 0, 0], null);
  const flightAnchor = labels.at(-1).anchor;
  for (const [id, scanner] of Object.entries(warehouse.lasers)) {
    addMarker(`LiDAR ${id}`, "sensor-marker", [scanner.pose[0], scanner.pose[1], .20], null);
  }
  if (layout.localization) {
    const layers = [["twin-warehouse-model", warehouseModel], ["twin-measured-map", mapLayer],
                    ["twin-estimated-path", estimatedPath], ["twin-reference-path", referencePath]];
    byId("localization-layers").hidden = false;
    byId("twin-mapping-key").hidden = byId("twin-estimate-key").hidden = false;
    byId("twin-reference-key").hidden = !referencePath;
    for (const [id, layer] of layers) {
      if (!layer) continue;
      const button = byId(id);
      button.hidden = false;
      button.addEventListener("click", () => {
        layer.visible = !layer.visible;
        button.setAttribute("aria-pressed", String(layer.visible));
        queue();
      });
    }
  }

  function queue() {
    if (visible && !document.hidden && !raf) raf = requestAnimationFrame(draw);
  }
  function draw(time) {
    raf = 0;
    if (!visible || document.hidden) return;
    if (time - lastDraw < (eco ? 64 : 40)) { queue(); return; }
    lastDraw = time;
    if (transition) {
      const ratio = Math.min(1, (time - transition.time) / (scanMode ? 620 : 440));
      const eased = 1 - (1 - ratio) ** 3;
      camera.position.lerpVectors(transition.from, transition.to, eased);
      controls.target.lerpVectors(transition.start, transition.end, eased);
      if (ratio === 1) transition = null;
    }
    if (moving) {
      const ratio = Math.min(1, (time - startedAt) / 270);
      drone.position.lerpVectors(startPosition, endPosition, ratio);
      drone.quaternion.slerpQuaternions(startRotation, endRotation, ratio);
      moving = ratio < 1;
    }
    if (following && !transition && sourceSnapshot) {
      followDelta.subVectors(drone.position, followAnchor);
      camera.position.add(followDelta);
      controls.target.add(followDelta);
      followAnchor.copy(drone.position);
    }
    const orbiting = controls.update();
    if (scanMode) scan.scalePoints(camera.position.distanceTo(controls.target));
    renderer.render(scanMode ? scan.scene : scene, camera);
    flightAnchor.copy(drone.position);
    flightAnchor.y += scanMode ? .87 : 1.10;
    const used = [];
    const denseOffsets = [0, -17, 17, -34, 34, -51, 51, -68, 68];
    for (const { element, anchor, kind } of labels) {
      projected.copy(anchor).project(camera);
      const within = projected.z > -1 && projected.z < 1 && Math.abs(projected.x) < .97 && Math.abs(projected.y) < .97;
      const show = within && (element === flightLabel ? drone.visible
        : kind === "taught-marker" ? scanMode : !scanMode && warehouseModel.visible)
        && (kind !== "aerial-marker" || warehouse.aerial.infrastructure.visible);
      element.style.visibility = show ? "visible" : "hidden";
      if (!show) continue;
      const x = (projected.x + 1) * width / 2;
      const y = (1 - projected.y) * height / 2;
      const dense = kind === "taught-marker" || kind === "slot-marker" && (preset === "top" || width < 1000);
      const shift = dense
        ? denseOffsets.find((delta) => y + delta > 19 && y + delta < height - 18
            && used.every(([cx, cy]) => Math.abs(cx - x) > 58 || Math.abs(cy - (y + delta)) >= 17)) || 0
        : 0;
      if (dense) used.push([x, y + shift]);
      element.style.transform = `translate(${x}px,${y + shift}px) translate(-50%,-50%)`;
    }
    if (transition || moving || orbiting) queue();
  }
  function resize() {
    if (!visible || !viewport.clientWidth || !viewport.clientHeight) return;
    width = viewport.clientWidth;
    height = viewport.clientHeight;
    const dpr = window.devicePixelRatio || 1;
    renderer.setPixelRatio(Math.min(dpr, eco ? .85 : scanMode ? 1 : 1.2));
    renderer.setSize(width, height, false);
    const previousAspect = camera.aspect;
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
    if (scanMode && autoFrameScan && !following && Math.abs(previousAspect - camera.aspect) > .06) {
      fitScan(scanDirection(preset), false);
    }
    queue();
  }
  function cameraTo(position, aim, animate = true) {
    animate &&= !matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (animate) transition = { from: camera.position.clone(), start: controls.target.clone(),
      to: position, end: aim, time: performance.now() };
    else {
      transition = null;
      camera.position.copy(position);
      controls.target.copy(aim);
      controls.update();
    }
    queue();
  }

  function scanDirection(view) {
    if (view === "top") return new T.Vector3(0, 1, .004);
    if (view === "side") return new T.Vector3(.99, .055, .17);
    return new T.Vector3(-.62, .53, .74);
  }

  function fitScan(direction, animate) {
    const empty = scan.bounds.isEmpty();
    const target = empty ? drone.position.clone() : scan.bounds.getCenter(new T.Vector3());
    framedCenter.copy(target);
    framedSpan = empty ? 8 : scan.bounds.getSize(new T.Vector3()).length();
    direction.normalize();
    const right = new T.Vector3(0, 1, 0).cross(direction).normalize();
    const up = direction.clone().cross(right);
    const tanV = Math.tan(T.MathUtils.degToRad(camera.fov) / 2);
    const tanH = tanV * camera.aspect;
    let distance = empty ? 13 : 6;
    if (!empty) {
      const { min, max } = scan.bounds;
      for (const x of [min.x, max.x]) for (const y of [min.y, max.y]) for (const z of [min.z, max.z]) {
        scanOffset.set(x, y, z).sub(target);
        const projected = Math.max(Math.abs(scanOffset.dot(right)) / tanH, Math.abs(scanOffset.dot(up)) / tanV);
        distance = Math.max(distance, scanOffset.dot(direction) + projected * 1.13);
      }
    }
    cameraTo(target.clone().addScaledVector(direction, distance), target, animate);
  }

  function choosePreset(next, animate = true) {
    setFollow(false);
    preset = next;
    byId("twin-iso").setAttribute("aria-pressed", String(next === "iso"));
    byId("twin-top").setAttribute("aria-pressed", String(next === "top"));
    byId("scan-side").setAttribute("aria-pressed", String(next === "side"));
    if (scanMode) {
      fitScan(scanDirection(next), animate);
      return;
    }
    const f = layout.floor;
    const target = at([f.x + f.width * .47, f.y + f.height / 2, 0]);
    const offset = next === "iso" ? new T.Vector3(-26, 32, 33) : new T.Vector3(0, 43, .12);
    // Keep the whole floor in view on narrow cards as well.
    offset.multiplyScalar(Math.max(1, 1.31 / camera.aspect));
    cameraTo(target.clone().add(offset), target, animate);
  }
  function frameMeasuredCloud(first) {
    if (following || !autoFrameScan || scan.bounds.isEmpty()) return;
    const span = scan.bounds.getSize(new T.Vector3()).length();
    const center = scan.bounds.getCenter(new T.Vector3());
    if (first || span > framedSpan * 1.20 || center.distanceTo(framedCenter) > 2.8) fitScan(scanDirection(preset), !first);
  }
  function focusRack() {
    if (!focus) return;
    setFollow(false);
    const target = at(layout.slots[focus].bay_center);
    target.y += .75;
    cameraTo(target.clone().add(new T.Vector3(-3.5, 4.0, 7.3)), target);
  }
  function setFollow(enabled) {
    following = enabled;
    byId("twin-follow").setAttribute("aria-pressed", String(enabled));
    if (enabled) {
      followAnchor.copy(drone.position);
      const target = drone.position.clone();
      const offset = scanMode ? scanDirection(preset).normalize().multiplyScalar(10) : new T.Vector3(-6.4, 6.0, 9.5);
      cameraTo(target.clone().add(offset), target);
    }
  }
  function selectSlot(id) {
    callbacks.onSlot(id);
  }
  const ray = new T.Raycaster(), pointer = new T.Vector2();
  let down = null;
  renderer.domElement.addEventListener("pointerdown", (event) => {
    if (event.isPrimary && event.button === 0) down = [event.clientX, event.clientY];
  });
  renderer.domElement.addEventListener("pointerup", (event) => {
    if (!event.isPrimary || event.button !== 0 || !down) return;
    const [x, y] = down;
    down = null;
    if (scanMode) return;
    if (Math.hypot(event.clientX - x, event.clientY - y) > 5) return;
    const bounds = renderer.domElement.getBoundingClientRect();
    pointer.set((x - bounds.left) / bounds.width * 2 - 1, 1 - (y - bounds.top) / bounds.height * 2);
    ray.setFromCamera(pointer, camera);
    const item = ray.intersectObjects(warehouse.picks, false)[0]?.object?.userData.selection;
    if (item?.type === "slot") selectSlot(item.id);
    if (item?.type === "aisle") callbacks.onAisle(item.id);
  });
  renderer.domElement.addEventListener("pointercancel", () => { down = null; });
  controls.addEventListener("change", queue);
  controls.addEventListener("start", () => { transition = null; if (scanMode) autoFrameScan = false; });
  new ResizeObserver(resize).observe(viewport);
  document.addEventListener("visibilitychange", queue);
  byId("twin-iso").addEventListener("click", () => { autoFrameScan = true; choosePreset("iso"); });
  byId("twin-top").addEventListener("click", () => { autoFrameScan = true; choosePreset("top"); });
  byId("scan-side").addEventListener("click", () => { autoFrameScan = true; choosePreset("side"); });
  byId("scan-fit").addEventListener("click", () => {
    setFollow(false);
    fitScan(camera.position.clone().sub(controls.target), true);
  });
  byId("twin-follow").addEventListener("click", () => setFollow(!following));
  byId("twin-reset").addEventListener("click", () => { autoFrameScan = true; choosePreset(scanMode ? "iso" : preset); });
  byId("twin-focus").addEventListener("click", focusRack);
  byId("twin-reinspect").addEventListener("click", () => { if (focus) callbacks.onReinspect(focus); });
  byId("twin-economy").addEventListener("click", () => {
    eco = !eco;
    byId("twin-economy").setAttribute("aria-pressed", String(eco));
    resize();
    update(renderData);
  });
  byId("twin-laser-key").hidden = byId("twin-returns-key").hidden = !layout.laser_fields;
  byId("twin-access-key").hidden = !layout.safety_fields;
  if (warehouse.aerial) {
    for (const [id, target] of [["twin-aerial", warehouse.aerial.infrastructure], ["twin-corridor", corridor]]) {
      const button = byId(id);
      button.hidden = false;
      button.addEventListener("click", () => {
        target.visible = !target.visible;
        button.setAttribute("aria-pressed", String(target.visible));
        queue();
      });
    }
  }

  function updateDrone(state) {
    const fresh = Boolean(state?.robot && state.position);
    byId("twin-follow").disabled = !fresh;
    const position = state?.position;
    if (position) {
      const [, , z, yaw] = position;
      const rot = state.orientation || [0, 0, Math.sin(yaw / 2), Math.cos(yaw / 2)];
      endPosition.copy(at(position));
      endRotation.set(rot[0], rot[2], -rot[1], rot[3]).normalize();
      if (!drone.visible || !fresh || sourceSnapshot === null) {
        drone.position.copy(endPosition);
        drone.quaternion.copy(endRotation);
        moving = false;
      } else if (sourceSnapshot !== JSON.stringify([position, rot])) {
        startPosition.copy(drone.position);
        startRotation.copy(drone.quaternion);
        startedAt = performance.now();
        moving = true;
      }
      sourceSnapshot = fresh ? JSON.stringify([position, rot]) : null;
      drone.visible = true;
      flightLabel.textContent = fresh ? `UAV · ${z.toFixed(2)} m` : "UAV · Last pose";
      if (fresh && state.energy?.fresh) flightLabel.textContent += ` · ${Math.round(state.energy.percent)}%`;
      fill("twin-odom", fresh ? `Live odometry · Z ${z.toFixed(2)} m` : "Odometry stale · Last pose");
    } else {
      if (moving) {
        drone.position.copy(endPosition);
        drone.quaternion.copy(endRotation);
        moving = false;
      }
      sourceSnapshot = null;
      fill("twin-odom", drone.visible ? "Connection lost · Last pose" : "Waiting for odometry");
      flightLabel.textContent = "UAV · Last pose";
    }
    body.color.setHex(fresh ? scanMode ? 0x58a4ee : 0x3974ba : 0x9d7844);
    edge.color.setHex(fresh ? scanMode ? 0x76c5ff : 0x214b80 : 0xa46522);
    scanHeading.visible = scanMode && fresh;
    flightLabel.classList.toggle("stale", !fresh);
    byId("twin-odom").classList.toggle("stale", !fresh);
  }
  function updateSafety(state) {
    const safety = state?.safety;
    for (const [id, zone] of Object.entries(warehouse.zones)) {
      const status = safety?.zones?.[id]?.state || "FAULT";
      const opacity = { OPEN: .12, PREPARING: .25, RESERVED: .24, INTRUSION: .37, FAULT: .20 }[status];
      tint(zone, accessColors[status], opacity);
      if (markerForAisle[id]) markerForAisle[id].title = `Aisle ${id} · ${status}`;
    }
    for (const signal of warehouse.signals) {
      const zone = safety?.zones?.[signal.zone];
      const active = zone && zone.signals_acknowledged ? zone.state : "FAULT";
      const activeIndex = active === "OPEN" ? 2 : active === "PREPARING" ? 1 : 0;
      signal.lenses.forEach((lens, index) => {
        const activeLens = index === activeIndex || (active === "FAULT" && index === 1);
        lens.material.color.setHex(activeLens ? accessColors[active] : 0x2b3b49);
      });
    }
    if (!layout.safety_fields) { fill("twin-source", "Safety disabled"); return; }
    if (safety?.sensor_mode === "virtual" || !layout.laser_fields) {
      fill("twin-source", `Virtual presence · ${safety?.alarm ? statusText(safety.alarm.event) : safety?.phase || "Unavailable"}`);
      return;
    }
    const scans = Object.entries(safety?.scans || {}).filter(([id]) => safety.zones[id]?.sensor === "FRESH");
    const points = [], hits = [], rays = [];
    for (const [id, scan] of scans) {
      const [x, y, z] = warehouse.lasers[id].pose;
      scan.points.forEach(([px, py], i) => {
        if (!eco || i % 2 === 0) points.push([px, z, -py]);
        if (!eco && i % 9 === 0) rays.push([x, y, z], [px, py, z]);
      });
      hits.push(...scan.hits.map(([px, py]) => [px, z, -py]));
    }
    const signature = JSON.stringify([points, hits]);
    if (signature !== sampleSignature) {
      sampleSignature = signature;
      lidarReturns(points);
      lidarHits(hits);
    }
    setPath(beams, rays);
    const age = scans.length ? ` · Max age ${Math.max(...scans.map(([, scan]) => scan.age_ms))} ms` : "";
    const scanHealth = scans.length === Object.keys(warehouse.lasers).length ? "live scan" : scans.length ? "partial feed" : "scan unavailable";
    fill("twin-source", safety?.alarm ? `LiDAR · ${statusText(safety.alarm.event)} · ${scanHealth} · ${hits.length} returns`
      : `LiDAR · ${scanHealth} · ${hits.length} returns${age}`);
  }
  function statusText(value) { return value.replaceAll("_", " "); }
  function update(data) {
    renderData = data;
    if (!visible || !data) return;
    const { state, view, preview, job, selection } = data;
    if (scanMode) {
      drawTaughtLocations(data.taught, data.taughtSelection);
      updateDrone(state);
      scan.update(state, data.activeFlight);
      return;
    }
    const planning = view === "plan";
    const current = planning ? null : job;
    const scope = planning ? (selection.size ? selection : null) : job ? new Set(job.slots) : null;
    const selectedAisles = new Set(Array.from(scope || []).map((id) => layout.slots[id].aisle));
    for (const [id, area] of Object.entries(warehouse.aisles)) {
      const selected = selectedAisles.has(id);
      area.group.visible = selected;
      markerForAisle[id].setAttribute("aria-pressed", String(selected));
    }
    for (const [id, meshes] of Object.entries(warehouse.slots)) {
      const record = slotRecord(id, scope, current);
      const marker = markerForSlot[id];
      const color = slotColors[record.state];
      const active = record.state === "inspecting";
      marker.dataset.status = record.state;
      marker.dataset.quality = record.quality.toLowerCase();
      marker.dataset.focused = String(id === focus);
      marker.setAttribute("aria-pressed", String(scope?.has(id) || false));
      marker.title = statusNames[record.state] + " · " + record.quality;
      marker.style.setProperty("--marker", "#" + color.toString(16).padStart(6, "0"));
      meshes.outline.material.color.setHex(active || id === focus ? 0x123f76 : color);
      meshes.outline.material.transparent = true;
      meshes.outline.material.opacity = record.state === "outside" ? .33 : .95;
      meshes.face.material.color.setHex(record.quality === "Damaged" ? 0xb14251 : color);
      meshes.face.material.opacity = record.quality === "Damaged" || active ? .92 : scope?.has(id) ? .51 : .16;
      meshes.cover.visible = !record.reading || record.reading.occupancy === "uncertain";
      meshes.cargo.visible = record.reading?.occupancy === "occupied";
      if (id === focus) {
        const signature = JSON.stringify([id, record, !!state?.busy, current?.inspection_id]);
        if (signature !== detailSignature) {
          detailSignature = signature;
          showSlot(id, record, current, !!state?.busy);
        }
      }
    }
    const recovery = state?.recovery;
    if (recoveryPlan) {
      setPath(recoveryPlan, recovery?.planned || [], .045);
      setPath(recoveryFlown, recovery?.flown || [], .065);
      const stop = recovery?.stopped?.position;
      stopped(stop ? [[stop[0], stop[2], -stop[1]]] : []);
    }
    const returnPath = current?.status?.energy?.return_path;
    setPath(planLine, planning ? preview?.points || [] : recovery ? [] : returnPath?.length ? returnPath : job?.planned || []);
    setPath(flownLine, planning || recovery ? [] : job?.flown || [], .047);
    const moves = current?.status?.adaptive?.moves || [];
    setPath(extraLine, moves.filter((move) => move.actual).flatMap((move) => [move.from, move.actual]), .088);
    setPath(pendingLine, moves.filter((move) => !move.actual).flatMap((move) => [move.from, move.target]), .088);
    if (layout.avoidance) {
      const a = current?.status?.avoidance;
      const coordinates = points => (points || []).map(([x, y, z]) => [x, z, -y]);
      onboardPoints(coordinates(a?.point_cloud));
      onboardHazards(coordinates(a?.hazard_points));
      setPath(bypass, a?.maneuver || [], .033);
      const rays = [];
      if (a?.origin) {
        const [x, y, z] = a.origin;
        const rings = (angle) => [
          [x + 1.1 * Math.cos(angle), y + 1.1 * Math.sin(angle), z],
          [x + 1.1 * Math.cos(angle), y, z + 1.1 * Math.sin(angle)],
        ];
        for (let i = 0; i < 36; i++) {
          const begin = rings(i * Math.PI / 18), end = rings((i + 1) * Math.PI / 18);
          rays.push(begin[0], end[0], begin[1], end[1]);
        }
      }
      setPath(field, rays);
      setPath(direction, a?.origin ? [a.origin, a.origin.map((v, i) => v + a.direction[i] * a.verified_distance)] : []);
    }
    if (layout.localization) {
      const localization = state?.localization;
      const vectors = points => (points || []).map(([x, y, z]) => [x, z, -y]);
      measuredMap(vectors(localization?.map_points));
      unmatched(vectors(localization?.unmatched));
      setPath(estimatedPath, localization?.trajectory || [], .021);
      if (referencePath) setPath(referencePath, state?.localization_validation?.trajectory || [], .035);
    }
    updateDrone(state);
    if (recovery?.cause && recovery.phase !== "RECOVERY_COMPLETE")
      flightLabel.textContent += ` · ${recovery.cause.replaceAll("_", " ")}`;
    if (warehouse.aerial) {
      const safety = state?.safety?.aerial;
      warehouse.aerial.worker.visible = !!safety?.worker;
      if (safety?.worker) warehouse.aerial.worker.position.copy(at([safety.worker[0], safety.worker[1], 0]));
      for (const [id, area] of Object.entries(warehouse.aerial.gates)) {
        const cleared = safety?.descents?.[id]?.cleared;
        gateLabels[id].dataset.cleared = String(!!cleared);
        gateLabels[id].title = `Focus descent ${id} · ${cleared ? "Cleared" : "Clearance unavailable"}`;
        tint(area, cleared ? 0x27835d : 0x8a5cb8, .22);
      }
    }
    if (dockLabel) {
      const phase = state?.energy?.dock || "FAULT";
      dockLabel.dataset.dock = phase.toLowerCase();
      dockLabel.textContent = stageName(phase);
    }
    updateSafety(state);
    queue();
  }
  return {
    update,
    setMode(mode) {
      const measured = mode === "scan" && !!scan;
      if (measured === scanMode) return;
      if (scanMode) scanPreset = preset;
      else modelPreset = preset;
      scanMode = measured;
      autoFrameScan = true;
      controls.maxPolarAngle = Math.PI / 2 - (scanMode ? .045 : .12);
      (scanMode ? scan.scene : scene).add(drone);
      renderer.domElement.setAttribute("aria-label", scanMode ? "Measured LiDAR point cloud" : "3D warehouse scene");
      byId("twin-panel").dataset.mapMode = mode;
      scan.setVisible(visible && scanMode);
      choosePreset(scanMode ? scanPreset : modelPreset, false);
      update(renderData);
    },
    focusTaughtLocation(position) {
      if (!scanMode) return;
      setFollow(false);
      autoFrameScan = false;
      const target = at(position);
      cameraTo(target.clone().add(scanDirection(preset).normalize().multiplyScalar(6.8)), target);
    },
    focusDock() {
      if (!dockLabel) return;
      setFollow(false);
      const target = at([layout.pad.x, layout.pad.y, .22]);
      cameraTo(target.clone().add(new T.Vector3(-4.2, 3.3, 3.9)), target);
    },
    focusSlot(id) { focus = id; if (renderData) update(renderData); },
    setVisible(enabled) {
      const first = !visible && enabled && lastDraw === 0;
      visible = enabled;
      scan?.setVisible(visible && scanMode);
      if (!visible) { cancelAnimationFrame(raf); raf = 0; return; }
      resize();
      if (first) choosePreset("iso", false);
      update(renderData);
    },
  };
}

function stageName(phase) {
  return "Dock · " + phase.toLowerCase().replace(/^./, (letter) => letter.toUpperCase());
}
