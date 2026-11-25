"""The databases a move or a restore leaves or makes beside a hub's own."""

import datetime
import uuid

import pytest
from django.db import IntegrityError, connection, transaction

from control.models.hubs import Cluster, Hub

pytestmark = pytest.mark.django_db


def test_a_moved_copy_is_one_per_database_and_server_the_settings_own_included():
    from control.models.copies import MovedCopy

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY)
    old = Cluster.objects.create(name="old", host="writer-old.example")
    name = f"{connection.settings_dict['NAME']}_move_{hub.id.hex}"
    MovedCopy.objects.create(hub=hub, cluster=old, db_name=name, moved_at="2026-10-31T10:00Z")
    MovedCopy.objects.create(hub=hub, cluster=None, db_name=name, moved_at="2026-10-31T11:00Z")

    for cluster in (old, None):
        with pytest.raises(IntegrityError), transaction.atomic():
            MovedCopy.objects.create(hub=hub, cluster=cluster, db_name=name, moved_at="2026-10-31T12:00Z")
    hub.delete()
    assert not MovedCopy.objects.exists()


def test_the_move_is_in_spanish():
    from django.utils import translation

    from control.models.copies import MovedCopy

    with translation.override("es"):
        assert str(Hub._meta.get_field("moving_to").verbose_name) == "moviéndose a"
        assert str(MovedCopy._meta.verbose_name_plural) == "copias tras mover"


def test_a_leftover_of_an_undone_move_is_one_per_database_and_server_and_goes_with_its_hub():
    from control.models.copies import LeftoverDatabase

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    there = Cluster.objects.create(name="there", host="writer-there.example")
    LeftoverDatabase.objects.create(hub=hub, cluster=there, db_name=hub.db_name, noted_at="2026-10-31T10:00Z")
    with pytest.raises(IntegrityError), transaction.atomic():
        LeftoverDatabase.objects.create(hub=hub, cluster=there, db_name=hub.db_name, noted_at="2026-10-31T11:00Z")
    hub.delete()
    assert not LeftoverDatabase.objects.exists()


def test_a_moves_note_keeps_the_origins_schema_record_and_a_hub_says_when_its_move_was_asked_to_be_undone():
    from django.utils import translation

    from control.models.copies import MovedCopy

    hub = Hub.objects.create(slug="acme", status=Hub.Status.READY)
    note = MovedCopy.objects.create(
        hub=hub, db_name=f"hub_move_{hub.id.hex}", schema_state="behind", schema_apps={"base": "0001_initial"}
    )
    note.refresh_from_db()
    hub.refresh_from_db()
    assert (note.moved_at, note.schema_state, note.schema_apps) == (None, "behind", {"base": "0001_initial"})
    assert hub.move_undo_asked_at is None
    with translation.override("es"):
        assert str(Hub._meta.get_field("move_undo_asked_at").verbose_name) == "deshacer el traslado pedido"


def test_a_separate_copy_is_named_by_its_hub_and_its_moment_never_its_long_database_name():
    """What its admin page heads with (and its breadcrumbs): words a phone can wrap, never the 40-odd characters of
    ``<control>_copy_<hex>`` in one piece."""
    from control.models.copies import RestoredCopy

    hub = Hub.objects.create(slug="bistro-aurora", status=Hub.Status.READY, db_name=f"hub_{uuid.uuid7().hex}")
    copy = RestoredCopy.objects.create(
        hub=hub,
        restore_point=datetime.datetime(2026, 11, 9, 15, 30, tzinfo=datetime.timezone(datetime.timedelta(hours=1))),
        db_name=f"hub_copy_{uuid.uuid7().hex}",
        asked_by="root",
    )

    assert str(copy) == "bistro-aurora · 2026-11-09 14:30 UTC"
