"""FIX-HUB-RESERVATION-ASSISTANT-CARD-LEAVES-OUT-ITS-RECORDS: one record of the book by its id or as a person says it — a
reservation, a waitlist entry, a slot, a blocked date —, with the words its screen names it by (``label``), in the
language of whoever asks. The assistant's card names by them what a write of reservation names by its id, never by the
id; the API reads them too. Each is read with the permission of its list, and each is of the business that asks.
"""

import datetime as dt

import pytest
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from live.errors import Conflict, NotFound, PermissionDenied

from base.models import Membership
from base.tenancy import context
from base.tenancy.context import use_hub
from base.tenancy.tests import hubs

from .conftest import (
    THURSDAY,
    TOMORROW,
    ctx_for,
    make_blocked,
    make_entry,
    make_reservation,
    make_slot,
    run,
)

#: Thursday 15 October 2026 at 21:00, as each language writes a day and a time (the card's own CLDR words).
WHEN = {"es": "15 oct 2026 · 21:00", "en": "Oct 15, 2026 · 9:00 PM"}


def in_(language: str):
    return ctx_for(language=language)


# ── reservation.reservation.get ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_reservation_is_named_by_its_guest_its_day_and_its_time_as_its_dialog_says_it(language):
    booked = make_reservation()
    assert run("reservation.reservation.get", {"id": str(booked.id)}, in_(language)).label == f"Ana García · {WHEN[language]}"


@pytest.mark.django_db
def test_a_guest_booked_under_her_phone_is_named_by_it_and_an_erased_one_by_when_alone():
    """A guest who booked herself by WhatsApp without a name goes by her phone; once her data are erased, nothing of
    hers is left to say: the reservation is named by its day and its time."""
    by_phone = make_reservation(guest_name="", guest_phone="+34600111222")
    erased = make_reservation(guest_name="", guest_phone="", time="22:30")
    assert run("reservation.reservation.get", {"id": str(by_phone.id)}, in_("es")).label == f"+34600111222 · {WHEN['es']}"
    assert run("reservation.reservation.get", {"id": str(erased.id)}, in_("es")).label == "15 oct 2026 · 22:30"


# ── reservation.waitlist.get ─────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize("language", ["es", "en"])
def test_a_waitlist_entry_is_read_by_id_or_by_its_guest_and_named_by_them_and_when(language):
    entry = make_entry()
    make_entry(guest_name="Eva Gil", guest_phone="+34600999888", time="13:30")
    by_id = run("reservation.waitlist.get", {"id": str(entry.id)}, in_(language))
    assert (by_id.id, by_id.guest_name, by_id.label) == (entry.id, "Luis Pérez", f"Luis Pérez · {WHEN[language]}")
    assert run("reservation.waitlist.get", {"guest": "luis"}, in_(language)).id == entry.id
    assert run("reservation.waitlist.get", {"guest": "600222333", "day": TOMORROW.isoformat()}).id == entry.id


@pytest.mark.django_db
def test_a_missing_or_deleted_entry_is_not_found_and_a_guest_waiting_twice_must_say_which_day():
    gone = make_entry(is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"guest": "Nadie"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.waitlist.get", ref)
        assert caught.value.code == "reservation.entry_not_found"
    make_entry(guest_name="Ana Ruiz")
    make_entry(TOMORROW + dt.timedelta(days=1), guest_name="Ana Ruiz")
    with pytest.raises(Conflict) as caught:
        run("reservation.waitlist.get", {"guest": "Ana Ruiz"})
    assert caught.value.code == "reservation.entry_ambiguous"


# ── reservation.time_slot.get ────────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "label"),
    [("es", "Jueves · 20:00–23:30"), ("en", "Thursday · 8:00 PM–11:30 PM")],
)
def test_a_slot_is_read_by_id_or_by_its_weekday_and_start_and_named_by_them_and_its_end(language, label):
    slot = make_slot()
    make_slot(THURSDAY, "13:00", "16:00")
    by_id = run("reservation.time_slot.get", {"id": str(slot.id)}, in_(language))
    assert (by_id.id, by_id.max_reservations, by_id.label) == (slot.id, 10, label)
    said = run("reservation.time_slot.get", {"day_of_week": THURSDAY, "start_time": "20:00"}, in_(language))
    assert said.id == slot.id


@pytest.mark.django_db
def test_a_missing_or_removed_slot_is_not_found():
    gone = make_slot(is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"day_of_week": THURSDAY, "start_time": "20:00"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.time_slot.get", ref)
        assert caught.value.code == "reservation.slot_not_found"


# ── reservation.blocked_date.get ─────────────────────────────────────────────────────────────────


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("language", "christmas", "afternoon"),
    [
        ("es", "25 dic 2026", "15 oct 2026 · 13:00–16:00"),
        ("en", "Dec 25, 2026", "Oct 15, 2026 · 1:00 PM–4:00 PM"),
    ],
)
def test_a_blocked_date_is_read_by_id_or_by_its_date_and_named_by_it_and_the_hours_it_blocks(
    language, christmas, afternoon
):
    whole = make_blocked(dt.date(2026, 12, 25), reason="Navidad")
    some = make_blocked(TOMORROW, is_full_day=False, blocked_from=dt.time(13), blocked_until=dt.time(16))
    by_id = run("reservation.blocked_date.get", {"id": str(whole.id)}, in_(language))
    assert (by_id.id, by_id.reason, by_id.label) == (whole.id, "Navidad", christmas)
    assert run("reservation.blocked_date.get", {"date": TOMORROW.isoformat()}, in_(language)).label == afternoon
    assert run("reservation.blocked_date.get", {"id": str(some.id)}).id == some.id


