"""The Hub admin's «Delete» of a card and the customer app's writes at once: real sessions in threads, real row
locks.

A void or a refund of a sale finds the card of its purchase and then locks it: a card the Hub admin deleted
between the two (its purchases go with it) leaves nothing to void or refund, as a sale with no purchase does,
never a 500. The Hub admin's «Delete» of a card (its page and the list's «Delete selected») locks it before
Django gathers what hangs from it: a write under way that holds the card and adds to it (a note, a purchase, a
consent, a value, a group, its health data) is waited for and what it added goes too, instead of failing at the
COMMIT; a write that comes second waits for the deletion and finds the card gone. The same for a group, a tag or
a custom field a write names, and a card and its duplicate are taken as a merge and an erasure take them, so
none of them waits in a circle.
"""

import uuid
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from django.db import connections
from live.context import system_context
from live.errors import InvalidPayload, NotFound
from live.models import OutboxEvent
from live.operations import atomic, get

from apps.customer import events
from apps.customer.models import (
    Activity,
    Consent,
    Customer,
    CustomerGroup,
    CustomerTag,
    CustomField,
    CustomFieldValue,
    HealthRecord,
    OrderLink,
    Purchase,
)
from apps.customer.schemas.activity import NoteIn
from apps.customer.schemas.cards import CustomerPatchIn
from apps.customer.schemas.consent import ConsentGrantIn
from apps.customer.schemas.erasing import EraseIn
from apps.customer.schemas.fields import GroupRefIn
from apps.customer.schemas.health import HealthGrantIn, HealthIn
from apps.customer.schemas.memberships import SetGroupsIn, SetTagsIn
from apps.customer.schemas.merging import MergeIn
from apps.customer.schemas.orders import OrderLinkIn
from apps.customer.schemas.purchases import PurchaseRecordIn, PurchaseRefundIn, PurchaseVoidIn
from apps.customer.queries.reads import CUSTOMER_UNAVAILABLE_CODE
from apps.sale.tests.test_concurrency import delete_page_while_held, in_turn, locks
from base.tenancy.context import current_alias
from base.tenancy.tests.concurrency import HOW, admin_delete, at_once, meanwhile

from .conftest import HUB_DB_COMMITTED, A, reads, run

#: Several sessions of the business at once, each committing: its plan has room for them all.
pytestmark = [HUB_DB_COMMITTED, pytest.mark.usefixtures("plan_with_room")]

NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"


def card(name="Ana García", **fields) -> Customer:
    return Customer.objects.create(name=name, **fields)


def system(name: str, data):
    return get(name)(system_context(A), data)


def record(customer: Customer, sale, total=500):
    return system(
        "customer.purchase.record",
        PurchaseRecordIn(customer_id=customer.id, sale_id=sale, total=total, purchased_at=NOW),
    )


def void(sale):
    return system("customer.purchase.void", PurchaseVoidIn(sale_id=sale, reason="mistake"))


def refund(sale, refund_id=None):
    data = PurchaseRefundIn(sale_id=sale, refund_id=refund_id or uuid.uuid7(), total=200)
    return system("customer.purchase.refund", data)


def gone(answer, *targets) -> None:
    """The Hub admin deleted ``targets``: its answer is the redirect back to the list, never an error."""
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302, answer.content[:500]
    assert not Customer.objects.filter(pk__in=[target.pk for target in targets]).exists()


def with_lock_timeout(deletion):
    """``deletion`` in a transaction that gives up after LOCK_TIMEOUT on a row another session holds. The lock
    timeout is the transaction's (SET LOCAL): a session-level one would go back with the connection and reach
    the tests after this one."""

    def call():
        with atomic():
            with connections[current_alias()].cursor() as cursor:
                cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
            return deletion()

    return call


@contextmanager
def deleted_just_before(statement: Callable[[str], bool], deletion):
    """Runs ``deletion`` in another session right before the first statement of this one that ``statement``
    accepts (the lock on the row it found): between the read that found it and that statement, every time. It
    commits, or waits for this session when it holds the row (and gives up). Yields its outcome."""
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        if not deletions and statement(sql):
            deletions.extend(at_once(with_lock_timeout(deletion)))
        return execute(sql, params, many, context)

    with connections[current_alias()].execute_wrapper(wrapper):
        yield deletions
    assert deletions, "the statement never ran"


