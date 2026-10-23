"""The registry's operations (plan 2026-10-17, §1.5): what ``/internal/hubs/{id}`` runs, as the platform only.

``base.hub.register`` (``PUT``), ``base.hub.state_apply`` (``PUT …/state``), ``base.hub.cancel`` (``DELETE``),
``base.hub.restore`` (``POST …/restore``) and the query ``base.hub.get`` (``GET``). A sign-up is ready at once
in phase 1 (no database to clone), and the SaaS hears it after the COMMIT (``report_ready``).
"""

import json
import logging
import uuid

import pytest
from django.contrib.auth import get_user_model
from live.context import OperationContext, system_context
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.verifactu.models import Config
from base import registry, signing
from base.models import Hub
from base.queries import hub_get, hubs_by_slugs
from base.schemas import HubCancelIn, HubGetIn, HubRegistryIn, HubRestoreIn, HubsBySlugIn, HubStateIn
from base.services import hub_cancel, hub_register, hub_restore, hub_state_apply, report_ready
from base.tests.conftest import SECRET

pytestmark = pytest.mark.django_db

HUB_ID = uuid.UUID("0199c4b0-0000-7000-8000-000000000001")
OTHER_ID = uuid.UUID("0199c4b0-0000-7000-8000-000000000002")
SYSTEM = system_context(registry.REGISTRY_SCOPE)
REGISTRY = {
    "id": str(HUB_ID),
    "slug": "acme",
    "name": "Acme Bar",
    "country": "ES",
    "timezone": "Europe/Madrid",
    "language": "es",
    "vertical": "restaurant",
}


def register(**changes):
    return hub_register(SYSTEM, HubRegistryIn(**{**REGISTRY, **changes}))


def a_user_context():
    user = get_user_model().objects.create_user(username="ana", password="pw")
    return OperationContext(scope=registry.REGISTRY_SCOPE, actor=user, permissions=frozenset({"*"}))


def events(name):
    return list(OutboxEvent.objects.filter(name=name).values_list("payload", flat=True))


class TestRegister:
    def test_a_new_business_is_registered_ready_at_once(self, django_capture_on_commit_callbacks, fake_saas):
        fake_saas()
        with django_capture_on_commit_callbacks():
            answer = register()
        assert (answer.created, answer.status, answer.is_demo, answer.state_version) == (True, "ready", False, 0)
        assert answer.ready_at is not None and answer.expires_at is None
        hub = Hub.objects.get(pk=HUB_ID)
        assert (hub.slug, hub.name, hub.country, hub.timezone, hub.language, hub.vertical) == (
            "acme",
            "Acme Bar",
            "ES",
            "Europe/Madrid",
            "es",
            "restaurant",
        )
        assert events("base.hub.registered") == [{"id": str(HUB_ID), "slug": "acme", "created": True}]

    def test_the_saas_hears_ready_after_the_commit_signed_v1_and_v2(self, django_capture_on_commit_callbacks, fake_saas):
        fake = fake_saas(body={"id": str(HUB_ID), "status": "active"})
        with django_capture_on_commit_callbacks() as callbacks:
            register()
            assert fake.calls == []  # never inside the transaction
        for callback in callbacks:
            callback()
        [call] = fake.calls
        path = f"/internal/hubs/{HUB_ID}/ready"
        assert call["url"] == f"http://localhost:8001{path}"
        assert json.loads(call["body"]) == {"id": str(HUB_ID)}
        assert call["timeout"] == 5
        headers = call["headers"]
        assert headers["Content-Type"] == "application/json"
        now = int(headers["X-Erplora-Timestamp"])
        assert signing.verify_signed("POST", path, call["body"], headers, secrets=[SECRET], now=now)
        assert "X-Erplora-Signature-V2" in headers and "X-Erplora-Signature" in headers

    def test_registering_again_updates_it_without_another_ready(self, django_capture_on_commit_callbacks, fake_saas):
        fake = fake_saas()
        with django_capture_on_commit_callbacks(execute=True):
            register()
        with django_capture_on_commit_callbacks(execute=True):
            answer = register(name="Acme Café", slug="acme-cafe", vertical=None)
        assert (answer.created, answer.status) == (False, "ready")
        hub = Hub.objects.get(pk=HUB_ID)
        assert (hub.name, hub.slug, hub.vertical) == ("Acme Café", "acme-cafe", "")
        assert len(fake.calls) == 1

    def test_a_hub_that_was_not_ready_becomes_ready_and_the_saas_hears_it(
        self, django_capture_on_commit_callbacks, fake_saas
    ):
        Hub.objects.create(id=HUB_ID, slug="acme", status="failed")
        fake = fake_saas()
        with django_capture_on_commit_callbacks(execute=True):
            answer = register()
        assert (answer.created, answer.status) == (False, "ready")
        assert Hub.objects.get(pk=HUB_ID).ready_at is not None
        assert len(fake.calls) == 1

    @pytest.mark.parametrize("slug", ["demo-abcd1234", "hub", "demo", "Acme", "a b", "xn--bcher-kva"])
    def test_a_slug_no_business_may_take_is_refused(self, slug):
        with pytest.raises(InvalidPayload) as refused:
            register(slug=slug)
        assert (refused.value.status, refused.value.code) == (422, "base.slug_invalid")
        assert not Hub.objects.filter(pk=HUB_ID).exists()

    def test_the_slug_of_another_hub_is_taken(self):
        Hub.objects.create(id=OTHER_ID, slug="acme", status="ready")
        with pytest.raises(Conflict) as refused:
            register()
        assert (refused.value.status, refused.value.code) == (409, "base.slug_taken")
        assert not Hub.objects.filter(pk=HUB_ID).exists()

    def test_renaming_onto_another_hub_s_slug_is_taken(self, django_capture_on_commit_callbacks, fake_saas):
        fake_saas()
        Hub.objects.create(id=OTHER_ID, slug="other", status="ready")
        with django_capture_on_commit_callbacks(execute=True):
            register()
        with pytest.raises(Conflict) as refused:
            register(slug="other")
        assert refused.value.code == "base.slug_taken"
        assert Hub.objects.get(pk=HUB_ID).slug == "acme"

    def test_a_cancelled_hub_must_be_restored_first(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="cancelled")
        with pytest.raises(Conflict) as refused:
            register(name="New name")
        assert (refused.value.status, refused.value.code) == (409, "base.hub_cancelled")
        assert Hub.objects.get(pk=HUB_ID).name == ""

    @pytest.mark.parametrize("status", ["purged", "expired"])
    def test_a_purged_hub_is_never_registered_again(self, status):
        Hub.objects.create(id=HUB_ID, slug="acme", status=status)
        with pytest.raises(Conflict) as refused:
            register()
        assert refused.value.code == "hub_purged"

    def test_only_the_platform_registers(self):
        with pytest.raises(PermissionDenied) as refused:
            hub_register(a_user_context(), HubRegistryIn(**REGISTRY))
        assert (refused.value.status, refused.value.code) == (403, "base.internal_only")


