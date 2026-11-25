"""Operator-approved return driven by the existing Mission command owner."""

import json
from datetime import datetime, timezone
from math import dist, hypot
from pathlib import Path
from uuid import uuid4

from geometry_msgs.msg import Twist
from rackonaut_avoidance.planner import LOOKAHEAD, Navigator, sweep
from rackonaut_energy.model import estimate

from .route import Target, heading_error

ACTIVE = {"RETURNING_TO_DOCK", "EMERGENCY_DOCKING"}
COMPLETE = "RECOVERY_COMPLETE"
FAILED = "RECOVERY_FAILED"
STABILIZE = 1.25
STATUS_AGE = .55
ENERGY_MARGIN = 1.5


def utc():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def cause(detail, alarm, stage):
    text = detail.lower()
    if "localization_lost" in text:
        return "LOCALIZATION_LOST"
    if not alarm:
        alarm = {}
    event = alarm.get("event")
    specific = {"intrusion": "ZONE_INTRUSION", "sensor_fault": "SAFETY_SENSOR_LOST",
                "signal_fault": "COMMUNICATION_FAILURE", "mission_fault": "COMMUNICATION_FAILURE",
                "touchdown_unknown": "DOCK_UNCONFIRMED"}
    if event in specific:
        return specific[event]
    if "lidar stopped" in text:
        return "ONBOARD_LIDAR_LOST"
    if "blocked" in text or "envelope" in text or "travel timeout" in text:
        return "ROUTE_BLOCKED"
    if "battery" in text or "energy" in text and "telemetry" not in text:
        return "INSUFFICIENT_ENERGY"
    if stage in {"LAND", "DOCKING"} and "stopped by" not in text:
        return "DOCK_UNCONFIRMED"
    if "operator" in text:
        return "OPERATOR_ABORT"
    return "COMMUNICATION_FAILURE"


