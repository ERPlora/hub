"""Django admin of the verifactu app, for the platform's staff (hubs.erplora.com, PLAN §17–§18).

Nothing fiscal is typed in the admin: every model is shown whole and read-only, never added, changed nor deleted
(the law keeps what was sealed; the route, the environment and the SaaS's photo move only through their
operations, which hold the guards). The records list shows what the module's records screen showed. Its one
action, «Resend to the AEAT», runs ``verifactu.record.transmit`` for the hub chosen in the admin session.
"""

import pytest
from django.contrib import admin
from django.contrib.admin.utils import flatten_fieldsets
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory
from django.utils import translation

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
from apps.verifactu.tests.conftest import answering, manual, run
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
        (ConfigAdmin, Config),
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


def test_the_record_page_shows_every_field_once(request_of):
    fields = flatten_fieldsets(model_admin(RecordAdmin, Record).get_fieldsets(request_of()))
    assert sorted(fields) == sorted(field.name for field in Record._meta.concrete_fields)


def test_the_only_action_is_resend_to_the_aeat(request_of):
    actions = model_admin(RecordAdmin, Record).get_actions(request_of())
    assert list(actions) == ["resend_to_aeat"]
    with translation.override("es"):
        assert str(actions["resend_to_aeat"].description) == "Reenviar a la AEAT"


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
