"""Invoicing on the Home (PLAN-HUB round 2026-10-21; FIX-INVOICE-SETUP-HOOKS): base's own query brings «Your business
details», the ⛔ of the list, pending while the issuer lacks what every document needs and done once it has it, told
also to whoever may not set it up (``actionable: false``, gh:hub#435: it is what stops their invoice); and «Your
invoice numbering», recommended, to whoever keeps the series only, pending while the business has no series and done
once it has one, created by hand or born with the first document (INVOICE-F14). The issuer saved in hub B re-runs
B's checklist and tells A nothing.

base and invoice run for real: the steps come from InvoiceConfig through base's own query, as the person.
"""

import json

import psycopg
import pytest
from live.context import OperationContext
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.invoice.models import InvoiceSeries
from apps.invoice.tests.conftest import A, B, ISSUER, ctx_for, run
from base.schemas import SetupStatusIn

IDENTITY = "invoice.business_identity"
NUMBERING = "invoice.numbering"
WAIT = 1.0
QUIET = 0.3


def document(ctx) -> dict:
    return get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")


def steps(ctx) -> dict[str, dict]:
    return {item["key"]: item for item in document(ctx)["items"] if item["app"] == "invoice"}


def fields(item: dict, *names: str) -> dict:
    return {name: item[name] for name in names}


def ticket(scope=A):
    """A ticket issued by hand in TICKET: the first document opens the year's series on its own."""
    return run(
        "invoice.invoice.create",
        {
            "series_code": "TICKET",
            "lines": [{"description": "Coffee", "quantity": "1", "unit_price": 150, "tax_rate": "10"}],
        },
        ctx_for(scope=scope),
    )


@pytest.mark.django_db
def test_a_hub_without_an_issuer_has_your_business_details_pending_as_the_wall_and_it_leads_to_the_issuer():
    status = document(ctx_for("hub_owner"))
    item = {item["key"]: item for item in status["items"]}[IDENTITY]
    assert fields(item, "state", "level", "required", "actionable", "route", "order", "icon") == {
        "state": "pending",
        "level": "legal",
        "required": True,
        "actionable": True,
        "route": "/invoice/issuer",
        "order": 40,
        "icon": "ion:storefront-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your business details",
        "Legal name, tax ID and address: without them you cannot issue an invoice.",
    )
    # The red strip of every screen reads this count (PLAN-HUB round 2026-10-21, «Franja bloqueante»).
    assert status["blocking_pending"] == 1


@pytest.mark.django_db
def test_the_issuer_saved_ticks_it_and_the_wall_comes_down():
    run("invoice.issuer.update", ISSUER)
    status = document(ctx_for("hub_owner"))
    assert {item["key"]: item for item in status["items"]}[IDENTITY]["state"] == "done"
    assert status["blocking_pending"] == 0


@pytest.mark.django_db
def test_whoever_may_not_set_up_the_issuer_is_told_about_the_pending_wall_without_the_way_to_set_it_up():
    """gh:hub#435: an employee or a manager is told what stops their invoice, but not offered to set it up; once
    the issuer is there, they are told nothing more about it."""
    for role in ("hub_employee", "hub_manager"):
        ctx = ctx_for(role)
        assert not ctx.has("invoice.manage_issuer")
        assert fields(steps(ctx)[IDENTITY], "state", "level", "actionable") == {
            "state": "pending",
            "level": "legal",
            "actionable": False,
        }, role
    run("invoice.issuer.update", ISSUER)
    for role in ("hub_employee", "hub_manager"):
        assert IDENTITY not in steps(ctx_for(role)), role


@pytest.mark.django_db
def test_whoever_may_not_even_read_the_invoices_is_still_told_about_the_wall():
    # A custom role with the Home and nothing of Invoicing: the wall is a fact about the hub, read as the system.
    outsider = OperationContext(scope=A, actor="tester", permissions=frozenset({"base.view_home"}))
    assert fields(steps(outsider)[IDENTITY], "state", "actionable") == {"state": "pending", "actionable": False}
    assert NUMBERING not in steps(outsider)


