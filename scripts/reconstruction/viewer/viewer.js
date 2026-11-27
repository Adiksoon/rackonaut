import * as THREE from "three";
import { OrbitControls } from "../../../ros2_ws/src/rackonaut_control/web/vendor/OrbitControls.js";
import { instances, measuredCloud, warehouseTemplate, world } from "../../../ros2_ws/src/rackonaut_control/web/rack-templates.js";

const el = id => document.getElementById(id);
const fmt = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
const samples = {
  goal24: "../../../docs/enhanced-twin-evidence/goal24.json",
  goal26: "../../../docs/enhanced-twin-evidence/goal26.json",
};
const scene = new THREE.Scene();
const lightBackground = new THREE.Color("#dce6f1"), scanBackground = new THREE.Color("#182b42");
scene.background = lightBackground;
const perspective = new THREE.PerspectiveCamera(38, 1, .05, 280);
const plan = new THREE.OrthographicCamera(-1, 1, 1, -1, .05, 280);
let camera = perspective, orthoHeight = 5;
const viewport = el("viewport");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({antialias: true});
} catch {
  el("error").textContent = "The 3D comparison requires a working WebGL browser.";
  el("error").hidden = false;
  throw new Error("WebGL unavailable");
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.6));
viewport.append(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.minDistance = .5;
controls.maxDistance = 170;
controls.minZoom = .18;
controls.maxZoom = 16;
controls.addEventListener("change", paint);
scene.add(new THREE.HemisphereLight(0xf7fbff, 0x74849c, 1.85));
const key = new THREE.DirectionalLight(0xfff3db, 2.1);
key.position.set(-7, 17, 9);
scene.add(key);

let data, cloud, measured, enhanced, selectedLine, localFile;
let mode = "enhanced", view = "isometric", fitTarget = "racks", selectedId;
let markers = [], request = 0;
const projection = new THREE.Vector3();

function paint() {
  renderer.render(scene, camera);
  for (const {button, point, dock} of markers) {
    projection.copy(point).project(camera);
    button.hidden = (dock && mode !== "enhanced") || !Number.isFinite(projection.x) ||
      Math.abs(projection.x) > .985 || Math.abs(projection.y) > .96 || Math.abs(projection.z) > 1;
    button.style.left = `${(projection.x+1)*50}%`;
    button.style.top = `${(1-projection.y)*50}%`;
  }
}

function destroy(object) {
  if (!object) return;
  scene.remove(object);
  object.traverse(item => {
    item.geometry?.dispose();
    item.material?.dispose();
  });
}

function measuredModel(packet, highlight = false) {
  const result = new THREE.Group();
  for (const row of packet.rows) {
    const group = new THREE.Group();
    group.rotation.y = row.yaw_rad;
    const shelves = row.levels.flatMap(level => level.patches_uv.map(([ul,vl,uh,vh]) =>
      [(ul+uh)/2,level.z+(highlight ? .013 : 0),-(vl+vh)/2,uh-ul,.05,vh-vl]));
    const uprights = row.posts.map(([u,v,lo,hi]) => [u,(lo+hi)/2,-v,.085,hi-lo,.085]);
    for (const mesh of [instances(shelves, highlight ? "#238f88" : "#cb9156"), instances(uprights, "#4f8586")]) {
      if (mesh) group.add(mesh);
    }
    result.add(group);
  }
  return result;
}

let support;
function changeLayer(next) {
  if (!data) return;
  mode = next;
  const twin = mode === "enhanced" && enhanced;
  const overlay = el("overlay").checked && mode !== "cloud";
  el("overlay").disabled = mode === "cloud";
  el("show-route").disabled = !twin || !data.enhanced.route_edges_m.length;
  el("route-label").textContent = data.enhanced?.route_source === "recorded_trajectory" ? "Recorded calibration flight" : "Recorded route";
  el("show-support").disabled = !twin || !data.rows.length;
  scene.background = mode === "cloud" ? scanBackground : lightBackground;
  measured.visible = mode === "measured";
  support.visible = Boolean(twin && el("show-support").checked);
  if (enhanced) {
    enhanced.model.visible = Boolean(twin);
    enhanced.context.visible = Boolean(twin);
    enhanced.route.visible = Boolean(twin && el("show-route").checked);
  }
  cloud.visible = mode === "cloud" || overlay;
  cloud.material.opacity = overlay ? .39 : .9;
  cloud.material.size = overlay ? .061 : .074;
  cloud.material.depthTest = !overlay;
  cloud.renderOrder = 4;
  selectedLine && (selectedLine.renderOrder = 6);
  document.querySelectorAll("[data-mode]").forEach(button =>
    button.setAttribute("aria-pressed", String(button.dataset.mode === mode)));
  const legends = {
    enhanced: support.visible ? "Teal · measured rack fragments" : "Rack templates · fitted to calibration",
    measured: "Measured shelf fragments and uprights",
    cloud: "Original LiDAR endpoints · colored by height",
  };
  el("legend").textContent = legends[mode] + (overlay ? " · LiDAR overlay" : "");
  showLocations();
}

function viewBounds() {
  if (fitTarget === "survey" && mode === "enhanced" && enhanced && (data.enhanced.floor || data.enhanced.dock)) {
    const box = new THREE.Box3().setFromObject(enhanced.context).union(new THREE.Box3().setFromObject(enhanced.model));
    if (enhanced.route.visible && data.enhanced.route_edges_m.length) box.union(new THREE.Box3().setFromObject(enhanced.route));
    return box;
  }
  if ((fitTarget === "survey" && mode !== "enhanced") || !data.rows.length || mode === "cloud") {
    return cloud.geometry.boundingBox.clone();
  }
  return new THREE.Box3().setFromObject(mode === "enhanced" ? enhanced.model : measured);
}

function cameraBasis() {
  const yaw = (data.rows[0]?.yaw_rad ?? 0) % Math.PI;
  // Point the plan consistently along the row even when its undirected axis
  // crosses the zero-degree boundary between two calibrations.
  const axis = yaw > Math.PI/2 ? yaw - Math.PI : yaw;
  const vector = view === "top" ? new THREE.Vector3(0,1,.000001)
    : view === "side" ? new THREE.Vector3(0,0,1).applyAxisAngle(THREE.Object3D.DEFAULT_UP, axis)
    : new THREE.Vector3(.66,.69,.94).applyAxisAngle(THREE.Object3D.DEFAULT_UP, axis);
  return vector.normalize();
}

function sizeOrtho() {
  plan.left = -orthoHeight*perspective.aspect;
  plan.right = -plan.left;
  plan.top = orthoHeight;
  plan.bottom = -orthoHeight;
  plan.updateProjectionMatrix();
}

function setView(next, target = fitTarget) {
  if (!data) return;
  view = next;
  fitTarget = target;
  document.querySelectorAll("[data-view]").forEach(button =>
    button.setAttribute("aria-pressed", String(button.dataset.view === view)));
  el("view-help").textContent = view === "isometric" ? "Drag to orbit · Scroll to zoom" : "Drag to pan · Scroll to zoom";
  const box = viewBounds();
  box.getCenter(controls.target);
  const direction = cameraBasis();
  const right = new THREE.Vector3().crossVectors(THREE.Object3D.DEFAULT_UP,direction).normalize();
  const up = new THREE.Vector3().crossVectors(direction,right);
  let distance = 1;
  orthoHeight = 1;
  const tan = Math.tan(THREE.MathUtils.degToRad(perspective.fov)/2);
  const corners = [];
  for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y])
    for (const z of [box.min.z, box.max.z]) corners.push(new THREE.Vector3(x,y,z).sub(controls.target));
  for (const point of corners) {
    const half = Math.max(Math.abs(point.dot(up)), Math.abs(point.dot(right))/perspective.aspect);
    orthoHeight = Math.max(orthoHeight, half*1.20);
    distance = Math.max(distance, point.dot(direction) + half*1.19/tan);
  }
  camera = view === "isometric" ? perspective : plan;
  controls.object = camera;
  controls.enableRotate = view === "isometric";
  controls.mouseButtons.LEFT = controls.enableRotate ? THREE.MOUSE.ROTATE : THREE.MOUSE.PAN;
  controls.touches.ONE = controls.enableRotate ? THREE.TOUCH.ROTATE : THREE.TOUCH.PAN;
  if (camera === plan) {
    plan.zoom = 1;
    sizeOrtho();
    distance = Math.max(distance, 10);
  }
  camera.position.copy(controls.target).addScaledVector(direction,distance);
  controls.update();
  paint();
}