# ── A void or a refund whose card the Hub admin deletes after finding it ─────────────────────────────
#
# Both read the purchase's card unlocked (a merge locks the cards before their purchases) and then lock it. The
# Hub admin's «Delete» of the card removes it and, with it, its purchases: the lock found nothing, a
# ``Customer.DoesNotExist`` (500) that the outbox relay would retry for ever. Nothing is left to void or
# refund, the answer of a sale without purchase.

PURCHASE_WRITES = {
    "void": (void, {"voided": False}),
    "refund": (refund, {"refunded": False}),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(PURCHASE_WRITES))
def test_a_void_or_a_refund_whose_card_the_hub_admin_deleted_after_finding_it_finds_nothing(
    hub_staff, write, how
):
    ana = card()
    sale = uuid.uuid7()
    record(ana, sale)
    OutboxEvent.objects.all().delete()
    write_call, nothing = PURCHASE_WRITES[write]
    with deleted_just_before(locks("customer_customer"), admin_delete(hub_staff, how, ana)) as answers:
        out = write_call(sale)
    [answer] = answers
    gone(answer, ana)
    assert out.model_dump(include=set(nothing)) == nothing
    assert not Purchase.objects.exists()
    assert not OutboxEvent.objects.exists()


def test_a_void_follows_its_purchase_to_the_card_a_merge_kept_when_the_hub_admin_deleted_the_other(
    hub_staff,
):
    survivor, absorbed = card("Ana"), card("ana")
    sale = uuid.uuid7()
    record(absorbed, sale)

    def merge_then_delete_the_duplicate():
        run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))
        return admin_delete(hub_staff, "page", absorbed)()

    with deleted_just_before(locks("customer_customer"), merge_then_delete_the_duplicate) as answers:
        out = void(sale)
    [answer] = answers
    gone(answer, absorbed)
    assert out.voided is True
    survivor.refresh_from_db()
    assert (survivor.total_purchases, survivor.total_spent) == (0, 0)
    assert Purchase.objects.get().status == Purchase.Status.VOIDED


def test_a_void_whose_purchase_the_hub_admin_deleted_after_its_card_was_locked_finds_nothing(
    hub_staff,
):
    ana = card()
    sale = uuid.uuid7()
    record(ana, sale)
    purchase = Purchase.objects.get()
    with deleted_just_before(
        locks("customer_purchase"), admin_delete(hub_staff, "page", purchase)
    ) as answers:
        out = void(sale)
    [answer] = answers
    assert answer.status_code == 302
    assert out.voided is False
    ana.refresh_from_db()
    assert (ana.total_purchases, ana.total_spent) == (1, 500)


# ── The Hub admin's «Delete» of a card a write holds ─────────────────────────────────────────────────
#
# Django's «Delete» gathers what hangs from the card (its activity, purchases, consents, values, groups, health
# data, order links) and deletes the card last. A write under way held the card and added a row to it: the
# deletion missed that row, waited for the card and then deleted it, and the database refused it at the COMMIT
# (an IntegrityError, a 500). Locked first, the deletion waits for the write and takes what it added; a write
# that comes second waits for the deletion and finds the card gone.


def _field_value(ana):
    field = CustomField.objects.create(name="Shoe size", field_type="text")
    return lambda: run(
        "customer.customer.update",
        CustomerPatchIn(id=ana.id, field_values=[{"field_id": field.id, "value": "38"}]),
    )


def _group(ana):
    group = CustomerGroup.objects.create(name="VIP")
    return lambda: run("customer.customer.set_groups", SetGroupsIn(id=ana.id, group_ids=[group.id]))


def _health(ana):
    run(
        "customer.health.grant",
        HealthGrantIn(customer_id=ana.id, notice_text="I agree.", notice_version="v1"),
    )
    return lambda: run("customer.health.update", HealthIn(customer_id=ana.id, allergies="Latex"))


