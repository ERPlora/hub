"""VeriFactu on the Home (PLAN-HUB round 2026-10-21; FIX-VERIFACTU-SETUP-HOOKS): base's own queries bring VeriFactu's
step of «Finish setting up your business» to whoever configures it (pending until the way to production is ready,
done with the authorisation approved by the account's photo) and its four panels to whoever reads its records, each
answered by its own query as that person; the photo received in hub B re-runs B's checklist and tells A nothing.

base and verifactu run for real: the step and the panels come from VerifactuConfig through base's own queries.
"""

import datetime as dt
import json

import psycopg
import pytest
from django.utils import timezone
from live.context import system_context
from live.live_registry import live_registry
from live.operations import get
from live.outbox import channel_for

from apps.verifactu import certificates
from apps.verifactu.models import OwnCertificate
from apps.verifactu.tests.conftest import A, B, b64, ctx_for, make_p12, manual, run
from base.schemas import SetupStatusIn, WidgetListIn

STEP = "verifactu.sending_route"
PANELS = ["verifactu.pending", "verifactu.contingency", "verifactu.by_status", "verifactu.events"]
WAIT = 1.0
QUIET = 0.3


@pytest.fixture(autouse=True)
def storage(settings):
    """The key that keeps the own certificates, as on a server set up."""
    settings.FISCAL_CERTIFICATE_KEY = certificates.generate_key()


def steps(ctx) -> dict[str, dict]:
    document = get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")
    return {item["key"]: item for item in document["items"] if item["app"] == "verifactu"}


def panels(ctx) -> dict[str, dict]:
    widgets = get("base.widget.list")(ctx, WidgetListIn()).model_dump(mode="json")["widgets"]
    return {widget["key"]: widget for widget in widgets if widget["app"] == "verifactu"}


def answer(panel: dict, ctx) -> dict:
    """What a declarative panel reads: its operation with its params, as the person (what the SPA's useLive asks)."""
    op = get(panel["operation"])
    return op(ctx, op.input.model_validate(panel["params"])).model_dump(mode="json")


def photo(version: int, status: str, scope=A) -> None:
    """The account's photo with the signed authorisation's state, as the SaaS pushes it."""
    run(
        "verifactu.config.sync",
        {"version": version, "representation": {"status": status}},
        system_context(scope),
    )


def ticket():
    return manual(
        [{"description": "Cut", "quantity": "1", "unit_price": 1000, "tax_rate": "21"}],
        series_code="TICKET",
    )


@pytest.mark.django_db
def test_the_owner_has_the_step_pending_until_erplora_may_file_in_production(issuer):
    owner = ctx_for("hub_owner")
    step = steps(owner)[STEP]
    assert {key: step[key] for key in ("state", "level", "required", "actionable", "route", "icon")} == {
        "state": "pending",
        "level": "functional",
        "required": True,
        "actionable": True,
        "route": "/verifactu/config",
        "icon": "lucide:shield-check",
    }
    assert step["title"] == "Set up VeriFactu"
    # Under review is not ready yet: only the approval opens ERPlora's way to production.
    photo(1, "submitted")
    assert steps(owner)[STEP]["state"] == "pending"
    photo(2, "approved")
    assert steps(owner)[STEP]["state"] == "done"
    photo(3, "revoked")
    assert steps(owner)[STEP]["state"] == "pending"


@pytest.mark.django_db
def test_the_own_certificate_also_completes_the_step(issuer):
    owner = ctx_for("hub_admin")
    run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"})
    # Uploaded but not chosen: ERPlora still files, and its way still waits for the authorisation.
    assert steps(owner)[STEP]["state"] == "pending"
    run("verifactu.config.update", {"route": "own"})
    assert steps(owner)[STEP]["state"] == "done"
    run("verifactu.certificate.remove")
    assert steps(owner)[STEP]["state"] == "pending"


@pytest.mark.django_db
def test_the_step_is_in_spanish_for_a_spanish_reader(issuer):
    step = steps(ctx_for("hub_owner", language="es"))[STEP]
    assert (step["title"], step["description"]) == (
        "Configura VeriFactu",
        "Firma la autorización para que ERPlora envíe tus facturas a la AEAT, o sube el certificado del negocio.",
    )


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["hub_manager", "hub_employee"])
def test_whoever_cannot_configure_verifactu_is_not_told_about_the_step(issuer, role):
    # In testing a functional step goes to whoever can do it; the legal level, which reaches everybody, is base's
    # (LEGAL_IN_PRODUCTION) and only where the hub files in production.
    assert STEP not in steps(ctx_for(role))


# ── In production the way to the AEAT is a wall (PLAN-HUB round 2026-10-21) ───────────────────────────────────────


@pytest.fixture
def opened(settings):
    """The prod deployment opened by ERPlora, with its gateway."""
    settings.ERPLORA_ENVIRONMENT = "prod"
    settings.VERIFACTU_PRODUCTION_ENABLED = True
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"
    return settings


def status(ctx) -> dict:
    return get("base.setup.status")(ctx, SetupStatusIn()).model_dump(mode="json")


def wall(ctx) -> tuple:
    """How the person of ``ctx`` is told about the step, and how many walls the strip counts."""
    document = status(ctx)
    step = {item["key"]: item for item in document["items"]}.get(STEP)
    told = (step["level"], step["state"], step["actionable"]) if step else None
    return told, document["blocking_pending"]


