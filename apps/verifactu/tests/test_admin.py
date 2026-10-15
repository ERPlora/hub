"""Django admin of the verifactu app, for the platform's staff (hubs.erplora.com, PLAN §17–§18), at the service of
support (Ioan, 2026-10-15: «a record not sent is not a record registered»; support fixes a sending problem, it never
deletes a sale).

Nothing fiscal is typed: what was sealed is shown whole and read-only, never added, changed nor deleted, and a record
the AEAT registered stays as it is. What support changes, it changes through the module's operations, for the hub
chosen in the admin session: resend, reschedule, ask the AEAT (a record leaves the queue only when the AEAT holds
it), correct a rejection with a new record, and choose the route (``verifactu.config.update``, whose refusal is the
form's error). The SaaS's photo, the environment and the certificate are never typed here.
"""

import pytest
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from django.utils import timezone, translation

from apps.verifactu.admin import (
    AeatRecordAdmin,
    ChainAdmin,
    ConfigAdmin,
    EventAdmin,
    OwnCertificateAdmin,
    RecordAdmin,
    SendControlAdmin,
)
from apps.verifactu.models import (
    AeatRecord,
    Chain,
    Config,
    Event,
    OwnCertificate,
    Record,
    SendControl,
)
from apps.verifactu import gateway
from apps.verifactu.models import wait_reason_text
from apps.verifactu.tests.conftest import aeat_holds, aeat_answer, answering, manual, records_of, run
from base.admin import ADMIN_HUB_SESSION_KEY

pytestmark = pytest.mark.django_db

PLATFORM = "hubs.localhost:8000"
RECORDS = "/admin/verifactu/record/"


@pytest.fixture
def staff(db):
    users = get_user_model().objects
    return users.filter(username="staff").first() or users.create_superuser("staff", password="pw")


@pytest.fixture
def request_of(staff):
    def make(hub: str | None = "a"):
        request = RequestFactory().post(RECORDS)
        request.user = staff
        request.session = SessionStore()
        if hub:
            request.session[ADMIN_HUB_SESSION_KEY] = hub
        request._messages = FallbackStorage(request)
        return request

    return make


def model_admin(admin_class, model):
    return admin_class(model, admin.site)


def record() -> Record:
    invoice = manual(series_code="TICKET")
    created = run("verifactu.record.create", {"invoice_id": str(invoice.id)})
    return Record.objects.get(pk=created.record.id)


def said(request) -> list[str]:
    return [str(message) for message in request._messages]


def test_every_model_is_registered():
    for model in (Config, Chain, SendControl, Record, Event, AeatRecord, OwnCertificate):
        assert model in admin.site._registry, model


def test_the_own_certificate_shows_its_holder_kind_and_expiry_and_never_its_material(
    request_of,
):
    request = request_of()
    instance = model_admin(OwnCertificateAdmin, OwnCertificate)
    shown = set(instance.get_fields(request)) | set(instance.list_display)
    assert {"holder", "holder_tax_id", "kind", "expires_at"} <= shown
    assert "sealed_blob" not in shown


@pytest.mark.parametrize(
    ("admin_class", "model"),
    [
        (OwnCertificateAdmin, OwnCertificate),
        (ChainAdmin, Chain),
        (SendControlAdmin, SendControl),
        (RecordAdmin, Record),
        (EventAdmin, Event),
        (AeatRecordAdmin, AeatRecord),
    ],
)
def test_nothing_fiscal_is_typed_added_changed_nor_deleted(admin_class, model, request_of):
    # The route, the environment and the SaaS's photo move only through their operations (their guards are the
    # law's: no filing under ERPlora's seal without the approved authorisation); what was sealed never changes.
    request = request_of()
    instance = model_admin(admin_class, model)
    assert instance.has_view_permission(request) is True
    assert instance.has_add_permission(request) is False
    assert instance.has_change_permission(request) is False
    assert instance.has_delete_permission(request) is False


def test_the_records_list_shows_what_the_records_screen_showed(client, staff, issuer):
    instance = model_admin(RecordAdmin, Record)
    assert list(instance.list_display) == [
        "sequence",
        "invoice_number",
        "issue_date",
        "record_type",
        "issuer_nif",
        "total",
        "environment",
        "status",
        "csv",
    ]
    assert {"status", "record_type", "invoice_type", "environment"} <= set(instance.list_filter)
    assert {"invoice_number", "issuer_nif", "csv", "fingerprint"} <= set(instance.search_fields)
    sealed = record()
    client.force_login(staff)
    response = client.get(RECORDS, HTTP_HOST=PLATFORM)
    assert response.status_code == 200
    html = response.content.decode()
    assert sealed.invoice_number in html
    assert "12.10 €" in html


