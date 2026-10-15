"""The gate of the book without a database (engine.py): what refuses a reservation, and in what order.

The cases come from the old module's handler and gate tests (party size, blocked date, no slot, full slot,
the pre-check order) plus what this port adds: the business's opening hours, the table out of service or
already booked, the covers of a slot, and the notice that only binds the guest who books herself.
"""

import datetime as dt

from apps.reservation import engine
from apps.reservation.engine import (
    Block,
    Hours,
    Request,
    Rules,
    Slot,
    TableFacts,
    Window,
)

DAY = dt.date(2026, 10, 15)
NOW = dt.datetime(2026, 10, 14, 12, 0)
DINNER = Slot(
    id="dinner", start=dt.time(20, 0), end=dt.time(23, 30), max_reservations=3
)


def at(hour: int, minute: int = 0, day: dt.date = DAY) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(hour, minute))


def request(**fields) -> Request:
    fields.setdefault("date", DAY)
    fields.setdefault("time", dt.time(21, 0))
    fields.setdefault("party_size", 4)
    fields.setdefault("duration_minutes", 120)
    return Request(**fields)


def verdict(req: Request | None = None, **context):
    context.setdefault("rules", Rules())
    context.setdefault("now", NOW)
    context.setdefault("blocks", ())
    context.setdefault("hours", Hours(restricted=False))
    context.setdefault("slots", (DINNER,))
    context.setdefault("table", None)
    return engine.verdict(req or request(), **context)


def code(req: Request | None = None, **context) -> str | None:
    refusal = verdict(req, **context)
    return refusal.code if refusal else None


def test_a_reservation_inside_an_open_slot_with_room_passes():
    assert verdict() is None


def test_contact_required_by_the_rules_is_asked_when_booking():
    rules = Rules(require_phone=True, require_email=True)
    assert code(request(check_contact=True), rules=rules) == "phone_required"
    assert (
        code(request(check_contact=True, phone="600111222"), rules=rules)
        == "email_required"
    )
    assert (
        code(request(check_contact=True, phone="600", email="a@b.es"), rules=rules)
        is None
    )
    # A change of an existing reservation does not ask again (as the old update gate).
    assert code(request(), rules=rules) is None


def test_the_party_size_limits_bind_the_guest_who_books_herself_not_the_staff():
    # Market (WORKBOOK «Investigación de mercado», duda 8): the online rules are the guest's.
    rules = Rules(min_party_size=2, max_party_size=8)
    online = dict(source="online", date=DAY + dt.timedelta(days=1))
    assert code(request(party_size=1, **online), rules=rules) == "party_size_exceeded"
    assert code(request(party_size=9, **online), rules=rules) == "party_size_exceeded"
    refusal = verdict(request(party_size=9, **online), rules=rules)
    assert refusal.params == {"min": 2, "max": 8}
    assert code(request(party_size=8, **online), rules=rules) is None
    assert code(request(party_size=12), rules=rules) is None


def test_the_staff_book_from_now_on_but_never_a_time_that_passed():
    now = dt.datetime(2026, 10, 15, 21, 0, 30)
    assert code(request(time=dt.time(21, 0)), now=now) is None
    assert code(request(time=dt.time(20, 59)), now=now) == "in_past"
    assert code(request(date=dt.date(2026, 10, 14)), now=now) == "in_past"


def test_the_minimum_notice_binds_only_the_guest_who_books_herself():
    now = dt.datetime(2026, 10, 15, 20, 30)
    for source in ("online", "whatsapp"):
        assert code(request(source=source), now=now) == "too_soon", source
        refusal = verdict(request(source=source), now=now)
        assert refusal.params == {"hours": 1}
    assert code(request(source="phone"), now=now) is None
    assert code(request(source="in_person"), now=now) is None
    assert (
        code(request(source="online"), now=now, rules=Rules(min_advance_hours=0))
        is None
    )


