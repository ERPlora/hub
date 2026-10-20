"""Two bookings of the same professional at once: real sessions in threads, real row locks (WORKBOOK «Para
quien lo mantiene»: solapes con bloqueo).

Whichever comes first wins; the other one waits for the staff record's lock, then sees the first booking
and is refused with the real reason. Two bookings on the same day never share a number, and two runs of
the same series never book a date twice.

A detail (an appointment, a series) that a deletion lands in the middle of answers what it read or 404,
never a 500. The Hub admin's «Delete» of an appointment or a series that a write holds waits for it and takes
what it added (or answers «Cannot delete»); a write that comes second finds it gone.
"""

import datetime as dt
import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from uuid import uuid7

import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection, transaction
from django.test import Client, RequestFactory
from live.context import system_context
from live.errors import OperationError
from live.operations import get

from apps.appointment.models import Appointment, Recurring
from apps.customer.models import Customer
from apps.customer.tests.conftest import cannot_delete, card_deleted_on_screen, reads, writes
from apps.staff.models import Member
from apps.staff.tests.conftest import WAIT_LIMIT, _waited_for, deleted_on_screen

from .conftest import (
    MONDAY,
    A,
    at,
    make_appointment,
    make_customer,
    make_series,
    make_settings,
    run,
    wall,
)

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("anytime"),
]


def at_once(*calls):
    """Runs every ``call`` in its own thread and session, released together; their results or errors."""
    barrier = threading.Barrier(len(calls))
    results: list = [None] * len(calls)

    def worker(index, call):
        try:
            barrier.wait(5)
            results[index] = call()
        except OperationError as error:
            results[index] = error
        except Exception as error:  # an unexpected failure is reported by the test
            results[index] = error
        finally:
            connection.close()

    threads = [
        threading.Thread(target=worker, args=(i, call)) for i, call in enumerate(calls)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(30)
    return results


def codes(results) -> list[str]:
    return sorted(getattr(result, "code", "ok") for result in results)


def booking(salon, start: str, staff=None):
    data = {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str((staff or salon.ana).id),
        "start": wall(MONDAY, start),
    }
    return lambda: run("appointment.appointment.create", data)


def test_two_bookings_of_the_same_time_with_overlaps_off_one_wins(salon):
    make_settings(allow_overlapping=False)
    assert codes(at_once(booking(salon, "10:00"), booking(salon, "10:15"))) == [
        "appointment.slot_taken",
        "ok",
    ]
    assert Appointment.objects.count() == 1


def test_two_bookings_of_the_same_time_at_the_front_desk_the_second_is_asked_to_confirm(
    salon,
):
    results = at_once(booking(salon, "10:00"), booking(salon, "10:00"))
    assert codes(results) == ["appointment.overlap_needs_confirmation", "ok"]


def test_two_professionals_at_the_same_time_both_book_with_their_own_numbers(salon):
    make_settings(allow_overlapping=False)
    results = at_once(booking(salon, "10:00"), booking(salon, "10:00", staff=salon.bea))
    assert codes(results) == ["ok", "ok"]
    assert len({result.number for result in results}) == 2


def test_two_runs_of_the_same_series_never_book_a_date_twice(salon):
    out = run(
        "appointment.recurring.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "frequency": "weekly",
            "start_date": MONDAY.isoformat(),
            "time": "10:00",
            "max_occurrences": 2,
        },
    )
    Appointment.objects.filter(recurring_id=out.recurring.id).delete()
    again = lambda: run(
        "appointment.recurring.materialize", {"id": str(out.recurring.id)}
    )  # noqa: E731
    at_once(again, again)
    dates = list(
        Appointment.objects.filter(recurring_id=out.recurring.id).values_list(
            "occurrence_date", flat=True
        )
    )
    assert len(dates) == len(set(dates)) == 2


def test_two_charges_of_the_same_appointment_at_once_open_one_check(salon):
    from apps.sale.models import Order

    booked = booking(salon, "10:00")()
    charge = lambda: run("appointment.appointment.charge", {"id": str(booked.id)})  # noqa: E731
    results = at_once(charge, charge)
    assert codes(results) == ["ok", "ok"]
    assert results[0].order_id == results[1].order_id
    assert Order.objects.filter(appointment_id=booked.id).count() == 1


