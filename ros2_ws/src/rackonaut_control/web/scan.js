import * as T from "three";

const HEIGHT_COLOURS = [0x5f9fff, 0x44d1e5, 0x74e6b7, 0xffdc80, 0xff976e].map(hex => new T.Color(hex));
const MAX_POINTS = 80000;
const MAP_INTERVAL = { low: 1100, balanced: 1300, high: 2300 };
const POINT_PIXELS = { low: 3.6, balanced: 2.8, high: 2.15 };
const FULL_HEIGHT = [-Infinity, Infinity];
const INTERIOR_HEIGHT = [.3, 5.9];

function pointBuffer(limit, material) {
  const geometry = new T.BufferGeometry();
  const position = new T.BufferAttribute(new Float32Array(limit * 3), 3).setUsage(T.DynamicDrawUsage);
  geometry.setAttribute("position", position);
  geometry.setDrawRange(0, 0);
  const object = new T.Points(geometry, material);
  object.frustumCulled = false;
  const bounds = new T.Box3();
  const point = new T.Vector3();
  return {
    object, bounds,
    replace(values, colour, [minimum, maximum] = FULL_HEIGHT) {
      const length = Math.min(limit, values.length / 3);
      let count = 0;
      bounds.makeEmpty();
      for (let i = 0; i < length; i++) {
        const offset = i * 3;
        const x = values[offset], y = values[offset + 1], z = values[offset + 2];
        if (z < minimum || z > maximum) continue;
        position.setXYZ(count, x, z, -y);
        bounds.expandByPoint(point.set(x, z, -y));
        colour?.(count, z);
        count++;
      }
      position.clearUpdateRanges();
      if (count) {
        position.addUpdateRange(0, count * 3);
        position.needsUpdate = true;
      }
      geometry.setDrawRange(0, count);
      return count;
    },
  };
}

function pointMask(ring = false) {
  const size = 32;
  const data = new Uint8Array(size * size * 4).fill(255);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const distance = Math.hypot(x + .5 - size / 2, y + .5 - size / 2) / (size / 2);
      const outside = T.MathUtils.clamp((.94 - distance) * 14, 0, 1);
      const inside = ring ? T.MathUtils.clamp((distance - .42) * 11, 0, 1) : 1;
      data[(y * size + x) * 4 + 3] = Math.round(255 * outside * inside);
    }
  }
  const texture = new T.DataTexture(data, size, size);
  texture.magFilter = texture.minFilter = T.LinearFilter;
  texture.needsUpdate = true;
  return texture;
}

function axisLines() {
  const geometry = new T.BufferGeometry();
  geometry.setAttribute("position", new T.Float32BufferAttribute([
    0, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, -2, 0, 0, 0, 0, 2, 0,
  ], 3));
  geometry.setAttribute("color", new T.Float32BufferAttribute([
    1, .22, .2, 1, .22, .2, .24, .92, .36, .24, .92, .36, .26, .46, 1, .26, .46, 1,
  ], 3));
  return new T.LineSegments(geometry, new T.LineBasicMaterial({ vertexColors: true }));
}

