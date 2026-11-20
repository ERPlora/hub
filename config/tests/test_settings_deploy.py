"""Production's settings pass `check --deploy`, run in a child that can never wait for ever."""

import os
import secrets
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings

from config.tests.settings_env import BASE_DIR, ENV_KEYS, PRODUCTION_ENV


def test_only_the_checks_the_platform_answers_elsewhere_are_silenced():
    # W008: the ALB redirects HTTP to HTTPS, and the SaaS calls /internal over plain HTTP on the private
    # name; W005/W021: HSTS for subdomains and the preload list is the apex's decision (erplora.com).
    assert settings.SILENCED_SYSTEM_CHECKS == [
        "security.W005",
        "security.W008",
        "security.W021",
    ]


# Exit codes of a child that run_to_the_end stops at once instead of waiting for it.
WAITED = 97
KEPT_ALIVE = 98
# The child of run_to_the_end: the script as __main__, with what could keep it from ever ending turned into an
# immediate failure that says what it was (hub#807): its main thread waiting, on the network or in a sleep, for what
# may never come, and a thread that is not a daemon, which the interpreter waits for at exit. os._exit, so that no
# except in the script can swallow it.
CHILD = f"""
import os, runpy, socket, sys, threading, time

def stop(code, why):
    sys.stdout.flush()  # what the script said up to here, which os._exit would drop
    os.write(2, f"{{why}}\\n".encode())
    os._exit(code)

def refused(call):
    def waits(*args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            stop({WAITED}, f"the main thread waits: {{call.__qualname__}}{{args!r}}")
        return call(*args, **kwargs)
    return waits

socket.getaddrinfo = refused(socket.getaddrinfo)
socket.socket.connect = refused(socket.socket.connect)
time.sleep = refused(time.sleep)
sys.argv = sys.argv[1:]
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
finally:
    alive = [t.name for t in threading.enumerate() if not t.daemon and t is not threading.main_thread()]
    if alive:
        stop({KEPT_ALIVE}, f"threads that keep it from ending: {{alive}}")
"""


def run_to_the_end(script: Path, *args: str, **kwargs) -> subprocess.CompletedProcess:
    """Run ``script`` in a fresh Python and wait for it to end, however long the machine takes (hub#807).

    No clock: a cut at N seconds cannot tell a stuck child from a slow one, and a loaded machine makes it slow. What the
    clock was there for, a child that never ends, is what CHILD turns into an exit of its own. What it cannot see, a
    main thread blocked on a lock or an event nobody releases, or a loop that never ends, nothing but a clock tells from
    a slow child: the cap of the CI job (30 minutes) still ends that run in red.
    """
    return subprocess.run(
        [sys.executable, "-c", CHILD, str(script), *args], capture_output=True, text=True, **kwargs
    )


@pytest.mark.parametrize("waits", ["socket.create_connection(('127.0.0.1', 9))", "time.sleep(1)"])
def test_a_child_whose_main_thread_waits_ends_at_once(tmp_path, waits):
    # A retry that swallows the error, or a loop that sleeps until something is ready, would wait on what never comes
    # for ever: its first try ends it.
    script = tmp_path / "waits.py"
    script.write_text(f"import socket, time\ntry:\n    {waits}\nexcept OSError:\n    pass\n")
    result = run_to_the_end(script)
    assert result.returncode == WAITED, result.stdout + result.stderr


def test_a_child_that_leaves_a_thread_keeping_it_alive_ends_at_once(tmp_path):
    # The interpreter waits at exit for every thread that is not a daemon: one that never ends keeps the child alive.
    script = tmp_path / "keeps_alive.py"
    script.write_text("import threading, time\nthreading.Thread(target=time.sleep, args=(1,), name='keeper').start()\n")
    result = run_to_the_end(script)
    assert result.returncode == KEPT_ALIVE, result.stdout + result.stderr
    assert "keeper" in result.stderr


def test_check_deploy_is_clean_in_production():
    # A fresh process: the settings of this one are the development ones (.env, DEBUG=True).
    env = {key: value for key, value in os.environ.items() if key not in ENV_KEYS}
    # SES_REGION as ECS sets it: the SES backend must not trip mail.E001 (development-only backend).
    env |= {
        **PRODUCTION_ENV,
        "SECRET_KEY": secrets.token_urlsafe(50),
        "ALLOWED_HOSTS": ".erplora.com",
        "SES_REGION": "eu-west-1",
    }
    result = run_to_the_end(
        BASE_DIR / "manage.py", "check", "--deploy", "--fail-level", "WARNING", cwd=BASE_DIR, env=env
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "System check identified no issues" in result.stdout
