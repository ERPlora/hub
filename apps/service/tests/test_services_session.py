"""The sessions of the till (SERVICE-F22–F27): hold one for a line of an open check, release it, deliver
it when the sale is charged, expire the holds nobody charged and give back the ones of a sale voided or
refunded. Sales calls these operations by name inside its own transaction (WORKBOOK «Contrato con
Ventas»); here they are run on their own, with real rows.
"""

import datetime as dt
import uuid

import pytest
from django.utils import timezone
from live.errors import Conflict, NotFound, PermissionDenied
from live.operations import get
from live.models import OutboxEvent

from apps.service.models import Redemption
from apps.service.schemas import (
    ExpiredOut,
    HoldIn,
    ReturnIn,
    SessionOut,
    SessionRefIn,
    SessionsOut,
    SettleIn,
    NoIn,
)

from .conftest import (
    A,
    ctx_for,
    make_customer,
    make_grant,
    make_package,
    make_redemption,
    make_service,
    make_tax,
)
from live.context import system_context

pytestmark = pytest.mark.django_db


def run(name, data, role="hub_admin", **ctx):
    op = get(name)
    return op(ctx_for(role, **ctx), op.input.model_validate(data))


def events(name):
    return list(OutboxEvent.objects.filter(name=name).order_by("id").values_list("payload", flat=True))


@pytest.fixture
def cut():
    return make_service("Cut", tax=make_tax())


@pytest.fixture
def lucia():
    return make_customer("Lucía Pérez")


def hold(grant, service, line=None, role="hub_employee"):
    return run(
        "service.session.hold",
        {
            "grant_id": str(grant.id),
            "service_id": str(service.id),
            "order_line_id": str(line or uuid.uuid7()),
        },
        role=role,
    )


@pytest.mark.parametrize(
    ("name", "input", "output", "permission", "risk"),
    [
        (
            "service.session.hold",
            HoldIn,
            SessionOut,
            "service.redeem_package",
            "normal",
        ),
        (
            "service.session.release",
            SessionRefIn,
            SessionOut,
            "service.redeem_package",
            "normal",
        ),
        (
            "service.session.settle",
            SettleIn,
            SessionsOut,
            "service.redeem_package",
            "high",
        ),
        ("service.session.expire", NoIn, ExpiredOut, "service.system", "normal"),
        (
            "service.session.return",
            ReturnIn,
            SessionsOut,
            "service.return_session",
            "high",
        ),
    ],
)
def test_declarations(name, input, output, permission, risk):
    op = get(name)
    assert (
        op.kind,
        op.input,
        op.output,
        op.permission,
        op.expose_api,
        op.ai["risk"],
    ) == (
        "command",
        input,
        output,
        permission,
        False,
        risk,
    )


# ── Hold (SERVICE-F22) ──────────────────────────────────────────────────────────────────────


def test_a_hold_reserves_one_session_for_a_line_for_one_day(cut, lucia):
    grant = make_grant(make_package("Bono 5", [cut], max_uses=5), lucia)
    line = uuid.uuid7()
    before = timezone.now()
    out = hold(grant, cut, line)
    session = Redemption.objects.get(pk=out.id)
    assert (session.status, session.order_line_id, session.service_id) == (
        "held",
        line,
        cut.id,
    )
    assert (
        before + dt.timedelta(days=1)
        <= session.hold_until
        <= timezone.now() + dt.timedelta(days=1)
    )
    assert (out.grant_id, out.package_name, out.customer_id, out.remaining) == (
        grant.id,
        "Bono 5",
        lucia.id,
        4,
    )
    assert (out.status, out.order_line_id, out.hold_until) == (
        "held",
        line,
        session.hold_until,
    )
    assert events("service.session.reserved") == [
        {"id": str(session.id), "grant_id": str(grant.id)}
    ]


def test_an_unlimited_voucher_holds_without_a_count(cut, lucia):
    grant = make_grant(make_package("Unlimited", [cut]), lucia)
    assert hold(grant, cut).remaining is None


