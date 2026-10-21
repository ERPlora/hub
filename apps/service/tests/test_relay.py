"""Services hears Customers and Staff through the worker's outbox relay, end to end (SERVICE-F28, F29, F32).

The real Customers and Staff operations write their events; one tick of the worker's real loop (``base.worker.run``,
which runs ``base.relay``) hands them to this app's reactions, and the vouchers of a merged card move to the one
that stays, an erased card's vouchers lose their free texts, or the professional who left stops performing every
service. Once: another tick, or the same notice delivered again, changes nothing. What hub B does runs in B and is
heard in B only.
"""

import json
import threading

import psycopg
import pytest
from django.db.backends.base.base import BaseDatabaseWrapper
from django.utils import timezone
from live.context import Scope
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.service.models import Assignment, Grant, Redemption
from base import catalog, worker
from base.catalog import RegisterResult
from base.models import EventDelivery

from .conftest import A, B, ctx_for, make_package, make_redemption, make_service, make_tax

REGISTERED = RegisterResult(written=0, retired=0, docs_changed=0, skipped=True)


def run(name: str, data: dict, scope: Scope = A):
    op = get(name)
    return op(ctx_for(scope=scope), op.input.model_validate(data))


@pytest.fixture
def tick(monkeypatch):
    """One tick of the worker's real loop, without the SaaS (``register_apps``) and, inside a test's transaction,
    without releasing the connections (that would close the test's own)."""
    monkeypatch.setattr(catalog, "register_apps", lambda: REGISTERED)
    monkeypatch.setattr(BaseDatabaseWrapper, "close_if_unusable_or_obsolete", lambda self: None)

    def once() -> None:
        stop = threading.Event()

        def wait(_seconds: float) -> bool:
            stop.set()
            return True

        now = timezone.now()
        assert worker.run(stop, tick_seconds=0, wait=wait, clock=lambda: now) == 0

    return once


def newest(name: str) -> OutboxEvent:
    return OutboxEvent.objects.filter(name=name).latest("created_at", "id")


def delivered(name: str) -> tuple[str, int]:
    """``(status, attempts)`` of the delivery of the newest ``name`` event to Services."""
    row = EventDelivery.objects.get(event=newest(name), app_label="service")
    return row.status, row.attempts


def deliver_again(name: str) -> None:
    """The relay owes Services the newest ``name`` event once more: the next tick hands it over again."""
    EventDelivery.objects.filter(event=newest(name), app_label="service").update(
        status=EventDelivery.Status.PENDING, delivered_at=None, next_attempt_at=timezone.now()
    )


def recorded(name: str) -> int:
    return OutboxEvent.objects.filter(name=name).count()


def sell(customer, *, scope: Scope = A, **data):
    return run(
        "service.grant.create",
        {"package": "Bono 5 cortes", "customer_id": str(customer.id), **data},
        scope,
    )


@pytest.fixture
def cut(db):
    return make_service("Cut", tax=make_tax(), price=2000, duration_minutes=30)


@pytest.fixture
def bono(cut):
    return make_package("Bono 5 cortes", [cut], max_uses=5, validity_days=180)


# ── SERVICE-F28: two cards merged in Customers ────────────────────────────────────────────────


def balances(customer) -> dict:
    """``{voucher: (used, left, status)}`` of the vouchers listed on ``customer``'s card."""
    page = run("service.grant.list", {"customer_id": str(customer.id)})
    assert page.total == len(page.rows)
    return {row.id: (row.used, row.remaining, row.status) for row in page.rows}


def test_two_cards_merged_in_customers_take_every_voucher_to_the_one_that_stays(bono, tick):
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    twin = run("customer.customer.create", {"name": "Lucia P."})
    # Two purchases of the same package stay two vouchers, each with its balance; a voided one moves too.
    first, second, wrong = (sell(twin) for _ in range(3))
    run("service.grant.redeem", {"id": str(first.id)})
    run("service.grant.adjust", {"id": str(second.id), "uses_delta": 1, "reason": "Courtesy"})
    run("service.grant.void", {"id": str(wrong.id), "reason": "Sold twice"})
    run("customer.customer.merge", {"id": str(lucia.id), "absorbed_id": str(twin.id)})
    # Her card already lists them (read through the merged card) while the vouchers still name the twin.
    shown = balances(lucia)
    assert set(Grant.objects.values_list("customer_id", flat=True)) == {twin.id}

    tick()

    assert delivered("customer.customer.merged") == ("delivered", 1)
    assert set(Grant.objects.values_list("customer_id", flat=True)) == {lucia.id}
    # Each voucher once, as before the move: nothing counted twice.
    assert balances(lucia) == shown == {
        first.id: (1, 4, "active"),
        second.id: (0, 6, "active"),
        wrong.id: (0, 5, "voided"),
    }
    names = {row.customer_name for row in run("service.grant.list", {"customer_id": str(lucia.id)}).rows}
    assert names == {"Lucía Pérez"}
    assert run("service.grant.list", {"customer_id": str(twin.id)}).total == 0
    assert run("service.grant.list_orphans", {}).total == 0
    assert recorded("service.grant.reassigned") == 1
    stamps = dict(Grant.objects.values_list("id", "updated_at"))

    tick()
    deliver_again("customer.customer.merged")
    tick()

    assert delivered("customer.customer.merged") == ("delivered", 2)
    assert balances(lucia) == shown
    assert dict(Grant.objects.values_list("id", "updated_at")) == stamps
    assert recorded("service.grant.reassigned") == 1


