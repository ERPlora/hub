"""The movements of a voucher: its sessions and adjustments, most recent first, every state of a session, the
professional who did it and how they page."""

import datetime as dt
import uuid

from django.db import connections
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.service.models.grants import GrantAdjustment
from apps.service.schemas.movements import MovementListIn

from base.tenancy.context import current_alias

from .conftest import HUB_DB, make_customer, make_grant, make_member, make_package, make_redemption, make_service, run

pytestmark = HUB_DB


def test_the_movements_of_a_package_are_its_sessions_and_adjustments_most_recent_first(
    tax,
):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=5)
    lucia = make_customer("Lucía")
    grant = make_grant(package, lucia, days_ago=3)
    now = timezone.now()
    first = make_redemption(
        grant, cut, redeemed_at=now - dt.timedelta(days=2), actor="ana"
    )
    courtesy = GrantAdjustment.objects.create(
        grant=grant,
        uses_delta=1,
        days_delta=10,
        reason="closed",
        actor="boss",
        created_at=now - dt.timedelta(days=1),
    )
    correction = GrantAdjustment.objects.create(
        grant=grant, uses_delta=-1, reason="typo", actor="boss", created_at=now
    )
    make_redemption(make_grant(make_package("Other", max_uses=1), lucia))
    page = run("service.movement.list", MovementListIn(package="Bono"))
    assert [(row.kind, row.id) for row in page.rows] == [
        ("corrected", correction.id),
        ("adjusted", courtesy.id),
        ("consumed", first.id),
    ]
    assert (
        page.total,
        page.rows[2].service_name,
        page.rows[2].customer_name,
        page.rows[2].actor,
    ) == (3, "Cut", "Lucía", "ana")
    assert (page.rows[1].uses_delta, page.rows[1].days_delta, page.rows[1].reason) == (
        1,
        10,
        "closed",
    )
    second_page = run(
        "service.movement.list",
        MovementListIn(package_id=package.id, limit=2, offset=2),
    )
    assert [row.id for row in second_page.rows] == [first.id]


def test_a_session_of_the_movements_says_the_professional_who_did_it(tax):
    # flow: SERVICE-F19, SERVICE-F21 (hub#1236): a session spent saying who did it shows her, like its customer; one
    # said by nobody and a courtesy show nobody. Before, MovementOut had no professional at all.
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=5)
    grant = make_grant(package, make_customer("Lucía"), days_ago=3)
    now = timezone.now()
    ana = make_member("Ana", "López")
    hers = make_redemption(grant, cut, member=ana, redeemed_at=now - dt.timedelta(days=2))
    nobodys = make_redemption(grant, cut, redeemed_at=now - dt.timedelta(days=1))
    courtesy = GrantAdjustment.objects.create(grant=grant, uses_delta=1, reason="gift", actor="boss", created_at=now)
    rows = {row.id: row for row in run("service.movement.list", MovementListIn(package_id=package.id)).rows}
    assert [(rows[key].member_id, rows[key].member_name) for key in (hers.id, nobodys.id, courtesy.id)] == [
        (ana.id, "Ana López"),
        (None, None),
        (None, None),
    ]


def test_naming_the_professional_of_each_session_costs_no_query_per_row(tax):
    # hub#1236: the professional is read with her session (select_related), so a voucher with many sessions done by
    # many professionals reads in as many queries as one with a single session.
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=10)
    grant = make_grant(package, make_customer("Lucía"), days_ago=1)
    make_redemption(grant, cut, member=make_member("Ana", "López"))

    def reads() -> int:
        with CaptureQueriesContext(connections[current_alias()]) as queries:
            run("service.movement.list", MovementListIn(package_id=package.id))
        return len(queries)

    reads()  # The first read also warms what the operation caches once.
    one = reads()
    for first_name in ("Bea", "Carla", "Dora"):
        make_redemption(grant, cut, member=make_member(first_name, "Gil"))
    assert reads() == one


# ── Sessions of the till (SERVICE-F22–F27) ───────────────────────────────────────────────────

def test_the_movements_show_every_state_of_a_session(tax):
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=9)
    grant = make_grant(package, make_customer("Lucía"), days_ago=2)
    now = timezone.now()
    held = make_redemption(
        grant,
        cut,
        status="held",
        hold_until=now + dt.timedelta(hours=5),
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=6),
    )
    lapsed = make_redemption(
        grant,
        cut,
        status="held",
        hold_until=now - dt.timedelta(hours=1),
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=25),
    )
    released = make_redemption(
        grant,
        cut,
        status="released",
        order_line_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=10),
        ended_at=now - dt.timedelta(hours=9),
        ended_by="ana",
    )
    returned = make_redemption(
        grant,
        cut,
        status="returned",
        sale_id=uuid.uuid7(),
        redeemed_at=now - dt.timedelta(hours=30),
        ended_at=now - dt.timedelta(hours=2),
        ended_by="boss",
        return_reason="did not come",
    )
    page = run("service.movement.list", MovementListIn(package_id=package.id))
    rows = {row.id: row for row in page.rows}
    assert (rows[held.id].kind, rows[held.id].uses_delta) == ("held", -1)
    # A hold past its deadline reads as expired, at its deadline, before the task marks it.
    assert (rows[lapsed.id].kind, rows[lapsed.id].uses_delta, rows[lapsed.id].at) == (
        "expired",
        0,
        lapsed.hold_until,
    )
    assert (rows[released.id].kind, rows[released.id].at, rows[released.id].actor) == (
        "released",
        released.ended_at,
        "ana",
    )
    assert (
        rows[returned.id].kind,
        rows[returned.id].uses_delta,
        rows[returned.id].reason,
        rows[returned.id].actor,
    ) == ("returned", 0, "did not come", "boss")
    # Each row is dated by its last step (released, expired, given back, held), the latest first.
    assert [row.id for row in page.rows] == [lapsed.id, returned.id, held.id, released.id]


def test_the_movements_page_through_sessions_at_the_same_instant_each_once(tax):
    # SERVICE-F19: sessions spent at the same instant (a bulk grant, an import) tie on their
    # date; page after page every movement shows exactly once and the total is the whole set's, not the page's.
    cut = make_service("Cut", tax=tax)
    package = make_package("Bono", [cut], max_uses=None)
    grant = make_grant(package, make_customer("Lucía"), days_ago=1)
    instant = timezone.now() - dt.timedelta(hours=1)
    # Sessions and adjustments made one after the other, so that every page needs some of each.
    made = []
    for turn in range(7):
        if turn % 2:
            made.append(
                GrantAdjustment.objects.create(
                    grant=grant, days_delta=1, reason="closed", actor="boss", created_at=instant
                ).id
            )
        else:
            made.append(make_redemption(grant, cut, redeemed_at=instant).id)
    seen = []
    for offset in range(0, 8, 2):
        page = run(
            "service.movement.list",
            MovementListIn(package_id=package.id, limit=2, offset=offset),
        )
        assert page.total == 7
        seen += [row.id for row in page.rows]
    # The tie is broken the same way on every page: the newest id first.
    assert seen == made[::-1]