def _purchase_then(write):
    def prepare(ana):
        sale = uuid.uuid7()
        record(ana, sale)
        return lambda: write(sale)

    return prepare


#: Writes that lock a card and add to what hangs from it; each prepares what it needs and returns the write.
CARD_WRITES = {
    "note": lambda ana: lambda: run("customer.note.add", NoteIn(customer_id=ana.id, content="Mornings")),
    "consent": lambda ana: lambda: run(
        "customer.consent.grant", ConsentGrantIn(customer_id=ana.id, channel="email")
    ),
    "order link": lambda ana: lambda: run(
        "customer.order.link", OrderLinkIn(order_id=uuid.uuid7(), customer_id=ana.id)
    ),
    "purchase": lambda ana: lambda: record(ana, uuid.uuid7()),
    "void": _purchase_then(void),
    "refund": _purchase_then(refund),
    "custom value": _field_value,
    "group": _group,
    "health": _health,
}
#: What hangs from a card, all of which goes with it.
HANGING = (Activity, Purchase, Consent, OrderLink, CustomFieldValue, HealthRecord)


def nothing_hangs_from(ana) -> None:
    for model in HANGING:
        assert not model.objects.filter(customer_id=ana.pk).exists(), model.__name__
    assert not Customer.groups.through.objects.filter(customer_id=ana.pk).exists()


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(CARD_WRITES))
def test_the_hub_admin_deletes_a_card_a_write_holds_once_it_is_written(hub_staff, write, how):
    ana = card()
    write_call = CARD_WRITES[write](ana)
    with meanwhile(locks("customer_customer"), admin_delete(hub_staff, how, ana)) as answers:
        write_call()
    [answer] = answers
    gone(answer, ana)
    nothing_hangs_from(ana)


#: Writes that come second, once the Hub admin's «Delete» holds the card, and what each answers then.
SECOND_WRITES = {
    "note": (
        lambda ana: lambda: run("customer.note.add", NoteIn(customer_id=ana.id, content="Mornings")),
        CUSTOMER_UNAVAILABLE_CODE,
    ),
    "purchase": (lambda ana: lambda: record(ana, uuid.uuid7()), {"recorded": False}),
    "void": (_purchase_then(void), {"voided": False}),
    "refund": (_purchase_then(refund), {"refunded": False}),
}


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(SECOND_WRITES))
def test_a_write_while_the_hub_admin_deletes_the_card_finds_it_gone(hub_staff, write, how):
    ana = card()
    prepare, expected = SECOND_WRITES[write]
    write_call = prepare(ana)
    with meanwhile(locks("customer_customer"), write_call) as outcomes:
        answer = admin_delete(hub_staff, how, ana)()
    gone(answer, ana)
    [outcome] = outcomes
    if isinstance(expected, str):
        assert isinstance(outcome, NotFound), outcome
        assert (outcome.status, outcome.code) == (404, expected)
    else:
        assert not isinstance(outcome, Exception), outcome
        assert outcome.model_dump(include=set(expected)) == expected
    nothing_hangs_from(ana)


@pytest.mark.parametrize(
    "make",
    [
        card,
        lambda: CustomerGroup.objects.create(name="VIP"),
        lambda: CustomerTag.objects.create(name="Allergic"),
        lambda: CustomField.objects.create(name="Shoe size", field_type="text"),
    ],
    ids=["card", "group", "tag", "custom field"],
)
def test_the_hub_admin_confirmation_page_of_a_row_a_write_holds_does_not_wait(hub_staff, make):
    """The delete page (a GET, before the staff confirm) runs outside a transaction and locks nothing: it answers
    while a write still holds the row; only the confirmed deletion (a POST) waits for the write."""
    row = make()
    answered_while_held, answer = delete_page_while_held(row, hub_staff)
    assert answered_while_held, "the delete page waited for the write that held the row"
    assert answer.status_code == 200, answer.content[:500]
    assert type(row).objects.filter(pk=row.pk).exists()


