"""A gateway slower than the cluster's patience with an idle transaction (hub#623; VERIFACTU-F10, F15, F20, F25, F27).

Every call to the gateway waits inside its operation's transaction, whose row locks are what keep two passes from
sending the same chain. The cluster cuts a session idle in a transaction for 30 s (``idle_in_transaction_session_timeout``,
``aws`` ``stacks/prod/aurora.tf``) and the gateway may take 45 s to read: the cut came first, and what the AEAT answered
was lost with the transaction.

Everything here is real but the SaaS's gateway: the sessions, the commits, Postgres's cut and the HTTP call, which goes
to a stand-in on this machine (:class:`SlowGateway`) answering the AEAT's real preproduction answers. The 30 s and 31 s
are scaled down so the suite does not wait them (:data:`CUT`, :data:`DELAY_SECONDS`).

Nothing can reach the AEAT, and that is measured, not deduced: every test here ends in :func:`assert_testing_only`, which
fails if a call named production or if, read with ``lsof`` while the call is in flight, this process held a connection to
anything off this machine.
"""

import datetime as dt
import ipaddress
import json
import os
import shutil
import socket
import subprocess
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from django.db import Error, connection, transaction
from django.utils import timezone

from apps.verifactu import gateway
from apps.verifactu.models import AeatRecord, Record
from apps.verifactu.tests.conftest import FIXTURES, aeat_answer, manual, records_of, run
from base import scheduler
from base.models import TaskSchedule

#: The cluster's cut and a gateway slower than it: production's 30 s and 31 s, scaled down, and no further. The cut also
#: counts the work an operation does between two statements before it calls (building and validating the XML, seconds
#: on a machine under load), which must not be what it cuts.
CUT = "5s"
DELAY_SECONDS = 6
SUBMIT_ANSWER = "rotation_a_2026-09-22.xml"
QUERY_ANSWER = "consulta_preproduccion_2026-08-01.xml"
QUEUE = "verifactu.process_queue"

committed = pytest.mark.usefixtures("committed_factory_data")


def peers_of_this_process() -> list[str]:
    """The far end (``host:port``) of each established TCP connection of this process, as ``lsof`` reads it."""
    listing = subprocess.run(
        [shutil.which("lsof"), "-nP", "-a", "-p", str(os.getpid()), "-iTCP", "-sTCP:ESTABLISHED", "-Fn"],
        capture_output=True,
        text=True,
        timeout=30,
        check=True,
    )
    return [line.split("->", 1)[1] for line in listing.stdout.splitlines() if line.startswith("n") and "->" in line]


def assert_testing_only(calls: list[tuple[str, dict]], measured: list[list[str]], gateway_port: int) -> None:
    """Fails if the destination could be production: a call that named it, or a connection seen leaving this machine.

    ``measured`` must also have seen the call itself: a reading that does not find it proves nothing."""
    assert calls, "No call reached the gateway: nothing was measured."
    assert {payload["environment"] for _, payload in calls} == {"testing"}
    assert len(measured) == len(calls), "A call went unmeasured."
    for peers in measured:
        assert any(peer.rsplit(":", 1)[1] == str(gateway_port) for peer in peers), f"The call is not in {peers}."
        for peer in peers:
            host = peer.rsplit(":", 1)[0].strip("[]")
            assert ipaddress.ip_address(host).is_loopback, f"This process is connected off this machine: {peer}."


