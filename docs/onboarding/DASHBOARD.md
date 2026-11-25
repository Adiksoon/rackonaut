# Dashboard · inspection results

Build the dashboard against the fixture API while backend development proceeds independently. You need Git, a browser, and either Python 3.13 on Windows or Python 3.10 on Ubuntu/WSL. The baseline leaves the frontend framework to the dashboard owner.

Accept the private GitHub invitation, then clone the repository and create your branch.

```sh
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
git switch -c feature/dashboard
```

## Start the fixture API

For a one-command dependency setup, run `python3.10 scripts/api/setup.py` on Ubuntu or WSL, or `python scripts/api/setup.py` in Windows PowerShell with Python 3.13. Then continue with the smoke and Uvicorn commands. The manual equivalents are included below.

On Ubuntu or WSL, select the virtual environment's interpreter explicitly.

```bash
python3.10 -m venv .venv-backend
.venv-backend/bin/python -m pip install -r backend/requirements.txt
.venv-backend/bin/python scripts/api/smoke.py
.venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

On Windows, check `python --version` for Python 3.13. Run the commands below in PowerShell.

```powershell
python -m venv .venv-backend
& .\.venv-backend\Scripts\python.exe -m pip install -r backend/requirements.txt
& .\.venv-backend\Scripts\python.exe scripts/api/smoke.py
& .\.venv-backend\Scripts\python.exe -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

Open [the API docs](http://127.0.0.1:8000/docs), then request the health, summary, and discrepancies for the seeded inspection. The smoke script uses its own temporary port. The browser uses the separate mock at port 8000. Stop the API with Ctrl+C in its own terminal.

## Your first change

- Work in `dashboard/`. Use the [OpenAPI contract](../../contracts/openapi.json), [request and response examples](../../contracts/http.md), and [fixtures](../../test_data/).
- Use `http://127.0.0.1:8000` as the API base URL. Serve a browser-based dashboard from an allowed local origin such as `http://localhost:3000` or `http://localhost:5173`. Refresh using REST polling.
- Check that the view shows expected inventory, inspection progress, discrepancies, and review states for the fixture inspection. Label demo data and make pending, uncertain, and uninspected states distinguishable from confirmed empty or matching slots.
- Commit owned paths and open a PR to `main` with startup steps, smoke evidence, and the chosen stack. Follow the [Git workflow](../TEAM_TASKS.md#git-workflow) and use the [dashboard agent prompt](AI_PROMPT_DASHBOARD.md) if helpful.

## Confirm readiness

Report your OS, Python version, mock URL, and smoke result.

- [ ] Repository cloned.
- [ ] Correct branch created.
- [ ] Dependencies installed.
- [ ] Mock or reference component started.
- [ ] Smoke test passed.
- [ ] Ready for development.
