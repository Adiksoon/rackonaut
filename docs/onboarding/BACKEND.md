# Backend · inventory comparison and REST

Build a backend that accepts observations, compares them with the expected mock SAP inventory, and returns inspection results. The fixture API and contract tests let you start on Windows or Linux with Git and Python. Use Python 3.10 on Ubuntu/WSL or Python 3.13 on native Windows.

Accept the private GitHub invitation, then clone and create your branch in Bash or PowerShell.

```sh
git clone https://github.com/Adiksoon/rackonaut.git
cd rackonaut
git switch -c feature/backend
```

## Ubuntu or WSL

For a one-command dependency setup, run `python3.10 scripts/api/setup.py` on Ubuntu or WSL, or `python scripts/api/setup.py` in Windows PowerShell with Python 3.13. Then continue with the smoke and Uvicorn commands. The manual equivalents are included below.

Create and use a local virtual environment from the repository root.

```bash
python3.10 -m venv .venv-backend
.venv-backend/bin/python -m pip install -r backend/requirements.txt
.venv-backend/bin/python -m unittest discover -s tests -v
.venv-backend/bin/python scripts/api/smoke.py
.venv-backend/bin/python -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

## Native Windows

Check that `python --version` reports Python 3.13 before creating the environment. PowerShell can use the environment's Python directly.

```powershell
python -m venv .venv-backend
& .\.venv-backend\Scripts\python.exe -m pip install -r backend/requirements.txt
& .\.venv-backend\Scripts\python.exe -m unittest discover -s tests -v
& .\.venv-backend\Scripts\python.exe scripts/api/smoke.py
& .\.venv-backend\Scripts\python.exe -m uvicorn backend.mock_api:app --host 127.0.0.1 --port 8000
```

The smoke script starts and stops its own loopback server. The Uvicorn command starts a persistent local mock for manual requests. Visit [the mock API docs](http://127.0.0.1:8000/docs) to try requests. Stop the server with Ctrl+C in its own terminal. Virtual environment setup uses your existing Python installation. If Ubuntu lacks Python's `venv` module, installing the system package `python3.10-venv` requires administrator privileges.

## Your first change

- Work in `backend/` and backend-specific tests. Use the [HTTP contract](../../contracts/http.md), [OpenAPI](../../contracts/openapi.json), and [synthetic scenarios](../../test_data/).
- Keep the fixture API available for dashboard work. Implement comparison behavior in the backend and test it against the expected fixture results, including repeated observations and uninspected, uncertain and unreadable cases.
- Commit owned paths and open a PR to `main` with the test command and observed output. Follow the [Git workflow](../TEAM_TASKS.md#git-workflow). Pass the [backend prompt](AI_PROMPT_BACKEND.md) to your agent if using one.

## Confirm readiness

Report your OS, Python version, and results with this checklist.

- [ ] Repository cloned.
- [ ] Correct branch created.
- [ ] Dependencies installed.
- [ ] Mock or reference component started.
- [ ] Smoke test passed.
- [ ] Ready for development.