class SlowGateway:
    """The SaaS's gateway on this machine, taking :data:`DELAY_SECONDS` to hand back the AEAT's real answers."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.measured: list[list[str]] = []
        #: What it answers instead of the AEAT's real answers, as ``(HTTP status, body)``.
        self.instead: tuple[int, dict] | None = None
        stand_in = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stand_in.calls.append((self.path, payload))
                stand_in.measured.append(peers_of_this_process())
                time.sleep(DELAY_SECONDS)
                status, answer = stand_in.instead or (200, stand_in.answer(self.path, payload))
                body = json.dumps(answer).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @staticmethod
    def answer(path: str, payload: dict) -> dict:
        if path == gateway.PROBE_PATH:
            return {"ready": True, "detail": "Ready."}
        if path == gateway.QUERY_PATH:
            return {"aeat_status": 200, "aeat_body": FIXTURES.joinpath(QUERY_ANSWER).read_text(encoding="utf-8")}
        return {"aeat_status": 200, "aeat_body": aeat_answer(SUBMIT_ANSWER, records_of(payload["envelope"]))}

    @property
    def port(self) -> int:
        return self.server.server_port

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def slow_gateway(settings):
    stand_in = SlowGateway()
    settings.VERIFACTU_GATEWAY_URL = f"http://127.0.0.1:{stand_in.port}"
    settings.INTERNAL_SHARED_SECRET = "test-internal-secret"
    yield stand_in
    stand_in.close()
    assert_testing_only(stand_in.calls, stand_in.measured, stand_in.port)


@contextmanager
def cluster_cut():
    """This session cut as the cluster cuts them, for the block only: a session it cut is gone, with its setting."""
    with connection.cursor() as cursor:
        cursor.execute(f"SET idle_in_transaction_session_timeout = '{CUT}'")
    try:
        yield
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("RESET idle_in_transaction_session_timeout")
        except Error:
            connection.close()


def sealed_ticket() -> Record:
    invoice = manual(series_code="TICKET")
    return Record.objects.get(invoice_id=invoice.id)


def assert_kept_the_aeats_answer(record: Record) -> None:
    record.refresh_from_db()
    assert (record.status, record.csv) == ("accepted", "A-86MZ448LPLEBV7")
    assert record.transmitted_at is not None
    # Nothing was lost: no attempt spent, no wait, and nothing to declare late on a second sending.
    assert (record.attempts, record.wait_reason, record.incident) == (0, "", False)


@committed
def test_a_sending_by_hand_slower_than_the_cut_keeps_the_aeats_answer(slow_gateway):
    record = sealed_ticket()

    with cluster_cut():
        out = run("verifactu.record.transmit", {"record_id": str(record.id)})

    assert (out.sent, out.accepted, out.waiting) == (1, 1, 0)
    assert_kept_the_aeats_answer(record)
    assert [path for path, _ in slow_gateway.calls] == [gateway.SUBMIT_PATH]


@committed
def test_an_aeat_that_never_answers_leaves_the_sending_recorded_as_sent(slow_gateway):
    # The likeliest wait past the cut: the gateway gives up on the AEAT after its own 30 s, and the request had left.
    slow_gateway.instead = (502, {"error": {"code": "aeat_unreachable", "sent": True, "message": "No answer."}})
    record = sealed_ticket()

    with cluster_cut():
        out = run("verifactu.record.transmit", {"record_id": str(record.id)})

    assert (out.sent, out.accepted, out.waiting, out.reason) == (1, 0, 1, "unknown")
    record.refresh_from_db()
    assert (record.status, record.attempts, record.wait_reason) == ("sent", 1, "unknown")
    assert record.transmitted_at is not None


@committed
def test_the_workers_pass_slower_than_the_cut_keeps_the_answer_and_moves_its_clock(slow_gateway, settings, monkeypatch):
    settings.WORKER_SCOPE_SLUG = "a"
    # The session of ``cluster_cut`` lives through the pass: released, it would reach the pool with its setting.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    started = timezone.now()
    scheduler.sync(started, declared=[task for task in scheduler.tasks() if task.app_label == "verifactu"])
    minute = scheduler.next_after("* * * * *", started)
    record = sealed_ticket()

    with cluster_cut():
        assert scheduler.run_due(minute) == [QUEUE]

    assert_kept_the_aeats_answer(record)
    assert [path for path, _ in slow_gateway.calls] == [gateway.SUBMIT_PATH]
    schedule = TaskSchedule.objects.get(app_label="verifactu", name="process_queue")
    assert schedule.last_run == minute
    assert schedule.next_run == minute + dt.timedelta(minutes=1)


@committed
def test_a_question_to_the_aeat_slower_than_the_cut_keeps_its_answer(slow_gateway):
    with cluster_cut():
        out = run("verifactu.aeat.query", {"issuer_nif": "B27593136", "year": 2026, "month": 8})

    assert out.count == 4
    assert AeatRecord.objects.count() == 4


@committed
def test_a_probe_of_the_gateway_slower_than_the_cut_keeps_its_answer(slow_gateway):
    with cluster_cut():
        out = run("verifactu.diagnostic.run")

    assert (out.gateway_ready, out.gateway_detail) == (True, "Ready.")


@committed
def test_the_cut_is_real_for_a_transaction_that_waits_on_nothing_declared():
    # What makes the tests above mean something: the same wait, without the allowance, loses its session.
    with cluster_cut(), pytest.raises(Error), transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            time.sleep(DELAY_SECONDS)
            cursor.execute("SELECT 1")


def test_the_allowance_outlasts_every_wait_of_a_call_and_the_clusters_cut():
    timeout = gateway.TIMEOUT
    assert gateway.LONGEST_WAIT_SECONDS > timeout.connect + timeout.write + timeout.read
    assert gateway.LONGEST_WAIT_SECONDS > 30


GATEWAY_PORT = 8001
HERE = [f"127.0.0.1:{GATEWAY_PORT}", "127.0.0.1:5432"]


def test_the_guard_passes_a_testing_call_seen_going_to_this_machine():
    assert_testing_only([("/submit", {"environment": "testing"})], [HERE], GATEWAY_PORT)


@pytest.mark.parametrize(
    ("calls", "measured"),
    [
        ([("/submit", {"environment": "production"})], [HERE]),
        ([("/submit", {"environment": "testing"})], [[*HERE, "145.86.1.1:443"]]),
        ([("/submit", {"environment": "testing"})], [["127.0.0.1:5432"]]),
        ([("/submit", {"environment": "testing"})], []),
        ([], []),
    ],
    ids=["names-production", "connected-off-this-machine", "call-not-seen", "not-measured", "no-call"],
)
def test_the_guard_fails_when_the_destination_could_be_production(calls, measured):
    with pytest.raises(AssertionError):
        assert_testing_only(calls, measured, GATEWAY_PORT)


def test_lsof_reads_a_connection_this_process_really_holds():
    # The guard's instrument, caught seeing the positive: a listener of this process and the connection to it.
    with socket.create_server(("127.0.0.1", 0)) as listener:
        port = listener.getsockname()[1]
        with socket.create_connection(("127.0.0.1", port)):
            assert f"127.0.0.1:{port}" in peers_of_this_process()