@pytest.mark.parametrize(
    ("state", "code"),
    [
        ("voided", "service.grant_voided"),
        ("expired", "service.grant_expired"),
        ("spent", "service.grant_no_uses_left"),
        ("other_service", "service.grant_does_not_cover_service"),
    ],
)
def test_a_hold_is_refused_with_the_real_reason(cut, lucia, state, code):
    grant = make_grant(
        make_package("Bono", [cut], max_uses=1, validity_days=30),
        lucia,
        days_ago=31 if state == "expired" else 0,
    )
    service = cut
    if state == "voided":
        grant.voided_at = timezone.now()
        grant.save()
    elif state == "spent":
        make_redemption(grant, cut)
    elif state == "other_service":
        service = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    with pytest.raises(Conflict) as refusal:
        hold(grant, service)
    assert refusal.value.code == code
    assert not Redemption.objects.filter(status="held").exists()


def test_the_last_session_held_for_a_line_is_not_there_for_another(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), lucia)
    hold(grant, cut)
    with pytest.raises(Conflict) as refusal:
        hold(grant, cut)
    assert refusal.value.code == "service.grant_no_uses_left"


def test_a_line_holds_one_session_at_most(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia)
    line = uuid.uuid7()
    hold(grant, cut, line)
    with pytest.raises(Conflict) as refusal:
        hold(grant, cut, line)
    assert refusal.value.code == "service.line_already_held"
    assert Redemption.objects.filter(order_line_id=line).count() == 1


def test_a_line_whose_hold_lapsed_can_hold_again_and_the_lapsed_one_is_marked(
    cut, lucia
):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), lucia)
    line = uuid.uuid7()
    lapsed = make_redemption(
        grant,
        cut,
        status="held",
        order_line_id=line,
        hold_until=timezone.now() - dt.timedelta(minutes=1),
    )
    out = hold(grant, cut, line)
    lapsed.refresh_from_db()
    assert (lapsed.status, lapsed.ended_by) == ("expired", "system")
    assert lapsed.ended_at == lapsed.hold_until
    assert Redemption.objects.get(pk=out.id).status == "held"


def test_a_hold_of_a_voucher_that_does_not_exist_is_404(cut):
    with pytest.raises(NotFound) as missing:
        run(
            "service.session.hold",
            {
                "grant_id": str(uuid.uuid7()),
                "service_id": str(cut.id),
                "order_line_id": str(uuid.uuid7()),
            },
        )
    assert missing.value.code == "service.grant_not_found"


def test_a_hold_needs_the_permission_to_spend_sessions(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia)
    with pytest.raises(PermissionDenied):
        run(
            "service.session.hold",
            {
                "grant_id": str(grant.id),
                "service_id": str(cut.id),
                "order_line_id": str(uuid.uuid7()),
            },
            permissions={"service.view_package"},
        )


# ── Release (SERVICE-F23) ───────────────────────────────────────────────────────────────────


def test_releasing_a_hold_gives_the_session_back_at_once(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), lucia)
    held = hold(grant, cut)
    out = run(
        "service.session.release",
        {"id": str(held.id)},
        role="hub_employee",
        actor="ana",
    )
    session = Redemption.objects.get(pk=held.id)
    assert (session.status, session.ended_by, out.status, out.remaining) == (
        "released",
        "ana",
        "released",
        1,
    )
    assert session.ended_at is not None
    assert events("service.session.released") == [
        {"id": str(held.id), "grant_id": str(grant.id)}
    ]
    # The session is there for another line again.
    assert hold(grant, cut).remaining == 0


def test_releasing_twice_or_a_lapsed_hold_changes_nothing_more(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=3), lucia)
    held = hold(grant, cut)
    run("service.session.release", {"id": str(held.id)})
    again = run("service.session.release", {"id": str(held.id)})
    assert again.status == "released"
    assert len(events("service.session.released")) == 1
    expired = make_redemption(
        grant,
        cut,
        status="expired",
        ended_at=timezone.now(),
        order_line_id=uuid.uuid7(),
    )
    assert run("service.session.release", {"id": str(expired.id)}).status == "expired"


@pytest.mark.parametrize("state", ["consumed", "returned"])
def test_a_session_charged_is_not_released(cut, lucia, state):
    grant = make_grant(make_package("Bono", [cut], max_uses=3), lucia)
    session = make_redemption(
        grant, cut, status=state, sale_id=uuid.uuid7(), order_line_id=uuid.uuid7()
    )
    with pytest.raises(Conflict) as refusal:
        run("service.session.release", {"id": str(session.id)})
    assert refusal.value.code == "service.session_settled"


