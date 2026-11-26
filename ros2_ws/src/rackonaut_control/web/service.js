export function createService() {
  const el = (id) => document.getElementById(id);
  const text = (id, value) => { el(id).textContent = value ?? "—"; };
  const label = (value) => value ? value.toLowerCase().replaceAll("_", " ").replace(/^./, c => c.toUpperCase()) : "—";
  const fresh = (value) => value ? "Fresh" : "Unavailable / stale";
  const percent = (value) => value == null ? "—" : `${value.toFixed(1)}%`;
  const modes = {
    PRODUCTION: "Production", CALIBRATION_REQUESTED: "Calibration requested",
    STOPPING_INSPECTION: "Stopping inspection", RETURNING_TO_DOCK: "Returning to dock",
    WAITING_FOR_DOCK: "Waiting for dock", PREPARING_CALIBRATION: "Preparing calibration",
    CALIBRATION_READY: "Calibration ready", CALIBRATION_BLOCKED: "Calibration blocked", RECOVERY_REQUIRED: "Recovery required",
  };
  let visible = false, busy = false, loading = false, generation = 0, current = null;
  let nextRefresh = 0;

  async function request(path, data) {
    const response = await fetch(`/api/service/${path}`, data === undefined ? { cache: "no-store" } : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
    });
    const body = await response.json();
    return { response, body };
  }

  function feedback(message = "") {
    text("service-feedback", message);
    el("service-feedback").hidden = !message;
  }

  function render() {
    el("service-panel").hidden = !visible;
    el("service-access").hidden = !!current;
    el("service-content").hidden = !current;
    el("service-unlock").disabled = busy;
    if (!current) {
      el("service-camera").removeAttribute("src");
      return;
    }
    const { system, warehouse, calibration, available } = current;
    const production = calibration.mode === "PRODUCTION";
    const ready = calibration.mode === "CALIBRATION_READY";
    const draft = calibration.draft;
    text("service-drone", label(system.drone));
    text("service-connection", system.connection ? "Connected" : "Offline");
    text("service-localization", label(system.localization));
    text("service-lidar", fresh(system.lidar));
    text("service-imu", fresh(system.imu));
    text("service-camera-status", system.camera ? "Live" : "Unavailable");
    text("service-battery", percent(system.battery));
    text("service-dock", system.contact ? "Physical contact confirmed" : label(system.dock));
    text("service-safety", [label(system.safety), system.safety_sensors && `${label(system.safety_sensors)} sensors`].filter(Boolean).join(" · "));
    text("service-mission", system.mission ? `${label(system.mission.stage)} · ${system.mission.inspection_id}` : "Idle");
    text("service-profile", warehouse.profile);
    text("service-map-source", warehouse.map_source);
    text("service-map", warehouse.map);
    text("service-locations", warehouse.locations);
    text("service-config-state", label(warehouse.status));
    text("service-mode", modes[calibration.mode] || label(calibration.mode));
    text("service-calibration-detail", !available && production
      ? "Calibration is unavailable in this profile. Use Full Robotics."
      : calibration.detail + (calibration.cancel_pending ? " Cancellation will finish at the confirmed dock." : ""));
    el("service-overview").hidden = ready;
    el("service-introduction").hidden = !production;
    el("service-start").disabled = busy || !available || system.safety === "RECOVERY";
    el("service-lock").disabled = busy;
    el("service-cancel").hidden = production;
    el("service-cancel").disabled = busy || calibration.cancel_pending;
    text("service-cancel", calibration.cancel_pending ? "Cancellation pending" : "Cancel Calibration");
    el("calibration-workspace").hidden = !ready;
    if (!ready) return;
    text("calibration-position", system.position?.slice(0, 3).map(value => value.toFixed(2)).join(" / "));
    text("calibration-speed", system.speed?.toFixed(2));
    text("calibration-battery", percent(system.battery));
    text("calibration-dock", system.contact ? "Confirmed" : "Unconfirmed");
    text("calibration-id", draft.calibration_id);
    text("calibration-started", new Date(draft.started_at).toLocaleString());
    text("calibration-name", draft.warehouse_name || "Unnamed warehouse");
    text("calibration-map-source", "Future sensor measurement");
    text("calibration-map", draft.map_reference || "No approved map");
    text("calibration-locations", `${draft.locations.length} · Registration unavailable`);
    text("calibration-waypoints", `${draft.waypoints.length} waypoints · Recording unavailable`);
    const camera = el("service-camera");
    camera.hidden = !system.camera;
    el("service-camera-empty").hidden = system.camera;
    if (visible && system.camera && !document.hidden) camera.src = `/api/frame.jpg?t=${Date.now()}`;
  }

  async function refresh() {
    if (!visible || busy || loading || Date.now() < nextRefresh) return;
    const requestGeneration = generation;
    loading = true;
    nextRefresh = Date.now() + (current ? 700 : 1500);
    try {
      const { response, body } = await request("state");
      if (requestGeneration !== generation) return;
      if (response.ok) {
        current = body;
      } else if (response.status === 401) {
        if (current) text("service-access-message", "Service session expired. Enter the code to unlock it again.");
        if (body.configured === false) text("service-access-message", "Service access is disabled until a code is configured on the server.");
        current = null;
      }
      render();
    } catch {
      if (requestGeneration === generation) {
        current = null;
        text("service-access-message", "Control Center connection lost.");
        render();
      }
    } finally {
      loading = false;
    }
  }

  async function action(path, data) {
    if (busy) return;
    busy = true;
    generation++;
    feedback();
    render();
    try {
      const { response, body } = await request(path, data);
      if (path === "unlock") {
        text("service-access-message", response.ok ? "" : body.error);
      } else if (path === "lock" || response.status === 401) {
        current = null;
        text("service-access-message", response.ok ? "" : body.error);
      } else if (response.ok) {
        current = { ...current, calibration: body };
      } else {
        feedback(body.error);
      }
    } catch {
      const message = "Control Center connection lost.";
      if (current) feedback(message);
      else text("service-access-message", message);
    } finally {
      busy = false;
      nextRefresh = 0;
      render();
      refresh();
    }
  }

  el("service-access").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = el("service-code");
    action("unlock", { code: input.value });
    input.value = "";
  });
  el("service-lock").addEventListener("click", () => action("lock", {}));
  el("service-start").addEventListener("click", () => action("calibration/start", {}));
  el("service-cancel").addEventListener("click", () => action("calibration/cancel", {}));
  return {
    show(value) {
      visible = value;
      if (value) nextRefresh = 0;
      render();
      refresh();
    },
    refresh,
  };
}