# ── SERVICE-F29: a card erased in Customers (GDPR) ───────────────────────────────────────────


def free_texts() -> dict:
    """Every free text Services keeps on a voucher, by its owner's card id: through the lists of this app."""
    texts: dict = {}
    for row in run("service.grant.list", {"package": "Bono 5 cortes", "limit": 100}).rows:
        texts.setdefault(row.customer_id, set()).update({row.note, row.void_reason} - {""})
    for row in run("service.movement.list", {"package": "Bono 5 cortes", "limit": 100}).rows:
        texts.setdefault(row.customer_id, set()).update({row.note, row.reason} - {""})
    return texts


def test_a_card_erased_in_customers_loses_every_free_text_of_its_vouchers(bono, cut, tick):
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    eva = run("customer.customer.create", {"name": "Eva Sanz"})
    kept = sell(lucia, amount=9000, note="Lucía, cash")
    run("service.grant.redeem", {"id": str(kept.id), "note": "Lucía came on Friday"})
    run("service.grant.adjust", {"id": str(kept.id), "uses_delta": 1, "reason": "Lucía was ill"})
    make_redemption(
        Grant.objects.get(pk=kept.id),
        cut,
        note="Booked by Lucía",
        status=Redemption.Status.RETURNED,
        ended_at=timezone.now(),
        return_reason="Lucía cancelled",
    )
    wrong = sell(lucia, note="For Lucía's sister")
    run("service.grant.void", {"id": str(wrong.id), "reason": "Lucía asked for another"})
    evas = sell(eva, note="Eva, card")
    run("service.grant.redeem", {"id": str(evas.id), "note": "Eva on Monday"})
    run("customer.customer.erase", {"id": str(lucia.id), "reason": "GDPR request"})
    assert free_texts()[lucia.id] == {
        "Lucía, cash",
        "Lucía came on Friday",
        "Lucía was ill",
        "Booked by Lucía",
        "Lucía cancelled",
        "For Lucía's sister",
        "Lucía asked for another",
    }

    tick()

    assert delivered("customer.customer.erased") == ("delivered", 1)
    assert free_texts() == {lucia.id: set(), eva.id: {"Eva, card", "Eva on Monday"}}
    # The voucher keeps her reference, its amount and its sessions: it is what matches it with the sale.
    [orphan] = run("service.grant.list_orphans", {}).rows
    assert (orphan.id, orphan.customer_id, orphan.remaining) == (kept.id, lucia.id, 5)
    assert Grant.objects.get(pk=kept.id).amount == 9000
    assert recorded("service.grant.erased") == 1

    tick()
    deliver_again("customer.customer.erased")
    tick()
    # Customers announces the erasure every time it is asked again: Services hears it and writes nothing.
    run("customer.customer.erase", {"id": str(lucia.id), "reason": "GDPR request"})
    tick()

    assert recorded("customer.customer.erased") == 2
    assert delivered("customer.customer.erased") == ("delivered", 1)
    assert free_texts() == {lucia.id: set(), eva.id: {"Eva, card", "Eva on Monday"}}
    assert recorded("service.grant.erased") == 1


def test_a_card_erased_right_after_a_duplicate_was_merged_into_it_loses_the_duplicates_texts_too(bono, tick):
    # Merging and erasing before the next tick: the relay hands both over, in the order they happened.
    lucia = run("customer.customer.create", {"name": "Lucía Pérez"})
    twin = run("customer.customer.create", {"name": "Lucia P."})
    sold = sell(twin, note="Lucia P., cash")
    run("customer.customer.merge", {"id": str(lucia.id), "absorbed_id": str(twin.id)})
    run("customer.customer.erase", {"id": str(lucia.id), "reason": "GDPR request"})

    tick()

    grant = Grant.objects.get(pk=sold.id)
    assert (grant.customer_id, grant.note) == (lucia.id, "")
    assert free_texts() == {lucia.id: set()}