def test_releasing_a_session_that_does_not_exist_is_404():
    with pytest.raises(NotFound) as missing:
        run("service.session.release", {"id": str(uuid.uuid7())})
    assert missing.value.code == "service.session_not_found"


# ── Settle (SERVICE-F24) ────────────────────────────────────────────────────────────────────


def settle(ids, sale_id, customer_id, role="hub_employee"):
    return run(
        "service.session.settle",
        {
            "ids": [str(i) for i in ids],
            "sale_id": str(sale_id),
            "customer_id": str(customer_id) if customer_id else None,
        },
        role=role,
    )


def test_charging_delivers_the_held_sessions_and_links_them_to_the_sale(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia)
    first, second = hold(grant, cut), hold(grant, cut)
    sale = uuid.uuid7()
    out = settle([first.id, second.id], sale, lucia.id)
    assert [row.id for row in out.rows] == [first.id, second.id]
    for session in Redemption.objects.filter(pk__in=[first.id, second.id]):
        assert (session.status, session.sale_id) == ("consumed", sale)
        assert session.settled_at is not None
    assert [row.status for row in out.rows] == ["consumed", "consumed"]
    assert len(events("service.session.settled")) == 2
    assert events("service.session.settled")[0] == {
        "id": str(first.id),
        "grant_id": str(grant.id),
        "sale_id": str(sale),
    }


def test_charging_the_same_sale_again_delivers_nothing_twice(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia)
    held = hold(grant, cut)
    sale = uuid.uuid7()
    settle([held.id], sale, lucia.id)
    assert settle([held.id], sale, lucia.id).rows[0].status == "consumed"
    assert len(events("service.session.settled")) == 1


@pytest.mark.parametrize("state", ["released", "expired", "lapsed", "other_sale"])
def test_a_session_no_longer_held_is_not_charged(cut, lucia, state):
    grant = make_grant(make_package("Bono Cortes", [cut], max_uses=5), lucia)
    held = hold(grant, cut)
    session = Redemption.objects.get(pk=held.id)
    if state == "lapsed":
        session.hold_until = timezone.now() - dt.timedelta(seconds=1)
    elif state == "other_sale":
        session.status, session.sale_id = "consumed", uuid.uuid7()
    else:
        session.status = state
    session.save()
    with pytest.raises(Conflict) as refusal:
        settle([held.id], uuid.uuid7(), lucia.id)
    assert refusal.value.code == "service.hold_lost"
    assert "Bono Cortes" in refusal.value.message


def test_a_sale_of_another_customer_or_of_nobody_does_not_spend_her_voucher(cut, lucia):
    grant = make_grant(make_package("Bono Cortes", [cut], max_uses=5), lucia)
    held = hold(grant, cut)
    for customer in (make_customer("Marta").id, None):
        with pytest.raises(Conflict) as refusal:
            settle([held.id], uuid.uuid7(), customer)
        assert refusal.value.code == "service.hold_customer_mismatch"
        assert "Bono Cortes" in refusal.value.message
    assert Redemption.objects.get(pk=held.id).status == "held"


def test_a_sale_to_the_card_her_card_was_merged_into_spends_it(cut, lucia):
    duplicate = make_customer("Lucia P.")
    grant = make_grant(make_package("Bono", [cut], max_uses=5), duplicate)
    held = hold(grant, cut)
    duplicate.deleted_at, duplicate.merged_into = timezone.now(), lucia
    duplicate.save()
    assert settle([held.id], uuid.uuid7(), lucia.id).rows[0].status == "consumed"


def test_one_session_lost_charges_none_of_them(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), lucia)
    good, gone = hold(grant, cut), hold(grant, cut)
    run("service.session.release", {"id": str(gone.id)})
    with pytest.raises(Conflict):
        settle([good.id, gone.id], uuid.uuid7(), lucia.id)
    assert Redemption.objects.get(pk=good.id).status == "held"


def test_charging_a_session_that_does_not_exist_is_404(lucia):
    with pytest.raises(NotFound) as missing:
        settle([uuid.uuid7()], uuid.uuid7(), lucia.id)
    assert missing.value.code == "service.session_not_found"