# ── The Hub admin's «Delete» of a professional while a booking is written ─────────────────────────
#
# A booking holds the professional's record and then writes the appointment, which protects the record.
# Django's delete page and its «Delete selected» check what protects a record before deleting it: the check
# ran before the booking committed, and the deletion then found the appointment (a 500). The admin locks the
# record before the check, so it waits for the booking and answers «Cannot delete», as for one protected
# before.


@pytest.mark.parametrize("how", ["page", "list"])
def test_a_booking_while_the_hub_admin_deletes_the_professional_leaves_them_protected(salon, how):
    books = lambda sql: sql.lstrip().startswith('INSERT INTO "appointment_appointment"')  # noqa: E731
    with deleted_on_screen(salon.ana, how, books) as answers:
        booking(salon, "10:00")()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (200, "Cannot delete staff member")
    assert len(answer.context["protected"]) == 1
    assert Member.objects.filter(pk=salon.ana.pk).exists()
    assert Appointment.objects.filter(staff=salon.ana).count() == 1


# ── A deletion that lands in the middle of a detail ─────────────────────────────────────────────
#
# The series' detail found it and then loaded it again by its id: a deletion committed between the two reads
# raised DoesNotExist (a 500) when the Hub admin deleted it (the row goes), and mixed both reads when the
# business deleted it (the row stays, marked: the detail showed it paused). In one read it is the series as
# it was read; what the deletion's event runs next says it is not found. An appointment's detail already
# reads its row once: it stays here so that a second read never comes back.

#: How a detail's row is taken away: the Hub admin's «Delete» from its page or with the list's «Delete
#: selected» (the row goes, with what its ``on_delete`` takes), or the business's «Delete» (the row is marked).
DELETIONS = ["delete_model", "delete_queryset", "operation"]

#: Each detail: how its row is made, the business's «Delete» of it, what the detail shows of it (and what it
#: was made with), and how it says it is not found.
DETAILS = {
    "appointment.recurring.get": (
        make_series,
        "appointment.recurring.delete",
        lambda shown: (shown.id, shown.customer_name, shown.frequency, shown.is_active),
        lambda series: (series.id, "Lucía Pérez", "weekly", True),
        "appointment.recurring_not_found",
    ),
    "appointment.appointment.get": (
        lambda salon: make_appointment(
            salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00")
        ),
        "appointment.appointment.delete",
        lambda shown: (shown.id, shown.customer_name, shown.status),
        lambda appointment: (appointment.id, "Lucía Pérez", "confirmed"),
        "appointment.appointment_not_found",
    ),
}


def delete(target, how: str, business_delete: str) -> None:
    """Takes ``target`` away in this session, ``how`` it says (see ``DELETIONS``), as the staff run it."""
    if how == "operation":
        run(business_delete, {"id": str(target.pk)})
        return
    model_admin = admin.site._registry[type(target)]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, type(target).objects.filter(pk=target.pk))
    else:
        model_admin.delete_model(request, type(target).objects.get(pk=target.pk))


