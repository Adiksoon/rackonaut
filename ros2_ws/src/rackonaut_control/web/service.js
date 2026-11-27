import { activeMission, displayDate, dockState, droneProfile, operatorState } from "/operator.js";

export function createService({ openWarehouse, openPreview, openPlan, sessionChanged } = {}) {
  const el = (id) => document.getElementById(id);
  const text = (id, value) => {
    const node = el(id), content = String(value ?? "Unavailable");
    if (node.textContent !== content) node.textContent = content;
  };
  const label = (value) => value ? value.toLowerCase().replaceAll("_", " ").replace(/^./, c => c.toUpperCase()) : "—";
  const fresh = (value) => value ? "Fresh" : "Unavailable / stale";
  const percent = (value) => value == null ? "—" : `${value.toFixed(1)}%`;
  const modes = {
    PRODUCTION: "Inspection mode", CALIBRATION_REQUESTED: "Calibration requested",
    STOPPING_INSPECTION: "Stopping inspection", RETURNING_TO_DOCK: "Returning to dock",
    WAITING_FOR_DOCK: "Waiting for dock", PREPARING_CALIBRATION: "Preparing calibration",
    CALIBRATION_READY: "Calibration ready", CALIBRATION_BLOCKED: "Calibration blocked", RECOVERY_REQUIRED: "Recovery required",
    MAPPING_ACTIVE: "Mapping flight", MAPPING_COMPLETE: "Mapping complete",
  };
  let visible = false, section = "management", busy = false, loading = false, generation = 0, current = null;
  let nextRefresh = 0;
  let catalog = [], details = null, warehouseBusy = false, nextCatalog = 0, confirmationRun = null;
  let warehouseFeedback = "";

  function renderWarehouses() {
    const status = current?.learned_warehouse;
    const {system, calibration} = current;
    const name = row => row ? [row.name, row.revision != null ? `Rev ${row.revision}` : null,
      row.configuration_id.slice(-8)].filter(Boolean).join(" · ") : "";
    const activeEntry = catalog.find(row => row.configuration_id === status?.active_id);
    const job = activeMission(system.mission) ? system.mission : null;
    const selected = el("warehouse-select").value;
    const selectedEntry = catalog.find(row => row.configuration_id === selected);
    const verified = details?.manifest.configuration_id === selected;
    const active = !!selected && status?.active_id === selected;
    const idle = calibration.mode === "PRODUCTION" && system.contact && system.at_pad && !system.busy
      && !["PREPARING", "RESERVED", "RECOVERY", "UNAVAILABLE"].includes(system.safety);
    const selectedDate = verified ? details.locations.map(location => location.received_at_utc).filter(Boolean).sort()[0] : null;
    text("warehouse-active", status?.error || (status?.active_id
      ? `${name(activeEntry) || "Saved configuration"} · ${status.ready ? "Ready for inspections" : "Selected · takeoff blocked until the dock map matches"}`
      : status?.enabled ? "No active saved warehouse" : "Reference warehouse profile"));
    text("warehouse-mission", job ? (!job.configuration_id ? "Reference or manual flight" :
      name(catalog.find(row => row.configuration_id === job.configuration_id)) || "Saved mission configuration") : "No active mission");
    text("warehouse-selected", name(selectedEntry) || "No saved selection");
    text("warehouse-date", displayDate(selectedDate) || (verified ? "Date unavailable" : "Check integrity to read"));
    text("warehouse-count", verified ? details.locations.length : "Check integrity to read");
    text("warehouse-route-status", verified ? label(details.status) : "Check integrity to read");
    text("warehouse-integrity", verified ? "Verified" : "Verification required");
    text("warehouse-model-status", selectedEntry?.model_saved ? "Available" : selectedEntry ? "Open preview to check" : "Unavailable");
    el("warehouse-confirm-row").hidden = !verified || active;
    el("warehouse-select").disabled = warehouseBusy || !catalog.length;
    el("warehouse-verify").disabled = warehouseBusy || !selected;
    el("warehouse-preview").disabled = warehouseBusy || !selected;
    el("warehouse-activate").hidden = active;
    el("warehouse-activate").disabled = warehouseBusy || !verified || active || !idle || !el("warehouse-confirm").checked;
    el("warehouse-map-open").disabled = warehouseBusy || !verified;
    el("warehouse-plan").hidden = !status?.ready || !idle;
    text("warehouse-action-help", !status?.enabled ? "Saved configurations are available in the learned warehouse profile."
      : !selected ? "Save a completed calibration to create a warehouse configuration."
      : warehouseBusy ? "Checking the selected configuration…"
      : !verified ? "Check integrity before reviewing the route or activating this revision."
      : active ? "This revision is already selected as the active warehouse."
      : calibration.mode !== "PRODUCTION" ? "Close calibration before activating another warehouse."
      : job || system.busy ? "Finish the current flight or wait for its report before activating another revision."
      : !system.contact || !system.at_pad ? "Wait for confirmed physical docking before activating another revision."
      : !idle ? "Wait for Safety to release flight reservations."
      : !el("warehouse-confirm").checked ? "Confirm that this revision should be activated at the dock."
      : "Activation changes the warehouse used for the next inspection.");
    text("warehouse-feedback", warehouseFeedback);
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
    warehouseFeedback = "";
    renderWarehouses();
    try {
      const { response, body } = await request("warehouses/" + action, {
        configuration_id:identifier, confirm:el("warehouse-confirm").checked,
      });
      if (!response.ok) throw new Error(body.error);
      details = body;
      el("warehouse-confirm").checked = false;
      warehouseFeedback = action === "verify"
        ? "Verified · " + body.locations.length + " locations"
        : "Activation requested. Waiting for the drone to match the saved map.";
    } catch (error) {
      details = null;
      warehouseFeedback = error.message;
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
    el("service-overview").hidden = section !== "management";
    el("service-calibration").hidden = section !== "calibration";
    el("warehouse-configurations").hidden = section !== "configuration";
    if (section === "configuration") renderWarehouses();
    const production = calibration.mode === "PRODUCTION";
    const ready = !!mapping;
    const draft = calibration.draft;
    const active = activeMission(system.mission) ? system.mission : null;
    const summary = {robot:system.connection, at_pad:system.at_pad, physical_dock:system.contact,
      mission:system.mission, service_mode:calibration.mode, safety:{phase:system.safety}};
    const docked = dockState(summary);
    const state = operatorState(summary);
    const blocked = !available ? "Calibration requires the Full Robotics profile."
      : system.safety === "RECOVERY" ? "Complete Recovery before starting calibration."
      : active?.mode === "manual" ? "Return the manual flight to the dock before starting calibration." : "";
    text("service-phase", state.label);
    el("service-phase").dataset.tone = state.tone;
    text("service-mission-summary", active ? `${active.slots?.join(" → ") || "Manual flight"} · ${percent(system.battery)} battery`
      : system.connection ? "No active mission" : "Drone telemetry unavailable");
    text("service-start-hint", blocked || (active
      ? `Inspection ${active.inspection_id} is running. Starting calibration interrupts it and returns the drone to the dock.`
      : "Prepare a new warehouse survey. New inspections remain locked until calibration is closed."));
    text("service-start", active && !blocked ? "Review interruption and start calibration" : "Start calibration");
    const saved = draft && catalog.find(row => row.mapping_id === draft.calibration_id);
    const captures = calibration.locations || [];
    const multi = draft?.multi_sortie === true;
    const remaining = calibration.remaining || [];
    const sorties = draft?.sorties || [];
    el("calibration-full-option").hidden = !current.full_calibration_available;
    el("calibration-full-option").querySelector("input").disabled = !production || busy;
    el("calibration-full-progress").hidden = !multi;
    if (multi) {
      const total = calibration.location_total;
      const flightStatus = sorties.map(row => `Flight ${row.number} docked`).join(" · ");
      text("calibration-full-progress", [
        `${total - remaining.length}/${total} locations registered`,
        remaining.length ? `Missing ${remaining.join(", ")}` : "All location markers confirmed",
        `Battery ${percent(system.battery)} · ${label(system.dock)}`,
        Number.isFinite(calibration.return_budget) ? `Return estimate ${percent(calibration.return_budget)}` : "",
        flightStatus,
      ].filter(Boolean).join(" · "));
    }
    const step = production ? 0 : calibration.mode === "MAPPING_COMPLETE" ? (saved ? 6 : 4)
      : calibration.mode === "MAPPING_ACTIVE" ? (mapping?.mapping_phase === "FINISHING" ? 3 : captures.length ? 2 : 1)
        : calibration.mode === "CALIBRATION_READY" ? 1 : 0;
    for (const [index, item] of [...el("calibration-steps").children].entries()) {
      if (index === step) item.setAttribute("aria-current", "step");
      else item.removeAttribute("aria-current");
      item.classList.toggle("completed", index < step || !!saved);
    }
    text("service-connection", system.connection ? "Connected" : "Offline");
    text("service-drone-model", droneProfile(system.drone_model));
    text("service-localization", label(system.localization));
    text("service-lidar", fresh(system.lidar));
    text("service-imu", fresh(system.imu));
    text("service-camera-status", system.camera ? "Live" : "Unavailable");
    text("service-battery", percent(system.battery));
    text("service-dock", docked.label);
    text("service-safety", system.safety === "RELEASED" ? "Released · aisles open" : label(system.safety));
    el("service-return").hidden = system.contact || !(system.safety === "RECOVERY" || system.mission?.stage === "MANUAL_FLIGHT");
    text("service-profile", warehouse.profile);
    text("service-map-source", warehouse.map_source);
    text("service-map", warehouse.map);
    text("service-locations", current.learned_warehouse.enabled
      ? (current.learned_warehouse.active_id ? "See Warehouse Configuration" : "No active configuration") : warehouse.locations);
    text("service-config-state", label(warehouse.status));
    text("service-mode", modes[calibration.mode] || label(calibration.mode));
    text("service-calibration-detail", !available && production
      ? "Calibration is unavailable in this profile. Use Full Robotics."
      : calibration.detail + (calibration.cancel_pending ? " Cancellation will finish at the confirmed dock." : ""));
    el("service-introduction").hidden = !production;
    el("service-start").disabled = busy || !!blocked;
    el("service-lock").disabled = busy;
    el("service-cancel").hidden = production;
    el("service-cancel").disabled = busy || calibration.cancel_pending || calibration.mode === "MAPPING_ACTIVE";
    text("service-cancel", calibration.cancel_pending ? "Waiting for inspection localization" :
      calibration.mode === "MAPPING_COMPLETE" ? "Close calibration" : "Cancel calibration");
    const conditions = [
      ["Position", system.at_pad ? "At dock" : system.connection ? "Away from dock" : "Unavailable", system.at_pad],
      ["Physical contact", system.contact ? "Confirmed" : "Not confirmed", system.contact],
      ["Safety", system.safety_ready ? "Dock area clear" : "Waiting for safe access", system.safety_ready],
      ["Sensors", system.lidar && system.imu && system.camera ? "Fresh" : "Waiting for live data",
        system.lidar && system.imu && system.camera],
      ["Drone position", system.localization === "TRACKING" ? "Verified" : "Waiting for position", system.localization === "TRACKING"],
    ];
    const readiness = conditions.map(([title, message, valid]) =>
      `<li data-tone="${valid ? "ready" : "warning"}"><span>${title}</span><strong>${message}</strong></li>`).join("");
    if (el("calibration-readiness").innerHTML !== readiness) el("calibration-readiness").innerHTML = readiness;
    el("calibration-readiness").hidden = production;
    const tabCanFly = calibration.mode === "CALIBRATION_READY" && mapping?.mapping_phase === "READY";
    const tabReview = calibration.mode === "MAPPING_COMPLETE";
    const canFinish = multi && ["CALIBRATION_READY", "CALIBRATION_CHARGING"].includes(calibration.mode)
      && !!sorties.length && !remaining.length && system.contact && !active;
    el("calibration-finish").hidden = !canFinish;
    el("calibration-finish").disabled = busy;
    el("calibration-next").hidden = production;
    el("calibration-fly").hidden = tabReview;
    el("calibration-fly").disabled = !tabCanFly || busy;
    text("calibration-fly", multi && sorties.length ? "Continue mapping" : "Open mapping controls");
    el("service-review-route").hidden = !tabReview;
    el("service-review-route").disabled = !draft?.map_reference || !system.contact || !system.at_pad || !!active || busy;
    el("service-preview-calibration").hidden = !tabReview || !draft?.map_reference;
    el("service-review-route").dataset.session = draft?.calibration_id || "";
    text("calibration-action-help", saved ? `Saved as revision ${saved.revision}. Close calibration to activate it.`
      : tabReview && el("service-review-route").disabled ? "Wait for the measured map and verified physical dock before reviewing the route."
      : tabReview ? "Review and approve the measured route, then save the configuration."
      : tabCanFly ? "Opens the mapping controls. Takeoff requires a separate command."
      : calibration.mode === "CALIBRATION_CHARGING" ? "The measured map, locations and flight are saved. Continue when charged."
      : calibration.mode === "CALIBRATION_FINALIZING" ? "Saving the measured warehouse and preparing the Digital Twin."
      : calibration.mode === "MAPPING_ACTIVE" ? "Finish registering locations and return using Manual Control."
      : `${docked.label}. Mapping controls unlock after dock, Safety and sensors are ready.`);
    el("calibration-workspace").hidden = !ready;
    if (!ready) return;
    el("calibration-captures").hidden = !captures.length;
    const captured = el("calibration-location-list");
    const signature = JSON.stringify(captures);
    if (captured.dataset.signature !== signature) {
      captured.dataset.signature = signature;
      captured.replaceChildren(...captures.map(record => {
        const row = document.createElement("li"), photo = document.createElement("a");
        photo.href = `/api/service/mapping/${encodeURIComponent(draft.calibration_id)}/${record.photo}`;
        photo.target = "_blank";
        photo.rel = "noopener";
        photo.textContent = record.id + " · Camera reference";
        row.append(photo);
        return row;
      }));
    }
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
    el("calibration-ply").hidden = el("calibration-result").hidden = !draft.map_reference;
    el("calibration-locations").hidden = !draft.map_reference || !draft.locations_reference;
    if (draft.map_reference) {
      el("calibration-ply").href = draft.map_reference;
      el("calibration-result").href = draft.map_reference.replace(/map\.ply$/, "result.json");
      if (draft.locations_reference) el("calibration-locations").href = draft.locations_reference;
    }
    if (mapping.mapping_error) feedback(mapping.mapping_error);
    const camera = el("service-camera");
    camera.hidden = !system.camera;
    el("service-camera-empty").hidden = system.camera;
    if (visible && section === "calibration" && system.camera && !document.hidden && camera.closest("details").open) {
      camera.src = `/api/frame.jpg?t=${Date.now()}`;
    }
  }

  async function refresh() {
    if (!visible || busy || loading || Date.now() < nextRefresh) return;
    const requestGeneration = generation;
    loading = true;
    nextRefresh = Date.now() + (current ? 700 : 1500);
    try {
      const { response, body } = await request("state");
      if (requestGeneration !== generation) return;
      const hadSession = !!current;
      if (response.ok) {
        current = body;
        if (body.learned_warehouse?.enabled && Date.now() >= nextCatalog) {
          nextCatalog = Date.now() + 4000;
          await updateCatalog();
          if (requestGeneration !== generation) return;
        }
      } else if (response.status === 401) {
        if (current) text("service-access-message", "Service session expired. Enter the code to unlock it again.");
        if (body.configured === false) text("service-access-message", "Service access is disabled until a code is configured on the server.");
        current = null;
      }
      if (hadSession !== !!current) sessionChanged?.(!!current);
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
        sessionChanged?.(false);
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
  el("service-start").addEventListener("click", () => {
    const mission = current?.system?.mission;
    if (!activeMission(mission)) {
      action("calibration/start", {expected_inspection_id: null,
        multi_sortie: !el("calibration-full-option").hidden && el("calibration-full").checked});
      return;
    }
    confirmationRun = mission.inspection_id;
    const dialog = el("calibration-confirm");
    dialog.returnValue = "";
    text("calibration-confirm-mission", `Inspection ${confirmationRun}${mission.slots?.length ? " · " + mission.slots.join(" → ") : ""}`);
    dialog.showModal();
  });
  el("calibration-confirm").addEventListener("close", event => {
    if (event.target.returnValue === "interrupt")
      action("calibration/start", {expected_inspection_id: confirmationRun,
        multi_sortie: !el("calibration-full-option").hidden && el("calibration-full").checked});
    confirmationRun = null;
  });
  el("service-cancel").addEventListener("click", () => action("calibration/cancel", {}));
  el("calibration-finish").addEventListener("click", () =>
    action("mapping/finish", {calibration_id: current.calibration.draft.calibration_id}));
  el("warehouse-verify").addEventListener("click", () => warehouseAction("verify"));
  el("warehouse-activate").addEventListener("click", () => warehouseAction("activate"));
  el("warehouse-plan").addEventListener("click", () => openPlan(details));
  el("warehouse-map-open").addEventListener("click", () => openWarehouse(details));
  el("warehouse-preview").addEventListener("click", () => {
    const selected = catalog.find(item => item.configuration_id === el("warehouse-select").value);
    if (selected) openPreview(selected);
  });
  el("warehouse-confirm").addEventListener("change", renderWarehouses);
  el("warehouse-select").addEventListener("change", () => {
    details = null;
    el("warehouse-confirm").checked = false;
    warehouseFeedback = "";
    renderWarehouses();
  });
  return {
    async planConfiguration(identifier) {
      const { response, body } = await request("warehouses/verify", {configuration_id:identifier});
      if (response.status === 401) return null;
      if (!response.ok) throw new Error(body.error);
      return body;
    },
    show(value, panel) {
      visible = value;
      if (value) {
        section = panel;
        nextRefresh = nextCatalog = 0;
      } else if (el("calibration-confirm").open) el("calibration-confirm").close("cancel");
      render();
      refresh();
    },
    refresh,
  };
}