export function createMeasuredScene(panel, invalidate, onCloud) {
  const el = (id) => panel.querySelector(`#scan-${id}`);
  const show = (id, text) => { if (el(id).textContent !== text) el(id).textContent = text; };
  const wholeNumber = new Intl.NumberFormat("en");
  const scene = new T.Scene();
  scene.background = new T.Color(0x081527);
  scene.add(new T.HemisphereLight(0xe2efff, 0xa5b6c7, 2.2));
  const light = new T.DirectionalLight(0xfff4df, 2.3);
  light.position.set(-12, 18, 12);
  const grid = new T.GridHelper(64, 32, 0x3b536d, 0x1b3047);
  grid.position.y = -.025;
  scene.add(grid, axisLines(), light);
  const dot = pointMask();
  const mapMaterial = new T.PointsMaterial({ size: POINT_PIXELS.balanced, sizeAttenuation: false,
    vertexColors: true, map: dot, alphaTest: .32 });
  const map = pointBuffer(MAX_POINTS, mapMaterial);
  const colour = new T.BufferAttribute(new Float32Array(MAX_POINTS * 3), 3).setUsage(T.DynamicDrawUsage);
  map.object.geometry.setAttribute("color", colour);
  const mixed = new T.Color();
  const live = pointBuffer(8000, new T.PointsMaterial({ size: 2.7, sizeAttenuation: false, map: dot,
    alphaTest: .24, color: 0xb5f7ff, transparent: true, opacity: .71, depthWrite: false }));
  const hazards = pointBuffer(60, new T.PointsMaterial({ size: 10, sizeAttenuation: false, map: pointMask(true),
    alphaTest: .32, color: 0xff7185, depthTest: false, depthWrite: false, transparent: true }));
  live.object.renderOrder = 3;
  hazards.object.renderOrder = 5;
  const walked = new T.Line(new T.BufferGeometry(), new T.LineBasicMaterial({ color: 0xf2e8ff,
    depthTest: false, depthWrite: false, transparent: true }));
  walked.frustumCulled = false;
  walked.renderOrder = 4;
  scene.add(map.object, live.object, hazards.object, walked);
  const rawTrack = new T.Line(new T.BufferGeometry(), new T.LineBasicMaterial({
    color: 0x93e6ff, depthTest: false, depthWrite: false, transparent: true, opacity: .74 }));
  const learned = new T.Line(new T.BufferGeometry(), new T.LineDashedMaterial({
    color: 0xffb050, dashSize: .20, gapSize: .12, depthTest: false, depthWrite: false }));
  const waypoints = new T.Points(new T.BufferGeometry(), new T.PointsMaterial({
    color: 0xffd294, size: 6, sizeAttenuation: false, map: dot, alphaTest: .32,
    depthTest: false, depthWrite: false }));
  const directions = new T.Group();
  const dock = new T.Mesh(new T.SphereGeometry(.21, 12, 8),new T.MeshBasicMaterial({ color: 0x64f0b7, depthTest: false }));
  for (const [item,order] of [[rawTrack,6],[learned,7],[waypoints,8],[dock,9]]) {
    item.renderOrder=order;
    item.visible=false;
  }
  scene.add(rawTrack, learned, waypoints, directions, dock);
  let currentRaw = null, currentNodes = null;

  function routeLayers(review) {
    rawTrack.visible=!!review?.showRaw;
    learned.visible=waypoints.visible=directions.visible=dock.visible=!!review?.showLearned;
    if (!review) return;
    const toWorld = ([x,y,z]) => new T.Vector3(x,z,-y);
    if (currentRaw!==review.raw) {
      currentRaw=review.raw;
      rawTrack.geometry.dispose();
      rawTrack.geometry=new T.BufferGeometry().setFromPoints(review.raw.map(toWorld));
    }
    if (currentNodes===review.nodes) return;
    currentNodes=review.nodes;
    const points=review.nodes.map(n=>toWorld(n.position_m));
    for (const line of [learned,waypoints]) {
      line.geometry.dispose();
      line.geometry=new T.BufferGeometry().setFromPoints(points);
    }
    learned.computeLineDistances();
    for (const arrow of directions.children.slice()) {
      arrow.line.material.dispose();
      arrow.cone.material.dispose();
      directions.remove(arrow);
    }
    for (let i=1; i<points.length; i+=Math.max(1,Math.ceil(points.length/17))) {
      const delta=points[i].clone().sub(points[i-1]);
      if (delta.length()<.18) continue;
      const arrow = new T.ArrowHelper(delta.normalize(),points[i-1],.45,0xffb050,.16,.12);
      for (const part of arrow.children) { part.material.depthTest=false; part.renderOrder=9; }
      directions.add(arrow);
    }
    if (points[0]) dock.position.copy(points[0]);
  }

  let visible = false, timer = 0, request = null, activeSession = null;
  let detail = "balanced", mapTag = null, liveTag = null;
  let displayed = 0, registered = 0, mapTime = -Infinity, updatedAt = null, tfTime = -Infinity;
  let liveTime = -Infinity, liveRequested = false, localization = null, odomPath = null, sourceAvailable = false;
  let mapping = null, warehouse = null;
  let mapValues = null, heightRange = FULL_HEIGHT, pointScale = 1, hazardSignature = "";

  function updateDetails() {
    const now = performance.now();
    const maximumAge = Math.max(2850, MAP_INTERVAL[detail] + 1400);
    const fresh = sourceAvailable && now - mapTime <= maximumAge && localization?.state === "TRACKING";
    const phase = localization?.mapping_phase;
    show("status", warehouse ? "Saved learned map" : phase === "COMPLETE" ? "Saved session" : registered ?
      (fresh ? "Live accumulation" : "Historical snapshot · updates paused") :
      phase === "READY" ? "Empty · ready to record" : "Waiting for measured points");
    el("session-field").hidden = !mapping && !warehouse;
    show("session", mapping || warehouse || "—");
    el("status").dataset.stale = String(registered > 0 && !fresh && !warehouse);
    show("registered", wholeNumber.format(registered));
    show("displayed", wholeNumber.format(displayed));
    show("updated", updatedAt ? `${updatedAt.toLocaleTimeString()} · ${Math.max(0, (now - mapTime) / 1000).toFixed(1)} s ago` : "—");
    const fit = localization?.rms;
    const tracking = localization?.state ? localization.state.toLowerCase().replace(/^./, c => c.toUpperCase()) : "Unavailable";
    const source = warehouse ? "Learned map" : mapping ? "SLAM" : "";
    show("localization", source ? `${source} · ${tracking}${fit == null ? "" : ` · ${fit.toFixed(3)} m`}` : tracking);
    show("quality", fit != null ? `${fit.toFixed(3)} m RMS · ${Math.round(localization.overlap * 100)}% scan fit` : "—");
    const verifiedFrame = now - tfTime <= maximumAge && localization?.state === "TRACKING";
    show("frame", `rackonaut_odom · ${verifiedFrame ? "TF verified" : "TF unavailable"}`);
    live.object.visible = liveRequested && now - liveTime <= 850 && localization?.state === "TRACKING";
    el("empty").hidden = !mapValues || displayed > 0;
  }

  function drawMapPoints() {
    if (!mapValues) return;
    displayed = map.replace(mapValues, (i, z) => {
      const step = T.MathUtils.clamp(z / 2.5, 0, 4);
      const index = Math.min(3, Math.floor(step));
      mixed.lerpColors(HEIGHT_COLOURS[index], HEIGHT_COLOURS[index + 1], step - index);
      colour.setXYZ(i, mixed.r, mixed.g, mixed.b);
    }, heightRange);
    colour.clearUpdateRanges();
    if (displayed) {
      colour.addUpdateRange(0, displayed * 3);
      colour.needsUpdate = true;
    }
  }

  async function getCloud(url, tag, signal) {
    const response = await fetch(url, { cache: "no-store", signal, headers: tag ? { "If-None-Match": tag } : {} });
    if (![200, 204, 304].includes(response.status)) throw new Error(`Point cloud request failed (${response.status})`);
    const values = response.status === 200 ? new Float32Array(await response.arrayBuffer()) : null;
    if (values && values.length % 3) throw new Error("Incomplete XYZ point cloud");
    return { response, values };
  }

  async function refreshMap(signal) {
    const { response, values } = await getCloud(`/api/measured-map?detail=${detail}`, mapTag, signal);
    const nextSession = response.headers.get("X-Map-Session");
    if (signal.aborted || (mapping && nextSession !== mapping)) return;
    const count = response.headers.get("X-Point-Count");
    sourceAvailable = !!count;
    if (!count) return;
    const now = performance.now();
    mapTime = now - Number(response.headers.get("X-Sample-Age-Ms"));
    const tf = response.headers.get("X-TF-Age-Ms");
    tfTime = tf ? now - Number(tf) : -Infinity;
    updatedAt = new Date(response.headers.get("X-Received-At"));
    registered = Number(count);
    if (!values) return;
    const first = activeSession !== nextSession;
    activeSession = nextSession;
    mapValues = values;
    drawMapPoints();
    mapTag = response.headers.get("ETag");
    onCloud(first);
  }

  async function refreshLive(signal) {
    const { response, values } = await getCloud("/api/measured-scan", liveTag, signal);
    if (signal.aborted) return;
    if (response.status === 204) { liveTime = -Infinity; return; }
    liveTime = performance.now() - Number(response.headers.get("X-Sample-Age-Ms"));
    if (values) {
      live.replace(values);
      liveTag = response.headers.get("ETag");
    }
  }

  let nextMap = 0;
  function stopPolling() {
    clearTimeout(timer);
    request?.abort();
    request = null;
  }
  async function poll() {
    if (!visible || document.hidden || request) return;
    const controller = new AbortController();
    request = controller;
    const tasks = [];
    if (performance.now() >= nextMap) {
      nextMap = performance.now() + MAP_INTERVAL[detail];
      tasks.push(refreshMap(controller.signal).catch(() => { if (!controller.signal.aborted) sourceAvailable = false; }));
    }
    if (liveRequested) tasks.push(refreshLive(controller.signal));
    await Promise.allSettled(tasks);
    if (controller.signal.aborted) return;
    request = null;
    updateDetails();
    invalidate();
    timer = setTimeout(poll, liveRequested ? 420 : Math.max(100, nextMap - performance.now()));
  }

  function resume() {
    stopPolling();
    nextMap = 0;
    poll();
  }
  document.addEventListener("visibilitychange", resume);
  el("detail").addEventListener("change", () => {
    detail = el("detail").value;
    mapTag = null;
    resume();
  });
  el("colour").addEventListener("change", () => {
    mapMaterial.vertexColors = el("colour").value === "height";
    mapMaterial.color.setHex(mapMaterial.vertexColors ? 0xffffff : 0xc4e8ff);
    mapMaterial.needsUpdate = true;
    el("height-key").hidden = !mapMaterial.vertexColors;
    invalidate();
  });
  function applyHeightFilter() {
    const preset = el("height").value;
    const custom = preset === "custom";
    el("height-inputs").hidden = !custom;
    const min = el("min-z"), max = el("max-z");
    max.setCustomValidity("");
    if (custom) {
      if (!Number.isFinite(min.valueAsNumber) || !Number.isFinite(max.valueAsNumber)) return;
      if (min.valueAsNumber > max.valueAsNumber) {
        max.setCustomValidity("Maximum height must be at least the minimum height.");
        max.reportValidity();
        return;
      }
    }
    heightRange = custom ? [min.valueAsNumber, max.valueAsNumber] : preset === "interior" ? INTERIOR_HEIGHT : FULL_HEIGHT;
    drawMapPoints();
    updateDetails();
    invalidate();
  }
  for (const id of ["height", "min-z", "max-z"]) el(id).addEventListener("change", applyHeightFilter);
  el("size").addEventListener("input", () => {
    pointScale = el("size").valueAsNumber / 100;
    show("size-value", `${el("size").value}%`);
    invalidate();
  });
  el("live").addEventListener("change", () => {
    liveRequested = el("live").checked;
    resume();
  });

  return {
    scene, bounds: map.bounds,
    scalePoints(distance) {
      const adapt = T.MathUtils.clamp(1 + (distance - 24) / 90, .82, 1.23);
      mapMaterial.size = POINT_PIXELS[detail] * pointScale * adapt;
    },
    setVisible(value) {
      if (visible === value) return;
      visible = value;
      resume();
    },
    update(state, activeFlight, review) {
      if (!visible) return;
      localization = state?.localization;
      const next = localization?.mapping_id || null;
      const loaded = localization?.warehouse_id || null;
      if (next !== mapping || loaded !== warehouse) {
        mapping = next;
        warehouse = loaded;
        displayed = registered = 0;
        mapValues = mapTag = liveTag = activeSession = updatedAt = null;
        mapTime = liveTime = tfTime = -Infinity;
        sourceAvailable = false;
        map.replace([]);
        live.replace([]);
        resume();
      }
      const job = state?.mission;
      const points = !mapping && job?.flown?.length ? job.flown : localization?.trajectory || [];
      const signature = JSON.stringify(points);
      if (signature !== odomPath) {
        odomPath = signature;
        walked.geometry.dispose();
        walked.geometry = new T.BufferGeometry().setFromPoints(points.map(([x, y, z]) => new T.Vector3(x, z, -y)));
      }
      walked.visible = points.length > 1 && !review;
      routeLayers(review);
      const avoidance = job?.status?.avoidance;
      const measured = activeFlight && avoidance?.scan_age_ms != null && avoidance.scan_age_ms <= 650
        && localization?.state === "TRACKING";
      const hazardPoints = measured ? avoidance?.hazard_points || [] : [];
      const signatureHazards = JSON.stringify(hazardPoints);
      if (signatureHazards !== hazardSignature) {
        hazardSignature = signatureHazards;
        hazards.replace(hazardPoints.flat());
      }
      updateDetails();
      invalidate();
    },
  };
}