class TestReportReady:
    def test_a_saas_that_is_away_is_logged_and_never_raises(self, fake_saas, caplog):
        fake_saas(raises=OSError("connection refused"))
        with caplog.at_level(logging.WARNING, logger="base.services"):
            report_ready(HUB_ID)
        assert f"hub={HUB_ID}" in caplog.text and "connection refused" in caplog.text

    def test_a_refusal_of_the_saas_is_logged(self, fake_saas, caplog):
        fake_saas(status=409, body={"error": {"code": "hubs.not_preparing", "message": "Already active."}})
        with caplog.at_level(logging.WARNING, logger="base.services"):
            report_ready(HUB_ID)
        assert "409" in caplog.text

    def test_a_heard_ready_is_logged_as_info(self, fake_saas, caplog):
        fake_saas(body={"id": str(HUB_ID), "status": "active"})
        with caplog.at_level(logging.INFO, logger="base.services"):
            report_ready(HUB_ID)
        assert "base.hub.ready_reported" in caplog.text


class TestStateApply:
    @pytest.fixture
    def hub(self):
        return Hub.objects.create(id=HUB_ID, slug="acme", status="ready")

    def apply(self, version, **photo):
        body = {"hub_id": str(HUB_ID), "slug": "acme", "version": version, **photo}
        return hub_state_apply(
            SYSTEM,
            HubStateIn(id=HUB_ID, version=version, status=photo.get("status"), verifactu=photo.get("verifactu"), photo=body),
        )

    def test_a_newer_photo_is_kept_as_it_came(self, hub):
        answer = self.apply(3, plan={"slug": "starter"}, members=[])
        assert (answer.applied, answer.version) == (True, 3)
        hub.refresh_from_db()
        assert hub.state_version == 3
        assert hub.state == {"hub_id": str(HUB_ID), "slug": "acme", "version": 3, "plan": {"slug": "starter"}, "members": []}
        assert events("base.hub.state_applied") == [{"id": str(HUB_ID), "version": 3}]

    @pytest.mark.parametrize("version", [3, 2])
    def test_an_equal_or_older_photo_changes_nothing(self, hub, version):
        self.apply(3, plan={"slug": "starter"})
        answer = self.apply(version, plan={"slug": "free"})
        assert (answer.applied, answer.version) == (False, 3)
        hub.refresh_from_db()
        assert hub.state["plan"] == {"slug": "starter"}

    def test_the_verifactu_block_and_the_status_reach_verifactu_on_the_hub_s_slug(self, hub):
        self.apply(4, status="active", verifactu={"representation": {"status": "approved"}})
        config = Config.objects.get()
        assert (config.representation_status, config.hub_status, config.synced_version, str(config.hub_id)) == (
            "approved",
            "active",
            4,
            str(HUB_ID),
        )

    def test_a_photo_without_block_or_status_leaves_verifactu_alone(self, hub):
        self.apply(1, plan=None)
        assert not Config.objects.exists()

    def test_a_verifactu_block_out_of_contract_keeps_nothing(self, hub):
        with pytest.raises(InvalidPayload) as refused:
            self.apply(2, verifactu={"representation": {"status": "maybe"}})
        assert (refused.value.status, refused.value.code) == (422, "internal.payload_invalid")

    def test_an_unknown_hub_is_not_found(self):
        with pytest.raises(NotFound):
            self.apply(1)

    def test_only_the_platform_applies_a_photo(self, hub):
        with pytest.raises(PermissionDenied) as refused:
            hub_state_apply(a_user_context(), HubStateIn(id=HUB_ID, version=1, photo={}))
        assert refused.value.code == "base.internal_only"