def test_settle_takes_one_to_a_hundred_sessions():
    op = get("service.session.settle")
    with pytest.raises(Exception):
        op.input.model_validate(
            {"ids": [], "sale_id": str(uuid.uuid7()), "customer_id": None}
        )
    with pytest.raises(Exception):
        op.input.model_validate(
            {
                "ids": [str(uuid.uuid7()) for _ in range(101)],
                "sale_id": str(uuid.uuid7()),
                "customer_id": None,
            }
        )


# ── Expire (SERVICE-F25) ────────────────────────────────────────────────────────────────────


def test_the_hourly_task_marks_the_holds_past_their_deadline(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=9), lucia)
    now = timezone.now()
    lapsed = make_redemption(
        grant,
        cut,
        status="held",
        order_line_id=uuid.uuid7(),
        hold_until=now - dt.timedelta(minutes=5),
    )
    alive = make_redemption(
        grant,
        cut,
        status="held",
        order_line_id=uuid.uuid7(),
        hold_until=now + dt.timedelta(hours=1),
    )
    op = get("service.session.expire")
    out = op(system_context(A), NoIn())
    assert out.expired == 1
    lapsed.refresh_from_db()
    alive.refresh_from_db()
    assert (lapsed.status, lapsed.ended_by, lapsed.ended_at) == (
        "expired",
        "system",
        lapsed.hold_until,
    )
    assert alive.status == "held"
    # hub#2681: one notice per session the task marks, saying which session of which voucher (WORKBOOK
    # «Lo que avisa»), so whatever follows it knows what changed; a pass that marks nothing says nothing.
    assert events("service.session.expired") == [
        {"id": str(lapsed.id), "grant_id": str(grant.id)}
    ]
    assert op(system_context(A), NoIn()).expired == 0
    assert len(events("service.session.expired")) == 1


def test_the_hourly_task_tells_each_session_it_marks(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=9), lucia)
    other = make_grant(make_package("Other", [cut], max_uses=9), make_customer("Marta"))
    past = timezone.now() - dt.timedelta(minutes=5)
    lapsed = [
        make_redemption(g, cut, status="held", order_line_id=uuid.uuid7(), hold_until=past)
        for g in (grant, grant, other)
    ]
    assert get("service.session.expire")(system_context(A), NoIn()).expired == 3
    assert sorted(
        (e["id"], e["grant_id"]) for e in events("service.session.expired")
    ) == sorted((str(r.id), str(r.grant_id)) for r in lapsed)


def test_only_the_platform_runs_the_hourly_task():
    with pytest.raises(PermissionDenied):
        run("service.session.expire", {}, role="hub_owner")


# ── Return (SERVICE-F26, F27) ───────────────────────────────────────────────────────────────


def give_back(ids, reference, reason="did not like it", role="hub_manager", **ctx):
    return run(
        "service.session.return",
        {"ids": [str(i) for i in ids], "reference": str(reference), "reason": reason},
        role=role,
        **ctx,
    )


def test_a_session_charged_comes_back_with_its_document_and_reason(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=2), lucia)
    session = make_redemption(
        grant, cut, status="consumed", sale_id=uuid.uuid7(), order_line_id=uuid.uuid7()
    )
    refund = uuid.uuid7()
    out = give_back([session.id], refund, actor="boss")
    session.refresh_from_db()
    assert (
        session.status,
        session.return_reference,
        session.return_reason,
        session.ended_by,
    ) == (
        "returned",
        refund,
        "did not like it",
        "boss",
    )
    assert (out.rows[0].status, out.rows[0].remaining, out.rows[0].voucher_expired) == (
        "returned",
        2,
        False,
    )
    assert events("service.session.returned") == [
        {"id": str(session.id), "grant_id": str(grant.id), "reference": str(refund)}
    ]


def test_the_same_document_twice_gives_one_session_back_and_another_one_is_refused(
    cut, lucia
):
    grant = make_grant(make_package("Bono", [cut], max_uses=2), lucia)
    session = make_redemption(grant, cut, status="consumed", sale_id=uuid.uuid7())
    refund = uuid.uuid7()
    give_back([session.id], refund)
    assert give_back([session.id], refund).rows[0].status == "returned"
    assert len(events("service.session.returned")) == 1
    with pytest.raises(Conflict) as refusal:
        give_back([session.id], uuid.uuid7())
    assert refusal.value.code == "service.session_already_returned"