@pytest.mark.django_db
def test_a_missing_or_unblocked_date_is_not_found_and_a_date_blocked_twice_must_be_said_by_its_id():
    gone = make_blocked(dt.date(2026, 12, 24), is_deleted=True)
    for ref in ({"id": str(gone.id)}, {"date": "2026-12-24"}):
        with pytest.raises(NotFound) as caught:
            run("reservation.blocked_date.get", ref)
        assert caught.value.code == "reservation.blocked_date_not_found"
    make_blocked(TOMORROW, is_full_day=False, blocked_from=dt.time(13), blocked_until=dt.time(14))
    make_blocked(TOMORROW, is_full_day=False, blocked_from=dt.time(20), blocked_until=dt.time(21))
    with pytest.raises(Conflict) as caught:
        run("reservation.blocked_date.get", {"date": TOMORROW.isoformat()})
    assert caught.value.code == "reservation.blocked_date_ambiguous"


# ── Who reads them ───────────────────────────────────────────────────────────────────────────────

#: Each read by id, a record of it, and the permission of the list it comes from (the same screen shows it).
READS = [
    pytest.param("reservation.waitlist.get", lambda: make_entry(), "reservation.view_waitlistentry", id="entry"),
    pytest.param("reservation.time_slot.get", lambda: make_slot(), "reservation.view_timeslot", id="slot"),
    pytest.param("reservation.blocked_date.get", lambda: make_blocked(), "reservation.view_blockeddate", id="block"),
]


@pytest.mark.django_db
@pytest.mark.parametrize(("name", "made", "permission"), READS)
def test_each_is_read_with_the_permission_of_its_list_and_only_with_it(name, made, permission):
    record = made()
    assert run(name, {"id": str(record.id)}, ctx_for(permissions={permission})).id == record.id
    with pytest.raises(PermissionDenied):
        run(name, {"id": str(record.id)}, ctx_for(permissions={"reservation.view_reservation"}))


# ── Over HTTP, each of the business that asks ────────────────────────────────────────────────────

#: Each read's route and how a record of it is made.
ROUTES = [
    pytest.param("/reservation/waitlist/detail", lambda: make_entry(), id="entry"),
    pytest.param("/reservation/time_slots/detail", lambda: make_slot(), id="slot"),
    pytest.param("/reservation/blocked_dates/detail", lambda: make_blocked(), id="block"),
    pytest.param("/reservation/reservations/detail", lambda: make_reservation(), id="reservation"),
]


@pytest.fixture
def as_in_production(monkeypatch):
    """Every request opens its own database context, as in production (``base/tenancy/tests/conftest.py``)."""
    monkeypatch.setattr(context, "_test_fallback", None)
    cache.clear()
    yield
    cache.clear()


def signed_in(client, hub):
    user, _ = get_user_model().objects.get_or_create(username="saas:1", defaults={"first_name": "Olga"})
    Membership.objects.get_or_create(user=user, host=hub.slug, defaults={"role": "hub_admin"})
    client.force_login(user)
    return client


def read(client, hub, path: str, record_id) -> tuple[int, dict]:
    answer = client.get(f"/api{path}", {"id": str(record_id)}, HTTP_HOST=f"{hub.slug}.localhost:8000")
    return answer.status_code, answer.json()


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("path", "made"), ROUTES)
def test_the_api_reads_one_of_this_business_by_its_id_with_its_label(client, hub_a, as_in_production, path, made):
    signed_in(client, hub_a)
    with use_hub(hub_a):
        record = made()
    status, body = read(client, hub_a, path, record.id)
    assert status == 200, body
    assert body["id"] == str(record.id) and body["label"]


@pytest.mark.django_db(databases=hubs.HUB_DATABASES)
@pytest.mark.parametrize(("path", "made"), ROUTES)
def test_another_businesss_record_is_not_there(client, hub_a, hub_b, as_in_production, path, made):
    with use_hub(hub_b):
        theirs = made()
    signed_in(client, hub_a)
    status, body = read(client, hub_a, path, theirs.id)
    assert status == 404 and body["error"]["code"].endswith("_not_found"), body


# ── The lookups a write shares with its read lock the row for the write, never for the read ───────


@pytest.mark.django_db
def test_removing_a_slot_or_unblocking_a_date_locks_its_row_first_and_reading_one_locks_nothing():
    """``delete_slot`` and ``delete_blocked`` find their record through the lookups the reads by id share
    (``find_slot``, ``find_block``), locked (``FOR UPDATE``) as they were before they were shared; a read by id
    locks nothing."""
    slot, block = make_slot(), make_blocked()
    with CaptureQueriesContext(connection) as reading:
        run("reservation.time_slot.get", {"id": str(slot.id)})
        run("reservation.blocked_date.get", {"id": str(block.id)})
    assert not [query["sql"] for query in reading.captured_queries if "FOR UPDATE" in query["sql"]]
    with CaptureQueriesContext(connection) as writing:
        run("reservation.time_slot.delete", {"id": str(slot.id)})
        run("reservation.blocked_date.delete", {"id": str(block.id)})
    locked = [query["sql"] for query in writing.captured_queries if "FOR UPDATE" in query["sql"]]
    assert any('"reservation_timeslot"' in sql for sql in locked), locked
    assert any('"reservation_blockeddate"' in sql for sql in locked), locked