@contextmanager
def deleted_after_the_first_read_of(target, how: str, business_delete: str):
    """Commits the deletion of ``target`` in another session right after the first statement of this one that
    reads its table: a deletion landing in the middle of a read, every time. Yields its outcome."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(target, how, business_delete)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


@pytest.mark.parametrize("how", DELETIONS)
@pytest.mark.parametrize("detail", sorted(DETAILS))
def test_a_row_deleted_while_its_detail_is_read_is_never_a_server_error(salon, detail, how):
    make, business_delete, shows, made_with, missing = DETAILS[detail]
    target = make(salon)
    with deleted_after_the_first_read_of(target, how, business_delete) as deletions:
        shown = run(detail, {"id": str(target.pk)})
    assert [getattr(outcome, "code", "ok") for outcome in deletions] == ["ok"]
    assert shows(shown) == made_with(target)
    # What the deletion's event runs next: not found, and the open sheet closes.
    try:
        gone = run(detail, {"id": str(target.pk)})
    except OperationError as error:
        gone = error
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, missing)


# ── The Hub admin's «Delete» of an appointment or a series that a write holds ───────────────────
#
# A write locks the appointment (a state change, new services) or the series (booking its dates, splitting it)
# and then adds what hangs from it: a history line, service lines, booked appointments, the series it splits
# into. Django's «Delete» gathered what hangs from the row before the write committed and deleted the row
# after: it missed what the write added and failed at its COMMIT, or waited for the write in a circle (a 500
# either way). Locked first, it waits for the write and then takes what it added, or answers «Cannot delete»
# when that protects the row; a write that comes second waits for the deletion and finds nothing.

#: How the platform staff delete: from the row's delete page, or with the list's «Delete selected».
HOW = ["page", "list"]


def locks(table: str) -> Callable[[str], bool]:
    """Whether a statement locks rows of ``table``."""
    return lambda sql: f'FROM "{table}"' in sql and "FOR UPDATE" in sql


@pytest.fixture
def hub_staff(db) -> Client:
    """The platform staff, signed in to the Hub admin."""
    staff = get_user_model().objects.create_superuser(
        username="root", password="pw", email="root@example.com"
    )
    client = Client()
    client.force_login(staff)
    return client


def admin_delete(client: Client, how: str, *targets):
    """The Hub admin's «Delete» of ``targets`` (one for its page), ``how`` it says (see ``HOW``); it returns
    the answer."""
    meta = type(targets[0])._meta
    changelist = f"/admin/{meta.app_label}/{meta.model_name}/"
    if how == "page":
        [target] = targets
        url, data = f"{changelist}{target.pk}/delete/", {"post": "yes"}
    else:
        url, data = changelist, {
            "action": "delete_selected",
            "_selected_action": [str(target.pk) for target in targets],
            "post": "yes",
        }
    return lambda: client.post(
        url, data, HTTP_HOST="hubs.localhost", HTTP_ACCEPT_LANGUAGE="en"
    )


@contextmanager
def meanwhile(after: Callable[[str], bool], call):
    """Runs ``call`` in another session right after the first statement of this one for which ``after``
    holds; this one goes on once ``call`` waits for what it holds (or has ended). Yields its outcome (an
    error raised, a 500 included, is the outcome)."""
    outcome: list = []

    def other():
        try:
            outcome.append(call())
        except Exception as error:  # reported to the test
            outcome.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=other)

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if thread.ident is None and after(sql):
            thread.start()
            deadline = time.monotonic() + WAIT_LIMIT
            while thread.is_alive() and not _waited_for() and time.monotonic() < deadline:
                time.sleep(0.02)
        return result

    try:
        with connection.execute_wrapper(wrapper):
            yield outcome
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "this session never locked"


def booked_pending(salon) -> Appointment:
    return make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), status="pending"
    )


#: Writes that lock an appointment and add to what hangs from it: a history line, and new service lines.
APPOINTMENT_WRITES = {
    "confirm": lambda salon, booked: run(
        "appointment.appointment.confirm", {"id": str(booked.id)}
    ),
    "new services": lambda salon, booked: run(
        "appointment.appointment.update",
        {"id": str(booked.id), "services": [{"service_id": str(salon.colour.id)}]},
    ),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(APPOINTMENT_WRITES))
def test_the_hub_admin_deletes_an_appointment_a_write_holds_once_it_is_written(
    salon, hub_staff, write, how
):
    booked = booked_pending(salon)
    deletion = admin_delete(hub_staff, how, booked)
    with meanwhile(locks("appointment_appointment"), deletion) as answers:
        APPOINTMENT_WRITES[write](salon, booked)
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Appointment.objects.filter(pk=booked.pk).exists()


@pytest.mark.parametrize("how", HOW)
def test_a_state_change_while_the_hub_admin_deletes_the_appointment_finds_it_gone(
    salon, hub_staff, how
):
    booked = booked_pending(salon)
    confirm = lambda: run("appointment.appointment.confirm", {"id": str(booked.id)})  # noqa: E731
    with meanwhile(locks("appointment_appointment"), confirm) as outcomes:
        answer = admin_delete(hub_staff, how, booked)()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "appointment.appointment_not_found")
    assert not Appointment.objects.filter(pk=booked.pk).exists()


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_cannot_delete_a_series_whose_dates_a_run_books_meanwhile(
    salon, hub_staff, how
):
    series = make_series(salon)
    deletion = admin_delete(hub_staff, how, series)
    with meanwhile(locks("appointment_recurring"), deletion) as answers:
        run("appointment.recurring.materialize", {"id": str(series.id)})
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert (answer.status_code, str(answer.context["title"])) == (
        200,
        "Cannot delete repeating appointment",
    )
    assert Recurring.objects.filter(pk=series.pk).exists()
    assert Appointment.objects.filter(recurring=series).exists()


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_deletes_a_series_an_edit_splits_and_keeps_the_new_one(
    salon, hub_staff, how
):
    series = make_series(salon, is_active=False)
    deletion = admin_delete(hub_staff, how, series)
    split = {
        "id": str(series.id),
        "from_date": (MONDAY + dt.timedelta(weeks=1)).isoformat(),
        "time": "11:00",
    }
    with meanwhile(locks("appointment_recurring"), deletion) as answers:
        out = run("appointment.recurring.update", split)
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Recurring.objects.filter(pk=series.pk).exists()
    assert Recurring.objects.get(pk=out.recurring.id).split_from_id is None


@pytest.mark.parametrize("how", HOW)
def test_a_run_of_a_series_while_the_hub_admin_deletes_it_finds_it_gone(
    salon, hub_staff, how
):
    series = make_series(salon)
    book = lambda: run("appointment.recurring.materialize", {"id": str(series.id)})  # noqa: E731
    with meanwhile(locks("appointment_recurring"), book) as outcomes:
        answer = admin_delete(hub_staff, how, series)()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "appointment.recurring_not_found")
    assert not Recurring.objects.filter(pk=series.pk).exists()
    assert not Appointment.objects.exists()


def test_the_agenda_and_the_hub_admin_deleting_the_same_appointments_never_wait_in_a_circle(
    salon, hub_staff
):
    first = booked_pending(salon)
    second = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), status="pending"
    )
    deletion = admin_delete(hub_staff, "list", first, second)
    with meanwhile(locks("appointment_appointment"), deletion) as answers:
        # The agenda names them the other way round from the admin's list.
        out = run(
            "appointment.appointment.bulk_delete", {"ids": [str(second.id), str(first.id)]}
        )
    assert out.deleted == [second.id, first.id]
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    assert not Appointment.objects.exists()


# ── Writes that lock several appointments or series at once ─────────────────────────────────────
#
# The Hub admin's «Delete selected» and ``appointment.appointment.bulk_delete`` lock their rows in id order. A
# write that locked several of the same rows in its own order (by start, by date, as the table stores them)
# could take one of them while the deletion held the other: each waited for the other (``deadlock detected``,
# a 500 or a failed reaction). Every write that locks several takes them in id order too, and the series
# before their appointments (as an edit of a series does).


def system(name: str, data: dict):
    """Runs ``name`` as the platform (the outbox relay's reactions)."""
    op = get(name)
    return op(system_context(A), op.input.model_validate(data))


def waiting() -> int:
    """How many other sessions on this database wait for a lock."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_stat_clear_snapshot()")
        cursor.execute(
            "SELECT count(*) FROM pg_stat_activity WHERE datname = current_database()"
            " AND wait_event_type = 'Lock' AND pid <> pg_backend_pid()"
        )
        return cursor.fetchone()[0]


def in_turn(row, *calls) -> list:
    """Holds ``row`` locked in this session and starts ``calls`` in their own sessions, each once the ones before
    wait for a lock, so they queue for ``row`` in that order; then lets it go. Their outcomes (an error raised,
    a 500 included, is the outcome)."""
    outcomes: list = [None] * len(calls)

    def other(index, call):
        try:
            outcomes[index] = call()
        except Exception as error:  # reported to the test
            outcomes[index] = error
        finally:
            connection.close()

    threads = [threading.Thread(target=other, args=(i, call)) for i, call in enumerate(calls)]
    with transaction.atomic():
        list(type(row).objects.select_for_update().filter(pk=row.pk))
        for queued, thread in enumerate(threads, start=1):
            thread.start()
            deadline = time.monotonic() + WAIT_LIMIT
            while thread.is_alive() and waiting() < queued and time.monotonic() < deadline:
                time.sleep(0.02)
    for thread in threads:
        thread.join(30)
    return outcomes


def ids_in_order() -> tuple:
    return tuple(sorted((uuid7(), uuid7())))


# Two rows (the first and the second by id) that a write takes the other way round.


def by_start(salon):
    """Two of Ana's appointments: the first by id starts later (the professional's release goes by start)."""
    later = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"))
    sooner = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    return later, sooner


def by_date(salon):
    """Two appointments of a series: the first by id is the later date (an edit of the series goes by date)."""
    series = make_series(salon)
    week = MONDAY + dt.timedelta(weeks=1)
    later = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(week, "10:00"), recurring=series, occurrence_date=week
    )
    sooner = make_appointment(
        salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), recurring=series, occurrence_date=MONDAY
    )
    return later, sooner


def appointments_stored_backwards(salon):
    """Two of Lucía's appointments, the second by id stored first (a change of all of hers goes as stored)."""
    first, second = ids_in_order()
    stored = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"), id=second)
    return make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "12:00"), id=first), stored


