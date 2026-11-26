import * as THREE from "three";
import { OrbitControls } from "../../../ros2_ws/src/rackonaut_control/web/vendor/OrbitControls.js";

const el = id => document.getElementById(id);
const fmt = new Intl.NumberFormat("en", {maximumFractionDigits: 2});
const world = ([x, y, z]) => new THREE.Vector3(x, z, -y);
const samples = {
  goal24: "../../../docs/reconstruction-evidence/goal24.json",
  goal26: "../../../docs/reconstruction-evidence/goal26.json",
};
const scene = new THREE.Scene();
scene.background = new THREE.Color("#101b28");
const perspective = new THREE.PerspectiveCamera(42, 1, .05, 230);
const overhead = new THREE.OrthographicCamera(-1,1,1,-1,.05,230);
let camera = perspective, topHalfHeight = 5;
const viewport = el("viewport");
let renderer;
try {
  renderer = new THREE.WebGLRenderer({antialias: true});
} catch {
  el("error").textContent = "The 3D comparison requires a working WebGL browser.";
  el("error").hidden = false;
  throw new Error("WebGL unavailable");
}
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 1.75));
viewport.append(renderer.domElement);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = false;
controls.minDistance = .7;
controls.maxDistance = 115;
controls.addEventListener("change", paint);
scene.add(new THREE.HemisphereLight(0xe9f6ff, 0x323140, 2.1));
const key = new THREE.DirectionalLight(0xffffff, 2.4);
key.position.set(8, 13, 7);
scene.add(key);

let data, cloud, model, grid, selectedLine, localFile, mode = "model", pose = "isometric";
let markers = [], request = 0;
const temp = new THREE.Vector3();

