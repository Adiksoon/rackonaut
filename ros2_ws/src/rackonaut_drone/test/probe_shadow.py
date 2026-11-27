#!/usr/bin/python3
"""Fly the scripted X3 shadow trial in its own Gazebo/ROS domain."""
import argparse
import json
import math
import time
from functools import partial
from pathlib import Path

from ament_index_python.packages import get_package_share_path
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
from sensor_msgs.msg import Imu, PointCloud2
from std_msgs.msg import String

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("output", type=Path, help="directory for traffic.json")
args = parser.parse_args()
out = args.output
out.mkdir(parents=True, exist_ok=True)
layout = json.loads((get_package_share_path("rackonaut_warehouse")/"config/aerial_layout.json").read_text())["nodes"]
ODOM = "/rackonaut/drone/odom"
ESTIMATE = "/rackonaut/localization/estimate"
CMD = "/rackonaut/drone/cmd_vel"
IMU = "/rackonaut/drone/imu"
LIDAR = "/rackonaut/drone/lidar/points"
data, diagnostics, streams, phases = {}, [], {}, []
rclpy.init(args=[])
node = Node("x3_shadow_trials")
cmd = node.create_publisher(Twist, CMD, 10)

def stamp(message):
    return message.header.stamp.sec + message.header.stamp.nanosec / 1e9

def odom(message):
    pos, quat = message.pose.pose.position, message.pose.pose.orientation
    vector = np.array([pos.x,pos.y,pos.z])
    angle = math.atan2(2*(quat.w*quat.z+quat.x*quat.y),1-2*(quat.y*quat.y+quat.z*quat.z))
    data["time"],data["xyz"],data["yaw"] = stamp(message),vector,angle

def status(message):
    item=json.loads(message.data)
    data["status"]=item
    if "time" in data:
        diagnostics.append({"sim_time":data["time"],"state":item["state"],"reason":item["reason"],
                            "accepted":item["accepted"]})

def watch(topic,message):
    t=stamp(message)
    item=streams.setdefault(topic,{"count":0,"first_s":t,"frame":message.header.frame_id})
    item["count"]+=1
    item["last_s"]=t
    if isinstance(message,PointCloud2):
        item["dimensions"]=[message.width,message.height]

node.create_subscription(Odometry,ODOM,odom,qos_profile_sensor_data)
node.create_subscription(Odometry,ESTIMATE,partial(watch,ESTIMATE),qos_profile_sensor_data)
node.create_subscription(Imu,IMU,partial(watch,IMU),qos_profile_sensor_data)
node.create_subscription(PointCloud2,LIDAR,partial(watch,LIDAR),qos_profile_sensor_data)
node.create_subscription(String,"/rackonaut/localization/state",status,
                         QoSProfile(depth=1,durability=DurabilityPolicy.TRANSIENT_LOCAL))

def tick_until(check,label,timeout=65,make=None):
    stop=time.monotonic()+timeout
    next_send=0.
    while time.monotonic()<stop:
        rclpy.spin_once(node,timeout_sec=.02)
        if make and time.monotonic()>=next_send:
            cmd.publish(make())
            next_send=time.monotonic()+.10
        if check():
            return
    raise RuntimeError(f"{label}: {data}")

def target(point, yaw):
    error=np.asarray(point)-data["xyz"]
    angle=data["yaw"]
    x=math.cos(angle)*error[0]+math.sin(angle)*error[1]
    y=-math.sin(angle)*error[0]+math.cos(angle)*error[1]
    yaw_error=math.atan2(math.sin(yaw-angle),math.cos(yaw-angle))
    message=Twist()
    message.linear.x = float(np.clip(x * .8, -.48, .48))
    message.linear.y = float(np.clip(y * .8, -.48, .48))
    message.linear.z = float(np.clip(error[2] * .9, -.48, .48))
    message.angular.z = float(np.clip(yaw_error * 1.1, -.38, .38))
    return message

def mark(name,start):
    row={"phase":name,"start_sim_s":start,"end_sim_s":data["time"],
         "position":[round(float(x),3) for x in data["xyz"]],"yaw_rad":round(data["yaw"],3)}
    phases.append(row)
    print(row,flush=True)

def go(point,yaw=0.,hold=1.,radius=.10):
    def settled():
        return (np.linalg.norm(data["xyz"]-point)<radius
                and abs(math.atan2(math.sin(data["yaw"]-yaw),math.cos(data["yaw"]-yaw)))<.07)
    tick_until(settled,f"reach {point}, yaw {yaw}",make=lambda:target(point,yaw))
    end=data["time"]+hold
    tick_until(lambda:data["time"]>=end,"hold at target",make=lambda:target(point,yaw))

def stage(name,points,yaw=0.,hold=1.):
    start=data["time"]
    for point in points:
        go(point,yaw,hold)
    mark(name,start)

ready_to_move = False
try:
    tick_until(lambda: data.get("status",{}).get("accepted",0)>=8 and all(
        stream in streams for stream in (ESTIMATE,IMU,LIDAR)) and cmd.get_subscription_count()==1,
        "calibration and first synchronized estimates",timeout=45)
    assert streams[LIDAR]["dimensions"]==[192,37],streams[LIDAR]
    publishers=node.get_publishers_info_by_topic(ODOM)
    assert [item.node_name for item in publishers]==["x3_bridge"]
    assert data["status"]["mode"] == "shadow"
    assert [item.node_name for item in node.get_publishers_info_by_topic(CMD)] == [node.get_name()]
    ready_to_move = True
    print("Ready",data["status"]["state"],data["status"]["accepted"],data["xyz"].tolist(),flush=True)
    dock=layout["dock"]
    hold_point=[dock[0],dock[1],.85]
    stage("takeoff",[hold_point])
    stage("hover",[hold_point],hold=4.)
    stage("yaw",[hold_point],yaw=math.pi/2,hold=2.)
    go(hold_point,0.)
    stage("shaft_and_approach_A",[layout["shaft"],layout["junction"],layout["trunk_A"],layout["entry_A"]])
    stage("transfer_A_B",[layout["trunk_A"],layout["trunk_B"],layout["entry_B"]])
    stage("hover_at_B",[layout["entry_B"]],hold=3.)
finally:
    if ready_to_move:
        for _ in range(4):
            cmd.publish(Twist())
            time.sleep(.10)
    measurements = {"streams": streams, "phases": phases, "diagnostics": diagnostics}
    (out / "traffic.json").write_text(json.dumps(measurements, indent=2) + "\n")
    node.destroy_node()
    rclpy.try_shutdown()