def test_the_guest_who_books_herself_cannot_book_beyond_the_maximum_days_ahead():
    rules = Rules(max_advance_days=30)
    anytime = (Slot("any", dt.time(0), dt.time(23, 59), 9),)
    far = request(date=NOW.date() + dt.timedelta(days=31), source="whatsapp")
    assert code(far, rules=rules, slots=anytime) == "too_far"
    assert verdict(far, rules=rules).params == {"days": 30}
    last = request(date=NOW.date() + dt.timedelta(days=30), source="whatsapp")
    assert code(last, rules=rules) is None
    # The staff book the wedding of next year by phone.
    assert code(request(date=NOW.date() + dt.timedelta(days=200)), rules=rules) is None


def test_a_blocked_day_refuses_and_a_blocked_window_refuses_its_hours_both_ends_included():
    assert code(blocks=(Block(is_full_day=True),)) == "date_blocked"
    window = (Block(is_full_day=False, start=dt.time(21, 0), end=dt.time(22, 0)),)
    assert code(request(time=dt.time(21, 0)), blocks=window) == "date_blocked"
    assert code(request(time=dt.time(22, 0)), blocks=window) == "date_blocked"
    assert code(request(time=dt.time(20, 30)), blocks=window) is None
    assert code(request(time=dt.time(22, 15)), blocks=window) is None


def test_the_business_must_be_open_when_the_reservation_starts():
    hours = Hours(
        restricted=True,
        spans=(
            (at(13), at(16)),
            (at(20), at(23, 59)),
        ),
    )
    assert code(hours=hours) is None
    shut = Hours(restricted=True, spans=((at(13), at(16)),))
    assert code(hours=shut) == "outside_schedule"
    # Closed all day (a holiday in Schedules): restricted without a span.
    assert code(hours=Hours(restricted=True)) == "outside_schedule"
    # The eve's span past midnight counts: open 20:00–02:00 the day before.
    late = request(time=dt.time(1, 0), date=DAY)
    eve = Hours(
        restricted=True, spans=((at(20, day=DAY - dt.timedelta(days=1)), at(2)),)
    )
    assert (
        code(late, hours=eve, slots=(Slot("night", dt.time(0), dt.time(3), 5),)) is None
    )
    # Without hours set, Schedules does not limit.
    assert code(hours=Hours(restricted=False)) is None


def test_a_slot_of_the_day_must_cover_the_time_start_included_end_excluded():
    assert code(request(time=dt.time(20, 0))) is None
    assert code(request(time=dt.time(23, 30))) == "no_service_day"
    assert code(request(time=dt.time(18, 0))) == "no_service_day"
    assert code(slots=()) == "no_service_day"


def test_a_full_slot_refuses_by_reservations():
    full = Slot("dinner", dt.time(20, 0), dt.time(23, 30), max_reservations=3, reserved=3)
    assert code(slots=(full,)) == "no_capacity"
    assert verdict(slots=(full,)).params == {"overbook": True}
    room = Slot("dinner", dt.time(20, 0), dt.time(23, 30), max_reservations=3, reserved=2)
    assert code(slots=(room,)) is None
    assert room.available == 1 and room.full is False
    assert full.available == 0 and full.full is True


def test_the_staff_may_overbook_a_full_slot_knowingly_the_guest_never():
    full = (Slot("dinner", dt.time(20, 0), dt.time(23, 30), 3, reserved=3),)
    assert code(request(overbook=True), slots=full) is None
    online = request(overbook=True, source="online", date=DAY + dt.timedelta(days=1))
    assert code(online, slots=full) == "no_capacity"
    assert verdict(online, slots=full).params == {}


def test_a_slot_with_a_covers_limit_also_refuses_a_party_that_does_not_fit():
    slot = Slot(
        "dinner",
        dt.time(20, 0),
        dt.time(23, 30),
        10,
        max_covers=20,
        reserved=4,
        covers=17,
    )
    assert code(request(party_size=4), slots=(slot,)) == "no_capacity"
    assert code(request(party_size=3), slots=(slot,)) is None
    assert slot.full is False
    assert (
        Slot("d", dt.time(20), dt.time(23), 10, max_covers=20, covers=20).full is True
    )