function chooseLocation(location) {
  selectedId = location?.id;
  el("location-detail").hidden = !location;
  for (const button of document.querySelectorAll("[data-location]")) {
    button.setAttribute("aria-pressed", String(button.dataset.location === selectedId));
  }
  destroy(selectedLine);
  selectedLine = null;
  if (location) {
    const level = location.level ? `Level ${location.level}.` : "Shelf level unconfirmed.";
    const explanation = {
      projected: `Measured rack face ${location.rack_id}. ${level} ${fmt.format(location.distance_m)} m from the camera. ${location.support_nearby} nearby returns.`,
      estimated: `Estimated rack face ${location.rack_id}. ${level} ${location.reason}`,
      unplaced: `${location.reason} The marker shows the drone’s capture position.`,
    };
    el("location-explanation").textContent = explanation[location.status];
    const photo = el("location-photo");
    photo.hidden = !location.photo_jpeg;
    if (location.photo_jpeg) photo.src = "data:image/jpeg;base64," + location.photo_jpeg;
    else photo.removeAttribute("src");
    if (location.camera_origin_m && location.position_m) {
      const line = new THREE.BufferGeometry().setFromPoints([world(location.camera_origin_m),world(location.position_m)]);
      selectedLine = new THREE.Line(line,new THREE.LineDashedMaterial({
        color: location.status === "estimated" ? 0xca8739 : 0x226dad,
        dashSize: .14, gapSize: .10, depthTest: false,
      }));
      selectedLine.renderOrder = 6;
      selectedLine.computeLineDistances();
      scene.add(selectedLine);
    }
  }
  paint();
}

