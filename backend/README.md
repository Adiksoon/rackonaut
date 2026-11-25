# Backend development

The in-memory FastAPI fixture server supports development and contract testing on Windows and Linux without ROS 2, Gazebo or a database. It starts with the synthetic inspection INS-001 and discards writes on exit. Implement production data comparison and persistence separately in this directory.

Use the [backend onboarding guide](../docs/onboarding/BACKEND.md) to install and run the mock. Follow the [HTTP interface guide](../contracts/http.md) and [OpenAPI contract](../contracts/openapi.json) when implementing the real endpoints. The same mock serves [dashboard development](../dashboard/README.md).
