"""Django admin of the verifactu app, for the platform's staff (hubs.erplora.com, PLAN §17–§18).

The configuration is edited (its environment only through the operations); the chain heads, the records, the
audit events and the AEAT's photo are read-only, never added nor deleted (the law keeps what was sealed, and
only the operations seal); the send control only lets its AEAT wait be released. «Send now» and «Retry» are
actions that run the operations, with the hub chosen in the admin session.
"""

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.test import RequestFactory

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
from apps.verifactu.tests.conftest import manual, run
from base.admin import ADMIN_HUB_SESSION_KEY

pytestmark = pytest.mark.django_db


@pytest.fixture
def request_of(db):
    def make(hub: str | None = "a"):
        users = get_user_model().objects
        user = users.filter(username="staff").first() or users.create_superuser("staff", password="pw")
        request = RequestFactory().post("/admin/verifactu/record/")
        request.user = user
        request.session = SessionStore()
        if hub:
            request.session[ADMIN_HUB_SESSION_KEY] = hub
        request._messages = FallbackStorage(request)
        return request

    return make


def model_admin(admin_class, model):
    return admin_class(model, admin.site)


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
    assert instance.has_add_permission(request) is False
    assert instance.has_change_permission(request) is False
    assert instance.has_delete_permission(request) is False


@pytest.mark.parametrize(
    ("admin_class", "model"),
    [
        (ChainAdmin, Chain),
        (RecordAdmin, Record),
        (EventAdmin, Event),
        (AeatRecordAdmin, AeatRecord),
    ],
)
def test_what_was_sealed_is_read_only_never_added_nor_deleted(
    admin_class, model, request_of
):
    request = request_of()
    instance = model_admin(admin_class, model)
    assert instance.has_add_permission(request) is False
    assert instance.has_delete_permission(request) is False
    editable = {field.name for field in model._meta.concrete_fields} - set(
        instance.get_readonly_fields(request, object())
    )
    assert editable == set()


def test_the_configuration_is_edited_but_its_environment_only_by_the_operations(
    request_of,
):
    instance = model_admin(ConfigAdmin, Config)
    readonly = set(instance.get_readonly_fields(request_of(), Config()))
    assert {"environment", "production_since", "id", "updated_at"} <= readonly
    assert "route" not in readonly and "multiple_taxpayers" not in readonly


def test_the_send_control_only_releases_the_aeats_wait(request_of):
    instance = model_admin(SendControlAdmin, SendControl)
    editable = {field.name for field in SendControl._meta.concrete_fields} - set(
        instance.get_readonly_fields(request_of(), SendControl())
    )
    assert editable == {"next_send_at"}
    assert instance.has_add_permission(request_of()) is False


def test_send_now_runs_the_operation_for_the_chosen_hub_and_says_why_it_could_not(
    issuer, request_of, settings
):
    settings.VERIFACTU_GATEWAY_URL = ""
    invoice = manual(series_code="TICKET")
    run("verifactu.record.create", {"invoice_id": str(invoice.id)})
    request = request_of()
    model_admin(RecordAdmin, Record).send_now(request, Record.objects.all())
    messages = [str(message) for message in request._messages]
    assert any("gateway" in message for message in messages)
    assert Record.objects.get().status == "pending"


def test_retry_runs_the_operation(issuer, request_of):
    invoice = manual(series_code="TICKET")
    run("verifactu.record.create", {"invoice_id": str(invoice.id)})
    request = request_of()
    model_admin(RecordAdmin, Record).retry(request, Record.objects.all())
    assert any("next pass" in str(message) for message in request._messages)


def test_without_a_chosen_hub_the_actions_do_nothing(issuer, request_of):
    invoice = manual(series_code="TICKET")
    run("verifactu.record.create", {"invoice_id": str(invoice.id)})
    request = request_of(hub=None)
    model_admin(RecordAdmin, Record).retry(request, Record.objects.all())
    assert any("Choose a hub" in str(message) for message in request._messages)