@pytest.mark.parametrize(
    "model", ["config", "owncertificate", "chain", "sendcontrol", "record", "event", "aeatrecord"]
)
def test_every_list_opens(client, staff, issuer, model):
    record()
    client.force_login(staff)
    assert client.get(f"/admin/verifactu/{model}/", HTTP_HOST=PLATFORM).status_code == 200


def test_a_record_opens_read_only_and_is_never_saved(client, staff, issuer):
    sealed = record()
    client.force_login(staff)
    page = f"{RECORDS}{sealed.pk}/change/"
    response = client.get(page, HTTP_HOST=PLATFORM)
    assert response.status_code == 200
    html = response.content.decode()
    assert sealed.fingerprint in html
    assert 'name="_save"' not in html
    assert 'name="xml"' not in html
    refused = client.post(page, {"status": "accepted", "csv": "X"}, HTTP_HOST=PLATFORM)
    assert refused.status_code == 403
    assert Record.objects.get(pk=sealed.pk).status == "pending"


def test_the_record_page_shows_every_field_once_and_why_it_waits(request_of):
    fields = flatten_fieldsets(model_admin(RecordAdmin, Record).get_fieldsets(request_of()))
    assert sorted(fields) == sorted(
        [field.name for field in Record._meta.concrete_fields] + ["why_waiting"]
    )


def test_the_records_actions_are_what_support_needs(request_of):
    actions = model_admin(RecordAdmin, Record).get_actions(request_of())
    assert list(actions) == ["resend_to_aeat", "reschedule", "ask_the_aeat", "correct_rejection"]
    with translation.override("es"):
        assert [str(action.description) for action in actions.values()] == [
            "Reenviar a la AEAT",
            "Reprogramar: enviar en la próxima pasada",
            "Consultar a la AEAT (sale de la cola si ya lo tiene)",
            "Subsanar el rechazo con un registro nuevo",
        ]


def test_resend_sends_the_chain_once_and_says_what_the_aeat_answered(
    issuer, gateway_answers, request_of
):
    gateway_answers.set(answering())
    first, second = record(), record()
    request = request_of()
    model_admin(RecordAdmin, Record).resend_to_aeat(
        request, Record.objects.filter(pk__in=[first.pk, second.pk])
    )
    assert len(gateway_answers.calls) == 1
    assert set(Record.objects.values_list("status", flat=True)) == {"accepted"}
    assert said(request) == ["Resend finished: 2 accepted, 0 rejected, 0 still waiting."]


def test_resend_of_a_record_out_of_the_queue_says_why_and_sends_nothing(
    issuer, gateway_answers, request_of
):
    gateway_answers.set(answering())
    sealed = record()
    run("verifactu.record.transmit", {"record_id": str(sealed.pk)})
    request = request_of()
    model_admin(RecordAdmin, Record).resend_to_aeat(request, Record.objects.filter(pk=sealed.pk))
    assert len(gateway_answers.calls) == 1
    messages = said(request)
    assert len(messages) == 1
    assert messages[0].startswith(f"{sealed.invoice_number}: This record is not in the queue")


def test_resend_without_the_gateway_says_why_and_keeps_it_queued(issuer, request_of, settings):
    settings.VERIFACTU_GATEWAY_URL = ""
    sealed = record()
    request = request_of()
    model_admin(RecordAdmin, Record).resend_to_aeat(request, Record.objects.all())
    assert any("gateway" in message for message in said(request))
    assert Record.objects.get(pk=sealed.pk).status == "pending"


def test_without_a_chosen_hub_the_action_does_nothing(issuer, gateway_answers, request_of):
    gateway_answers.set(answering())
    record()
    request = request_of(hub=None)
    model_admin(RecordAdmin, Record).resend_to_aeat(request, Record.objects.all())
    assert any("Choose a hub" in message for message in said(request))
    assert gateway_answers.calls == []