@pytest.mark.parametrize("state", ["held", "released", "expired"])
def test_a_session_never_charged_has_nothing_to_give_back(cut, lucia, state):
    grant = make_grant(make_package("Bono", [cut], max_uses=2), lucia)
    session = make_redemption(
        grant,
        cut,
        status=state,
        order_line_id=uuid.uuid7(),
        hold_until=timezone.now() + dt.timedelta(hours=1),
    )
    with pytest.raises(Conflict) as refusal:
        give_back([session.id], uuid.uuid7())
    assert refusal.value.code == "service.session_not_settled"


def test_a_session_of_an_expired_voucher_comes_back_all_the_same(cut, lucia):
    grant = make_grant(
        make_package("Bono", [cut], max_uses=2, validity_days=30), lucia, days_ago=40
    )
    session = make_redemption(grant, cut, status="consumed", sale_id=uuid.uuid7())
    out = give_back([session.id], uuid.uuid7())
    assert (out.rows[0].status, out.rows[0].voucher_expired) == ("returned", True)


def test_giving_sessions_back_is_the_managers(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=2), lucia)
    session = make_redemption(grant, cut, status="consumed", sale_id=uuid.uuid7())
    with pytest.raises(PermissionDenied):
        give_back([session.id], uuid.uuid7(), role="hub_employee")


def test_erasing_a_card_empties_the_reason_a_session_came_back(cut, lucia):
    grant = make_grant(make_package("Bono", [cut], max_uses=2), lucia)
    session = make_redemption(
        grant,
        cut,
        status="returned",
        ended_at=timezone.now(),
        return_reason="Lucía did not come",
    )
    get("service.grant.forget_customer")(
        system_context(A), get("service.grant.forget_customer").input(id=lucia.id)
    )
    session.refresh_from_db()
    assert session.return_reason == ""


# ── What a session is worth (SERVICE-F24, SALE-F28) ─────────────────────────────────────────


def paid_voucher(cut, lucia, *, amount=10000, uses=3, name="Bono de 100"):
    return make_grant(make_package(name, [cut], max_uses=uses), lucia, amount=amount)


def spend(grant, cut, lucia):
    """One session of ``grant`` held and delivered on a sale of its own; what it came to be worth."""
    return settle([hold(grant, cut).id], uuid.uuid7(), lucia.id).rows[0].value


def adjust(grant, uses_delta):
    return run(
        "service.grant.adjust",
        {"id": str(grant.id), "uses_delta": uses_delta, "reason": "courtesy"},
    )


def test_three_sessions_of_100_euros_add_up_to_the_cent(cut, lucia):
    # flow: SERVICE-F24: what is left of the price ÷ the sessions left, half up; nothing lost, nothing made up.
    grant = paid_voucher(cut, lucia)
    worth = [spend(grant, cut, lucia) for _ in range(3)]
    assert worth == [3333, 3334, 3333]
    assert sum(worth) == 10000


def test_sessions_delivered_together_are_worth_the_same_as_one_by_one(cut, lucia):
    grant = paid_voucher(cut, lucia)
    held = [hold(grant, cut).id for _ in range(3)]
    out = settle(held, uuid.uuid7(), lucia.id)
    assert [row.value for row in out.rows] == [3333, 3334, 3333]
    assert list(
        Redemption.objects.filter(pk__in=held).order_by("id").values_list("value", flat=True)
    ) == [3333, 3334, 3333]


def test_a_session_is_worth_nothing_until_it_is_delivered(cut, lucia):
    grant = paid_voucher(cut, lucia)
    held = hold(grant, cut)
    assert held.value is None
    assert Redemption.objects.get(pk=held.id).value is None


def test_a_held_session_nobody_charged_takes_no_share_of_the_price(cut, lucia):
    grant = paid_voucher(cut, lucia)
    released = hold(grant, cut)
    run("service.session.release", {"id": str(released.id)}, role="hub_employee")
    # Still in its hold when the next one is delivered: it is one of the sessions left, with no money taken.
    hold(grant, cut)
    assert spend(grant, cut, lucia) == 3333