@pytest.mark.django_db
def test_a_hub_without_series_has_your_invoice_numbering_pending_and_recommended_and_it_leads_to_the_series():
    item = steps(ctx_for("hub_manager"))[NUMBERING]
    assert fields(item, "state", "level", "required", "actionable", "route", "order", "icon") == {
        "state": "pending",
        "level": "recommended",
        "required": False,
        "actionable": True,
        "route": "/invoice/series",
        "order": 50,
        "icon": "ion:layers-outline",
    }
    assert (item["title"], item["description"]) == (
        "Your invoice numbering",
        "Before your first sale, check the prefix your invoice numbers will carry. If you are coming from another "
        "system, continue its numbering instead of starting again at 1.",
    )


@pytest.mark.django_db
def test_reading_the_step_never_opens_the_years_series():
    # Numbering is never optimistic: the step's query only reads.
    document(ctx_for("hub_owner"))
    assert not InvoiceSeries.objects.exists()


@pytest.mark.django_db
def test_a_series_created_by_hand_ticks_your_invoice_numbering(today):
    run("invoice.series.create", {"code": "FACT", "invoice_type": "F1", "year": today.year, "next_number": 1201})
    assert steps(ctx_for())[NUMBERING]["state"] == "done"


@pytest.mark.django_db
def test_the_first_document_opens_its_series_and_ticks_it():
    run("invoice.issuer.update", ISSUER)
    assert steps(ctx_for())[NUMBERING]["state"] == "pending"
    ticket()
    assert steps(ctx_for())[NUMBERING]["state"] == "done"


@pytest.mark.django_db
def test_last_years_series_keep_it_done_in_a_new_year(today):
    # A new year's series inherit the last one's prefix and format: there is nothing to check again on 1 January.
    run("invoice.series.create", {"code": "TICKET", "invoice_type": "F2", "year": today.year - 1})
    assert steps(ctx_for())[NUMBERING]["state"] == "done"


@pytest.mark.django_db
def test_whoever_may_not_keep_the_series_is_not_told_about_the_numbering():
    employee = ctx_for("hub_employee")
    assert employee.has("invoice.view_invoice") and not employee.has("invoice.manage_series")
    assert NUMBERING not in steps(employee)


@pytest.mark.django_db
def test_a_spanish_request_reads_both_steps_in_spanish(client, make_user):
    """gh:hub#868: the old checklist said a module's step in English although the module carried its Spanish."""
    client.force_login(make_user("boss", host="a", role="hub_owner"))
    setup = client.get("/api/home/setup", HTTP_HOST="a.localhost", HTTP_ACCEPT_LANGUAGE="es")
    assert setup.status_code == 200
    ours = {item["key"]: (item["title"], item["description"]) for item in setup.json()["items"] if item["app"] == "invoice"}
    assert ours == {
        IDENTITY: ("Los datos de tu negocio", "Razón social, NIF y domicilio: sin ellos no puedes emitir una factura."),
        NUMBERING: (
            "Tu numeración de facturas",
            "Antes de tu primera venta, revisa el prefijo con el que saldrán tus números de factura. Si vienes de "
            "otro sistema, continúa su numeración en vez de empezar otra vez por el 1.",
        ),
    }


@pytest.fixture
def listen(db_dsn):
    sessions = []

    def open_session(scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def received(session, timeout=WAIT):
    return [(note.channel, json.loads(note.payload)) for note in session.notifies(timeout=timeout)]


# Transactional: the notice leaves after a real COMMIT.
@pytest.mark.django_db(transaction=True)
def test_the_issuer_saved_in_hub_b_re_runs_the_checklist_of_b_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    run("invoice.issuer.update", ISSUER, ctx_for(scope=B))
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert steps(ctx_for(scope=B))[IDENTITY]["state"] == "done"
    assert received(on_a, timeout=QUIET) == []


@pytest.mark.django_db(transaction=True)
def test_a_series_created_in_hub_b_re_runs_the_checklist_of_b_and_tells_a_nothing(listen, today):
    on_a, on_b = listen(A), listen(B)
    run("invoice.series.create", {"code": "FACT", "invoice_type": "F1", "year": today.year}, ctx_for(scope=B))
    notes = received(on_b)
    events = {event for _, payload in notes for event in payload["events"]}
    assert "base.setup.status" in live_registry.affected(events)
    assert steps(ctx_for(scope=B))[NUMBERING]["state"] == "done"
    assert received(on_a, timeout=QUIET) == []