def test_the_staff_resends_from_the_records_list_of_the_chosen_hub(
    client, staff, issuer, gateway_answers
):
    gateway_answers.set(answering())
    sealed = record()
    client.force_login(staff)
    client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
    response = client.post(
        RECORDS,
        {"action": "resend_to_aeat", "_selected_action": [str(sealed.pk)], "index": "0"},
        HTTP_HOST=PLATFORM,
    )
    assert response.status_code == 302
    assert Record.objects.get(pk=sealed.pk).status == "accepted"
    assert [str(message) for message in get_messages(response.wsgi_request)] == [
        "Resend finished: 1 accepted, 0 rejected, 0 still waiting."
    ]


def test_without_staff_the_records_are_forbidden(client, make_user):
    client.force_login(make_user("ana", host="a", role="hub_owner"))
    assert client.get(RECORDS, HTTP_HOST=PLATFORM).status_code == 403


# Support's actions on what is not registered yet (Ioan, 2026-10-15)


def failed_once(gateway_answers) -> Record:
    """A ticket whose submission could not reach the AEAT: pending, waiting its backoff (5 minutes)."""
    gateway_answers.set(gateway.Reply(kind=gateway.UNREACHABLE, message="connection refused"))
    sealed = record()
    run("verifactu.contingency.process")
    sealed.refresh_from_db()
    assert (sealed.status, sealed.wait_reason) == ("pending", "unreachable")
    assert sealed.next_attempt_at > timezone.now()
    return sealed


def left_without_answer(gateway_answers, count: int = 1) -> list[Record]:
    """``count`` tickets sent together whose submission got no answer: «sent», in the queue."""
    gateway_answers.set(gateway.Reply(kind=gateway.UNKNOWN, message="read timeout"))
    sealed = [record() for _ in range(count)]
    run("verifactu.contingency.process")
    for item in sealed:
        item.refresh_from_db()
        assert item.status == "sent"
    return sealed


def rejected_by_the_aeat(gateway_answers) -> Record:
    """A ticket the AEAT rejected (its real answer, «Incorrecto» 1189)."""

    def reply(payload):
        body = aeat_answer("alta_2007_aceptado_con_errores_2026-08-02.xml", records_of(payload["envelope"]))
        body = body.replace(">AceptadoConErrores<", ">Incorrecto<").replace(">2007<", ">1189<")
        return gateway.Reply(kind=gateway.ANSWERED, aeat_status=200, aeat_body=body)

    gateway_answers.set(reply)
    sealed = record()
    run("verifactu.contingency.process")
    sealed.refresh_from_db()
    assert sealed.status == "rejected"
    return sealed


def accepted(gateway_answers) -> Record:
    gateway_answers.set(answering())
    sealed = record()
    run("verifactu.record.transmit", {"record_id": str(sealed.pk)})
    sealed.refresh_from_db()
    assert sealed.status == "accepted"
    return sealed


def frozen(sealed: Record) -> dict:
    return {
        key: value
        for key, value in Record.objects.values().get(pk=sealed.pk).items()
        if key != "updated_at"
    }


def test_reschedule_puts_the_record_out_with_the_next_pass_and_keeps_why_it_was_late(
    issuer, gateway_answers, request_of
):
    sealed = failed_once(gateway_answers)
    request = request_of()
    model_admin(RecordAdmin, Record).reschedule(request, Record.objects.filter(pk=sealed.pk))
    sealed.refresh_from_db()
    assert sealed.next_attempt_at <= timezone.now()
    # Its reason stays: it is what declares it late (Incidencia S) when it goes; the next pass rewrites it.
    assert (sealed.status, sealed.wait_reason, sealed.attempts) == ("pending", "unreachable", 1)
    assert Event.objects.filter(message_key="queue_retried", record=sealed, actor="staff").exists()
    assert said(request) == ["Rescheduled: 1 record(s) go out with the next pass."]
    with translation.override("es"):
        request = request_of()
        model_admin(RecordAdmin, Record).reschedule(request, Record.objects.filter(pk=sealed.pk))
        assert said(request) == ["Reprogramado: 1 registro(s) salen en la próxima pasada."]


def test_reschedule_leaves_a_registered_record_as_it_is(issuer, gateway_answers, request_of):
    sealed = accepted(gateway_answers)
    before = frozen(sealed)
    request = request_of()
    model_admin(RecordAdmin, Record).reschedule(request, Record.objects.filter(pk=sealed.pk))
    assert frozen(sealed) == before
    messages = said(request)
    assert len(messages) == 1
    assert messages[0].startswith(f"{sealed.invoice_number}: This record is not in the queue")


