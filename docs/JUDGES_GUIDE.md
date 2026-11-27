# Judge's Guide

Rackonaut is an integrated simulation prototype for automated warehouse inventory and quality inspection. In Gazebo Fortress, a simulated drone uses LiDAR and IMU to localize, flies through protected warehouse routes, captures images at planned locations, and returns to a dock. Control Center compares the camera-derived observations with synthetic Mock SAP inventory and gives the supervisor a report with evidence and suggested actions.

## Review in 5 minutes

1. **See the product.** View the open-aisle warehouse, measured Digital Twin and Control Center in the [README](../README.md#our-solution) and [gallery](GALLERY.md).
2. **Open a finding.** Download and open the [Warehouse in Motion report](final-branch-audit-evidence/report.html). At A-01-02, the original camera image shows P003 where Mock SAP expected P002. A-01-01 has a covered label and A-01-03 is unexpectedly empty. [Expected vs. observed screenshot](final-branch-audit-evidence/results-A-01-02.png)
3. **Follow the data.** Start with the [architecture diagram](../README.md#system-architecture), then open the [interface contracts](INTERFACES.md). The camera-to-report path runs from Gazebo through ROS 2 perception and the observation API to Mock SAP and the Control Center.
4. **Check the numbers.** The open-aisle calibration was a **reference-drone** campaign. The **X3** 11-location inspection, automatic charging and moving-cart response have their own records. [Validation highlights](../README.md#validation-highlights)
5. **Review the code or run one short scenario.** Use the [code pointers](#where-the-code-lives) or start the [one-location open-aisle demo](GETTING_STARTED.md#open-aisle-reference-inspection). [Release checks](RELEASE_VALIDATION.md)

## What is implemented

Control Center plans inspections, shows live telemetry and a reference or measured Digital Twin, and presents stock and quality findings. Calibration records measured LiDAR, teaches camera-identified locations and seals approved routes in a restorable archive. Mission execution uses localization, Safety reservations, Collision Prevention and an energy budget. The operator can authorize guarded Recovery. Perception feeds ArUco, occupancy and carton-quality observations into Mock SAP, which produces business comparisons. A standalone CSV importer prepares expected inventory and product records for that backend. [Capabilities and evidence](../README.md#key-capabilities)

## Where the code lives

| Review area | Entry point |
| --- | --- |
| Integrated launch and operator interface | [`control.launch.py`](../ros2_ws/src/rackonaut_control/launch/control.launch.py) · [Control Center and Digital Twin views](../ros2_ws/src/rackonaut_control/web/) |
| Warehouse and drone | [SDF generator](../ros2_ws/src/rackonaut_warehouse/scripts/generate.py) · [X3 model preparation](../ros2_ws/src/rackonaut_drone/scripts/prepare_model) · [Reference packages](../ros2_ws/src/rackonaut_reference/) |
| SLAM and calibration | [Localization package](../ros2_ws/src/rackonaut_localization/) · [Warehouse archive verification](../ros2_ws/src/rackonaut_localization/rackonaut_localization/warehouse_config.py) · [Control-side calibration and learned routes](../ros2_ws/src/rackonaut_control/rackonaut_control/) |
| Flight, protection and energy | [Mission Manager and Recovery](../ros2_ws/src/rackonaut_mission/) · [Safety](../ros2_ws/src/rackonaut_safety/) · [Collision Prevention](../ros2_ws/src/rackonaut_avoidance/) · [Energy](../ros2_ws/src/rackonaut_energy/) |
| Camera observations and business results | [Perception](../ros2_ws/src/rackonaut_perception/) · [Mock SAP application](../backend/sap_api.py) · [CSV import](../scripts/inventory/import_csv.py) · [ROS and HTTP contracts](INTERFACES.md) |

## Scenarios and evidence

| Scenario | What to look for | Original record |
| --- | --- | --- |
| Reference open-aisle inspection | A selected location, descent through portal A, camera confirmation and return to dock. | [Flight telemetry](open-aisle-evidence/reference-flight.json) |
| Restore the reference survey | Eleven taught locations, 94,194 points, 496 directed edges, a three-row reconstructed twin and four separately planned sorties. A and B were replayed in separate autonomous runs. | [Archive and survey](FULL_WAREHOUSE_CALIBRATION.md) · [Restart and replay evidence](FULL_WAREHOUSE_CALIBRATION.md#restart-i-odtworzenie) |
| X3 known-map inventory | 11 unique inspection locations and automatic charging and resumption with the same mission ID. | [Mission telemetry](full-system-evidence/x3-known-inventory.json) · [HTML report](full-system-evidence/x3-known-report.html) |
| Warehouse in Motion | X3 stops for a cart during descent, continues once clear and reports three inspected locations. | [Obstacle and mission telemetry](final-branch-audit-evidence/result.json) · [Experiment report](FINAL_BRANCH_AUDIT.md#walidacja) |
| Three additional warehouses | Distribution Center, High-Bay Warehouse and Large Logistics Hub. Each has its own SDF, markers, protected graph, fixtures and recorded dock startup. | [Pinned companion revision and launch](GETTING_STARTED.md#additional-warehouses) · [Gallery](GALLERY.md#additional-warehouses) |

## Limitations and roadmap

- **Physical deployment.** The prototype operates in Gazebo. Physical drone commissioning, camera and LiDAR calibration on hardware, flight tests and site acceptance remain future work. Safety interlocks and docking are simulated. They have no physical safety certification. [Safety assumptions](../ros2_ws/src/rackonaut_safety/docs/SENSOR_SAFETY.md)
- **Inventory and perception.** Mock SAP runs locally with synthetic fixtures. Production SAP integration and validation under actual warehouse lighting, label variation and occlusions are future work. Carton-quality findings cover visible packaging in the captured image. [Mock SAP and quality evidence](SAP_BUSINESS_INTELLIGENCE.md)
- **Energy.** Automatic simulated charging and same-mission resumption were verified for X3 on a known map. Automatic battery swapping remains a concept. In the larger halls, several planned round trips exceed the modeled battery budget even before a complete inventory is attempted. [X3 charging trial](FULL_SYSTEM_INTEGRATION.md#c--x3-na-znanej-mapie) · [Larger-hall energy estimates](https://github.com/Adiksoon/rackonaut/blob/6b9ebfaba39bd5e091d5de5f7d23301a9ec35115/docs/multi-warehouse-evidence/validation.json)
- **Companion environments.** The three larger halls have static geometry, fixture and dock-startup evidence. Full calibration, sustained SLAM through the aisles and autonomous inventory remain unverified for those halls. [Companion validation scope](https://github.com/Adiksoon/rackonaut/blob/6b9ebfaba39bd5e091d5de5f7d23301a9ec35115/docs/MULTI_WAREHOUSE_ENVIRONMENTS.md)
- **Measured geometry and archive retention.** The third reconstructed rack is partial. The published calibration stored 480 of 910 accepted keyframes. Most interior aisle B keyframe poses were replaced, while the accumulated cloud still preserves B measurements. The current code has a retention fix for widely separated capture regions. The sealed archive contains the original measurements. [Calibration measurements and retention](FULL_WAREHOUSE_CALIBRATION.md)
- **Learned missions.** The restored plan shows four sortie budgets, with one separately dispatched sortie per learned mission. The flight evidence covers one target in each of A and B. The 11/11 X3 inspection was a separate known-map trial. [Reference restart and replay](FULL_WAREHOUSE_CALIBRATION.md#restart-i-odtworzenie) · [X3 known-map inventory](full-system-evidence/x3-known-inventory.json)
