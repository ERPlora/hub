"""Write operations of the cash register app (WORKBOOK flows F01–F03, F05, F06, F09, F10): one operation =
one transaction, with its event in the outbox. The sale lines of a shift are in test_integration_sale.py."""

import datetime as dt

import pytest
from django.utils import timezone
from live.errors import Conflict, InvalidPayload, NotFound, PermissionDenied
from live.models import OutboxEvent

from apps.cash_register.models import (
    Count,
    Movement,
    Register,
    Session,
    SessionCounter,
    Settings,
)
from apps.cash_register.tests.conftest import ctx_for, open_session, run

pytestmark = pytest.mark.django_db


def events(name: str) -> list[dict]:
    return [
        event.payload
        for event in OutboxEvent.objects.filter(name=name).order_by("created_at", "id")
    ]


def settings(**values):
    return run("cash_register.settings.update", values)


# ── CASH_REGISTER-F01 Settings ──────────────────────────────────────────────────────────────────


def test_the_first_save_creates_the_row_and_keeps_the_factory_values_not_sent():
    saved = settings(require_blind_count=True)
    assert saved.require_blind_count is True
    assert saved.require_closing_balance is True
    assert saved.auto_close_time == "04:00"
    assert saved.updated_at is not None
    assert Settings.objects.count() == 1
    assert events("cash_register.settings.updated") == [
        {"fields": ["require_blind_count"]}
    ]


def test_a_save_changes_only_what_is_sent():
    settings(auto_close_enabled=True, auto_close_time="23:00")
    saved = settings(allow_negative_balance=True)
    assert (
        saved.auto_close_enabled,
        saved.auto_close_time,
        saved.allow_negative_balance,
    ) == (
        True,
        "23:00",
        True,
    )
    assert Settings.objects.get().updated_by == "tester"


def test_a_save_that_changes_nothing_says_nothing():
    settings(require_blind_count=False)
    assert events("cash_register.settings.updated") == []


def test_only_whoever_manages_the_settings_saves_them():
    with pytest.raises(PermissionDenied):
        run(
            "cash_register.settings.update",
            {"require_blind_count": True},
            ctx_for("hub_manager"),
        )


# ── CASH_REGISTER-F02 Drawers ───────────────────────────────────────────────────────────────────


def test_a_drawer_is_created_with_its_name():
    drawer = run("cash_register.register.create", {"name": " Bar "})
    assert (drawer.name, drawer.is_active) == ("Bar", True)
    assert Register.objects.get().created_by == "tester"
    assert events("cash_register.register.created") == [{"id": str(drawer.id)}]


def test_two_drawers_never_share_a_name():
    run("cash_register.register.create", {"name": "Bar"})
    with pytest.raises(Conflict) as refused:
        run("cash_register.register.create", {"name": "BAR"})
    assert refused.value.code == "cash_register.register_exists"
    assert "name" in refused.value.fields


def test_a_drawer_is_renamed_and_deactivated_by_its_name():
    run("cash_register.register.create", {"name": "Bar"})
    renamed = run(
        "cash_register.register.update", {"register_name": "bar", "name": "Terrace"}
    )
    assert renamed.name == "Terrace"
    off = run(
        "cash_register.register.update",
        {"register_id": str(renamed.id), "is_active": False},
    )
    assert off.is_active is False
    assert len(events("cash_register.register.updated")) == 2


def test_renaming_to_another_drawers_name_is_refused():
    run("cash_register.register.create", {"name": "Bar"})
    run("cash_register.register.create", {"name": "Terrace"})
    with pytest.raises(Conflict) as refused:
        run(
            "cash_register.register.update", {"register_name": "Terrace", "name": "bar"}
        )
    assert refused.value.code == "cash_register.register_exists"


def test_an_unknown_drawer_is_not_found():
    with pytest.raises(NotFound) as refused:
        run(
            "cash_register.register.update",
            {"register_name": "Nope", "is_active": False},
        )
    assert refused.value.code == "cash_register.register_not_found"


def test_drawers_are_the_admins():
    with pytest.raises(PermissionDenied):
        run("cash_register.register.create", {"name": "Bar"}, ctx_for("hub_employee"))


# ── CASH_REGISTER-F03 Open ──────────────────────────────────────────────────────────────────────


