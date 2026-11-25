"""ROS-native path and markers for the RViz mission view."""

from math import cos, sin

from geometry_msgs.msg import PoseStamped
from nav_msgs.msg import Path
from visualization_msgs.msg import Marker, MarkerArray


def stamped_pose(pose, frame, stamp=None):
    message = PoseStamped()
    message.header.frame_id = frame
    if stamp is not None:
        message.header.stamp = stamp
    message.pose.position.x, message.pose.position.y, message.pose.position.z = pose.x, pose.y, pose.z
    message.pose.orientation.z = sin(pose.yaw / 2)
    message.pose.orientation.w = cos(pose.yaw / 2)
    return message


def planned_path(route, frame, land):
    path = Path()
    path.header.frame_id = frame
    points = (route.pad, route.takeoff, *route.stops, route.takeoff)
    if land:
        points += (route.pad,)
    path.poses = [stamped_pose(point, frame) for point in points]
    return path


def marker(frame, namespace, number, kind, xyz, size, color, text=""):
    item = Marker()
    item.header.frame_id, item.ns, item.id = frame, namespace, number
    item.type, item.action, item.text = kind, Marker.ADD, text
    item.pose.position.x, item.pose.position.y, item.pose.position.z = xyz
    item.pose.orientation.w = 1.
    item.scale.x, item.scale.y, item.scale.z = size
    item.color.r, item.color.g, item.color.b, item.color.a = color
    return item


def make_markers(route, pose, frame, status):
    pad = route.pad
    marks = [
        marker(frame, "pad", 0, Marker.CUBE, (pad.x, pad.y, pad.z - .04), (2.65, 2.1, .02), (.05, .36, .48, .74)),
        marker(frame, "pad", 1, Marker.TEXT_VIEW_FACING, (pad.x - .25, pad.y - .4, pad.z + .35), (.0, .0, .30),
               (.68, .9, .98, 1.), "LAUNCH PAD"),
    ]
    for number, point in enumerate(route.stops):
        slot = point.slot_id
        if slot in status["confirmed"]:
            event = status["confirmed"][slot]
            needs_review = event["occupancy"] == "uncertain" or event.get("label_status") == "unreadable"
            color = (1., .70, .24, 1.) if needs_review else (.23, .90, .62, 1.)
        elif slot in status["missed"]:
            color = (1., .70, .24, 1.)
        elif slot == status["target"]:
            color = (.95, .98, 1., 1.)
        else:
            color = (.28, .64, .86, 1.)
        marks.append(marker(frame, "stops", number, Marker.SPHERE, (point.x, point.y, point.z), (.18, .18, .18), color))
        marks.append(marker(frame, "labels", number, Marker.TEXT_VIEW_FACING,
                            (point.x, point.y + .52, point.z + .25), (.0, .0, .30), color, slot))
    if pose is not None:
        arrow = marker(frame, "drone", 0, Marker.ARROW, (pose.x, pose.y, pose.z), (.60, .11, .12), (.94, .77, .27, 1.))
        arrow.pose.orientation.z, arrow.pose.orientation.w = sin(pose.yaw / 2), cos(pose.yaw / 2)
        marks.append(arrow)
    center = route.stops[len(route.stops) // 2]
    text = (f"RACKONAUT / {status['stage'].replace('_', ' ')} / {status['target']}\n"
            f"{len(status['visited'])}/{status['total']} visited | {len(status['confirmed'])} confirmed"
            f" | {status['elapsed_seconds']:.1f}s")
    marks.append(marker(frame, "status", 0, Marker.TEXT_VIEW_FACING, (center.x - 1., pad.y, max(p.z for p in route.stops) + 1.3),
                        (.0, .0, .33), (.88, .95, 1., 1.), text))
    return MarkerArray(markers=marks)
