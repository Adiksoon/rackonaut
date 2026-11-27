# Rackonaut technical documentation

Start with the [Judge's Guide](JUDGES_GUIDE.md) for a five-minute tour or the [demo guide](GETTING_STARTED.md) for a clean-checkout setup. The [gallery](GALLERY.md) identifies the model and trial behind each capture.

| Topic | Documentation and code |
| --- | --- |
| Architecture | [System diagram](../README.md#system-architecture) · [Architecture notes](ARCHITECTURE.md) · [ROS and HTTP interfaces](INTERFACES.md) |
| Getting started | [Clean checkout and demo profiles](GETTING_STARTED.md) · [Troubleshooting](TROUBLESHOOTING.md) · [Control Center launch options](../ros2_ws/src/rackonaut_control/README.md) |
| Drone models | [Integrated X3 and reference profiles](X3_FULL_ROBOTICS_INTEGRATION.md) · [X3 package and Fuel asset](../ros2_ws/src/rackonaut_drone/README.md) · [Reference package](../ros2_ws/src/rackonaut_reference/) |
| Warehouse environments | [Open-aisle geometry](OPEN_AISLE_DESCENT.md) · [Warehouse generator](../ros2_ws/src/rackonaut_warehouse/) · [Three companion environments](GETTING_STARTED.md#additional-warehouses) |
| Localization and SLAM | [Sensor localization](SENSOR_LOCALIZATION.md) · [Empty-map mapping](UNKNOWN_WAREHOUSE_MAPPING.md) · [Full-route validation](SLAM_FULL_ROUTE_VALIDATION.md) |
| Warehouse calibration | [Full survey and verified archive](FULL_WAREHOUSE_CALIBRATION.md) · [Teach storage locations](STORAGE_LOCATION_TEACHING.md) · [Route review and approval](ROUTE_TEACHING.md) |
| Digital Twin | [Live measured 3D Scan](MEASURED_3D_MAP.md) · [Measured reconstruction](MEASURED_WAREHOUSE_RECONSTRUCTION.md) · [Control Center integration](DIGITAL_TWIN_CONTROL_CENTER.md) |
| Autonomous missions | [Mission Manager](../ros2_ws/src/rackonaut_mission/README.md) · [Learned replay](LEARNED_WAREHOUSE_AUTONOMY.md) · [Warehouse in Motion](WAREHOUSE_IN_MOTION.md) |
| Safety and recovery | [Safety sensors and zone reservations](../ros2_ws/src/rackonaut_safety/docs/SENSOR_SAFETY.md) · [Collision Prevention](OBSTACLE_AVOIDANCE.md) · [Recovery](AUTONOMOUS_RECOVERY.md) · [Protected manual flight](PROTECTED_MANUAL_FLIGHT.md) |
| Energy management | [Energy model, docking and charging](ENERGY_MANAGEMENT.md) · [X3 known-map charging and resumption](FULL_SYSTEM_INTEGRATION.md#c--x3-na-znanej-mapie) |
| Computer Vision | [Perception package and quality recognition](../ros2_ws/src/rackonaut_perception/README.md) · [Validation images and reports](../ros2_ws/src/rackonaut_perception/docs/VERIFICATION.md) |
| Mock SAP integration | [Business rules and reporting](SAP_BUSINESS_INTELLIGENCE.md) · [API setup](../backend/README.md) · [CSV importer and sample data](../scripts/inventory/README.md) |
| Validation and test evidence | [Release checks](RELEASE_VALIDATION.md) · [Full System Integration trials](FULL_SYSTEM_INTEGRATION.md) · [Historical baseline tests](TEST_RESULTS.md) · [Engineering tools and recorded bag](ENGINEERING_SHOWCASE.md) |
| Team contributions | [Verified contribution register](TEAM_TASKS.md) · [Branch and PR provenance](RELEASE_VALIDATION.md#repository-provenance) · [Third-party notices](ATTRIBUTION.md) |
| Known limitations | [Demonstration scope and engineering roadmap](JUDGES_GUIDE.md#limitations-and-roadmap) |

Detailed engineering reports retain their original language and filenames so references and evidence remain traceable.