def series_stored_backwards(salon):
    """Two of Lucía's series with Ana, the second by id stored first."""
    first, second = ids_in_order()
    stored = make_series(salon, id=second)
    return make_series(salon, id=first, day_of_week=1), stored


def series_by_name(salon):
    """Two of Ana's series: the first by id is Zoe's, after Lucía's by name (the release goes by name)."""
    zoe = make_customer("Zoe Ruiz", phone="+34600777666")
    first, second = make_series(salon), make_series(salon, day_of_week=1)
    Recurring.objects.filter(pk=first.pk).update(customer=zoe, customer_name=zoe.name)
    return first, second


def release(salon, rows):
    return system("appointment.staff.release", {"id": str(salon.ana.id)})


def edit_series(salon, rows):
    series = rows[0].recurring
    return run(
        "appointment.recurring.update",
        {"id": str(series.id), "from_date": MONDAY.isoformat(), "time": "11:00"},
    )


def erase(salon, rows):
    return system("appointment.customer.erase", {"id": str(salon.lucia.id)})


def reassign(salon, rows):
    marta = make_customer("Marta Gil", phone="+34600999888")
    return system(
        "appointment.customer.reassign", {"id": str(marta.id), "absorbed_id": str(salon.lucia.id)}
    )


#: A write that locks several rows, the two rows it takes the other way round from their ids, and the deletion
#: that takes them in id order.
IN_A_CIRCLE = {
    "release by start · admin": (release, by_start, "admin"),
    "release by start · agenda": (release, by_start, "agenda"),
    "release series by name · admin": (release, series_by_name, "admin"),
    "edit of a series by date · admin": (edit_series, by_date, "admin"),
    "erase as stored · admin": (erase, appointments_stored_backwards, "admin"),
    "erase series · admin": (erase, series_stored_backwards, "admin"),
    "reassign as stored · admin": (reassign, appointments_stored_backwards, "admin"),
    "reassign series · admin": (reassign, series_stored_backwards, "admin"),
}