def test_opening_numbers_the_session_on_the_business_day():
    session = open_session(15050, opening_notes="Morning")
    day = timezone.localdate()
    assert session.number == f"S-{day:%y%m%d}-0001"
    assert session.business_day == day
    assert (session.status, session.opening_balance, session.opened_by) == (
        "open",
        15050,
        "tester",
    )
    assert session.expected_balance == 15050
    assert Session.objects.get().opening_notes == "Morning"
    assert events("cash_register.session.opened") == [
        {
            "session_id": str(session.id),
            "number": session.number,
            "opening_balance": 15050,
            "register_id": None,
            "opened_by": "tester",
        }
    ]


def test_only_one_session_is_open():
    open_session()
    with pytest.raises(Conflict) as refused:
        open_session()
    assert refused.value.code == "cash_register.session_already_open"
    assert Session.objects.count() == 1
    # The refused open burnt no number.
    assert SessionCounter.objects.get().last == 1


def test_the_next_session_of_the_day_takes_the_next_number():
    first = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    second = open_session()
    assert second.number.endswith("-0002") and second.number != first.number


def test_an_empty_float_is_zero_unless_the_business_requires_one():
    assert open_session(None).opening_balance == 0
    run("cash_register.session.close", {"closing_balance": 0})
    settings(require_opening_balance=True)
    for empty in (None, 0):
        with pytest.raises(Conflict) as refused:
            open_session(empty)
        assert refused.value.code == "cash_register.opening_balance_required"
        assert "opening_balance" in refused.value.fields
    assert open_session(500).opening_balance == 500


def test_a_session_opens_in_the_drawer_named_and_alone_in_the_only_one():
    bar = run("cash_register.register.create", {"name": "Bar"})
    session = open_session()
    assert (session.register_id, session.register_name) == (bar.id, "Bar")
    run("cash_register.session.close", {"closing_balance": 10000})
    run("cash_register.register.create", {"name": "Terrace"})
    # Several drawers and none named: the session has no drawer (it is optional on the Cash screen).
    assert open_session().register_id is None
    run("cash_register.session.close", {"closing_balance": 10000})
    assert open_session(register_name="terrace").register_name == "Terrace"


def test_an_inactive_drawer_cannot_open_a_session():
    run("cash_register.register.create", {"name": "Bar"})
    run("cash_register.register.update", {"register_name": "Bar", "is_active": False})
    with pytest.raises(NotFound) as refused:
        open_session(register_name="Bar")
    assert refused.value.code == "cash_register.register_not_found"


# ── CASH_REGISTER-F05 Cash in and out ───────────────────────────────────────────────────────────


def test_cash_in_and_out_move_the_expected_with_the_sign_of_their_type():
    session = open_session(10000)
    cash_in = run(
        "cash_register.movement.add",
        {"type": "in", "amount": 2000, "description": "Change"},
    )
    cash_out = run(
        "cash_register.movement.add",
        {"type": "out", "amount": 500, "description": "Supplier"},
    )
    assert (cash_in.signed_amount, cash_out.signed_amount) == (2000, -500)
    assert cash_out.created_by == "tester" and cash_out.session_id == session.id
    current = run("cash_register.session.current")
    assert current.session.expected_balance == 11500
    assert [e["type"] for e in events("cash_register.movement.added")] == ["in", "out"]


def test_a_movement_by_card_is_listed_but_never_in_the_drawer():
    open_session(10000)
    run(
        "cash_register.movement.add",
        {"type": "out", "amount": 50000, "method_type": "card"},
    )
    assert run("cash_register.session.current").session.expected_balance == 10000


def test_a_cash_out_cannot_leave_the_drawer_below_zero_unless_allowed():
    open_session(1000)
    with pytest.raises(Conflict) as refused:
        run("cash_register.movement.add", {"type": "out", "amount": 1001})
    assert refused.value.code == "cash_register.negative_balance_not_allowed"
    run("cash_register.movement.add", {"type": "out", "amount": 1000})
    settings(allow_negative_balance=True)
    run("cash_register.movement.add", {"type": "out", "amount": 300})
    assert run("cash_register.session.current").session.expected_balance == -300


def test_a_closed_session_takes_no_movement():
    session = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    with pytest.raises(Conflict) as refused:
        run(
            "cash_register.movement.add",
            {"session_id": str(session.id), "type": "in", "amount": 100},
        )
    assert refused.value.code == "cash_register.session_not_open"
    assert not Movement.objects.exists()


def test_without_an_open_session_there_is_nothing_to_record_in():
    with pytest.raises(Conflict) as refused:
        run("cash_register.movement.add", {"type": "in", "amount": 100})
    assert refused.value.code == "cash_register.no_open_session"


