"""«Move to cluster…» and «Cancel the move» on Admin › Hubs: the platform's admins ask hubs to move to another
cluster, now or in the business's night, or take a move back; support never sees either.
"""

import datetime as dt
import re
import uuid

import pytest
from django.utils import timezone

from control import admin as control_admin
from control.models import Hub
from control.tests.conftest import events
from control.tests.test_admin import HUBS, PLATFORM, a_cluster, cluster_cell, nothing_kept, page, root, row_of, support

# Fixtures of test_admin.py, found by pytest under these names: its autouse one and the users the tests log in as.
__all__ = ["nothing_kept", "root", "support"]

pytestmark = pytest.mark.django_db


class TestMoveToCluster:
    """«Move to cluster…»: the platform's admins choose hubs, then an open
    cluster on a confirmation page; each is asked to move through ``control.hub.move`` (the worker moves it, its host
    503 meanwhile). Support never sees it."""

    @pytest.fixture(autouse=True)
    def small(self, monkeypatch):
        from control import queries

        monkeypatch.setattr(queries, "measure", lambda cluster, names: {name: 1024 for name in names})

    @staticmethod
    def a_hub(slug: str, **fields) -> Hub:
        row = {"slug": slug, "status": Hub.Status.READY, "db_name": f"hub_{uuid.uuid7().hex}"}
        return Hub.objects.create(**(row | fields))

    @staticmethod
    def choose(client, *hubs, **more):
        data = {"action": "move_to_cluster", "_selected_action": [str(hub.pk) for hub in hubs]} | more
        return client.post(HUBS, data, HTTP_HOST=PLATFORM, follow=True)

    def test_asks_for_an_open_cluster_first_and_changes_nothing(self, client, root):
        hub = self.a_hub("acme")
        open_one = a_cluster(name="cluster-2", host="writer-2.example")
        a_cluster(name="cluster-closed", host="writer-9.example", is_open=False)

        html = self.choose(client, hub).content.decode()

        assert "Move to cluster" in html and "acme" in html
        assert f'value="{open_one.pk}"' in html and "cluster-closed" not in html
        assert 'name="apply"' in html
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_asks_when_too_with_the_business_s_night_first(self, client, root):
        hub = self.a_hub("acme")
        a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, hub).content.decode()

        # Two choices whose text wraps on a phone, as RDS asks when a change applies: radio buttons, never a select.
        [night] = re.findall(r'<input type="radio" name="when" value="at_night"[^>]*>', html)
        [now] = re.findall(r'<input type="radio" name="when" value="now"[^>]*>', html)
        assert "checked" in night and "checked" not in now
        assert "between 03:00 and 05:00" in html

    def test_confirmed_each_hub_is_asked_to_move_and_it_says_so(self, client, root):
        first, second = self.a_hub("acme"), self.a_hub("bistro")
        target = a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, first, second, apply="yes", cluster=str(target.pk), when="now").content.decode()

        assert "2 hubs will move to cluster-2, one after another: each closed until its own move ends" in html
        for hub in (first, second):
            hub.refresh_from_db()
            assert hub.moving_to_id == target.pk
        assert len(events("control.hub.move_requested")) == 2
        on_cluster = row_of(page(client, HUBS), ">acme<")
        assert "cluster-2" in on_cluster

    def test_a_hub_the_operation_refuses_is_named_and_the_others_move(self, client, root):
        ready, preparing = self.a_hub("acme"), self.a_hub("bistro", status=Hub.Status.REQUESTED)
        target = a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, ready, preparing, apply="yes", cluster=str(target.pk), when="now").content.decode()

        assert "bistro: only a ready hub with a database of its own moves." in html.lower()
        assert "1 hub will move to cluster-2" in html
        preparing.refresh_from_db()
        assert preparing.moving_to_id is None

    def test_asked_for_the_night_each_waits_for_it_open_and_the_list_says_when(self, client, root, monkeypatch):
        monkeypatch.setattr(timezone, "now", lambda: dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.UTC))
        first = self.a_hub("acme", timezone="Europe/Madrid")
        second = self.a_hub("bistro", timezone="America/New_York")
        target = a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, first, second, apply="yes", cluster=str(target.pk), when="at_night").content.decode()

        assert "2 hubs will move to cluster-2 in their next night, each starting between 03:00 and 05:00" in html
        for hub in (first, second):
            hub.refresh_from_db()
            assert (hub.moving_to_id, hub.move_scheduled_to_id) == (None, target.pk)
        listed = page(client, HUBS)
        assert "cluster-2" in cluster_cell(row_of(listed, ">acme<"))
        assert "2026-11-17 03:00 Europe/Madrid" in cluster_cell(row_of(listed, ">acme<"))
        assert "2026-11-17 03:00 America/New_York" in cluster_cell(row_of(listed, ">bistro<"))
        assert len(events("control.hub.move_scheduled")) == 2

    def test_without_a_cluster_chosen_it_asks_again(self, client, root):
        hub = self.a_hub("acme")
        a_cluster(name="cluster-2", host="writer-2.example")

        html = self.choose(client, hub, apply="yes").content.decode()

        assert 'name="apply"' in html and "errorlist" in html
        hub.refresh_from_db()
        assert hub.moving_to_id is None

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        hub = self.a_hub("acme")
        target = a_cluster(name="cluster-2", host="writer-2.example")

        assert "move_to_cluster" not in page(client, HUBS)
        self.choose(client, hub, apply="yes", cluster=str(target.pk))

        hub.refresh_from_db()
        assert hub.moving_to_id is None


