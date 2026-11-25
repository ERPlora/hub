"""Admin › Freeze: the switch that holds the worker's work on the databases while their server is upgraded."""

import datetime as dt

import pytest
from django.contrib import admin
from django.contrib.admin.models import CHANGE, LogEntry
from django.utils import timezone

from control import admin_freeze
from control.models.freeze import Freeze
from control.models.hubs import Hub, HubDue
from control.tests.conftest import events
from control.tests.test_admin import PLATFORM, nothing_kept, page, root, row_of, support

# Fixtures of test_admin.py, found by pytest under these names: its autouse one and the users the tests log in as.
__all__ = ["nothing_kept", "root", "support"]

pytestmark = pytest.mark.django_db
FREEZE = "/admin/control/freeze/"


def the_switch() -> Freeze:
    """The switch's row, control's migration's (a test that flushed the tables before may have taken it away)."""
    row, _ = Freeze.objects.get_or_create()
    return row


def freeze_form(**fields) -> dict:
    values = {"frozen": "on", "reason": "Aurora upgrade"} | fields
    return {key: value for key, value in values.items() if value is not None} | {"_save": "Save"}


def held_by_the_worker(slug: str) -> None:
    """A hub the worker is working on now: its ``hub_due`` lease held."""
    now = timezone.now()
    hub = Hub.objects.create(slug=slug, status=Hub.Status.CREATING)
    HubDue.objects.create(hub=hub, due_at=now, lease_until=now + dt.timedelta(seconds=60), lease_owner="w1")


class TestFreeze:
    """Admin › Freeze: one row, its every write ``control.freeze.set``; the page says how many hubs the worker is still
    working on while frozen, the number the staff waits to see at 0 before the upgrade."""

    def test_is_registered(self):
        assert isinstance(admin.site._registry[Freeze], admin_freeze.FreezeAdmin)

    def test_lists_the_one_switch_not_frozen_and_offers_no_second(self, client, root):
        switch = the_switch()

        html = page(client, FREEZE)

        row = row_of(html, "field-frozen")
        assert "icon-no" in row and f'{switch.pk}/change/">not frozen</a>' in row
        assert f"{FREEZE}add/" not in html
        assert "the worker" not in html

    def test_a_platform_admin_freezes_it_through_its_operation(self, client, root):
        switch = the_switch()

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        row = Freeze.objects.get()
        assert (row.frozen, row.reason, row.by) == (True, "Aurora upgrade", "root")
        assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]
        assert LogEntry.objects.filter(object_id=str(row.pk), action_flag=CHANGE).exists()

    def test_frozen_its_page_says_how_many_hubs_the_worker_is_still_working_on(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)
        held_by_the_worker("acme")
        held_by_the_worker("other")

        html = page(client, FREEZE)

        assert "icon-yes" in row_of(html, "Aurora upgrade")
        assert "the worker is still working on 2 hubs" in html

    def test_frozen_with_nothing_running_its_page_says_the_upgrade_may_start(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        html = page(client, f"{FREEZE}{switch.pk}/change/")

        assert "the worker is working on no hub: the database may be upgraded" in html

    def test_unticking_it_lifts_the_freeze(self, client, root):
        switch = the_switch()
        client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM)

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(frozen=None, reason=""), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        assert Freeze.objects.get().frozen is False
        assert len(events("control.freeze.lifted")) == 1

    def test_what_its_operation_refuses_is_shown_on_its_field(self, client, root):
        switch = the_switch()

        response = client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(reason="x" * 501), HTTP_HOST=PLATFORM)

        assert response.status_code == 200 and "errorlist" in response.content.decode()
        assert Freeze.objects.get().frozen is False

    def test_without_its_row_a_platform_admin_adds_it_through_the_operation(self, client, root):
        Freeze.objects.all().delete()
        assert f"{FREEZE}add/" in page(client, FREEZE)

        response = client.post(f"{FREEZE}add/", freeze_form(), HTTP_HOST=PLATFORM)

        assert response.status_code == 302
        assert Freeze.objects.get().frozen is True
        assert events("control.freeze.started") == [{"reason": "Aurora upgrade"}]

    def test_it_is_never_deleted(self, client, root):
        switch = the_switch()

        assert client.post(f"{FREEZE}{switch.pk}/delete/", {"post": "yes"}, HTTP_HOST=PLATFORM).status_code == 403
        assert Freeze.objects.filter(pk=switch.pk).exists()

    def test_support_reads_it_and_changes_nothing(self, client, support):
        switch = the_switch()

        assert "icon-no" in row_of(page(client, FREEZE), "field-frozen")
        assert client.post(f"{FREEZE}{switch.pk}/change/", freeze_form(), HTTP_HOST=PLATFORM).status_code == 403
        assert Freeze.objects.get().frozen is False


def test_the_freeze_speaks_spanish():
    from django.utils import translation
    from django.utils.translation import gettext, ngettext

    with translation.override("es"):
        assert str(Freeze._meta.verbose_name) == "congelación"
        assert str(Freeze._meta.get_field("frozen").verbose_name) == "congelado"
        assert str(Freeze(frozen=False)) == "sin congelar"
        assert str(admin_freeze.FreezeAdmin.state.short_description) == "estado"
        assert ngettext(
            "Frozen: the worker is still working on %(count)d hub; wait until it is 0 before the upgrade.",
            "Frozen: the worker is still working on %(count)d hubs; wait until it is 0 before the upgrade.",
            2,
        ) % {"count": 2} == "Congelado: el worker aún trabaja en 2 hubs; espera a que sea 0 antes de la subida."
        assert gettext("Frozen: the worker is working on no hub: the database may be upgraded.") == (
            "Congelado: el worker no trabaja en ningún hub: ya se puede subir la base de datos."
        )
