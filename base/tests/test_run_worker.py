"""``manage.py run_worker``: the ``worker`` task, long-running (aws-next README, «Contrato app ↔ infra»).

SIGTERM (ECS stopping the task) and SIGINT (Ctrl-C) only ask ``base.worker.run`` to stop; it exits
with its code, 0 within the 30 s of ECS's ``stopTimeout``. In-process, the test's own handlers stand
guard, so a command that forgot to install or restore its own never stops pytest; then a real
process, against this suite's databases, from the start line to SIGTERM.
"""

import os
import queue
import signal
import subprocess
import sys
import threading
import time
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import CommandError, call_command
from django.db import connections

from base import worker
from shared.models import App, AppDoc

HUB_DIR = Path(__file__).resolve().parent.parent.parent
STOP_TIMEOUT = 30  # ECS's stopTimeout of the worker task
STARTUP = 60


@pytest.fixture
def guard():
    """Handlers of our own on SIGTERM and SIGINT for the test; the previous ones come back after."""
    received: list[int] = []

    def handler(signum, frame):
        received.append(signum)

    previous = {
        sig: signal.signal(sig, handler) for sig in (signal.SIGTERM, signal.SIGINT)
    }
    yield handler, received
    for sig, old in previous.items():
        signal.signal(sig, old)


def run_worker() -> str:
    out = StringIO()
    call_command("run_worker", stdout=out)
    return out.getvalue()


@pytest.mark.parametrize(
    "sig", [signal.SIGTERM, signal.SIGINT], ids=["SIGTERM", "SIGINT"]
)
def test_a_signal_asks_the_worker_to_stop_and_it_exits_0(monkeypatch, guard, sig):
    handler, received = guard
    seen = {}

    def fake_run(stop: threading.Event, **kwargs) -> int:
        signal.raise_signal(sig)
        seen["stop"] = stop.is_set()
        return 0

    monkeypatch.setattr(worker, "run", fake_run)

    out = run_worker()

    assert seen == {"stop": True}
    assert received == []  # the command's handler took it, not the guard
    assert "worker: started" in out
    # Its handlers are gone with it.
    assert signal.getsignal(signal.SIGTERM) is handler
    assert signal.getsignal(signal.SIGINT) is handler


def test_a_failed_worker_exits_with_its_code(monkeypatch, guard):
    handler, _ = guard
    monkeypatch.setattr(worker, "run", lambda stop, **kwargs: 1)

    with pytest.raises(
        CommandError, match="the worker stopped with exit code 1"
    ) as raised:
        run_worker()

    assert raised.value.returncode == 1
    assert signal.getsignal(signal.SIGTERM) is handler


def worker_env() -> dict[str, str]:
    """This suite's databases (``default`` and ``shared``), as the infra passes them to the task."""
    default, shared = (
        connections["default"].settings_dict,
        connections["shared"].settings_dict,
    )
    return {
        **os.environ,
        "DEBUG": "True",
        "PYTHONUNBUFFERED": "1",
        "DB_HOST": default["HOST"],
        "DB_PORT": str(default["PORT"]),
        "DB_NAME": default["NAME"],
        "DB_USER": default["USER"],
        "DB_PASSWORD": default["PASSWORD"],
        "SHARED_DB_NAME": shared["NAME"],
        "SHARED_DB_USER": shared["USER"],
        "SHARED_DB_PASSWORD": shared["PASSWORD"],
    }


def read_lines(stream, lines: queue.Queue) -> None:
    for line in stream:
        lines.put(line)
    lines.put(None)  # end of output


def wait_for(lines: queue.Queue, text: str, seen: list[str]) -> None:
    deadline = time.monotonic() + STARTUP
    while (remaining := deadline - time.monotonic()) > 0:
        try:
            line = lines.get(timeout=remaining)
        except queue.Empty:
            break
        if line is None:
            break
        seen.append(line)
        if text in line:
            return
    pytest.fail(f"the worker never wrote {text!r}; its output:\n{''.join(seen)}")


@pytest.mark.django_db(transaction=True, databases=["default", "shared"])
@pytest.mark.usefixtures("shared_schema")
def test_the_real_process_registers_the_apps_and_exits_0_on_sigterm():
    assert not App.objects.exists()
    process = subprocess.Popen(
        [sys.executable, "manage.py", "run_worker"],
        cwd=HUB_DIR,
        env=worker_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    lines: queue.Queue = queue.Queue()
    threading.Thread(
        target=read_lines, args=(process.stdout, lines), daemon=True
    ).start()
    seen: list[str] = []
    try:
        wait_for(lines, "worker: started", seen)
        wait_for(lines, "worker: waiting for work", seen)

        process.send_signal(signal.SIGTERM)
        sent = time.monotonic()
        code = process.wait(timeout=STOP_TIMEOUT)

        assert code == 0, "".join(seen)
        assert time.monotonic() - sent < STOP_TIMEOUT
        assert App.objects.filter(id="demo").exists()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        # The process committed its rows: they go, so the next test finds the registry empty.
        AppDoc.objects.all().delete()
        App.objects.all().delete()