@pytest.mark.parametrize("case", sorted(IN_A_CIRCLE))
def test_a_write_on_several_rows_and_a_deletion_of_them_never_wait_in_a_circle(salon, hub_staff, case):
    write, make, deleter = IN_A_CIRCLE[case]
    first, second = make(salon)
    assert first.pk < second.pk
    if deleter == "admin":
        deletion = admin_delete(hub_staff, "list", first, second)
    else:
        deletion = lambda: run(  # noqa: E731
            "appointment.appointment.bulk_delete", {"ids": [str(first.id), str(second.id)]}
        )
    deleted, written = in_turn(first, deletion, lambda: write(salon, (first, second)))
    assert not isinstance(deleted, Exception), deleted
    assert not isinstance(written, Exception), written
    if deleter == "admin":
        assert deleted.status_code == 302
        assert not type(first).objects.filter(pk__in=[first.pk, second.pk]).exists()


#: Writes that change a professional's or a customer's appointments and series (the series before them).
SERIES_THEN_APPOINTMENTS = {"release": release, "erase": erase, "reassign": reassign}


def locks_rows_of(table: str) -> Callable[[str], bool]:
    """Whether a statement locks rows of ``table`` (to read them or to change them)."""
    return lambda sql: locks(table)(sql) or sql.lstrip().startswith(f'UPDATE "{table}"')


@pytest.mark.parametrize("write", sorted(SERIES_THEN_APPOINTMENTS))
def test_a_write_on_a_series_and_its_appointments_and_an_edit_of_it_never_wait_in_a_circle(
    salon, write
):
    rows = by_date(salon)
    edit = lambda: edit_series(salon, rows)  # noqa: E731
    with meanwhile(locks_rows_of("appointment_appointment"), edit) as edited:
        SERIES_THEN_APPOINTMENTS[write](salon, rows)
    [outcome] = edited
    assert not isinstance(outcome, Exception), outcome


# ── The Hub admin's «Delete» of the customer's card while a write links it ───────────────────────
#
# A booking, a batch of bookings and a series find the customer's card and then write the row that points at it.
# The Hub admin's «Delete» of that card between the two found nothing protecting it and deleted it: the write then
# failed at its COMMIT (an IntegrityError, a 500). The write locks the card when it finds it, as the deletion does:
# the deletion waits for it and answers «Cannot delete», since the new row protects the card; a write that comes
# second waits for the deletion and is told the card is gone.


