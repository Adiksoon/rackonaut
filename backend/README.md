# Backend development

The in-memory FastAPI fixture server supports development and contract testing on Windows and Linux without ROS 2, Gazebo or a database. It starts with the synthetic inspection INS-001 and discards writes on exit. The functional Mock SAP profile compares incoming observations against the 11 synthetic expected locations and persists observations, linked evidence and operator verification in SQLite.

Use the [backend onboarding guide](../docs/onboarding/BACKEND.md) to install and run the mock. Follow the [HTTP interface guide](../contracts/http.md) and [OpenAPI contract](../contracts/openapi.json) when implementing the real endpoints. The same mock serves [dashboard development](../dashboard/README.md).

Start Mock SAP from the repository root after preparing the backend environment.

```bash
.venv-backend/bin/python -m uvicorn backend.sap_api:app --factory --host 127.0.0.1 --port 8000
```

Set `RACKONAUT_SAP_DB` to choose the database path. The default is `.rackonaut-data/warehouse.sqlite3`. The published inventory contract remains v1. [Warehouse Intelligence endpoints](../docs/SAP_BUSINESS_INTELLIGENCE.md)