def test_asking_the_aeat_takes_out_of_the_queue_only_what_it_holds(
    issuer, gateway_answers, request_of
):
    held, missing = left_without_answer(gateway_answers, 2)
    gateway_answers.set(aeat_holds(held))
    request = request_of()
    model_admin(RecordAdmin, Record).ask_the_aeat(
        request, Record.objects.filter(pk__in=[held.pk, missing.pk])
    )
    held.refresh_from_db()
    missing.refresh_from_db()
    assert (held.status, missing.status) == ("accepted", "sent")
    assert said(request) == [
        "Asked the AEAT: 1 already registered (out of the queue), 1 not in the AEAT (still in the queue)."
    ]
    assert Event.objects.get(message_key="record_reconciled").actor == "staff"
    with translation.override("es"):
        request = request_of()
        model_admin(RecordAdmin, Record).ask_the_aeat(request, Record.objects.filter(pk=missing.pk))
        assert said(request) == [
            "Consulta a la AEAT: 0 ya registrados (fuera de la cola), 1 no están en la AEAT (siguen en la cola)."
        ]


def test_asking_the_aeat_about_a_registered_record_asks_nothing(
    issuer, gateway_answers, request_of
):
    sealed = accepted(gateway_answers)
    calls = len(gateway_answers.calls)
    request = request_of()
    model_admin(RecordAdmin, Record).ask_the_aeat(request, Record.objects.filter(pk=sealed.pk))
    assert len(gateway_answers.calls) == calls
    assert said(request)[0].startswith(f"{sealed.invoice_number}: This record is not in the queue")


def test_a_rejection_is_corrected_with_a_new_record_and_the_rejected_one_stays(
    issuer, gateway_answers, request_of
):
    sealed = rejected_by_the_aeat(gateway_answers)
    before = frozen(sealed)
    request = request_of()
    model_admin(RecordAdmin, Record).correct_rejection(request, Record.objects.filter(pk=sealed.pk))
    assert frozen(sealed) == before
    correction = Record.objects.exclude(pk=sealed.pk).get(invoice_id=sealed.invoice_id)
    assert (correction.status, correction.correction) == ("pending", True)
    assert correction.created_by == "staff"
    assert said(request) == ["Corrected: 1 new record(s) in the queue."]


def test_a_registered_record_is_never_corrected_from_the_admin(
    issuer, gateway_answers, request_of
):
    sealed = accepted(gateway_answers)
    request = request_of()
    model_admin(RecordAdmin, Record).correct_rejection(request, Record.objects.filter(pk=sealed.pk))
    assert Record.objects.count() == 1
    assert said(request) == [
        f"{sealed.invoice_number}: only a record the AEAT rejected is corrected here; this one is registered."
    ]


@pytest.mark.parametrize("action", ["reschedule", "ask_the_aeat", "correct_rejection"])
def test_without_a_chosen_hub_no_action_runs(issuer, gateway_answers, request_of, action):
    sealed = failed_once(gateway_answers)
    calls = len(gateway_answers.calls)
    before = frozen(sealed)
    request = request_of(hub=None)
    getattr(model_admin(RecordAdmin, Record), action)(request, Record.objects.all())
    assert frozen(sealed) == before
    assert len(gateway_answers.calls) == calls
    assert any("Choose a hub" in message for message in said(request))


def test_the_staff_asks_the_aeat_from_the_records_list(client, staff, issuer, gateway_answers):
    [sealed] = left_without_answer(gateway_answers)
    gateway_answers.set(aeat_holds(sealed))
    client.force_login(staff)
    client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
    response = client.post(
        RECORDS,
        {"action": "ask_the_aeat", "_selected_action": [str(sealed.pk)], "index": "0"},
        HTTP_HOST=PLATFORM,
    )
    assert response.status_code == 302
    assert Record.objects.get(pk=sealed.pk).status == "accepted"


# The send control of a chain: its queue is rescheduled by the operation, never typed


def test_a_chain_is_rescheduled_from_its_send_control(issuer, gateway_answers, request_of):
    sealed = failed_once(gateway_answers)
    request = request_of()
    model_admin(SendControlAdmin, SendControl).reschedule_chain(request, SendControl.objects.all())
    sealed.refresh_from_db()
    assert sealed.next_attempt_at <= timezone.now()
    assert said(request) == ["Rescheduled: 1 chain(s) go out with the next pass."]


