# Interface index

Use the linked contracts to implement and review changes across module boundaries.

| Boundary | Canonical references | Integration check |
|---|---|---|
| Warehouse and drone | [ROS and simulation contract](../contracts/ros.md) | Spawn an independently described model into the world at the agreed pose. |
| Drone and computer vision | [ROS and simulation contract](../contracts/ros.md) | Check topic type, publisher and subscriber QoS, frames, calibration, and simulation time on the same run. |
| Vision and backend | [HTTP semantics and JSON validation](../contracts/http.md) · [OpenAPI](../contracts/openapi.json) | Submit a fixture observation, repeat its ID, and verify the documented response. |
| Backend and dashboard | [OpenAPI](../contracts/openapi.json) · [HTTP examples](../contracts/http.md) | Fetch inventory, observations, discrepancy records, and summary for the same inspection. |

Use the [fixtures](../test_data/) to test empty, occupied, unreadable, uncertain, and uninspected states independently. An unreadable label can coexist with an occupied slot. An uninspected slot has no observation for that inspection.

Follow the visible marker procedure and retain simulator ground truth for separate validation. [Slot association and capture timestamps](../contracts/http.md#recording-observations)
