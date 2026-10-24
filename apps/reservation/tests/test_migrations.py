"""Migration 0002 of the reservation app: the phones kept as typed are written as Customers keeps them.

Before it, a reservation or a waitlist entry whose card was chosen kept the phone as typed («600 111 222»), so the
inbox, which looks for exactly the international number, told nobody (RESERVATION-F19). The migration reads every
kept phone with Customers' rules in the business's country (Spain in phase 1) and writes it in E.164; what is not a
valid number of its country (a short number, letters, an extension) stays as it is, never guessed. Backwards it
changes nothing: the typed form is not known any more, and E.164 is what every reader already accepts.

The functions of the ``RunPython`` are called the way the migration runs them, with the app registry and a schema
editor whose connection is the test database.
"""

from importlib import import_module

import pytest
from django.apps import apps as global_apps
from django.db import connection

from apps.reservation.models import Reservation, WaitlistEntry

from .conftest import make_entry, make_reservation

pytestmark = pytest.mark.django_db

MIGRATION = import_module("apps.reservation.migrations.0002_guest_phone_e164")


class _SchemaEditor:
    connection = connection


KEPT = {
    "600 111 222": "+34600111222",
    "600111222": "+34600111222",
    "+34 600-11-12-22": "+34600111222",
    "(91) 123 45 67": "+34911234567",
    "+44 7911 123456": "+447911123456",
    "+44 7700 900123": "+44 7700 900123",
    "+33600111222": "+33600111222",
    "": "",
    "600111": "600111",
    "600111222 ext 2": "600111222 ext 2",
    "call her": "call her",
    "600+111222": "600+111222",
    "600111222 / 611222333": "600111222 / 611222333",
}


def test_the_phones_of_reservations_and_waitlist_entries_are_written_as_customers_keeps_them():
    reservations = {typed: make_reservation(guest_phone=typed) for typed in KEPT}
    entries = {typed: make_entry(guest_phone=typed) for typed in KEPT}
    MIGRATION.forwards(global_apps, _SchemaEditor())
    assert {typed: Reservation.objects.get(pk=row.pk).guest_phone for typed, row in reservations.items()} == KEPT
    assert {typed: WaitlistEntry.objects.get(pk=row.pk).guest_phone for typed, row in entries.items()} == KEPT


def test_it_touches_only_the_phone():
    row = make_reservation(guest_phone="600 111 222", notes="Window")
    stamp = Reservation.objects.get(pk=row.pk).updated_at
    MIGRATION.forwards(global_apps, _SchemaEditor())
    row.refresh_from_db()
    assert (row.guest_phone, row.notes, row.updated_at) == ("+34600111222", "Window", stamp)


def test_backwards_changes_nothing():
    row = make_reservation(guest_phone="+34600111222")
    MIGRATION.backwards(global_apps, _SchemaEditor())
    assert Reservation.objects.get(pk=row.pk).guest_phone == "+34600111222"