class Recovery:
    def __init__(self, mission, directory):
        self.mission = mission
        self.directory = Path(directory)
        self.clock_stable_since = None
        self.stop = None
        self.record = None
        self.phase = ""
        self.conditions = {}
        self.route = []
        self.origin = None
        self.target = None
        self.leg = 0
        self.leg_at = self.settled_at = self.thrust_disabled_at = None
        self.navigation = Navigator()
        self.return_cost = None
        self.at_dock = False
        self.proposal = None

    def stopped(self, now, detail, stage):
        if self.stop is None:
            m = self.mission
            self.stop = {"at": utc(), "wall": now, "mission_stage": stage, "detail": detail,
                         "energy": m.battery.get("percent"),
                         "position": list(m.coordinates(m.pose)) if m.pose else None}
            self.phase = "RECOVERY_REQUIRED"

    def action(self, action, recovery_id, proposal, now):
        m = self.mission
        if not self.stop or m.stage not in {"ABORTED", "COMPLETE", "COMPLETE_WITH_MISSES"}:
            return
        if action == "evaluate" and self.phase in {"RECOVERY_REQUIRED", FAILED} and m.safety_phase == "RECOVERY":
            self.record = {"recovery_id": f"REC-{uuid4().hex[:12].upper()}",
                           "inspection_id": m.inspection_id, "cause": cause(self.stop["detail"], m.safety_alarm, self.stop["mission_stage"]),
                           "trigger": m.safety_alarm, "stopped": {k: v for k, v in self.stop.items() if k != "wall"},
                           "evaluated_at": utc(), "flown": [], "zones": sorted(m.route.zones)}
            self.route, self.origin = [], None
            self.phase = "RECOVERY_PLANNING"
            self.persist()
        elif self.record and self.record["recovery_id"] == recovery_id:
            if action == "authorize" and self.phase == "WAITING_FOR_OPERATOR_APPROVAL" and proposal == self.proposal:
                self.check(now)
                if not all(self.conditions.values()) or not self.origin or dist(m.coordinates(m.pose)[:3], self.origin[:3]) > .12:
                    return
                self.phase = "RECOVERY_AUTHORIZED"
                self.record.update(authorized_at=utc(), authorized_wall=now,
                                   accepted_conditions=dict(self.conditions), planned=self.points(), energy_authorized=m.battery["percent"],
                                   waiting_energy_used=round(max(0., self.stop["energy"]-m.battery["percent"]), 3)
                                   if self.stop["energy"] is not None else None,
                                   predicted_return_percent=self.return_cost,
                                   waiting_wall_s=round(now-self.stop["wall"], 2))
                self.persist()
            elif action == "abort" and self.phase not in {FAILED, COMPLETE}:
                self.finish(now, FAILED, "Recovery stopped by the operator")

    def points(self):
        return [self.origin, *(leg.pose for leg in self.route)] if self.origin else []

    def check(self, now):
        m = self.mission
        p = m.coordinates(m.pose) if m.pose else None
        tracking = m.localization_ready(now) and now-m.odom_at <= .40 and p is not None
        if not tracking:
            self.clock_stable_since = None
        elif self.clock_stable_since is None:
            self.clock_stable_since = now
        stable = tracking and now-self.clock_stable_since >= STABILIZE
        cloud = m.scanner.current(now)
        energy = m.energy_fresh(now) and m.battery.get("budget_verified") is True and m.energy_model is not None
        health = m.safety_recovery
        reserved = (m.safety_phase == "RECOVERY" and now-m.safety_at <= STATUS_AGE
                    and set(m.route.zones) == m.safety_zones)
        envelope = bool(stable and m.aerial.allows(p, p, m.route.zones))
        still = bool(p and m.speed <= .12)
        locked = self.phase in ACTIVE | {"RECOVERY_AUTHORIZED", "WAITING_FOR_OPERATOR_APPROVAL"}
        self.at_dock = bool(energy and m.battery.get("contact") and m.battery.get("switch_engaged")
                            and m.battery.get("contact_source") == "gazebo_dock_switch")
        if not locked:
            self.route, self.origin = [], None
            if envelope and still:
                try:
                    self.route = [] if self.at_dock else m.dock_route(m.pose)
                    if self.route or self.at_dock:
                        self.origin = p
                except ValueError:
                    pass
        start_matches = bool(p and self.origin and dist(p[:3], self.origin[:3]) <= .12)
        route_ok = bool(self.origin and (self.route or self.at_dock) and (self.phase in ACTIVE or start_matches))
        first = False
        if route_ok and cloud and p and (self.route or self.at_dock):
            if self.route:
                goal = self.route[min(self.leg if self.phase in ACTIVE else 0, len(self.route)-1)].pose
                result = sweep(cloud, p, goal, LOOKAHEAD, pad=goal == self.route[-1].pose)
                first = result.hit is None and result.limit > .36
            else:
                first = self.at_dock
        points = [leg.pose for leg in self.route[self.leg if self.phase in ACTIVE else 0:]]
        self.return_cost = estimate(m.energy_model, p, points)[0] if route_ok and p and m.energy_model else None
        budget = (energy and self.return_cost is not None
                  and (self.at_dock or m.battery["percent"] >= self.return_cost + m.energy_model.reserve + ENERGY_MARGIN))
        self.conditions = {
            "stable_tracking": bool(stable), "onboard_lidar": cloud is not None,
            "safety_heartbeat_and_zones": reserved, "stationary": still,
            "zone_sensors": bool(reserved and health.get("sensors_fresh")),
            "fields_clear": bool(reserved and health.get("fields_clear")),
            "red_signals": bool(reserved and health.get("signals_confirmed")),
            "in_flight_envelope": envelope, "connected_return": route_ok, "first_leg_observed": first,
            "energy_telemetry": energy, "return_budget": bool(budget),
            "flight_enable_bridge": bool(m.flight_enable.get_subscription_count()),
            "command_ownership": m.count_publishers(m.command_topic) <= int(m.command is not None),
        }
        return p, cloud

    def tick(self, now):
        if not self.stop or self.phase == COMPLETE:
            return
        m = self.mission
        p, cloud = self.check(now)
        if self.phase in {"RECOVERY_REQUIRED", FAILED}:
            return
        if self.phase == "RECOVERY_AUTHORIZED":
            if not all(self.conditions.values()) or dist(p[:3], self.origin[:3]) > .12:
                self.finish(now, FAILED, "Conditions changed after operator approval")
            elif self.permitted():
                self.leg = 0
                self.record.update(started_at=utc(), started_wall=now, energy_start=m.battery["percent"])
                if self.at_dock:
                    m.set_flight_enabled(False)
                    self.finish(now, COMPLETE, "Physical dock contact already confirmed")
                    return
                m.set_flight_enabled(True)
                self.thrust_disabled_at = None
                m.command = m.create_publisher(Twist, m.command_topic, 10)
                self.follow(now)
                self.persist()
            elif now-self.record["authorized_wall"] > 4.:
                self.finish(now, FAILED, "Safety did not grant a scoped recovery permit")
            return
        if self.phase in ACTIVE:
            self.move(now, p, cloud)
            return
        if not self.conditions["stable_tracking"]:
            self.phase = "WAITING_FOR_LOCALIZATION"
        elif not all(self.conditions[key] for key in ("safety_heartbeat_and_zones", "zone_sensors", "fields_clear", "red_signals")):
            self.phase = "WAITING_FOR_ZONE_CLEARANCE"
        elif all(self.conditions.values()):
            if self.phase != "WAITING_FOR_OPERATOR_APPROVAL":
                self.proposal = uuid4().hex[:12]
            self.phase = "WAITING_FOR_OPERATOR_APPROVAL"
        else:
            self.phase = "RECOVERY_BLOCKED"

    def permitted(self):
        m = self.mission
        return m.safety_recovery.get("permit") == self.record["recovery_id"] and m.safety_phase == "RECOVERY"

    def follow(self, now):
        leg = self.route[self.leg]
        self.phase = "EMERGENCY_DOCKING" if self.leg == len(self.route)-1 else "RETURNING_TO_DOCK"
        self.target = Target(*leg.pose, phase=leg.phase, gate=leg.gate)
        if self.phase == "EMERGENCY_DOCKING":
            self.target = Target(*leg.pose[:2], max(0., leg.pose[2]-.05), leg.pose[3], phase=leg.phase)
        self.leg_at, self.settled_at = now, None

    def move(self, now, p, cloud):
        m = self.mission
        mandatory = set(self.conditions) - {"stationary", "first_leg_observed"}
        failed = sorted(key for key in mandatory if not self.conditions[key])
        if failed or not self.permitted():
            reason = m.safety_recovery.get("revoked") or ", ".join(failed) or "Safety recovery permit revoked"
            self.finish(now, FAILED, reason)
            return
        if now-self.leg_at > m.travel_timeout:
            self.finish(now, FAILED, "Recovery leg timed out")
            return
        ground = self.phase == "EMERGENCY_DOCKING"
        goal = self.route[self.leg].pose
        if not m.aerial.allows(p, goal, m.route.zones):
            self.finish(now, FAILED, "The active segment left the reserved flight envelope")
            return
        if not self.record["flown"] or dist(p[:3], self.record["flown"][-1][:3]) >= .12:
            self.record["flown"].append([round(x, 3) for x in p])
        if self.thrust_disabled_at is not None:
            if self.at_dock and m.speed <= .055 and now-self.thrust_disabled_at >= .8:
                self.finish(now, COMPLETE, "Stable physical dock contact after disabling thrust")
            elif now-self.thrust_disabled_at > 4.:
                self.finish(now, FAILED, "Dock contact did not settle after disabling thrust")
            return
        decision = self.navigation.step(cloud, p, goal, self.phase, m.speed, now, False, None, None,
                                        pad=ground and hypot(p[0]-goal[0], p[1]-goal[1]) < .13)
        if decision.fault:
            self.finish(now, FAILED, decision.fault)
            return
        m.send_velocity(self.target, scale=decision.scale if decision.advance else 0.)
        near = hypot(p[0]-goal[0], p[1]-goal[1]) <= .065
        stable = (near and m.speed <= .11 and abs(heading_error(goal[3], p[3])) <= .055
                  and (self.at_dock if ground else abs(p[2]-goal[2]) <= .06))
        if not stable:
            self.settled_at = None
            return
        if self.settled_at is None:
            self.settled_at = now
        if now-self.settled_at < (.6 if ground else .3):
            return
        if ground:
            m.set_flight_enabled(False)
            self.thrust_disabled_at = now
            self.record["thrust_disabled_at"] = utc()
        else:
            self.leg += 1
            self.follow(now)

    def finish(self, now, phase, reason):
        m = self.mission
        m.stop_motion()
        self.phase = phase
        start = self.record.get("started_wall")
        end_energy = m.battery.get("percent")
        initial = self.record.get("energy_start")
        self.record.update(ended_at=utc(), result=phase, detail=reason, duration_wall_s=round(now-start, 2) if start else None,
                           end_energy=end_energy, energy_used=round(max(0., initial-end_energy), 3) if initial is not None else None,
                           dock_confirmed=phase == COMPLETE, last_conditions=dict(self.conditions),
                           retry_slots=[slot.slot_id for slot in m.route.stops if slot.slot_id not in m.completed])
        self.persist()

    def persist(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{self.record['recovery_id']}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.snapshot(), indent=2) + "\n")
        temporary.replace(path)

    def snapshot(self):
        if not self.stop:
            return None
        m = self.mission
        record = self.record or {}
        budget = m.battery.get("percent")
        wait_draw = (m.energy_model.hover if m.battery.get("fresh") and m.energy_model
                     else m.battery.get("gap_draw_percent_per_sim_s"))
        reserve = m.energy_model.reserve if m.energy_model else None
        return {**{key: value for key, value in record.items() if not key.endswith("_wall")},
                "phase": self.phase, "proposal": self.proposal, "inspection_id": m.inspection_id,
                "cause": record.get("cause") or cause(self.stop["detail"], m.safety_alarm, self.stop["mission_stage"]),
                "stopped": {k: v for k, v in self.stop.items() if k != "wall"},
                "conditions": self.conditions, "required_zones": sorted(m.route.zones),
                "planned": record.get("planned") or self.points(), "leg": self.leg,
                "energy": budget, "return_cost": round(self.return_cost, 2) if self.return_cost is not None else None,
                "reserve": reserve, "wait_per_sim_s": wait_draw,
                "energy_verified": m.battery.get("budget_verified") is True,
                "permit_request": self.phase in ACTIVE | {"RECOVERY_AUTHORIZED"},
                "retry_slots": [slot.slot_id for slot in m.route.stops if slot.slot_id not in m.completed],
                "navigation": self.navigation.mode}
