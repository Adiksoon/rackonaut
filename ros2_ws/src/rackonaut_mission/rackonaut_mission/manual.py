"""Manual movement requests handled by the Mission Manager's command owner."""

import json
from dataclasses import replace
from math import isfinite
from time import monotonic

from geometry_msgs.msg import Twist

from rackonaut_avoidance.manual import ZERO, Motion, limit_request, protect, world_vector
from rackonaut_energy.aerial import interval
from rackonaut_energy.model import estimate


MANUAL_TOPIC = "/rackonaut/manual/request"
MANUAL_STAGE = "MANUAL_FLIGHT"
COMMAND_AGE = .55
TAKEOFF_HEIGHT = .72
RETURN_MARGIN = 2.


def departure_energy(model, pad):
    takeoff = pad[0], pad[1], TAKEOFF_HEIGHT, pad[3]
    return estimate(model, pad, [takeoff, pad], 3.)[0] + model.reserve + RETURN_MARGIN


def decode_axes(request):
    axes = request.get("axes")
    speed = request.get("speed")
    if (not isinstance(axes, list) or len(axes) != 4
            or any(type(v) not in (float, int) or not -1 <= v <= 1 for v in axes)
            or type(speed) not in (float, int) or not .2 <= speed <= 1.):
        raise ValueError("Use four normalized axes and a speed between 20 and 100 percent.")
    return tuple(axes), speed


