import * as T from "three";

const HEIGHT_COLOURS = [0x4293fd, 0x31c2d8, 0x69dfa0, 0xf1db70, 0xff9262].map(hex => new T.Color(hex));
const MAX_POINTS = 80000;
const MAP_INTERVAL = { low: 1100, balanced: 1300, high: 2300 };

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
    replace(values, colour) {
      const count = Math.min(limit, values.length / 3);
      bounds.makeEmpty();
      for (let i = 0; i < count; i++) {
        const offset = i * 3;
        const x = values[offset], y = values[offset + 1], z = values[offset + 2];
        position.setXYZ(i, x, z, -y);
        bounds.expandByPoint(point.set(x, z, -y));
        colour?.(i, z);
      }
      position.clearUpdateRanges();
      position.addUpdateRange(0, count * 3);
      position.needsUpdate = count > 0;
      geometry.setDrawRange(0, count);
    },
  };
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
  scene.background = new T.Color(0x0d1929);
  scene.add(new T.HemisphereLight(0xe2efff, 0xa5b6c7, 2.2));
  const light = new T.DirectionalLight(0xfff4df, 2.3);
  light.position.set(-12, 18, 12);
  const grid = new T.GridHelper(64, 32, 0x5b718f, 0x26384f);
  grid.position.y = -.025;
  scene.add(grid, axisLines(), light);
  const mapMaterial = new T.PointsMaterial({ size: .105, color: 0xc4e8ff, vertexColors: true });
  const map = pointBuffer(MAX_POINTS, mapMaterial);
  const colour = new T.BufferAttribute(new Float32Array(MAX_POINTS * 3), 3).setUsage(T.DynamicDrawUsage);
  map.object.geometry.setAttribute("color", colour);
  const mixed = new T.Color();
  const live = pointBuffer(8000, new T.PointsMaterial({ size: .075, color: 0x85f7ff, transparent: true, opacity: .70, depthWrite: false }));
  const hazards = pointBuffer(60, new T.PointsMaterial({ size: .19, color: 0xff766c, depthTest: false }));
  hazards.object.renderOrder = 4;
  const walked = new T.Line(new T.BufferGeometry(), new T.LineBasicMaterial({ color: 0xfafffa, depthTest: false }));
  walked.frustumCulled = false;
  walked.renderOrder = 3;
  scene.add(map.object, live.object, hazards.object, walked);

  let visible = false, timer = 0, request = null, activeSession = null;
  let detail = "balanced", mapTag = null, liveTag = null;
  let displayed = 0, registered = 0, mapTime = -Infinity, updatedAt = null, tfTime = -Infinity;
  let liveTime = -Infinity, liveRequested = false, localization = null, odomPath = null, sourceAvailable = false;

  function updateDetails() {
    const now = performance.now();
    const maximumAge = Math.max(2850, MAP_INTERVAL[detail] + 1400);
    const fresh = sourceAvailable && now - mapTime <= maximumAge && localization?.state === "TRACKING";
    show("status", registered ? (fresh ? "Live accumulation" : "Historical snapshot · updates paused") : "Waiting for measured points");
    el("status").dataset.stale = String(registered > 0 && !fresh);
    show("registered", wholeNumber.format(registered));
    show("displayed", wholeNumber.format(displayed));
    show("updated", updatedAt ? `${updatedAt.toLocaleTimeString()} · ${Math.max(0, (now - mapTime) / 1000).toFixed(1)} s ago` : "—");
    show("localization", localization?.state ? localization.state.toLowerCase().replace(/^./, c => c.toUpperCase()) : "Unavailable");
    const fit = localization?.rms;
    show("quality", fit != null ? `${fit.toFixed(3)} m RMS · ${Math.round(localization.overlap * 100)}% scan fit` : "—");
    const verifiedFrame = now - tfTime <= maximumAge && localization?.state === "TRACKING";
    show("frame", `rackonaut_odom · ${verifiedFrame ? "TF verified" : "TF unavailable"}`);
    live.object.visible = liveRequested && now - liveTime <= 850 && localization?.state === "TRACKING";
    el("surface").dataset.scanMode = registered ? (fresh ? "live" : "stale") : "waiting";
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
    if (signal.aborted) return;
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
    const nextSession = response.headers.get("X-Map-Session");
    const first = activeSession !== nextSession;
    activeSession = nextSession;
    displayed = values.length / 3;
    map.replace(values, (i, z) => {
      const step = T.MathUtils.clamp(z * .5, 0, 4);
      const index = Math.min(3, Math.floor(step));
      mixed.lerpColors(HEIGHT_COLOURS[index], HEIGHT_COLOURS[index + 1], step - index);
      colour.setXYZ(i, mixed.r, mixed.g, mixed.b);
    });
    colour.clearUpdateRanges();
    colour.addUpdateRange(0, values.length);
    colour.needsUpdate = true;
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
  mapMaterial.color.setHex(0xffffff);
  el("live").addEventListener("change", () => {
    liveRequested = el("live").checked;
    resume();
  });

  return {
    scene, bounds: map.bounds,
    setVisible(value) {
      if (visible === value) return;
      visible = value;
      resume();
    },
    update(state, activeFlight) {
      if (!visible) return;
      localization = state?.localization;
      const job = state?.mission;
      const points = job?.flown?.length ? job.flown : localization?.trajectory || [];
      const signature = JSON.stringify(points);
      if (signature !== odomPath) {
        odomPath = signature;
        walked.geometry.dispose();
        walked.geometry = new T.BufferGeometry().setFromPoints(points.map(([x, y, z]) => new T.Vector3(x, z, -y)));
        walked.visible = points.length > 1;
      }
      const avoidance = job?.status?.avoidance;
      const measured = activeFlight && avoidance?.scan_age_ms != null && avoidance.scan_age_ms <= 650
        && localization?.state === "TRACKING";
      hazards.replace(measured ? (avoidance?.hazard_points || []).flat() : []);
      updateDetails();
      invalidate();
    },
  };
}