def test_the_hub_admin_deletes_the_card_a_merge_keeps_with_what_the_merge_moved_to_it(hub_staff):
    survivor, absorbed = card("Ana"), card("ana")
    run("customer.note.add", NoteIn(customer_id=absorbed.id, content="Mornings"))
    merge = lambda: run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))  # noqa: E731
    with meanwhile(locks("customer_customer"), admin_delete(hub_staff, "page", survivor)) as answers:
        merge()
    [answer] = answers
    gone(answer, survivor)
    nothing_hangs_from(survivor)
    absorbed.refresh_from_db()
    assert (absorbed.merged_into_id, absorbed.deleted_at is not None) == (None, True)


def stored_backwards() -> tuple[Customer, Customer]:
    """Two cards, the first and the second by id, the second stored first: a scan meets them the other way
    round from their ids."""
    low, high = sorted((uuid.uuid7(), uuid.uuid7()))
    second = card("ana", id=high)
    return card("Ana", id=low), second


@pytest.mark.parametrize("survivor_first", [True, False])
def test_a_merge_and_the_hub_admin_deleting_both_cards_never_wait_in_a_circle(hub_staff, survivor_first):
    first, second = stored_backwards()
    survivor, absorbed = (first, second) if survivor_first else (second, first)
    merge = lambda: run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))  # noqa: E731
    # The merge waits for the first card, then the Hub admin's «Delete selected», which names them the other way
    # round: both take them in id order, so the deletion waits behind the merge instead of holding the second.
    merged, deleted = in_turn(first, merge, admin_delete(hub_staff, "list", second, first))
    assert not isinstance(merged, Exception), merged
    gone(deleted, first, second)
    assert OutboxEvent.objects.filter(name=events.CUSTOMER_MERGED).exists()



def test_an_erasure_and_the_hub_admin_deleting_the_card_and_its_duplicate_never_wait_in_a_circle(hub_staff):
    duplicate, kept = stored_backwards()
    duplicate.deleted_at, duplicate.merged_into = NOW, kept
    duplicate.save(update_fields=["deleted_at", "merged_into"])
    erase = lambda: run("customer.customer.erase", EraseIn(id=kept.id, reason="Asked for it"))  # noqa: E731
    # The erasure waits for the card it erases, then the Hub admin's «Delete selected» of both: both take them in
    # id order (the duplicate merged into it comes first), so the deletion waits behind the erasure instead of
    # holding the duplicate the erasure goes for next.
    erased, deleted = in_turn(kept, erase, admin_delete(hub_staff, "list", kept, duplicate))
    assert not isinstance(erased, Exception), erased
    gone(deleted, kept, duplicate)
    assert OutboxEvent.objects.filter(name=events.CUSTOMER_ERASED).count() == 2

# ── A group, a tag or a custom field the Hub admin deletes while a write names it ─────────────────────
#
# Setting a card's groups or tags, or its custom values, read the groups, tags or fields it names unheld and
# then wrote rows that point at them: one deleted in between (the Hub admin's «Delete», or the business's own)
# made the database refuse the write at its COMMIT, a 500. The write holds what it names, in id order, after
# its card; the Hub admin's «Delete» holds them before it gathers what points at them. Whichever comes second
# waits: the deletion takes what the write added, or the write answers that what it named no longer exists.


def _named(model, name, table, write, unavailable):
    def prepare(ana):
        target = model.objects.create(name=name)
        return target, table, lambda: write(ana, target), unavailable

    return prepare


NAMED_WRITES = {
    "group": _named(
        CustomerGroup,
        "VIP",
        "customer_customergroup",
        lambda ana, group: run(
            "customer.customer.set_groups", SetGroupsIn(id=ana.id, group_ids=[group.id])
        ),
        "customer.group_unavailable",
    ),
    "tag": _named(
        CustomerTag,
        "Allergic",
        "customer_customertag",
        lambda ana, tag: run("customer.customer.set_tags", SetTagsIn(id=ana.id, tag_ids=[tag.id])),
        "customer.tag_unavailable",
    ),
    "custom value": _named(
        CustomField,
        "Shoe size",
        "customer_customfield",
        lambda ana, field: run(
            "customer.customer.update",
            CustomerPatchIn(id=ana.id, field_values=[{"field_id": field.id, "value": "38"}]),
        ),
        "customer.field_unavailable",
    ),
}