def test_the_table_must_be_in_service():
    table = TableFacts(label="5 (Terrace)", in_service=False)
    assert code(table=table) == "table_unavailable"
    assert verdict(table=table).params == {"table": "5 (Terrace)"}
    assert code(table=TableFacts(label="5", in_service=True)) is None


def test_the_table_must_be_free_for_the_whole_window():
    booked = Window(start=at(21, 30), end=at(23, 30))
    table = TableFacts(label="5", in_service=True, booked=(booked,))
    refusal = verdict(table=table)
    assert refusal.code == "table_taken"
    assert refusal.params == {"table": "5", "start": "21:30", "end": "23:30"}
    # Back to back is free: 19:00–21:00 then 21:00–23:00.
    before = TableFacts(label="5", in_service=True, booked=(Window(at(19), at(21)),))
    assert code(table=before) is None
    after = TableFacts(label="5", in_service=True, booked=(Window(at(23), at(23, 59)),))
    assert code(table=after) is None


def test_a_waitlist_conversion_checks_the_clock_the_blocked_day_the_hours_and_a_slot_with_room():
    # The staff convert for right now: no party limits, notice or days ahead — but never a time gone.
    now = dt.datetime(2026, 10, 15, 20, 30)
    conversion = request(kind="waitlist", party_size=40)
    rules = Rules(max_party_size=20)
    assert code(conversion, now=now, rules=rules) is None
    late = dt.datetime(2026, 10, 15, 21, 30)
    assert code(conversion, now=late, rules=rules) == "in_past"
    assert code(conversion, now=now, rules=rules, blocks=(Block(is_full_day=True),)) == "date_blocked"
    full = Slot("dinner", dt.time(20, 0), dt.time(23, 30), 3, reserved=3)
    assert code(conversion, now=now, rules=rules, slots=(full,)) == "no_capacity"
    overbooked = request(kind="waitlist", overbook=True)
    assert code(overbooked, now=now, rules=rules, slots=(full,)) is None


def test_the_first_refusal_wins_in_the_old_gates_order():
    everything = dict(
        rules=Rules(max_party_size=2, require_phone=True),
        blocks=(Block(is_full_day=True),),
        slots=(),
        table=TableFacts(label="5", in_service=False),
    )
    online = dict(source="online", date=DAY + dt.timedelta(days=1))
    assert code(request(check_contact=True, **online), **everything) == "phone_required"
    assert code(request(phone="1", check_contact=True, **online), **everything) == "party_size_exceeded"
    assert code(request(party_size=2, **online), **everything) == "date_blocked"


def test_the_slot_of_a_time_is_the_one_that_covers_it():
    lunch = Slot("lunch", dt.time(13), dt.time(16), 5)
    assert engine.slot_for((lunch, DINNER), dt.time(21)) is DINNER
    assert engine.slot_for((lunch, DINNER), dt.time(17)) is None


def test_two_windows_overlap_when_each_starts_before_the_other_ends():
    a = Window(at(21), at(23))
    assert a.overlaps(Window(at(22), at(23, 30)))
    assert not a.overlaps(Window(at(23), at(23, 30)))
    assert Window.of(DAY, dt.time(21), 120) == a


def test_a_change_that_keeps_the_day_and_time_is_not_judged_on_the_clock_again():
    # A reservation already under way gets one more guest: «that time has passed» would be absurd.
    now = dt.datetime(2026, 10, 15, 21, 30)
    assert code(request(check_when=False), now=now) is None
    online = request(check_when=False, party_size=40, source="online")
    assert code(online, now=now) == "party_size_exceeded"
    assert code(request(), now=now) == "in_past"