# ── SERVICE-F32: a professional who leaves in Staff ──────────────────────────────────────────


def performers(service: str) -> list[str]:
    return [row.member_name for row in run("service.assignment.list", {"service": service}).rows]


def test_a_professional_who_leaves_in_staff_stops_performing_every_service(cut, tick):
    make_service("Colour", tax=make_tax("test.colour", "Colour"))
    ana = run("staff.member.create", {"first_name": "Ana", "last_name": "López"})
    run("staff.member.create", {"first_name": "Bea", "last_name": "Ruiz"})
    for service, member in (("Cut", "Ana López"), ("Colour", "Ana López"), ("Cut", "Bea Ruiz")):
        run("service.assignment.assign", {"service": service, "member": member, "is_primary": service == "Cut"})
    run("staff.member.terminate", {"id": str(ana.id), "reason": "Moved away"})
    # Out of the lists at once; her assignments wait for the relay.
    assert (performers("Cut"), performers("Colour")) == (["Bea Ruiz"], [])
    assert Assignment.objects.filter(member_id=ana.id).count() == 2

    tick()

    assert delivered("staff.member.terminated") == ("delivered", 1)
    assert not Assignment.objects.filter(member_id=ana.id).exists()
    assert (performers("Cut"), performers("Colour")) == (["Bea Ruiz"], [])
    [bea] = run("service.assignment.eligible", {"service": "Cut"}).rows
    assert (bea.full_name, bea.is_primary) == ("Bea Ruiz", True)
    assert recorded("service.assignment.removed") == 2

    tick()
    deliver_again("staff.member.terminated")
    tick()

    assert delivered("staff.member.terminated") == ("delivered", 2)
    assert performers("Cut") == ["Bea Ruiz"]
    assert recorded("service.assignment.removed") == 2


# ── Two hubs: what B does runs in B and is heard in B only ───────────────────────────────────


@pytest.fixture
def listen(transactional_db, db_dsn):
    sessions = []

    def open_session(scope: Scope):
        session = psycopg.connect(db_dsn, autocommit=True)
        sessions.append(session)
        session.execute(f"LISTEN {channel_for(scope)}")
        return session

    yield open_session
    for session in sessions:
        session.close()


def heard(session, timeout: float = 0.5) -> set[str]:
    return {name for note in session.notifies(timeout=timeout) for name in json.loads(note.payload)["events"]}


def test_what_hub_b_does_reaches_its_vouchers_and_team_and_is_heard_in_b_only(listen, tick):
    on_a, on_b = listen(A), listen(B)
    make_package("Bono 5 cortes", [make_service("Cut", tax=make_tax())], max_uses=5)
    # Hub A: Marta's voucher and Carla, who does cuts.
    marta = run("customer.customer.create", {"name": "Marta Gil"})
    martas = sell(marta, note="Marta, cash")
    carla = run("staff.member.create", {"first_name": "Carla", "last_name": "Ruiz"})
    run("service.assignment.assign", {"service": "Cut", "member": "Carla Ruiz"})
    # Hub B: two cards merged, one erased and a professional who leaves.
    keep = run("customer.customer.create", {"name": "Lucía Pérez"}, B)
    twin = run("customer.customer.create", {"name": "Lucia P."}, B)
    twins = sell(twin, scope=B)
    gone = run("customer.customer.create", {"name": "Eva Sanz"}, B)
    sell(gone, scope=B, note="Eva, card")
    dani = run("staff.member.create", {"first_name": "Dani", "last_name": "Gil"}, B)
    run("service.assignment.assign", {"service": "Cut", "member": "Dani Gil"}, B)
    run("customer.customer.merge", {"id": str(keep.id), "absorbed_id": str(twin.id)}, B)
    run("customer.customer.erase", {"id": str(gone.id), "reason": "GDPR request"}, B)
    run("staff.member.terminate", {"id": str(dani.id), "reason": "Moved away"}, B)
    heard(on_a), heard(on_b)  # the operations' own notices

    tick()

    assert {"service.grant.reassigned", "service.grant.erased", "service.assignment.removed"} <= heard(on_b)
    assert heard(on_a) == set()
    assert Grant.objects.get(pk=twins.id).customer_id == keep.id
    assert not Assignment.objects.filter(member_id=dani.id).exists()
    # A's voucher and team are untouched.
    assert Grant.objects.filter(pk=martas.id, customer_id=marta.id, note="Marta, cash").exists()
    assert performers("Cut") == ["Carla Ruiz"]
    # The positive control: Carla leaves in A, and A hears it.
    run("staff.member.terminate", {"id": str(carla.id), "reason": "Moved away"})
    heard(on_a)

    tick()

    assert "service.assignment.removed" in heard(on_a)
    assert heard(on_b) == set()