def _book(salon):
    return run("appointment.appointment.create", booking_data(salon, "10:00"))


def _book_a_batch(salon):
    data = booking_data(salon, "10:00")
    data["starts"] = [data.pop("start"), wall(MONDAY, "12:00")]
    return run("appointment.appointment.bulk_create", data)


def _book_a_series(salon):
    return run(
        "appointment.recurring.create",
        {
            "customer_id": str(salon.lucia.id),
            "services": [{"service_id": str(salon.cut.id)}],
            "staff_id": str(salon.ana.id),
            "frequency": "weekly",
            "start_date": MONDAY.isoformat(),
            "time": "10:00",
            "max_occurrences": 2,
        },
    )


def booking_data(salon, start: str) -> dict:
    return {
        "customer_id": str(salon.lucia.id),
        "services": [{"service_id": str(salon.cut.id)}],
        "staff_id": str(salon.ana.id),
        "start": wall(MONDAY, start),
    }


#: The writes that link a card, and the table of the row that points at it.
CARD_LINKS = {
    "booking": (_book, "appointment_appointment"),
    "batch": (_book_a_batch, "appointment_appointment"),
    "series": (_book_a_series, "appointment_recurring"),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CARD_LINKS))
def test_the_hub_admin_cannot_delete_a_card_a_booking_links_meanwhile(salon, write, how):
    book, table = CARD_LINKS[write]
    with card_deleted_on_screen(salon.lucia, how, writes(table)) as answers:
        book(salon)
    [answer] = answers
    assert cannot_delete(answer)
    assert Customer.objects.filter(pk=salon.lucia.pk).exists()
    assert Recurring.objects.filter(customer=salon.lucia).exists() == (write == "series")
    assert Appointment.objects.filter(customer=salon.lucia).exists()


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CARD_LINKS))
def test_a_booking_whose_card_the_hub_admin_deletes_first_is_told_it_is_gone(salon, write, how):
    book, _ = CARD_LINKS[write]
    with card_deleted_on_screen(salon.lucia, how, reads("customer_customer")) as answers:
        with pytest.raises(OperationError) as refused:
            book(salon)
    [answer] = answers
    assert answer.status_code == 302
    assert (refused.value.status, refused.value.code) == (404, "customer.customer_unavailable")
    assert not Customer.objects.filter(pk=salon.lucia.pk).exists()
    assert not Appointment.objects.exists() and not Recurring.objects.exists()


# The merge of two cards moves the absorbed card's appointments and series to the card that stays, later, as a
# reaction: the Hub admin may have deleted that card in between (nothing protected it), or delete it while the
# reaction moves them. The reaction locks the card that stays first: gone, nothing moves (they stay with the card
# they were booked with) instead of failing for ever at its COMMIT; there, the deletion waits and answers «Cannot
# delete».


def _merged_into_marta(salon):
    booked = make_appointment(salon.lucia, salon.ana, [salon.cut], at(MONDAY, "10:00"))
    series = make_series(salon)
    marta = make_customer("Marta Gil", phone="+34600999888")
    move = lambda: system(  # noqa: E731
        "appointment.customer.reassign", {"id": str(marta.id), "absorbed_id": str(salon.lucia.id)}
    )
    return booked, series, marta, move


@pytest.mark.parametrize("how", HOW)
def test_the_hub_admin_cannot_delete_the_card_a_merge_moves_the_appointments_to_meanwhile(salon, how):
    booked, series, marta, move = _merged_into_marta(salon)
    with card_deleted_on_screen(marta, how, writes("appointment_appointment")) as answers:
        move()
    [answer] = answers
    assert cannot_delete(answer)
    booked.refresh_from_db()
    series.refresh_from_db()
    assert (booked.customer_id, series.customer_id) == (marta.id, marta.id)


@pytest.mark.parametrize("how", HOW)
def test_a_merge_into_a_card_the_hub_admin_deleted_moves_nothing(salon, hub_staff, how):
    booked, series, marta, move = _merged_into_marta(salon)
    assert admin_delete(hub_staff, how, marta)().status_code == 302
    assert move().changed == 0
    booked.refresh_from_db()
    series.refresh_from_db()
    assert (booked.customer_id, series.customer_id) == (salon.lucia.id, salon.lucia.id)