def test_a_session_number_that_does_not_exist_is_not_found():
    with pytest.raises(NotFound) as refused:
        run(
            "cash_register.movement.add",
            {"session": "S-990101-0001", "type": "in", "amount": 100},
        )
    assert refused.value.code == "cash_register.session_not_found"


# ── CASH_REGISTER-F06 Counts ────────────────────────────────────────────────────────────────────


def test_a_count_by_notes_and_coins_is_added_up_by_the_server():
    session = open_session()
    count = run(
        "cash_register.count.add",
        {
            "denominations": {"bills": {"50": 2, "5": 0}, "coins": {"0.05": 3}},
            "notes": "evening",
        },
    )
    assert (count.total, count.type, count.session_id) == (10015, "closing", session.id)
    # What is stored is what was counted: the empty boxes leave.
    assert Count.objects.get().denominations == {
        "bills": {"50": 2},
        "coins": {"0.05": 3},
    }
    assert events("cash_register.count.added") == [
        {
            "session_id": str(session.id),
            "count_id": str(count.id),
            "type": "closing",
            "total": 10015,
        }
    ]


def test_a_typed_total_prevails_over_the_notes_and_coins():
    open_session()
    count = run(
        "cash_register.count.add",
        {"type": "opening", "total": 4321, "denominations": {"bills": {"50": 1}}},
    )
    assert count.total == 4321


def test_a_note_or_coin_of_another_currency_is_refused():
    open_session()
    with pytest.raises(InvalidPayload) as refused:
        run("cash_register.count.add", {"denominations": {"bills": {"25": 1}}})
    assert "denominations" in refused.value.fields


def test_a_closed_session_is_not_counted():
    session = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    with pytest.raises(Conflict) as refused:
        run("cash_register.count.add", {"session_id": str(session.id), "total": 100})
    assert refused.value.code == "cash_register.session_not_open"


# ── CASH_REGISTER-F09 Close ─────────────────────────────────────────────────────────────────────


def test_closing_freezes_expected_counted_and_difference():
    session = open_session(10000)
    run("cash_register.movement.add", {"type": "in", "amount": 2000})
    run("cash_register.movement.add", {"type": "out", "amount": 500})
    closed = run(
        "cash_register.session.close",
        {"closing_balance": 11450, "closing_notes": "short"},
    )
    assert (
        closed.status,
        closed.expected_balance,
        closed.closing_balance,
        closed.difference,
    ) == (
        "closed",
        11500,
        11450,
        -50,
    )
    assert closed.closed_by == "tester" and closed.closed_at is not None
    stored = Session.objects.get(pk=session.id)
    assert (stored.expected_balance, stored.difference, stored.closing_notes) == (
        11500,
        -50,
        "short",
    )
    assert events("cash_register.session.closed") == [
        {
            "session_id": str(session.id),
            "number": session.number,
            "expected_balance": 11500,
            "closing_balance": 11450,
            "difference": -50,
            "auto_closed": False,
        }
    ]


def test_the_count_is_required_to_close_unless_the_business_says_otherwise():
    open_session()
    with pytest.raises(Conflict) as refused:
        run("cash_register.session.close", {})
    assert refused.value.code == "cash_register.closing_balance_required"
    assert "closing_balance" in refused.value.fields
    settings(require_closing_balance=False)
    closed = run("cash_register.session.close", {})
    assert (closed.closing_balance, closed.difference, closed.expected_balance) == (
        None,
        None,
        10000,
    )


def test_a_closed_session_cannot_be_closed_again():
    session = open_session()
    run("cash_register.session.close", {"closing_balance": 10000})
    with pytest.raises(Conflict) as refused:
        run(
            "cash_register.session.close",
            {"session": session.number, "closing_balance": 1},
        )
    assert refused.value.code == "cash_register.session_not_open"
    assert Session.objects.get().closing_balance == 10000


def test_closing_needs_the_close_permission():
    open_session()
    ctx = ctx_for("hub_employee")
    assert (
        run("cash_register.session.close", {"closing_balance": 10000}, ctx).status
        == "closed"
    )


# ── CASH_REGISTER-F10 Auto-close ────────────────────────────────────────────────────────────────


def _opened_days_ago(session, days: int) -> None:
    Session.objects.filter(pk=session.id).update(
        opened_at=timezone.now() - dt.timedelta(days=days)
    )


def test_with_the_auto_close_off_nothing_closes():
    session = open_session()
    _opened_days_ago(session, 2)
    assert run("cash_register.session.auto_close").closed == []
    assert Session.objects.get().status == "open"