function locationButton(location, onStage) {
  const button = document.createElement("button");
  button.type = "button";
  button.dataset.location = location.id;
  button.setAttribute("aria-pressed","false");
  const labels = {projected: "Measured", estimated: "Estimated", unplaced: "Unplaced"};
  button.setAttribute("aria-label", location.id + " · " + labels[location.status]);
  button.textContent = location.id;
  if (onStage) {
    button.className = "marker";
    button.dataset.status = location.status;
    if (location.status === "unplaced") button.append(" · viewpoint");
  } else {
    const status = document.createElement("small");
    status.textContent = labels[location.status] + (location.rack_id ? ` · ${location.rack_id}` : "");
    button.append(status);
  }
  button.addEventListener("click", () => chooseLocation(location));
  return button;
}

function showLocations() {
  const items = (mode === "enhanced" ? data.enhanced?.locations : data.locations) ?? data.locations;
  markers = items.map(item => ({button: locationButton(item, true), point: world(item.position_m || item.viewpoint_m)}));
  if (data.enhanced?.dock) {
    const label = document.createElement("span");
    label.className = "dock-marker";
    label.textContent = "Dock";
    markers.push({button: label, point: world(data.enhanced.dock.position_m), dock: true});
  }
  el("markers").replaceChildren(...markers.map(item => item.button));
  el("location-list").replaceChildren(...items.map(item => locationButton(item, false)));
  chooseLocation(items.find(item => item.id === selectedId));
}