class ManualFlight:
    def __init__(self, mission):
        self.mission = mission
        self.input_at = -1e6
        self.sequence = -1
        self.requested = ZERO
        self.motion = Motion(state="PREPARING", detail="Waiting for Safety and an operator heartbeat")
        self.returning = self.return_requested = False

    @property
    def takeoff(self):
        return replace(self.mission.route.pad, z=TAKEOFF_HEIGHT, phase="VERTICAL_TAKEOFF")

    def departure_energy(self):
        m = self.mission
        return departure_energy(m.energy_model, m.coordinates(m.route.pad))

    def receive(self, message):
        m = self.mission
        now = monotonic()
        try:
            request = json.loads(message.data)
            if not isinstance(request, dict) or request.get("inspection_id") != m.inspection_id:
                return
            seq, sent, action = request.get("sequence"), request.get("sent"), request.get("action")
            if (type(seq) is not int or seq <= self.sequence or type(sent) not in (int, float)
                    or not 0 <= now - sent <= COMMAND_AGE or action not in {"movement", "return"}):
                return
            velocity = limit_request(*decode_axes(request)) if action == "movement" else ZERO
        except (ValueError, TypeError, OverflowError):
            return
        self.sequence, self.input_at = seq, sent
        if self.returning or self.return_requested:
            return
        self.requested = velocity
        self.return_requested = action == "return"

    def allowed(self, start, end, now):
        m = self.mission
        if not m.aerial.allows(start, end, m.route.zones):
            return False
        if end[2] >= start[2] - .001:
            return True
        return all(now - m.safety_at <= .45 and m.descents.get(zone, {}).get("cleared")
                   for _, _, zone, box in m.aerial.edges
                   if zone in m.aerial.gates and zone in m.route.zones and interval(start, end, box) is not None)

    def publish(self, motion, cloud):
        m = self.mission
        self.motion = motion
        command = Twist()
        command.linear.x, command.linear.y, command.linear.z, command.angular.z = map(float, motion.velocity)
        m.command.publish(command)
        m.navigation.position = m.coordinates(m.pose)
        m.navigation.cloud = cloud
        m.navigation.sweep = motion.scan
        m.navigation.direction = motion.direction
        m.navigation.checked_distance = motion.clearance or 0.
        m.navigation.set_state(motion.state, motion.detail)

    def step(self, now):
        m = self.mission
        if self.returning:
            if not m.battery.get("budget_verified") or (
                    not m.physical_dock(now) and m.battery["percent"] < m.return_motion_cost() + m.energy_model.reserve):
                m.finish("ABORTED", "Energy budget cannot confirm the rest of the manual return", now)
            else:
                m.move_with_avoidance(now)
            return
        cloud = m.scanner.current(now)
        if cloud is None:
            m.navigation.set_state("FAULT", "Onboard LiDAR stopped advancing")
            m.finish("ABORTED", "Onboard LiDAR stopped advancing", now)
            return
        if not m.battery.get("budget_verified"):
            m.finish("ABORTED", "Energy telemetry cannot verify the return budget", now)
            return
        pose = m.coordinates(m.pose)
        return_cost = m.return_cost(m.pose)
        reserve = m.energy_model.reserve
        remaining = m.battery["percent"]
        if not isfinite(return_cost) or remaining < return_cost + reserve:
            m.finish("ABORTED", "Insufficient energy for a verified return and reserve", now)
            return
        energy_return = remaining <= return_cost + reserve + RETURN_MARGIN
        if self.return_requested or energy_return:
            reason = "ENERGY_RETURN" if energy_return else "MANUAL_RETURN_REQUESTED"
            self.publish(Motion(state=reason, detail="Stopping before returning through the reserved route"), cloud)
            if m.speed <= .09 and abs(m.yaw_rate) <= .09:
                self.returning = True
                m.return_reason = reason
                m.follow_return(now, m.dock_route(m.pose))
            return
        if now - self.input_at > COMMAND_AGE:
            self.requested = ZERO
            self.publish(Motion(state="LINK_LOST", detail="Operator heartbeat expired; holding position"), cloud)
            if m.stage == "VERTICAL_TAKEOFF":
                # Reconnection never restarts an interrupted takeoff.
                m.finish("ABORTED", "Operator heartbeat expired during takeoff", now)
            return
        if m.stage == "VERTICAL_TAKEOFF":
            self.motion = Motion(state="TAKING_OFF", detail="Protected vertical departure")
            m.move_with_avoidance(now)
            return

        response = protect(cloud, pose, m.body_speed, self.requested, now, lambda a, b: self.allowed(a, b, now))
        if response.velocity != ZERO:
            delta = world_vector(response.velocity, pose[3]) * 1.5
            destination = replace(m.pose, x=pose[0]+delta[0], y=pose[1]+delta[1], z=pose[2]+delta[2],
                                  yaw=pose[3]+response.velocity[3]*1.5)
            spent = estimate(m.energy_model, pose, [m.coordinates(destination)])[0]
            if not self.allowed(pose, m.coordinates(destination), now):
                # The stopping envelope has already limited the command. Use
                # that shorter distance for the energy forecast at a boundary.
                spent = m.energy_model.draw(*response.velocity[:3], True) * 1.5
                destination = m.pose
            budget = spent + m.return_cost(destination) + reserve + RETURN_MARGIN
            if remaining < budget:
                response = Motion(state="ENERGY_LIMIT", detail="Requested motion exceeds the verified return budget")
        self.publish(response, cloud)

    def snapshot(self):
        m = self.mission
        if m.stage == "ABORTED":
            detail = m.detail
            alarm = m.safety_alarm or {}
            # The Safety Manager and Control Center share the Abort service.
            # The matching alarm can arrive after the service call.
            if detail == "Stopped by the operator" and alarm.get("event") in {
                    "intrusion", "sensor_fault", "signal_fault", "mission_fault"}:
                detail = "Safety: " + alarm.get("message", "Reservation revoked")
            state = ("LOCALIZATION_LOST" if "LOCALIZATION_LOST" in detail else
                     "SAFETY" if "Safety" in detail else
                     "FAULT" if ("LiDAR" in detail or "telemetry" in detail) else
                     "ENERGY_LIMIT" if "energy" in detail.lower() or "battery" in detail.lower() else
                     "LINK_LOST" if "heartbeat" in detail else
                     "EMERGENCY_STOP" if detail == "Stopped by the operator" else "FAULT")
            return self.status(state, detail, ZERO)
        if m.stage == "COMPLETE":
            return self.status("DOCKED", m.detail, ZERO)
        if self.returning:
            return self.status("RETURNING", m.detail, ZERO)
        return self.status(self.motion.state, self.motion.detail, self.motion.velocity)

    def status(self, state, detail, permitted):
        return {"state": state, "detail": detail, "requested": [round(v, 3) for v in self.requested],
                "permitted": [round(v, 3) for v in permitted],
                "clearance": round(self.motion.clearance, 3) if self.motion.clearance is not None else None}