def test_a_chain_with_nothing_waiting_says_so(issuer, gateway_answers, request_of):
    sealed = accepted(gateway_answers)
    request = request_of()
    model_admin(SendControlAdmin, SendControl).reschedule_chain(request, SendControl.objects.all())
    assert said(request) == [f"{sealed.issuer_nif} (testing): nothing is waiting in its queue."]


def test_the_send_controls_only_action_is_reschedule(request_of):
    actions = model_admin(SendControlAdmin, SendControl).get_actions(request_of())
    assert list(actions) == ["reschedule_chain"]
    with translation.override("es"):
        assert (
            str(actions["reschedule_chain"].description)
            == "Reprogramar su cola: enviar en la próxima pasada"
        )


# Filters and the record's page


def test_the_records_are_filtered_by_why_they_wait(client, staff, issuer, gateway_answers):
    waiting = failed_once(gateway_answers)
    fresh = record()
    client.force_login(staff)
    html = client.get(f"{RECORDS}?wait_reason=unreachable", HTTP_HOST=PLATFORM).content.decode()
    assert waiting.invoice_number in html
    assert fresh.invoice_number not in html
    assert "By waiting because" in client.get(RECORDS, HTTP_HOST=PLATFORM).content.decode()
    instance = model_admin(RecordAdmin, Record)
    assert {"status", "environment"} <= set(instance.list_filter)


def test_a_record_page_says_why_it_waits_and_links_its_invoice(
    client, staff, issuer, gateway_answers
):
    sealed = failed_once(gateway_answers)
    client.force_login(staff)
    html = client.get(f"{RECORDS}{sealed.pk}/change/", HTTP_HOST=PLATFORM).content.decode()
    assert wait_reason_text("unreachable", "connection refused") in html
    assert f"/admin/invoice/invoice/{sealed.invoice_id}/change/" in html


# The configuration: only the route, through its operation


@pytest.fixture
def config(issuer):
    run("verifactu.config.update", {"route": "erplora"})
    return Config.objects.get()


def test_the_configuration_is_seen_whole_and_only_its_route_is_chosen(config, request_of):
    request = request_of()
    instance = model_admin(ConfigAdmin, Config)
    assert instance.has_change_permission(request, config) is True
    assert instance.has_add_permission(request) is False
    assert instance.has_delete_permission(request, config) is False
    readonly = set(instance.get_readonly_fields(request, config))
    assert "route" not in readonly
    assert {
        "environment",
        "representation_status",
        "representation_updated_at",
        "representation_reason",
        "live_paid",
        "hub_status",
        "hub_id",
        "synced_version",
        "synced_at",
    } <= readonly


def config_page(config) -> str:
    return f"/admin/verifactu/config/{config.pk}/change/"


def test_the_route_is_chosen_through_its_operation(client, staff, config):
    Config.objects.filter(pk=config.pk).update(route="own")
    client.force_login(staff)
    client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
    response = client.post(
        config_page(config),
        {"route": "erplora", "live_paid": "on", "hub_status": "suspended", "_save": "Save"},
        HTTP_HOST=PLATFORM,
    )
    assert response.status_code == 302
    config.refresh_from_db()
    assert (config.route, config.live_paid, config.hub_status) == ("erplora", False, "active")
    assert config.updated_by == "staff"
    assert Event.objects.filter(message_key="route_erplora", actor="staff").exists()


def test_a_route_the_operation_refuses_is_the_forms_error(client, staff, config):
    client.force_login(staff)
    client.get("/admin/hub/a/", HTTP_HOST=PLATFORM)
    response = client.post(
        config_page(config), {"route": "own", "_save": "Save"}, HTTP_HOST=PLATFORM
    )
    assert response.status_code == 200
    assert "There is no valid certificate loaded" in response.content.decode()
    config.refresh_from_db()
    assert config.route == "erplora"
    assert not Event.objects.filter(message_key="route_own").exists()


def test_without_a_chosen_hub_the_route_is_not_changed(client, staff, config):
    Config.objects.filter(pk=config.pk).update(route="own")
    client.force_login(staff)
    response = client.post(
        config_page(config), {"route": "erplora", "_save": "Save"}, HTTP_HOST=PLATFORM
    )
    assert response.status_code == 200
    assert "Choose a hub first" in response.content.decode()
    config.refresh_from_db()
    assert config.route == "own"