function provenance(packet) {
  const twin = packet.enhanced;
  el("point-count").textContent = fmt.format(packet.point_count);
  el("row-count").textContent = fmt.format(packet.rows.length);
  el("archive-description").textContent = `${packet.label} · Warehouse calibration`;
  el("coverage").textContent = twin
    ? `${twin.rows.length} supported rack ${twin.rows.length === 1 ? "row" : "rows"} in the surveyed area.`
    : "This archive contains the measured reconstruction.";
  el("geometry-source").textContent = twin
    ? `Rack placement and levels come from LiDAR${twin.keyframes ? " and registered keyframes" : ""}. Shelves, steel profiles and bay ends are fitted templates. Floor and aisle outlines are inferred. Low wall sections show measured wall lines. Dock and route come from the archive.`
    : "The original rack model shows measured fragments.";
  const entries = (twin?.rows ?? []).map(row => {
    const entry = document.createElement("div");
    entry.className = "rack-entry";
    const line = document.createElement("p"), details = document.createElement("small");
    line.textContent = `${row.id} · ${row.dimensions_m.map(n => fmt.format(n)).join(" × ")} m`;
    const observed = row.observed_bounds_uv[1][0] - row.observed_bounds_uv[0][0];
    const additional = Math.max(0, row.dimensions_m[0] - observed);
    const pitch = row.post_pitch_m ? `${fmt.format(row.post_pitch_m)} m fitted bay pitch` : "Generic bays · pitch unresolved";
    const coverage = row.quality.deck_area_support_fraction.map(n => `${Math.round(100*n)}%`).join(" / ");
    details.textContent = `${row.levels_m.length} levels · ${pitch}. Measured length ${fmt.format(observed)} m` +
      (additional > .01 ? ` + ${fmt.format(additional)} m fitted beyond` : "") + `. Deck support ${coverage}.`;
    entry.append(line, details);
    return entry;
  });
  el("rack-details").replaceChildren(...entries);
}

function show(packet) {
  if (packet.version !== 1 || !Number.isInteger(packet.point_count) || packet.point_count < 1 || packet.point_count > 80000 ||
      !Array.isArray(packet.rows) || !Array.isArray(packet.locations)) throw new Error("Select a Rackonaut reconstruction bundle.");
  const nextCloud = measuredCloud(packet);
  const nextMeasured = measuredModel(packet);
  const nextSupport = measuredModel(packet, true);
  const nextEnhanced = packet.enhanced ? warehouseTemplate(packet.enhanced) : null;
  for (const object of [cloud, measured, support, enhanced?.model, enhanced?.context, enhanced?.route]) destroy(object);
  data = packet;
  cloud = nextCloud;
  measured = nextMeasured;
  support = nextSupport;
  enhanced = nextEnhanced;
  scene.add(cloud, measured, support);
  if (enhanced) scene.add(enhanced.model, enhanced.context, enhanced.route);
  selectedId = undefined;
  provenance(packet);
  document.querySelector('[data-mode="enhanced"]').disabled = !enhanced;
  changeLayer(mode === "enhanced" && !enhanced ? "measured" : mode);
  setView(view);
}

async function load(read) {
  const id = ++request;
  el("error").hidden = true;
  try {
    const packet = await read();
    if (request === id) show(packet);
  } catch (error) {
    if (request !== id) return;
    el("error").textContent = error.message;
    el("error").hidden = false;
  }
}

function loadSample() {
  const choice = el("archive").value;
  load(async () => {
    if (choice === "file" && localFile) return JSON.parse(await localFile.text());
    const response = await fetch(samples[choice]);
    if (!response.ok) throw new Error("Unable to load this calibration archive.");
    return response.json();
  });
}

document.querySelectorAll("[data-mode]").forEach(button => button.addEventListener("click", () => changeLayer(button.dataset.mode)));
document.querySelectorAll("[data-view]").forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
for (const id of ["overlay", "show-support", "show-route"]) el(id).addEventListener("change", () => changeLayer(mode));
el("fit").addEventListener("click", () => setView(view,"racks"));
el("survey").addEventListener("click", () => setView(view,"survey"));
el("archive").addEventListener("change", loadSample);
el("open").addEventListener("change", event => {
  const file = event.target.files[0];
  if (!file) return;
  event.target.value = "";
  if (file.size > 8_000_000) {
    el("error").textContent = "This reconstruction bundle exceeds the viewer’s input limit.";
    el("error").hidden = false;
    return;
  }
  localFile = file;
  el("archive").querySelector('[value="file"]').disabled = false;
  el("archive").value = "file";
  loadSample();
});
new ResizeObserver(() => {
  const {clientWidth: width, clientHeight: height} = viewport;
  if (!width || !height) return;
  perspective.aspect = width/height;
  perspective.updateProjectionMatrix();
  sizeOrtho();
  renderer.setSize(width,height,false);
  paint();
}).observe(viewport);
loadSample();
