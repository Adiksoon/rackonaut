"""Create the repository-local API virtual environment and install its lock."""

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "backend" / "requirements.txt"
ENVIRONMENT = ROOT / ".venv-backend"


def main():
    if not ((3, 10) <= sys.version_info[:2] <= (3, 13)):
        raise SystemExit("Use CPython 3.10 through 3.13 to set up the fixture API.")

    if ENVIRONMENT.is_symlink():
        raise SystemExit(f"Expected a repository-local virtual environment. Found a link at {ENVIRONMENT}.")
    if not ENVIRONMENT.exists():
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    elif not (ENVIRONMENT / "pyvenv.cfg").is_file():
        raise SystemExit(f"{ENVIRONMENT} already exists without pyvenv.cfg. Choose a clean checkout.")

    executable = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    version = subprocess.check_output([
        executable, "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
    ], text=True).strip()
    current = f"{sys.version_info.major}.{sys.version_info.minor}"
    if version != current:
        raise SystemExit(f"{executable} uses Python {version}. Run setup with Python {version} or in a clean checkout.")

    return subprocess.call([
        executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-cache-dir",
        "--only-binary=:all:", "-r", LOCK,
    ])


if __name__ == "__main__":
    raise SystemExit(main())