def nothing_points_at(target) -> None:
    model = type(target)
    assert not model.objects.filter(pk=target.pk).exists()
    if model is CustomField:
        assert not CustomFieldValue.objects.filter(field_id=target.pk).exists()
    else:
        relation = "groups" if model is CustomerGroup else "tags"
        through = getattr(Customer, relation).through
        assert not through.objects.filter(**{f"{model._meta.model_name}_id": target.pk}).exists()


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(NAMED_WRITES))
def test_the_hub_admin_deletes_what_a_write_names_once_it_is_written(hub_staff, write, how):
    target, table, write_call, _unavailable = NAMED_WRITES[write](card())
    with meanwhile(reads(table), admin_delete(hub_staff, how, target)) as answers:
        write_call()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    nothing_points_at(target)


@pytest.mark.parametrize("how", HOW)
@pytest.mark.parametrize("write", sorted(NAMED_WRITES))
def test_a_write_naming_what_the_hub_admin_deletes_meanwhile_finds_it_gone(hub_staff, write, how):
    target, table, write_call, unavailable = NAMED_WRITES[write](card())
    with meanwhile(locks(table), write_call) as outcomes:
        answer = admin_delete(hub_staff, how, target)()
    assert answer.status_code == 302
    [outcome] = outcomes
    assert isinstance(outcome, InvalidPayload), outcome
    assert (outcome.status, outcome.code) == (422, unavailable)
    nothing_points_at(target)


def test_a_group_named_by_its_name_and_deleted_before_it_is_held_is_one_that_no_longer_exists():
    ana = card()
    group = CustomerGroup.objects.create(name="VIP")
    delete = lambda: run("customer.group.delete", GroupRefIn(id=group.id))  # noqa: E731
    with deleted_just_before(locks("customer_customergroup"), delete) as deletions:
        with pytest.raises(InvalidPayload) as refused:
            run("customer.customer.set_groups", SetGroupsIn(id=ana.id, groups=["VIP"]))
    assert not isinstance(deletions[0], Exception), deletions[0]
    assert refused.value.code == "customer.group_unavailable"
    assert not Customer.groups.through.objects.exists()


@pytest.mark.parametrize("model", [CustomerGroup, CustomerTag])
def test_the_hub_admin_deletes_a_group_or_a_tag_a_merge_moves_to_the_card_that_stays(hub_staff, model):
    survivor, absorbed = card("Ana"), card("ana")
    target = model.objects.create(name="VIP")
    getattr(absorbed, "groups" if model is CustomerGroup else "tags").add(target)
    merge = lambda: run("customer.customer.merge", MergeIn(id=survivor.id, absorbed_id=absorbed.id))  # noqa: E731
    with meanwhile(reads(model._meta.db_table), admin_delete(hub_staff, "page", target)) as answers:
        merge()
    [answer] = answers
    assert not isinstance(answer, Exception), answer
    assert answer.status_code == 302
    nothing_points_at(target)


# ── A deleted card brought back from a separate copy while the person asks to erase it ─────────────────────────────
#
# The restore holds the card while it judges it and gives back to it what the business deleted since the copy (a
# group made again, hub#1356): an erasure that comes meanwhile waits, then erases the card that came back. Read
# unlocked, the restore would bring back, live and in its group, a card already erased.


def test_a_card_erased_while_it_is_brought_back_stays_erased_and_out_of_its_group():
    ana = card(deleted_at=NOW, is_active=False)
    restore = get("customer.customer.restore")
    asked = restore.input.model_validate({"id": str(ana.id), "groups": [{"id": str(uuid.uuid7()), "name": "VIP"}]})
    erase = lambda: run("customer.customer.erase", EraseIn(id=ana.id, reason="Asked for it"))  # noqa: E731
    with meanwhile(reads("customer_customer"), erase) as outcomes:
        restore(system_context(A), asked)
    [outcome] = outcomes
    assert not isinstance(outcome, Exception), outcome
    ana.refresh_from_db()
    assert (ana.erased_at is not None, ana.deleted_at is not None, ana.is_active) == (True, True, False)
    assert (list(ana.groups.all()), list(Customer.objects.live())) == ([], [])
