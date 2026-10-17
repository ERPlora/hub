"""The settings of the test run (config/settings_pytest.py, pytest.ini): Vite's port stays 5173."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

BASE_DIR = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("source", ["environment", "dotenv"])
def test_the_test_run_keeps_the_default_vite_port_whatever_the_developer_sets(
    tmp_path, source
):
    """A second checkout carries VITE_DEV_PORT in its shell or its .env (tests/e2e/README.md «Varias
    ejecuciones a la vez»; runserver honours both): the suite still reads 5173, since the environment
    wins over .env in python-decouple, so the tests that pin it (the SPA's dev HTML, LIVE["vite"]) hold.
    A fresh process: this one has already read its settings."""
    env = {
        key: value
        for key, value in os.environ.items()
        if key not in ("DEBUG", "VITE_DEV_PORT")
    }
    env["DEBUG"] = "True"
    if source == "environment":
        env["VITE_DEV_PORT"] = "5203"
    else:
        (tmp_path / ".env").write_text("VITE_DEV_PORT=5203\n")
    # The checkout's own .env stays out: decouple reads tmp_path's instead.
    preamble = f"import decouple; decouple.config = decouple.AutoConfig(search_path={str(tmp_path)!r})"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            f"{preamble}\nimport config.settings_pytest as s\n"
            "print(s.LIVE['spa']['dev_server'], s.LIVE['vite']['command'][1])",
        ],
        cwd=BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.split() == ["http://localhost:5173", "VITE_DEV_PORT=5173"]


def test_pytest_runs_on_the_test_settings():
    # pytest-django imports the settings before any conftest: only this module can pin the port first.
    assert os.environ["DJANGO_SETTINGS_MODULE"] == "config.settings_pytest"