def test_the_auto_close_says_a_session_closed_once_and_nothing_when_nothing_was_due():
    # cash_register#145, hub#2612: the task runs every 5 minutes and used to announce «drawer closed» on
    # every pass. Only a pass that closes a session says so, once per session.
    settings(auto_close_enabled=True, auto_close_time="04:00")
    assert run("cash_register.session.auto_close").closed == []
    assert events("cash_register.session.closed") == []
    session = open_session()
    _opened_days_ago(session, 2)
    assert len(run("cash_register.session.auto_close").closed) == 1
    assert run("cash_register.session.auto_close").closed == []
    assert [event["session_id"] for event in events("cash_register.session.closed")] == [
        str(session.id)
    ]


def test_a_session_open_since_before_the_cut_off_closes_by_itself_at_the_cut_off():
    session = open_session(10000)
    _opened_days_ago(session, 2)
    settings(auto_close_enabled=True, auto_close_time="04:00")
    (closed,) = run("cash_register.session.auto_close").closed
    assert (closed.id, closed.status, closed.auto_closed, closed.closed_by) == (
        session.id,
        "closed",
        True,
        "",
    )
    assert (closed.closing_balance, closed.difference, closed.expected_balance) == (
        None,
        None,
        10000,
    )
    local = timezone.localtime(closed.closed_at)
    assert (local.hour, local.minute) == (4, 0) and closed.closed_at <= timezone.now()
    assert [e["auto_closed"] for e in events("cash_register.session.closed")] == [True]
    # A second pass finds nothing to do and says nothing.
    assert run("cash_register.session.auto_close").closed == []
    assert len(events("cash_register.session.closed")) == 1


def test_a_session_opened_after_the_cut_off_is_left_alone():
    open_session()
    settings(auto_close_enabled=True, auto_close_time="04:00")
    Session.objects.update(opened_at=timezone.now())
    # Opened now: the last cut-off is behind it, whatever the hour.
    assert run("cash_register.session.auto_close").closed == []


def test_opening_closes_a_forgotten_session_first():
    old = open_session(10000)
    _opened_days_ago(old, 2)
    settings(auto_close_enabled=True)
    assert run("cash_register.session.current").session.auto_close_due is True
    new = open_session(5000)
    assert new.status == "open"
    assert Session.objects.get(pk=old.id).auto_closed is True


def test_the_last_cut_off_is_today_at_its_hour_or_yesterday_before_it():
    from apps.cash_register.queries import last_cut_off

    madrid = timezone.get_default_timezone()
    four = dt.time(4, 0)
    after = dt.datetime(2026, 10, 14, 9, 30, tzinfo=madrid)
    before = dt.datetime(2026, 10, 14, 3, 30, tzinfo=madrid)
    assert last_cut_off(after, four) == dt.datetime(2026, 10, 14, 4, 0, tzinfo=madrid)
    assert last_cut_off(before, four) == dt.datetime(2026, 10, 13, 4, 0, tzinfo=madrid)


def test_who_opened_and_closed_is_written_as_a_person_reads_it(make_user):
    # The session's user is a Django user: its name (or e-mail), never its internal username.
    from live.context import OperationContext

    from apps.cash_register.tests.conftest import A

    user = make_user("saas:0199e4f0-aaaa", host="a")
    user.first_name, user.email = "", "ana@example.com"
    user.save()
    ctx = OperationContext(scope=A, actor=user, permissions=ctx_for().permissions)
    assert run("cash_register.session.open", {"opening_balance": 100}, ctx).opened_by == "ana@example.com"
    user.first_name, user.last_name = "Ana", "López"
    user.save()
    closed = run("cash_register.session.close", {"closing_balance": 100}, ctx)
    assert closed.closed_by == "Ana López"


def test_a_forgotten_session_past_its_cut_takes_no_movement_count_or_close():
    session = open_session(10000)
    _opened_days_ago(session, 2)
    settings(auto_close_enabled=True)
    for name, data in (
        ("cash_register.movement.add", {"type": "in", "amount": 100}),
        ("cash_register.count.add", {"total": 100}),
        ("cash_register.session.close", {"closing_balance": 100}),
    ):
        with pytest.raises(Conflict) as refused:
            run(name, {"session_id": str(session.id), **data})
        assert refused.value.code == "cash_register.session_auto_close_due", name
    assert not Movement.objects.exists() and not Count.objects.exists()
    assert Session.objects.get().status == "open"
