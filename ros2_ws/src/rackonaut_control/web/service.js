export function createService({ openWarehouse, dispatchWarehouse, previewWarehouse } = {}) {
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
    MAPPING_ACTIVE: "Mapping flight", MAPPING_COMPLETE: "Mapping complete",
  };
  let visible = false, busy = false, loading = false, generation = 0, current = null;
  let nextRefresh = 0;
  let catalog = [], details = null, warehouseBusy = false, budgetKey = "";

  function warehouseSelection(identifier) {
    return {mode:"learned", configuration_id:identifier, revision:details.manifest.revision,
      record_ids:[...el("warehouse-stops").querySelectorAll("input:checked")].map(input => input.value)};
  }

  async function showBudget(selection) {
    const key = selection?.record_ids.length ? JSON.stringify(selection) : "";
    if (key === budgetKey) return;
    budgetKey = key;
    text("warehouse-budget", key ? "Calculating flight budget…" : "");
    if (!key) return;
    try {
      const {energy} = await previewWarehouse(selection);
      if (budgetKey === key) text("warehouse-budget",
        energy.seconds.toFixed(1) + " s sim · " + energy.percent.toFixed(1) + " pp · " + energy.reserve_percent.toFixed(1) + " pp reserve");
    } catch (error) {
      if (budgetKey === key) text("warehouse-budget", error.message);
    }
  }

  function renderWarehouses() {
    const status = current?.learned_warehouse;
    el("warehouse-configurations").hidden = !status?.enabled;
    if (!status?.enabled) return;
    text("warehouse-active", status.error || (status.ready ? "Active · localized on saved LiDAR map · " + status.active_id
      : status.active_id ? "Matching saved map at the dock" : "Choose a saved warehouse to activate"));
    const selected = el("warehouse-select").value;
    const verified = details?.manifest.configuration_id === selected;
    const active = verified && status.ready && status.active_id === selected;
    const idle = current.calibration.mode === "PRODUCTION" && current.system.contact
      && !["PREPARING", "RESERVED", "RECOVERY"].includes(current.system.safety);
    el("warehouse-confirm-row").hidden = !verified || active;
    el("warehouse-verify").disabled = warehouseBusy || !selected;
    el("warehouse-activate").disabled = warehouseBusy || !verified || active || !idle || !el("warehouse-confirm").checked;
    el("warehouse-map-open").disabled = warehouseBusy || !active;
    el("warehouse-mission").hidden = !active;
    el("warehouse-dispatch").disabled = warehouseBusy || !active || !idle
      || !el("warehouse-stops").querySelector("input:checked");
    showBudget(active ? warehouseSelection(selected) : null);
  }

  async function updateCatalog() {
    const { response, body } = await request("warehouses");
    if (!response.ok) return;
    const list = body.configurations;
    if (JSON.stringify(catalog) === JSON.stringify(list)) return;
    catalog = list;
    const select = el("warehouse-select");
    const previous = select.value || body.active_id;
    select.replaceChildren(...list.map(row => {
      const option = document.createElement("option");
      option.value = row.configuration_id;
      option.textContent = row.name + (row.revision ? " · Revision " + row.revision : "") + " · " + row.configuration_id.slice(-8);
      return option;
    }));
    if (list.some(row => row.configuration_id === previous)) select.value = previous;
  }

  async function warehouseAction(action) {
    const identifier = el("warehouse-select").value;
    warehouseBusy = true;
    text("warehouse-feedback", "");
    renderWarehouses();
    try {
      if (action === "dispatch") {
        await dispatchWarehouse(warehouseSelection(identifier));
      } else {
        const { response, body } = await request("warehouses/" + action, {
          configuration_id:identifier, confirm:el("warehouse-confirm").checked,
        });
        if (!response.ok) throw new Error(body.error);
        details = body;
        el("warehouse-stops").replaceChildren(...body.locations.map(row => {
          const label = document.createElement("label");
          const checkbox = document.createElement("input");
          checkbox.type = "checkbox";
          checkbox.value = row.record_id;
          checkbox.checked = true;
          checkbox.addEventListener("change", renderWarehouses);
          label.append(checkbox, document.createTextNode(" " + row.storage_location_id));
          return label;
        }));
        el("warehouse-confirm").checked = false;
        text("warehouse-feedback", action === "verify"
          ? "Verified · " + body.locations.length + " locations · " + body.route.edges.length + " directed segments"
          : "Activation requested. Waiting for a verified dock match.");
      }
    } catch (error) {
      if (action !== "dispatch") details = null;
      text("warehouse-feedback", error.message);
    } finally {
      warehouseBusy = false;
      renderWarehouses();
      nextRefresh = 0;
      refresh();
    }
  }

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
    const { system, warehouse, calibration, available, mapping } = current;
    renderWarehouses();
    const production = calibration.mode === "PRODUCTION";
    const ready = !!mapping;
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
    el("service-cancel").disabled = busy || calibration.cancel_pending || calibration.mode === "MAPPING_ACTIVE";
    text("service-cancel", calibration.cancel_pending ? "Waiting for production localization" :
      calibration.mode === "MAPPING_COMPLETE" ? "Close calibration" : "Cancel Calibration");
    el("calibration-workspace").hidden = !ready;
    if (!ready) return;
    text("calibration-position", system.position?.slice(0, 3).map(value => value.toFixed(2)).join(" / "));
    text("calibration-speed", system.speed?.toFixed(2));
    text("calibration-battery", percent(system.battery));
    text("calibration-dock", system.contact ? "Confirmed" : "Unconfirmed");
    text("calibration-id", draft.calibration_id);
    text("calibration-started", new Date(draft.started_at).toLocaleString());
    text("calibration-name", draft.warehouse_name || "Unnamed warehouse");
    text("calibration-map-source", "Onboard LiDAR and IMU");
    text("calibration-map", label(mapping.mapping_phase));
    text("calibration-slam", [label(mapping.state), mapping.rms == null ? null : `${mapping.rms.toFixed(3)} m scan fit RMS`].filter(Boolean).join(" · "));
    text("calibration-points", mapping.map_voxels);
    text("calibration-trajectory", mapping.trajectory.length);
    el("calibration-fly").disabled = mapping.mapping_phase === "EMPTY";
    el("calibration-ply").hidden = el("calibration-result").hidden = !draft.map_reference;
    el("calibration-locations").hidden = !draft.map_reference || !draft.locations_reference;
    el("service-review-route").hidden = calibration.mode !== "MAPPING_COMPLETE" || !draft.map_reference;
    el("service-review-route").dataset.session = draft.calibration_id;
    if (draft.map_reference) {
      el("calibration-ply").href = draft.map_reference;
      el("calibration-result").href = draft.map_reference.replace(/map\.ply$/, "result.json");
      if (draft.locations_reference) el("calibration-locations").href = draft.locations_reference;
    }
    if (mapping.mapping_error) feedback(mapping.mapping_error);
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
        if (body.learned_warehouse?.enabled) await updateCatalog();
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
  el("warehouse-verify").addEventListener("click", () => warehouseAction("verify"));
  el("warehouse-activate").addEventListener("click", () => warehouseAction("activate"));
  el("warehouse-dispatch").addEventListener("click", () => warehouseAction("dispatch"));
  el("warehouse-map-open").addEventListener("click", () => openWarehouse(details));
  el("warehouse-confirm").addEventListener("change", renderWarehouses);
  el("warehouse-select").addEventListener("change", () => {
    details = null;
    el("warehouse-confirm").checked = false;
    text("warehouse-feedback", "");
    renderWarehouses();
  });
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