class TestCancelTheMove:
    """«Cancel the move»: the worker puts each chosen hub back on its origin (``control.hub.move_cancel``)."""

    def test_asks_the_worker_to_undo_the_chosen_moves_and_says_which_were_not_moving(self, client, root):
        from control.models import MovedCopy

        target = a_cluster(name="cluster-2", host="writer-2.example")
        moving = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)
        still = Hub.objects.create(slug="bistro", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")

        html = client.post(
            HUBS,
            {"action": "cancel_the_move", "_selected_action": [str(moving.pk), str(still.pk)]},
            HTTP_HOST=PLATFORM,
            follow=True,
        ).content.decode().lower()

        assert "1 move will be undone: the hub goes back to its cluster" in html
        assert "bistro: this hub is not moving." in html
        assert Hub.objects.get(pk=moving.pk).move_undo_asked_at is not None
        assert not MovedCopy.objects.exists()

    def test_a_move_asked_for_the_night_is_taken_away_and_the_hub_stays_open_where_it_is(self, client, root):
        target = a_cluster(name="cluster-2", host="writer-2.example")
        tonight = Hub.objects.create(
            slug="acme",
            status=Hub.Status.READY,
            db_name=f"hub_{uuid.uuid7().hex}",
            move_scheduled_to=target,
            move_scheduled_for=timezone.now() + dt.timedelta(hours=10),
        )
        moving = Hub.objects.create(slug="bistro", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)

        html = client.post(
            HUBS,
            {"action": "cancel_the_move", "_selected_action": [str(tonight.pk), str(moving.pk)]},
            HTTP_HOST=PLATFORM,
            follow=True,
        ).content.decode()

        assert "1 move asked for the night was cancelled: the hub stays where it is, open." in html
        assert "1 move will be undone: the hub goes back to its cluster" in html
        tonight.refresh_from_db()
        assert (tonight.move_scheduled_to_id, tonight.move_scheduled_for, tonight.move_undo_asked_at) == (None, None, None)
        assert "cluster-2" not in cluster_cell(row_of(page(client, HUBS), ">acme<"))

    def test_support_neither_sees_it_nor_runs_it(self, client, support):
        target = a_cluster(name="cluster-2", host="writer-2.example")
        moving = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}", moving_to=target)

        assert "cancel_the_move" not in page(client, HUBS)
        client.post(HUBS, {"action": "cancel_the_move", "_selected_action": [str(moving.pk)]}, HTTP_HOST=PLATFORM)

        assert Hub.objects.get(pk=moving.pk).move_undo_asked_at is None


def test_the_move_speaks_spanish():
    from django.utils import translation
    from django.utils.translation import gettext

    with translation.override("es"):
        assert str(control_admin.HubAdmin.move_to_cluster.short_description) == "Mover a otro clúster…"
        assert str(control_admin.HubAdmin.cancel_the_move.short_description) == "Cancelar el traslado"
        assert gettext("Only a ready hub with a database of its own moves.") == (
            "Solo se mueve un hub listo con base de datos propia."
        )


def the_move_page_in_spanish(client) -> str:
    """The confirmation page of «Move to cluster…» for a ready hub, asked by a browser in Spanish."""
    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    a_cluster(name="cluster-2", host="writer-2.example")
    return client.post(
        HUBS,
        {"action": "move_to_cluster", "_selected_action": [str(hub.pk)]},
        HTTP_HOST=PLATFORM,
        HTTP_ACCEPT_LANGUAGE="es",
    ).content.decode()


def test_the_move_at_night_speaks_spanish(client, root):
    from django.utils import translation
    from django.utils.translation import gettext, ngettext

    html = the_move_page_in_spanish(client)

    assert "En su próxima madrugada, entre las 03:00 y las 05:00 de la hora del negocio" in html
    assert re.search(r'value="now"[^>]*>\s*Ahora</label>', html) and "Cuándo" in html
    with translation.override("es"):
        assert gettext("This hub already has a move asked for the night: cancel it first.") == (
            "Este hub ya tiene un traslado programado para la madrugada: cancélalo primero."
        )
        assert ngettext(
            "%(count)d move asked for the night was cancelled: the hub stays where it is, open.",
            "%(count)d moves asked for the night were cancelled: each hub stays where it is, open.",
            2,
        ) % {"count": 2} == "Se han cancelado 2 traslados programados para la madrugada: cada hub se queda donde está, abierto."
        assert str(Hub._meta.get_field("move_scheduled_for").verbose_name) == "traslado programado para"


def test_its_confirmation_page_speaks_spanish(client, root):
    html = the_move_page_in_spanish(client)

    assert "Cada hub elegido se cierra mientras su base de datos se copia" in html and 'value="Moverlos"' in html


def test_its_confirmation_page_promises_no_refusal_by_size(client, root):
    # A database of any size moves (its copy goes through the dumps bucket): the page never says a large one is refused.
    html = the_move_page_in_spanish(client)

    assert "Cada hub elegido se cierra mientras su base de datos se copia" in html
    assert "demasiado grande" not in html and "too large" not in html