def live_by_erplora():
    photo(1, "approved")
    run("verifactu.config.go_live")


def live_by_own_certificate():
    run("verifactu.certificate.upload", {"p12_base64": b64(make_p12()), "password": "secret"})
    run("verifactu.config.update", {"route": "own"})
    run("verifactu.config.go_live")


@pytest.mark.django_db
def test_in_production_with_the_way_ready_the_step_is_done_and_off_the_strip(issuer, opened):
    live_by_erplora()

    assert wall(ctx_for("hub_owner")) == (("legal", "done", True), 0)
    assert wall(ctx_for("hub_employee")) == (None, 0)
    assert run("verifactu.config.get").issue_blocker is None


@pytest.mark.django_db
def test_in_production_a_revoked_authorisation_is_a_wall_for_everybody(issuer, opened):
    """Its sales are refused from now on: the Home says so to the owner, and to the person at the till."""
    live_by_erplora()
    photo(2, "revoked")

    assert run("verifactu.config.get").issue_blocker.code == "representation_not_approved"
    assert wall(ctx_for("hub_owner")) == (("legal", "pending", True), 1)
    for role in ("hub_manager", "hub_employee"):
        assert wall(ctx_for(role)) == (("legal", "pending", False), 1)


@pytest.mark.django_db
def test_in_production_an_expired_or_removed_own_certificate_is_a_wall(issuer, opened):
    live_by_own_certificate()
    assert wall(ctx_for("hub_owner")) == (("legal", "done", True), 0)

    OwnCertificate.objects.update(expires_at=timezone.now() - dt.timedelta(minutes=1))
    assert run("verifactu.config.get").issue_blocker.code == "own_certificate_missing"
    assert wall(ctx_for("hub_owner")) == (("legal", "pending", True), 1)
    assert wall(ctx_for("hub_employee")) == (("legal", "pending", False), 1)

    run("verifactu.certificate.remove")
    assert wall(ctx_for("hub_owner")) == (("legal", "pending", True), 1)


@pytest.mark.django_db
def test_in_testing_a_revoked_authorisation_stops_nothing(issuer):
    """gh:hub#1726: a hub in testing sells without a way, so the step stays functional and off the strip."""
    photo(1, "approved")
    photo(2, "revoked")

    assert run("verifactu.config.get").issue_blocker is None
    assert wall(ctx_for("hub_owner")) == (("functional", "pending", True), 0)
    assert wall(ctx_for("hub_employee")) == (None, 0)


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["hub_owner", "hub_manager", "hub_employee"])
def test_whoever_reads_the_records_is_offered_the_four_panels(role):
    offered = panels(ctx_for(role))
    assert list(offered) == PANELS
    assert {key: (panel["kind"], panel["component"], panel["default"]) for key, panel in offered.items()} == {
        "verifactu.pending": ("kpi", None, True),
        "verifactu.contingency": ("stat", None, False),
        "verifactu.by_status": ("bar-list", None, False),
        "verifactu.events": (None, "RecentEventsPanel", False),
    }
    # The declarative ones are followed live; the picker groups them under the app's own name.
    assert all(offered[key]["live"] for key in PANELS[:3])
    assert {panel["category"] for panel in offered.values()} == {"VeriFactu"}


@pytest.mark.django_db
@pytest.mark.parametrize(("language", "label"), [("en", "In contingency queue"), ("es", "En cola de contingencia")])
def test_the_queue_panel_says_under_its_figure_what_it_counts(language, label):
    # The old module's text under the queue's figure (its module.json, `verifactu.contingency` options.label), in the
    # reader's language (FIX-HUB-HOME-WIDGET-OPTIONS-LAZY-TEXT).
    queue = panels(ctx_for("hub_employee", language=language))["verifactu.contingency"]
    assert queue["options"] == {"format": "number", "label": label}


@pytest.mark.django_db
def test_each_panel_paints_its_figure_from_its_own_query(issuer):
    for _ in range(2):
        ticket()
    employee = ctx_for("hub_employee")
    offered = panels(employee)

    pending = offered["verifactu.pending"]
    assert answer(pending, employee)[pending["map"]["value"]] == 2

    queue = offered["verifactu.contingency"]
    summary = answer(queue, employee)
    assert summary[queue["map"]["value"]] == 2
    assert summary[queue["map"]["severity"]] == "warning"

    by_status = offered["verifactu.by_status"]
    rows = answer(by_status, employee)["rows"]
    bars = {row[by_status["map"]["label"]]: row[by_status["map"]["value"]] for row in rows}
    assert bars["Pending"] == 2 and sum(bars.values()) == 2


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


@pytest.mark.django_db(transaction=True)
def test_the_photo_received_in_hub_b_re_runs_bs_checklist_and_tells_a_nothing(listen):
    on_a, on_b = listen(A), listen(B)
    photo(1, "approved", scope=B)
    notes = received(on_b)
    assert {channel for channel, _ in notes} == {channel_for(B)}
    events = {event for _, payload in notes for event in payload["events"]}
    assert {"base.setup.status", "verifactu.config.get"} <= live_registry.affected(events)
    assert received(on_a, timeout=QUIET) == []