class TestCancelAndRestore:
    def test_cancelling_ends_the_hub_and_is_idempotent(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        answer = hub_cancel(SYSTEM, HubCancelIn(id=HUB_ID))
        assert answer.status == "cancelled"
        hub = Hub.objects.get(pk=HUB_ID)
        assert hub.cancelled_at is not None
        again = hub_cancel(SYSTEM, HubCancelIn(id=HUB_ID))
        assert again.status == "cancelled"
        assert Hub.objects.get(pk=HUB_ID).cancelled_at == hub.cancelled_at
        assert len(events("base.hub.cancelled")) == 1

    def test_restoring_brings_a_cancelled_hub_back(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        hub_cancel(SYSTEM, HubCancelIn(id=HUB_ID))
        answer = hub_restore(SYSTEM, HubRestoreIn(id=HUB_ID))
        assert answer.status == "ready"
        hub = Hub.objects.get(pk=HUB_ID)
        assert (hub.status, hub.cancelled_at) == ("ready", None)
        assert events("base.hub.restored") == [{"id": str(HUB_ID)}]

    def test_restoring_a_hub_that_never_ended_changes_nothing(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        assert hub_restore(SYSTEM, HubRestoreIn(id=HUB_ID)).status == "ready"
        assert events("base.hub.restored") == []

    @pytest.mark.parametrize(("operation", "schema"), [(hub_cancel, HubCancelIn), (hub_restore, HubRestoreIn)])
    def test_an_unknown_hub_is_not_found(self, operation, schema):
        with pytest.raises(NotFound):
            operation(SYSTEM, schema(id=HUB_ID))

    @pytest.mark.parametrize(("operation", "schema"), [(hub_cancel, HubCancelIn), (hub_restore, HubRestoreIn)])
    @pytest.mark.parametrize("status", ["purged", "expired"])
    def test_a_purged_hub_is_gone_for_good(self, operation, schema, status):
        Hub.objects.create(id=HUB_ID, slug="acme", status=status)
        with pytest.raises(Conflict) as refused:
            operation(SYSTEM, schema(id=HUB_ID))
        assert (refused.value.status, refused.value.code) == (409, "hub_purged")

    @pytest.mark.parametrize(("operation", "schema"), [(hub_cancel, HubCancelIn), (hub_restore, HubRestoreIn)])
    def test_only_the_platform_cancels_or_restores(self, operation, schema):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        with pytest.raises(PermissionDenied) as refused:
            operation(a_user_context(), schema(id=HUB_ID))
        assert refused.value.code == "base.internal_only"


class TestGet:
    def test_the_registry_s_row(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready", state_version=7)
        answer = hub_get(SYSTEM, HubGetIn(id=HUB_ID))
        assert (answer.id, answer.slug, answer.status, answer.state_version) == (HUB_ID, "acme", "ready", 7)

    def test_an_unknown_hub_is_not_found(self):
        with pytest.raises(NotFound):
            hub_get(SYSTEM, HubGetIn(id=HUB_ID))

    def test_only_the_platform_reads_the_registry(self):
        Hub.objects.create(id=HUB_ID, slug="acme", status="ready")
        with pytest.raises(PermissionDenied) as refused:
            hub_get(a_user_context(), HubGetIn(id=HUB_ID))
        assert refused.value.code == "base.internal_only"


class TestBySlugs:
    def test_the_status_of_each_slug_in_its_order(self):
        Hub.objects.create(slug="acme", status="cancelled")
        answer = hubs_by_slugs(SYSTEM, HubsBySlugIn(slugs=["acme", "nobody", "a"]))
        assert [(hub.slug, hub.status) for hub in answer.hubs] == [("acme", "cancelled"), ("nobody", None), ("a", "ready")]

    def test_only_the_platform_reads_it(self):
        with pytest.raises(PermissionDenied):
            hubs_by_slugs(a_user_context(), HubsBySlugIn(slugs=["a"]))