function paint() {
  renderer.render(scene, camera);
  for (const {button, point} of markers) {
    temp.copy(point).project(camera);
    button.hidden = !Number.isFinite(temp.x) || Math.abs(temp.x) > 1 || Math.abs(temp.y) > 1 || Math.abs(temp.z) > 1;
    button.style.left = `${(temp.x+1)*50}%`;
    button.style.top = `${(1-temp.y)*50}%`;
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

function measuredCloud(packet) {
  const raw = Uint8Array.from(atob(packet.points_f32le), char => char.charCodeAt(0));
  if (raw.byteLength !== packet.point_count*12) throw new Error("The measured cloud is incomplete.");
  const source = new DataView(raw.buffer);
  const xyz = new Float32Array(packet.point_count*3);
  const colors = new Float32Array(xyz.length);
  const low = new THREE.Color("#41c7bd"), middle = new THREE.Color("#83a4de"), high = new THREE.Color("#d6a56f");
  const tint = new THREE.Color();
  for (let i = 0; i < xyz.length; i += 3) {
    const x = source.getFloat32(i*4, true), y = source.getFloat32((i+1)*4, true), z = source.getFloat32((i+2)*4, true);
    if (![x,y,z].every(Number.isFinite)) throw new Error("Invalid coordinates in the measured cloud.");
    xyz.set([x,z,-y], i);
    const height = THREE.MathUtils.clamp(z / 10, 0, 1);
    if (height < .5) tint.copy(low).lerp(middle, height*2);
    else tint.copy(middle).lerp(high, height*2-1);
    tint.toArray(colors, i);
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(xyz,3));
  geometry.setAttribute("color", new THREE.BufferAttribute(colors,3));
  geometry.computeBoundingBox();
  return new THREE.Points(geometry, new THREE.PointsMaterial({
    vertexColors: true, size: .075, transparent: true, depthWrite: false,
  }));
}

function instances(boxes, color) {
  if (!boxes.length) return null;
  const shape = new THREE.BoxGeometry(1,1,1);
  const material = new THREE.MeshStandardMaterial({color, metalness: .16, roughness: .7});
  const mesh = new THREE.InstancedMesh(shape, material, boxes.length);
  const item = new THREE.Object3D();
  boxes.forEach(([x, y, z, width, height, depth], i) => {
    item.position.set(x,y,z);
    item.scale.set(width,height,depth);
    item.updateMatrix();
    mesh.setMatrixAt(i,item.matrix);
  });
  mesh.computeBoundingBox();
  return mesh;
}

function rackModel(packet) {
  const result = new THREE.Group();
  for (const row of packet.rows) {
    const group = new THREE.Group();
    group.rotation.y = row.yaw_rad;
    const shelves = row.levels.flatMap(level => level.patches_uv.map(([ul,vl,uh,vh]) =>
      [(ul+uh)/2,level.z,-(vl+vh)/2,uh-ul,.05,vh-vl]));
    const uprights = row.posts.map(([u,v,lo,hi]) => [u,(lo+hi)/2,-v,.085,hi-lo,.085]);
    for (const mesh of [instances(shelves, "#d7ae70"), instances(uprights, "#5aa6a4")]) {
      if (mesh) group.add(mesh);
    }
    result.add(group);
  }
  return result;
}

function changeLayer(next) {
  mode = next;
  if (!data) return;
  model.visible = mode !== "cloud";
  cloud.visible = mode !== "model";
  cloud.material.opacity = mode === "cloud" ? .87 : .29;
  cloud.renderOrder = mode === "overlay" ? 2 : 0;
  document.querySelectorAll("[data-mode]").forEach(button => button.setAttribute("aria-pressed", String(button.dataset.mode === mode)));
  el("legend").textContent = {
    cloud: "Recorded LiDAR endpoints",
    model: "Shelf support · Measured uprights",
    overlay: "Rack model with translucent LiDAR endpoints",
  }[mode];
  paint();
}

function setView(next, fit = false) {
  if (!data) return;
  pose = next;
  el("isometric").setAttribute("aria-pressed", String(pose === "isometric"));
  el("top").setAttribute("aria-pressed", String(pose === "top"));
  el("view-help").textContent = pose === "top" ? "Drag to pan · Scroll to zoom" : "Drag to orbit · Scroll to zoom";
  let distance = camera.position.distanceTo(controls.target);
  if (fit || !distance) {
    const box = new THREE.Box3().setFromObject(mode === "cloud" || !data.rows.length ? cloud : model);
    controls.target.copy(box.getCenter(new THREE.Vector3()));
    const size = box.getSize(new THREE.Vector3());
    const fov = THREE.MathUtils.degToRad(perspective.fov);
    distance = Math.max(3, size.length() / (2*Math.tan(fov/2)*Math.min(perspective.aspect,1))*1.10);
  }
  camera = pose === "top" ? overhead : perspective;
  controls.object = camera;
  controls.enableRotate = pose !== "top";
  controls.mouseButtons.LEFT = pose === "top" ? THREE.MOUSE.PAN : THREE.MOUSE.ROTATE;
  if (pose === "top") {
    overhead.zoom = 1;
    topHalfHeight = distance * Math.tan(THREE.MathUtils.degToRad(perspective.fov)/2);
    sizeOverhead();
  }
  const direction = pose === "top" ? new THREE.Vector3(0,1,.0001) : new THREE.Vector3(.7,.64,1);
  camera.position.copy(controls.target).addScaledVector(direction.normalize(),distance);
  controls.update();
  paint();
}

function chooseLocation(location) {
  el("location-detail").hidden = !location;
  for (const button of document.querySelectorAll("[data-location]")) button.setAttribute("aria-pressed", String(button.dataset.location === location?.id));
  destroy(selectedLine);
  selectedLine = null;
  if (location) {
    const level = location.level ? `Level ${location.level}.` : "Shelf level unconfirmed here."
    const explanation = location.status === "projected"
      ? `Projected onto ${location.rack_id}. ${level} ${fmt.format(location.distance_m)} m from the camera, supported by ${location.support_nearby} nearby returns.`
      : `${location.reason} The marker shows the drone’s capture position.`;
    el("location-explanation").textContent = explanation;
    const photo = el("location-photo");
    photo.hidden = !location.photo_jpeg;
    if (location.photo_jpeg) photo.src = "data:image/jpeg;base64," + location.photo_jpeg;
    else photo.removeAttribute("src");
    if (location.status === "projected") {
      const line = new THREE.BufferGeometry().setFromPoints([world(location.camera_origin_m),world(location.position_m)]);
      selectedLine = new THREE.Line(line,new THREE.LineDashedMaterial({color: 0x91e4d6, dashSize: .14, gapSize: .10}));
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
  button.setAttribute("aria-label", location.id + (location.status === "projected" ? " projected location" : " capture viewpoint"));
  button.textContent = location.id;
  if (onStage) {
    button.className = "marker";
    button.dataset.status = location.status;
    if (location.status === "unplaced") button.append(" · viewpoint");
  } else {
    const status = document.createElement("small");
    status.textContent = location.status === "projected"
      ? `${location.rack_id} · ${location.level ? `level ${location.level}` : "rack face"}` : "Unplaced";
    button.append(status);
  }
  button.addEventListener("click", () => chooseLocation(location));
  return button;
}

function show(packet) {
  if (packet.version !== 1 || !Number.isInteger(packet.point_count) || packet.point_count < 1 || packet.point_count > 80000 ||
      !Array.isArray(packet.rows) || !Array.isArray(packet.locations)) throw new Error("Select a Rackonaut reconstruction bundle.");
  const nextCloud = measuredCloud(packet), nextModel = rackModel(packet);
  destroy(cloud);
  destroy(model);
  destroy(grid);
  data = packet;
  cloud = nextCloud;
  model = nextModel;
  scene.add(cloud, model);
  const box = cloud.geometry.boundingBox;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  grid = new THREE.GridHelper(Math.ceil(Math.max(size.x,size.z)/2)*2+4, 16, 0x3b5a72, 0x273e51);
  grid.position.set(center.x, box.min.y-.03, center.z);
  scene.add(grid);
  el("row-count").textContent = fmt.format(packet.rows.length);
  el("point-count").textContent = fmt.format(packet.point_count);
  el("archive-description").textContent = `${packet.label} · ${packet.archive.frame}`;
  markers = packet.locations.map(item => ({
    button: locationButton(item,true), point: world(item.position_m || item.viewpoint_m),
  }));
  el("markers").replaceChildren(...markers.map(item => item.button));
  el("location-list").replaceChildren(...packet.locations.map(item => locationButton(item,false)));
  el("rack-details").replaceChildren(...packet.rows.map(row => {
    const entry = document.createElement("p");
    const [lo,hi] = row.bounds_uv;
    const elevation = row.vertical_extent_m[1] - row.vertical_extent_m[0];
    entry.textContent = `${row.id} · ${fmt.format(hi[0]-lo[0])} × ${fmt.format(hi[1]-lo[1])} × ${fmt.format(elevation)} m observed` +
      ` · levels at ${row.levels.map(level => fmt.format(level.z)).join(", ")} m`;
    return entry;
  }));
  chooseLocation(null);
  changeLayer(packet.rows.length ? mode : "cloud");
  setView(pose,true);
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
  const fileOption = el("archive").querySelector('[value="file"]');
  fileOption.disabled = false;
  el("archive").value = "file";
  loadSample();
});
el("isometric").addEventListener("click", () => setView("isometric"));
el("top").addEventListener("click", () => setView("top"));
el("fit").addEventListener("click", () => setView(pose,true));
function sizeOverhead() {
  overhead.left = -topHalfHeight*perspective.aspect;
  overhead.right = -overhead.left;
  overhead.top = topHalfHeight;
  overhead.bottom = -topHalfHeight;
  overhead.updateProjectionMatrix();
}
new ResizeObserver(() => {
  const {clientWidth: width, clientHeight: height} = viewport;
  if (!width || !height) return;
  perspective.aspect = width/height;
  perspective.updateProjectionMatrix();
  sizeOverhead();
  renderer.setSize(width,height,false);
  paint();
}).observe(viewport);
loadSample();
