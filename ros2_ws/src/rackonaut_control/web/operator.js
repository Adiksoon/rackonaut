export const terminal = new Set(["COMPLETE", "COMPLETE_WITH_MISSES", "ABORTED", "INTERRUPTED_FOR_CALIBRATION", "ERROR"]);
export const activeMission = mission => !!mission && !terminal.has(mission.stage);
export const activeSafetyAlarm = safety => safety?.phase === "RECOVERY" ? safety.alarm : null;
export const batteryPercent = value => Number.isFinite(value) ? `${Math.round(value)}%` : "Unavailable";
export const percentagePoints = value => Number.isFinite(value)
  ? `${value >= 0 ? "+" : "−"}${Math.abs(value).toFixed(1)} pp` : "Unavailable";

const phases = {
  STARTING: "Starting inspection", WAITING: "Waiting for departure clearance",
  WAITING_FOR_AISLE_CLEARANCE: "Waiting for aisle clearance", TAKEOFF: "Taking off",
  VERTICAL_TAKEOFF: "Taking off", TAKING_OFF: "Taking off",
  INSPECT: "Inspecting location", LEARNED_INSPECTION: "Approaching inspection location",
  INSPECTION: "Inspecting location", REINSPECT: "Checking the label again",
  QUALITY_CLOSEUP: "Capturing packaging evidence", REPOSITION: "Adjusting the camera angle",
  RECENTER: "Returning to the inspection position", RETURN_TO_DOCK: "Returning to dock",
  LEARNED_LAND: "Landing at the dock", LAND: "Landing", DOCKING: "Aligning with the dock",
  CHARGING: "Charging at the dock", READY_TO_RESUME: "Waiting for clearance to resume",
  RESUMING: "Resuming inspection", COMPLETE: "Inspection complete",
  COMPLETE_WITH_MISSES: "Inspection complete with missed locations",
  INTERRUPTED_FOR_CALIBRATION: "Inspection interrupted for calibration",
  ABORTED: "Flight stopped", ERROR: "Flight could not start",
};

export function missionPhase(mission, target) {
  if (!mission) return "No inspection running";
  const manual = mission.status?.manual;
  const phase = mission.status?.flight_phase;
  if (manual?.state === "HOLD" && mission.stage === "MANUAL_FLIGHT") return "Manual flight · holding position";
  if (manual?.state === "RETURNING") return "Manual flight · returning to dock";
  if (["BLOCKED", "FAULT", "LINK_LOST", "LOCALIZATION_LOST", "ENERGY_LIMIT"].includes(manual?.state))
    return manual.state === "BLOCKED" ? "Manual flight · motion blocked" : "Manual flight · movement on hold";
  if (mission.stage === "MANUAL_FLIGHT") return "Manual flight · airborne";
  if (mission.stage === "LEARNED_TRANSIT")
    return target === "PAD" ? "Returning to dock" : "Flying to inspection location";
  if (mission.stage === "INSPECT" && /waiting for a fresh camera observation/i.test(mission.status?.detail || ""))
    return "Waiting for a valid observation";
  return phases[mission.stage] || phases[phase] || "Flying to inspection location";
}

export function dockState(state) {
  if (!state?.robot) return {label: "Dock status unavailable", tone: "neutral"};
  if (state.physical_dock === true) return {label: "Physical dock contact confirmed", tone: "ready"};
  if (state.at_pad && state.physical_dock === false)
    return {label: "At the dock · awaiting physical contact", tone: "warning"};
  if (state.at_pad) return {label: "At the launch pad", tone: "ready"};
  return {label: "Away from dock", tone: "neutral"};
}

export function operatorState(state, target, disconnected = false) {
  if (disconnected || !state) return {label: "Control Center reconnecting", tone: "warning"};
  const job = state.mission;
  const recovery = state.recovery?.phase;
  if (recovery === "WAITING_FOR_OPERATOR_APPROVAL") return {label: "Recovery awaiting approval", tone: "warning"};
  if (recovery === "RETURNING_TO_DOCK") return {label: "Recovery · returning to dock", tone: "active"};
  if (recovery === "EMERGENCY_DOCKING") return {label: "Recovery · awaiting physical docking", tone: "active"};
  if (recovery === "RECOVERY_FAILED") return {label: "Recovery failed · operator action required", tone: "danger"};
  if (state.safety?.phase === "RECOVERY") {
    const stopped = ["EMERGENCY_STOP", "OPERATOR_ABORT"].includes(state.recovery?.cause) ||
      /emergency stop|stopped by the operator/i.test(job?.status?.detail || "");
    return {label: stopped ? "Emergency stop active" : "Recovery required", tone: "danger"};
  }
  if (!state.robot) return {label: "Simulated drone offline", tone: "neutral"};
  if (state.service_mode && state.service_mode !== "PRODUCTION") {
    if (state.service_mode === "RETURNING_TO_DOCK" || state.service_mode === "STOPPING_INSPECTION")
      return {label: "Returning for calibration", tone: "active"};
    if (state.service_mode === "CALIBRATION_BLOCKED") return {label: "Calibration blocked", tone: "warning"};
    if (state.service_mode === "WAITING_FOR_DOCK") return dockState(state);
    if (state.service_mode === "MAPPING_ACTIVE") return {label: "Calibration · mapping flight", tone: "active"};
    return {label: "Calibration in progress", tone: "active"};
  }
  if (activeMission(job)) return {label: missionPhase(job, target), tone: "active"};
  if (state.energy?.fresh && state.energy.charging) return {label: "Docked · charging", tone: "ready"};
  if (state.physical_dock === true) return {label: "Docked", tone: "ready"};
  return dockState(state);
}

export function returnEnergy(telemetry, forecast) {
  const now = telemetry?.fresh && Number.isFinite(telemetry.percent) ? telemetry.percent : null;
  const reserve = Number.isFinite(forecast?.reserve_percent) ? forecast.reserve_percent : null;
  const cost = forecast?.return_percent;
  const verified = telemetry?.budget_verified === true && now != null && Number.isFinite(cost) && cost >= 0;
  const rawBalance = verified ? now - cost : null;
  return {
    now, reserve,
    atDock: rawBalance == null ? null : Math.max(0, rawBalance),
    margin: rawBalance == null || reserve == null ? null : rawBalance - reserve,
  };
}

export function displayDate(value, includeSeconds = false) {
  if (!value) return "";
  const date = new Date(value);
  return Number.isFinite(+date) ? new Intl.DateTimeFormat("en-GB", {
    day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit",
    ...(includeSeconds ? {second: "2-digit"} : {}),
  }).format(date) : "";
}
