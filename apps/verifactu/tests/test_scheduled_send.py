"""The queue's send as the worker runs it (VERIFACTU-F20): the scheduled task ``verifactu.process_queue``
through ``base.scheduler``, every minute, as the system on the worker's scope.

``respx`` stands in for the SaaS's gateway (``/internal/verifactu/submit``) and answers with the AEAT's real
preproduction answer ``rotation_a_2026-09-22.xml``, rewritten only to name the test's invoices: nothing reaches
the AEAT, and nothing it says is invented. The task runs on the worker's clock; the AEAT's waiting time
(``TiempoEsperaEnvio``) is kept on the real one, so a second minute inside the wait sends nothing.
"""

import datetime as dt
import json

import httpx
import pytest
import respx
from django.utils import timezone
from live.context import Scope, system_context

from apps.verifactu import gateway
from apps.verifactu.models import Record, SendControl
from apps.verifactu.tests.conftest import aeat_answer, manual, records_of, run
from base import scheduler

pytestmark = pytest.mark.django_db

URL = "http://saas.internal:8001"
ANSWER = "rotation_a_2026-09-22.xml"
QUEUE = "verifactu.process_queue"


@pytest.fixture
def worker(settings, monkeypatch):
    """The worker's scope and the gateway's address; the scheduler's tasks, as the worker schedules them."""
    settings.WORKER_SCOPE_SLUG = "a"
    settings.VERIFACTU_GATEWAY_URL = URL
    # Inside the test's transaction a released connection could not be opened again.
    monkeypatch.setattr(scheduler, "close_old_connections", lambda: None)
    started = timezone.now()
    # VeriFactu's task alone: the other apps' tasks fall due on minutes of their own.
    scheduler.sync(started, declared=[task for task in scheduler.tasks() if task.app_label == "verifactu"])
    return scheduler.next_after("* * * * *", started)


@pytest.fixture
def aeat():
    """The gateway answers every submission with the AEAT's acceptance of each record it carries."""

    def answer(request: httpx.Request) -> httpx.Response:
        envelope = json.loads(request.content)["envelope"]
        body = aeat_answer(ANSWER, records_of(envelope))
        return httpx.Response(200, json={"aeat_status": 200, "aeat_body": body})

    with respx.mock(assert_all_called=False) as mock:
        yield mock.post(f"{URL}{gateway.SUBMIT_PATH}").mock(side_effect=answer)


def sealed_ticket(price: int = 1000) -> Record:
    invoice = manual(
        [
            {
                "description": "Cut",
                "quantity": "1",
                "unit_price": price,
                "tax_rate": "21",
            }
        ],
        series_code="TICKET",
    )
    return Record.objects.get(
        pk=run("verifactu.record.create", {"invoice_id": str(invoice.id)}).record.id
    )


def test_the_worker_sends_the_queue_on_its_minute_and_takes_the_aeats_acceptance(
    issuer, worker, aeat
):
    record = sealed_ticket()
    assert record.status == "pending"

    assert scheduler.run_due(worker - dt.timedelta(seconds=30)) == []
    assert scheduler.run_due(worker) == [QUEUE]

    assert aeat.call_count == 1
    sent = json.loads(aeat.calls.last.request.content)
    assert (sent["hub"], sent["environment"]) == ("a", "testing")
    record.refresh_from_db()
    assert (record.status, record.csv) == ("accepted", "A-86MZ448LPLEBV7")


def test_a_minute_inside_the_aeats_wait_sends_nothing_and_the_next_batch_waits_for_it(
    issuer, worker, aeat
):
    sealed_ticket()
    scheduler.run_due(worker)
    later = sealed_ticket(2000)

    # The next minute comes, the task runs, and the AEAT's 60 s have not passed: nothing leaves.
    assert scheduler.run_due(worker + dt.timedelta(minutes=1)) == [QUEUE]
    assert aeat.call_count == 1
    later.refresh_from_db()
    assert later.status == "pending"

    # Once the wait is over, the following minute sends it.
    SendControl.objects.update(next_send_at=timezone.now() - dt.timedelta(seconds=1))
    assert scheduler.run_due(worker + dt.timedelta(minutes=2)) == [QUEUE]
    assert aeat.call_count == 2
    later.refresh_from_db()
    assert later.status == "accepted"


def test_on_erploras_own_scope_the_worker_presents_a_business_record_as_its_business(
    issuer, worker, aeat, settings
):
    # hub#454: the worker's scope by default is ERPlora's own hub (``WORKER_SCOPE_SLUG`` = ``PLATFORM_HUB_SLUG``),
    # and while the tables are shared its pass sees the businesses' records. Presented as ``erplora``, the SaaS's
    # gateway refused every ticket (409 ``nif_mismatch``): it must go as the business erplora.com linked.
    settings.PLATFORM_HUB_SLUG = "erplora"
    settings.WORKER_SCOPE_SLUG = settings.PLATFORM_HUB_SLUG
    settings.ERPLORA_ENVIRONMENT = "pre"
    business = "0192f0a3-8c4e-7d21-9b6a-3f5e2d1c0b7a"
    run("verifactu.config.sync", {"version": 1, "hub_id": business}, system_context(Scope("host", "a")))
    record = sealed_ticket()

    assert scheduler.run_due(worker) == [QUEUE]

    assert aeat.call_count == 1
    sent = json.loads(aeat.calls.last.request.content)
    assert (sent["hub"], sent["environment"]) == (business, "testing")
    record.refresh_from_db()
    assert (record.status, record.csv) == ("accepted", "A-86MZ448LPLEBV7")