def test_delivering_the_same_sale_again_does_not_value_the_session_again(cut, lucia):
    grant = paid_voucher(cut, lucia)
    held = hold(grant, cut)
    sale = uuid.uuid7()
    assert settle([held.id], sale, lucia.id).rows[0].value == 3333
    adjust(grant, 3)
    assert settle([held.id], sale, lucia.id).rows[0].value == 3333
    assert Redemption.objects.get(pk=held.id).value == 3333


def test_a_courtesy_session_shares_what_is_left_of_the_price(cut, lucia):
    # The money paid does not grow: the voucher is never worth more than it was paid for.
    grant = paid_voucher(cut, lucia)
    worth = [spend(grant, cut, lucia)]
    adjust(grant, 1)
    worth += [spend(grant, cut, lucia) for _ in range(3)]
    assert worth == [3333, 2222, 2223, 2222]
    assert sum(worth) == 10000


def test_a_session_taken_off_leaves_its_share_to_the_ones_left(cut, lucia):
    grant = paid_voucher(cut, lucia)
    worth = [spend(grant, cut, lucia)]
    adjust(grant, -1)
    worth.append(spend(grant, cut, lucia))
    assert worth == [3333, 6667]


def test_a_session_given_back_gives_its_share_back_to_the_voucher(cut, lucia):
    grant = paid_voucher(cut, lucia)
    first = hold(grant, cut)
    sale = uuid.uuid7()
    second = hold(grant, cut)
    settled = settle([first.id, second.id], sale, lucia.id)
    assert [row.value for row in settled.rows] == [3333, 3334]
    run(
        "service.session.return",
        {"ids": [str(second.id)], "reference": str(uuid.uuid7()), "reason": "did not come"},
    )
    # What it was worth stays on its own row: its trail never moves.
    assert Redemption.objects.get(pk=second.id).value == 3334
    worth = [spend(grant, cut, lucia), spend(grant, cut, lucia)]
    assert worth == [3334, 3333]
    assert 3333 + sum(worth) == 10000


def test_a_session_spent_outside_the_till_takes_its_share_of_the_price(cut, lucia):
    # flow: SERVICE-F21: nobody's production (it does not say who did it), but the sessions left are one fewer.
    grant = paid_voucher(cut, lucia)
    outside = run("service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)})
    assert Redemption.objects.get(pk=outside.id).value == 3333
    assert [spend(grant, cut, lucia), spend(grant, cut, lucia)] == [3334, 3333]


def test_a_voucher_given_for_free_is_worth_nothing_per_session(cut, lucia):
    grant = paid_voucher(cut, lucia, amount=0)
    assert spend(grant, cut, lucia) == 0


def test_an_unlimited_voucher_has_no_sessions_to_divide_its_price_by(cut, lucia):
    grant = paid_voucher(cut, lucia, uses=None)
    assert spend(grant, cut, lucia) is None


def test_the_catalog_changing_later_does_not_move_the_voucher_sold(cut, lucia):
    # The price paid and the sessions were frozen when it was sold (SERVICE-F14).
    grant = paid_voucher(cut, lucia)
    first = spend(grant, cut, lucia)
    run(
        "service.package.update",
        {"id": str(grant.package_id), "max_uses": 10, "fixed_price": 50000},
    )
    assert [first, spend(grant, cut, lucia), spend(grant, cut, lucia)] == [3333, 3334, 3333]


def test_a_voucher_repaired_by_hand_never_breaks_a_charge(cut, lucia):
    # Support repairs sessions in the admin (test_admin): more delivered than it has, or worth more than it was paid.
    over = paid_voucher(cut, lucia, uses=2, name="Bono de más")
    held = hold(over, cut)
    for _ in range(2):
        make_redemption(over, cut, status=Redemption.Status.CONSUMED, value=1000)
    assert settle([held.id], uuid.uuid7(), lucia.id).rows[0].value == 8000
    spent = paid_voucher(cut, lucia, name="Bono gastado")
    held = hold(spent, cut)
    make_redemption(spent, cut, status=Redemption.Status.CONSUMED, value=20000)
    assert settle([held.id], uuid.uuid7(), lucia.id).rows[0].value == 0
