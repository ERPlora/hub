"""Two tills at once on the same voucher, and two saves of the same name: real sessions in threads,
real row locks (WORKBOOK «Concurrencia»).

Whichever comes first wins; the other one waits for it and is refused with the real reason, never
with a broken balance or a duplicated name.

The writes that name a row (a tax category, a category, a service, a voucher of the catalog, a customer's
card, a professional) read it unheld: a deletion committed between that read and the write either left the
write naming a deleted row (the business's «Delete» only marks it) or, the Hub admin's (the row goes), made
the database refuse the write at its COMMIT (a 500). A write holds what it names, so the deletion waits for
it; one already under way when the write reads it is refused, as one deleted before.

A detail (a service, a category, a voucher of the catalog) that a deletion lands in the middle of answers
what it read or 404, never a 500.
"""

import threading
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest
from django.contrib import admin
from django.db import connection, transaction
from django.test import RequestFactory
from live.errors import OperationError
from live.operations import get

from apps.customer.models import Customer
from apps.service.models import (
    Assignment,
    Category,
    Grant,
    Package,
    PackageItem,
    Redemption,
    Service,
    ServiceSettings,
)
from apps.staff.models import Member
from apps.tax.models import TaxCategory

from .conftest import (
    ctx_for,
    make_category,
    make_customer,
    make_grant,
    make_member,
    make_package,
    make_service,
    make_tax,
)

pytestmark = pytest.mark.django_db(transaction=True)


def run(name, data):
    op = get(name)
    return op(ctx_for("hub_admin"), op.input.model_validate(data))


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


@pytest.fixture
def cut():
    return make_service("Cut", tax=make_tax())


def test_two_tills_spending_the_last_session_one_wins_and_the_other_hears_why(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    spend = lambda: run(
        "service.grant.redeem", {"id": str(grant.id), "service_id": str(cut.id)}
    )  # noqa: E731
    assert codes(at_once(spend, spend)) == ["ok", "service.grant_no_uses_left"]
    assert Redemption.objects.count() == 1


def test_a_void_and_a_session_at_once_never_leave_a_used_voucher_voided(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    results = at_once(
        lambda: run(
            "service.grant.void", {"id": str(grant.id), "reason": "wrong customer"}
        ),
        lambda: run("service.grant.redeem", {"id": str(grant.id)}),
    )
    assert codes(results) in (
        ["ok", "service.grant_voided"],
        ["ok", "service.grant_in_use"],
    )
    grant.refresh_from_db()
    assert (grant.voided_at is not None) != Redemption.objects.exists()


def test_a_correction_and_a_session_at_once_never_take_the_balance_below_zero(cut):
    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    results = at_once(
        lambda: run(
            "service.grant.adjust",
            {"id": str(grant.id), "uses_delta": -1, "reason": "typo"},
        ),
        lambda: run("service.grant.redeem", {"id": str(grant.id)}),
    )
    assert codes(results) in (
        ["ok", "service.grant_no_uses_left"],
        ["ok", "service.grant_adjust_below_used"],
    )
    [row] = run("service.grant.list", {"package_id": str(grant.package_id)}).rows
    assert row.remaining == 0


def test_two_categories_with_the_same_name_at_once_one_is_refused_with_the_409():
    create = lambda: run("service.category.create", {"name": "Hair"})  # noqa: E731
    assert codes(at_once(create, create)) == ["ok", "service.category_name_taken"]
    assert Category.objects.count() == 1


def test_two_main_services_for_the_same_professional_at_once_leave_one(cut):
    colour = make_service("Colour", tax=make_tax("test.colour", "Colour"))
    make_member("Ana", "López")
    results = at_once(
        lambda: run(
            "service.assignment.assign",
            {"service": "Cut", "member": "Ana López", "is_primary": True},
        ),
        lambda: run(
            "service.assignment.assign",
            {"service_id": str(colour.id), "member": "Ana López", "is_primary": True},
        ),
    )
    assert codes(results) == ["ok", "ok"]
    assert Assignment.objects.filter(is_primary=True).count() == 1


def test_two_categories_hung_from_each_other_at_once_one_is_refused():
    a = make_category("Hair")
    b = make_category("Colour")
    results = at_once(
        lambda: run("service.category.update", {"id": str(a.id), "parent_id": str(b.id)}),
        lambda: run("service.category.update", {"id": str(b.id), "parent_id": str(a.id)}),
    )
    assert codes(results) == ["ok", "service.category_cycle"]
    parents = dict(Category.objects.values_list("id", "parent_id"))
    assert parents[a.id] is None or parents[b.id] is None


# ── Sessions of the till (SERVICE-F22–F24) ──────────────────────────────────────────────────


def hold_for(grant, service, line):
    return lambda: run(
        "service.session.hold",
        {"grant_id": str(grant.id), "service_id": str(service.id), "order_line_id": str(line)},
    )


def test_two_tills_holding_the_last_session_for_two_lines_one_wins(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=1), make_customer())
    results = at_once(hold_for(grant, cut, uuid.uuid7()), hold_for(grant, cut, uuid.uuid7()))
    assert codes(results) == ["ok", "service.grant_no_uses_left"]
    assert Redemption.objects.filter(status="held").count() == 1


def test_the_same_line_held_twice_at_once_keeps_one_session(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    line = uuid.uuid7()
    results = at_once(hold_for(grant, cut, line), hold_for(grant, cut, line))
    assert codes(results) == ["ok", "service.line_already_held"]
    assert Redemption.objects.filter(order_line_id=line).count() == 1


def test_a_void_and_a_hold_at_once_never_leave_a_held_session_on_a_voided_voucher(cut):
    import uuid

    grant = make_grant(make_package("Bono", [cut], max_uses=5), make_customer())
    results = at_once(
        lambda: run("service.grant.void", {"id": str(grant.id), "reason": "wrong customer"}),
        hold_for(grant, cut, uuid.uuid7()),
    )
    assert codes(results) in (
        ["ok", "service.grant_voided"],
        ["ok", "service.grant_in_use"],
    )
    grant.refresh_from_db()
    assert (grant.voided_at is not None) != Redemption.objects.filter(status="held").exists()


def test_charging_and_releasing_a_session_at_once_do_one_or_the_other(cut):
    import uuid

    customer = make_customer()
    grant = make_grant(make_package("Bono", [cut], max_uses=5), customer)
    held = hold_for(grant, cut, uuid.uuid7())()
    results = at_once(
        lambda: run(
            "service.session.settle",
            {"ids": [str(held.id)], "sale_id": str(uuid.uuid7()), "customer_id": str(customer.id)},
        ),
        lambda: run("service.session.release", {"id": str(held.id)}),
    )
    assert codes(results) in (
        ["ok", "service.session_settled"],
        ["ok", "service.hold_lost"],
    )
    status = Redemption.objects.get(pk=held.id).status
    assert status in ("consumed", "released")


# ── The writes that name a row ──────────────────────────────────────────────────────────────────

#: A deletion gives up after this on a row another session holds (a real one waits for its COMMIT).
LOCK_TIMEOUT = "300ms"
#: Postgres' ``lock_not_available``: the deletion found the row held.
LOCK_NOT_AVAILABLE = "55P03"
#: How long a deletion under way holds its row before it commits.
IN_FLIGHT = 0.5
GENERAL, PROBE = "test.general", "test.probe"
#: How the business takes a row away: its «Delete» (the row stays, marked) or archiving a service. The Hub
#: admin's «Delete» is the row's delete() (``row``; tax categories and professionals have only that).
TAKEN_AWAY = {
    (Category, "operation"): "service.category.delete",
    (Package, "operation"): "service.package.delete",
    (Service, "archive"): "service.service.archive",
    (Customer, "operation"): "customer.customer.delete",
}


def run_as_system(name, data):
    op = get(name)
    return op(ctx_for(permissions={"service.system"}), op.input.model_validate(data))


def admin_delete(target, how: str = "delete_model") -> None:
    """The Hub admin's «Delete» of ``target``: its page (``delete_model``) or the list's «Delete selected»
    action (``delete_queryset``), as the staff run them."""
    model_admin = admin.site._registry[type(target)]
    request = RequestFactory().post("/admin/")
    if how == "delete_queryset":
        model_admin.delete_queryset(request, type(target).objects.filter(pk=target.pk))
    else:
        model_admin.delete_model(request, type(target).objects.get(pk=target.pk))


def remove(target, how: str) -> None:
    if how == "row":
        admin_delete(target)
    elif how == "default":
        # The settings' default tax category: they move to another one, and then the staff delete it.
        run("service.settings.update", {"default_tax_category_key": GENERAL})
        admin_delete(TaxCategory.objects.get(pk=target.pk))
    else:
        run(TAKEN_AWAY[type(target), how], {"id": str(target.pk)})


def delete(target, how: str) -> None:
    """Deletes ``target`` in this session, giving up after LOCK_TIMEOUT on a row another session holds. The
    lock timeout is the transaction's (SET LOCAL): a session-level one would go back with the connection and
    reach the tests after this one (the autouse fixture of conftest.py fails a test that leaves it)."""
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL lock_timeout = '{LOCK_TIMEOUT}'")
        remove(target, how)


@contextmanager
def deleted_just_before(statement: str, target, how: str):
    """Deletes ``target`` in another session right before the first statement of this one that starts with
    ``statement`` (the write that names it): between the read that found it and the write, every time. It
    commits, or waits for this session when it holds the row (and gives up)."""
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        if not deletions and sql.lstrip().startswith(statement):
            deletions.extend(at_once(lambda: delete(target, how)))
        return execute(sql, params, many, context)

    with connection.execute_wrapper(wrapper):
        yield deletions


@contextmanager
def deleted_in_flight(target, how: str):
    """A deletion of ``target`` under way in another session when this one first reads its table: it holds
    the row, as a deletion takes it first, and commits a moment later while this one goes on."""
    table = f'FROM "{type(target)._meta.db_table}"'
    holds = threading.Event()
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                type(target).objects.select_for_update().get(pk=target.pk)
                holds.set()
                time.sleep(IN_FLIGHT)
                remove(target, how)
            deletions.append("ok")
        except Exception as error:  # reported to the test, which fails on it
            deletions.append(error)
        finally:
            holds.set()
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and sql.lstrip().upper().startswith("SELECT") and table in sql:
            thread.start()
            holds.wait(5)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)


def deleted(deletions) -> list[str]:
    return ["ok" if not isinstance(result, Exception) else repr(result) for result in deletions]


def sqlstate(error) -> str | None:
    while error is not None:
        if getattr(error, "sqlstate", None):
            return error.sqlstate
        error = error.__cause__ or error.__context__
    return None


def held(deletions) -> bool:
    """The deletion waited for the row this write holds (and gave up)."""
    return len(deletions) == 1 and sqlstate(deletions[0]) == LOCK_NOT_AVAILABLE


def attempt(call):
    """What ``call`` answers: its result, or the error it is refused with (a 500 is raised as it comes)."""
    try:
        return call()
    except OperationError as error:
        return error


@pytest.fixture
def world():
    # transaction=True flushes Taxes' factory catalogue (a data migration): categories of its own.
    general = make_tax(GENERAL, "General")
    ServiceSettings.objects.create(default_tax_category=general)
    cut = make_service("Cut", tax=general)
    pablo = make_customer("Pablo Gil")
    # The rows the writes name: named by nothing yet, so each may be deleted in the Hub admin.
    return SimpleNamespace(
        probe=make_tax(PROBE, "Probe"),
        colour=make_category("Colour"),
        spare=make_service("Spare", tax=general),
        cut=cut,
        bono=make_package("Bono", [cut], max_uses=5),
        lucia=make_customer(),
        ana=make_member("Ana", "López"),
        # A card merged into Lucía's, with a voucher of its own.
        pablo=pablo,
        pablos=make_grant(make_package("Bono 10", [cut], max_uses=10), pablo),
    )


@dataclass(frozen=True)
class Write:
    """A write that names ``target`` (an attribute of the world): how it is called, the statement that writes
    the name down, whether it landed naming it, and how it is refused once the row is gone, per deletion."""

    call: Callable
    statement: str
    target: str
    named: Callable
    refused: dict
    setup: Callable = field(default=lambda w: None)


def perm(w, said: dict) -> dict:
    return {"name": "Perm", "price": 3000} | {name: value(w) for name, value in said.items()}


def new_service(**said):
    return lambda w: run("service.service.create", perm(w, said))


def new_services(**said):
    return lambda w: run("service.service.bulk_create", {"services": [perm(w, said)]})


def perm_named(**names):
    return lambda w: Service.objects.filter(
        name="Perm", **{name: getattr(w, attr) for name, attr in names.items()}
    ).exists()


def cut_names(**names):
    return lambda w: Service.objects.filter(
        pk=w.cut.pk, **{name: getattr(w, attr) for name, attr in names.items()}
    ).exists()


TAX_GONE = (422, "service.tax_category_unknown", ["tax_category_key"])
CATEGORY_GONE = (422, "service.category_unavailable", ["category_id"])
WRITES = {
    "service.create names a tax category": Write(
        new_service(tax_category_key=lambda w: PROBE),
        'INSERT INTO "service_service"',
        "probe",
        perm_named(tax_category="probe"),
        {"row": TAX_GONE},
    ),
    "service.create takes the settings' tax category": Write(
        new_service(),
        'INSERT INTO "service_service"',
        "probe",
        perm_named(tax_category="probe"),
        {"default": (422, "service.tax_category_required", ["tax_category_key"])},
        setup=lambda w: ServiceSettings.objects.update(default_tax_category=w.probe),
    ),
    "service.bulk_create names a tax category": Write(
        new_services(tax_category_key=lambda w: PROBE),
        'INSERT INTO "service_service"',
        "probe",
        perm_named(tax_category="probe"),
        {"row": (422, "service.bulk_invalid", ["services.0.tax_category_key"])},
    ),
    "service.update names a tax category": Write(
        lambda w: run("service.service.update", {"id": str(w.cut.id), "tax_category_key": PROBE}),
        'UPDATE "service_service" SET',
        "probe",
        cut_names(tax_category="probe"),
        {"row": TAX_GONE},
    ),
    "settings.update names a tax category": Write(
        lambda w: run("service.settings.update", {"default_tax_category_key": PROBE}),
        'UPDATE "service_servicesettings" SET',
        "probe",
        lambda w: ServiceSettings.objects.filter(default_tax_category=w.probe).exists(),
        {"row": (422, "service.tax_category_unknown", ["default_tax_category_key"])},
    ),
    "service.create names a category": Write(
        new_service(tax_category_key=lambda w: GENERAL, category_id=lambda w: str(w.colour.id)),
        'INSERT INTO "service_service"',
        "colour",
        perm_named(category="colour"),
        {"operation": CATEGORY_GONE, "row": CATEGORY_GONE},
    ),
    "service.bulk_create names a category": Write(
        new_services(tax_category_key=lambda w: GENERAL, category_id=lambda w: str(w.colour.id)),
        'INSERT INTO "service_service"',
        "colour",
        perm_named(category="colour"),
        {
            how: (422, "service.bulk_invalid", ["services.0.category_id"])
            for how in ("operation", "row")
        },
    ),
    "service.update names a category": Write(
        lambda w: run("service.service.update", {"id": str(w.cut.id), "category_id": str(w.colour.id)}),
        'UPDATE "service_service" SET',
        "colour",
        cut_names(category="colour"),
        {"operation": CATEGORY_GONE, "row": CATEGORY_GONE},
    ),
    "category.create names its parent": Write(
        lambda w: run("service.category.create", {"name": "Highlights", "parent_id": str(w.colour.id)}),
        'INSERT INTO "service_category"',
        "colour",
        lambda w: Category.objects.filter(name="Highlights", parent=w.colour).exists(),
        {
            how: (422, "service.parent_category_unavailable", ["parent_id"])
            for how in ("operation", "row")
        },
    ),
    "assignment.assign names a service": Write(
        lambda w: run(
            "service.assignment.assign", {"service_id": str(w.spare.id), "member_id": str(w.ana.id)}
        ),
        'INSERT INTO "service_assignment"',
        "spare",
        lambda w: Assignment.objects.filter(service=w.spare).exists(),
        {"row": (404, "service.service_not_found", [])},
    ),
    "assignment.assign names a professional": Write(
        lambda w: run(
            "service.assignment.assign", {"service_id": str(w.spare.id), "member_id": str(w.ana.id)}
        ),
        'INSERT INTO "service_assignment"',
        "ana",
        lambda w: Assignment.objects.filter(member=w.ana).exists(),
        {"row": (404, "not_found", [])},
    ),
    "package.create names a service": Write(
        lambda w: run(
            "service.package.create",
            {"name": "Pack", "items": [{"service_id": str(w.spare.id), "sessions": 1}]},
        ),
        'INSERT INTO "service_packageitem"',
        "spare",
        lambda w: PackageItem.objects.filter(service=w.spare).exists(),
        {
            "archive": (422, "service.service_archived", ["items.0.service_id"]),
            "row": (422, "service.service_not_found", ["items.0.service_id"]),
        },
    ),
    "grant.create names a package": Write(
        lambda w: run(
            "service.grant.create", {"package_id": str(w.bono.id), "customer_id": str(w.lucia.id)}
        ),
        'INSERT INTO "service_grant"',
        "bono",
        lambda w: Grant.objects.filter(package=w.bono, customer=w.lucia).exists(),
        {how: (404, "service.package_not_found", []) for how in ("operation", "row")},
    ),
    "grant.create names a customer": Write(
        lambda w: run(
            "service.grant.create", {"package_id": str(w.bono.id), "customer_id": str(w.lucia.id)}
        ),
        'INSERT INTO "service_grant"',
        "lucia",
        lambda w: Grant.objects.filter(customer=w.lucia).exists(),
        {how: (404, "customer.customer_unavailable", []) for how in ("operation", "row")},
    ),
    "grant.reassign names the card that stays": Write(
        lambda w: run_as_system(
            "service.grant.reassign", {"id": str(w.lucia.id), "absorbed_id": str(w.pablo.id)}
        ),
        'UPDATE "service_grant" SET',
        "lucia",
        lambda w: Grant.objects.filter(customer=w.lucia).exists(),
        {"row": (404, "service.customer_unavailable", [])},
    ),
}
CASES = [(write, how) for write, case in WRITES.items() for how in case.refused]


@pytest.mark.parametrize(("write", "how"), CASES)
def test_a_row_deleted_while_a_write_names_it_waits_for_the_write(world, write, how):
    case = WRITES[write]
    case.setup(world)
    target = getattr(world, case.target)
    with deleted_just_before(case.statement, target, how) as deletions:
        case.call(world)
    assert held(deletions), deleted(deletions)
    assert case.named(world)


@pytest.mark.parametrize(("write", "how"), CASES)
def test_a_row_being_deleted_when_a_write_names_it_is_refused(world, write, how):
    case = WRITES[write]
    case.setup(world)
    target = getattr(world, case.target)
    with deleted_in_flight(target, how) as deletions:
        outcome = attempt(lambda: case.call(world))
    assert deleted(deletions) == ["ok"]
    # As for one deleted before: refused with the app's key, under the field that named it.
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code, list(outcome.fields or {})) == case.refused[how]
    assert not case.named(world)


@contextmanager
def deleted_once_locked(target):
    """The business's «Delete» of the category ``target`` started in another session right after this one
    locks a service, and left to run a moment: it locks every category and then empties ``target``'s
    services, so it waits for this session's service."""
    deletions: list = []

    def deletion():
        try:
            run("service.category.delete", {"id": str(target.pk)})
            deletions.append("ok")
        except Exception as error:  # reported to the test, which fails on it
            deletions.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if thread.ident is None and 'FROM "service_service"' in sql and "FOR UPDATE" in sql:
            thread.start()
            time.sleep(IN_FLIGHT)
        return result

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)


def test_moving_a_service_while_its_old_category_is_deleted_never_waits_in_a_circle(world):
    # The edit locked the service and then named its new category; the deletion of the old one locks every
    # category and then empties its services: each waited for the other, and Postgres killed one (a 500).
    hair = make_category("Hair")
    Service.objects.filter(pk=world.cut.pk).update(category=hair)
    with deleted_once_locked(hair) as deletions:
        run("service.service.update", {"id": str(world.cut.id), "category_id": str(world.colour.id)})
    assert deleted(deletions) == ["ok"]
    assert Service.objects.get(pk=world.cut.pk).category_id == world.colour.id
    assert Category.objects.get(pk=hair.pk).is_deleted


# ── The Hub admin's «Delete» and the writes that hold what they name ───────────────────────────
#
# Django's deletion empties or deletes what names a row (services, subcategories, assignments) and then
# deletes the row. A write that held the row and then took one of those waited for it, while it waited for
# the write: Postgres killed one of the two (a 500). The admin's «Delete» of a category takes every category
# first, as the business's own «Delete» does, and assigning takes the assignment before the service, in the
# order the deletion of the service takes them.


@contextmanager
def admin_deleting(target, how: str, after: Callable):
    """The Hub admin's «Delete» of ``target`` started in another session right before the first statement of
    this one for which ``after`` holds, and left to run a moment before this one goes on."""
    deletions: list = []

    def deletion():
        try:
            with transaction.atomic():
                admin_delete(target, how)
            deletions.append("ok")
        except Exception as error:  # reported to the test, which fails on it
            deletions.append(error)
        finally:
            connection.close()

    thread = threading.Thread(target=deletion)

    def wrapper(execute, sql, params, many, context):
        if thread.ident is None and after(sql):
            thread.start()
            time.sleep(IN_FLIGHT)
        return execute(sql, params, many, context)

    try:
        with connection.execute_wrapper(wrapper):
            yield deletions
    finally:
        if thread.ident is not None:
            thread.join(30)
    assert thread.ident is not None, "the deletion never started"


ADMIN_DELETIONS = ["delete_model", "delete_queryset"]


def locks_the_service(sql: str) -> bool:
    return 'FROM "service_service"' in sql and "FOR UPDATE" in sql


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
def test_editing_a_service_in_its_own_category_while_the_hub_admin_deletes_it_never_waits_in_a_circle(
    world, how
):
    # The edit held the category and then its own row; the admin had emptied the category (the service's row
    # first) and waited for the category: each waited for the other.
    hair = make_category("Hair")
    Service.objects.filter(pk=world.cut.pk).update(category=hair)
    with admin_deleting(hair, how, locks_the_service) as deletions:
        outcome = attempt(
            lambda: run(
                "service.service.update",
                {"id": str(world.cut.id), "category_id": str(hair.id), "price": 2500},
            )
        )
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    cut = Service.objects.get(pk=world.cut.pk)
    assert (cut.category_id, cut.price) == (None, 2500)
    assert not Category.objects.filter(pk=hair.pk).exists()


#: What is written in a category the admin is deleting, how it names it and what it leaves.
WRITTEN_IN_A_CATEGORY = {
    "a service": (
        lambda w: run("service.service.create", {"name": "Perm", "price": 3000, "tax_category_key": GENERAL, "category_id": str(w.colour.id)}),
        'INSERT INTO "service_service"',
        lambda w: Service.objects.get(name="Perm").category_id,
    ),
    "a subcategory": (
        lambda w: run("service.category.create", {"name": "Highlights", "parent_id": str(w.colour.id)}),
        'INSERT INTO "service_category"',
        lambda w: Category.objects.get(name="Highlights").parent_id,
    ),
}


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
@pytest.mark.parametrize("written", sorted(WRITTEN_IN_A_CATEGORY))
def test_the_hub_admin_deleting_a_category_a_write_holds_waits_and_then_empties_it(world, written, how):
    # The admin's deletion read what named the category before the write committed and then deleted the row
    # the write had just named: refused at its COMMIT (a 500 for the staff). Entering through every category
    # first, it waits for the write and then reads what it left.
    call, statement, parent = WRITTEN_IN_A_CATEGORY[written]
    with admin_deleting(world.colour, how, lambda sql: sql.lstrip().startswith(statement)) as deletions:
        call(world)
    assert deleted(deletions) == ["ok"]
    assert not Category.objects.filter(pk=world.colour.pk).exists()
    assert parent(world) is None


def test_reassigning_a_professional_while_the_hub_admin_deletes_the_service_never_waits_in_a_circle(world):
    # Assigning held the service and then locked the assignment; the admin's deletion of the service had
    # deleted its assignments first and waited for the service: each waited for the other.
    Assignment.objects.create(service=world.spare, member=world.ana)
    locks_the_assignment = lambda sql: 'FROM "service_assignment"' in sql and "FOR UPDATE" in sql  # noqa: E731
    with admin_deleting(world.spare, "delete_model", locks_the_assignment) as deletions:
        outcome = attempt(
            lambda: run(
                "service.assignment.assign",
                {"service_id": str(world.spare.id), "member_id": str(world.ana.id), "custom_price": 1500},
            )
        )
    assert deleted(deletions) == ["ok"]
    # As for a service deleted before: not found, and nothing assigned.
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, "service.service_not_found")
    assert not Service.objects.filter(pk=world.spare.pk).exists()
    assert not Assignment.objects.exists()


# ── The Hub admin's «Delete» of a professional ─────────────────────────────────────────────────
#
# Who performs a service is held through the professional: a write locks the staff record and then the
# assignment. Django's deletion of the record deletes its assignments first and then the record, so it held
# the assignment the write went for while it waited for the record the write held: Postgres killed one of
# the two (a 500). The admin enters through the record (staff's ``lock_members``), so it waits for the write
# and then deletes what the write left.


def locks_an_assignment(sql: str) -> bool:
    return 'FROM "service_assignment"' in sql and "FOR UPDATE" in sql


def demotes_a_main_service(sql: str) -> bool:
    return sql.lstrip().startswith('UPDATE "service_assignment"')


#: What is written about Ana while the admin deletes her: what it needs, the call, and its first statement
#: on an assignment once her record is held.
WRITTEN_ABOUT_A_PROFESSIONAL = {
    "assigning her again": (
        lambda w: Assignment.objects.create(service=w.spare, member=w.ana),
        lambda w, a: run(
            "service.assignment.assign",
            {"service_id": str(w.spare.id), "member_id": str(w.ana.id), "custom_price": 1500},
        ),
        locks_an_assignment,
    ),
    "assigning her a new main service": (
        lambda w: Assignment.objects.create(service=w.cut, member=w.ana, is_primary=True),
        lambda w, a: run(
            "service.assignment.assign",
            {"service_id": str(w.spare.id), "member_id": str(w.ana.id), "is_primary": True},
        ),
        demotes_a_main_service,
    ),
    "changing her assignment": (
        lambda w: Assignment.objects.create(service=w.spare, member=w.ana),
        lambda w, a: run("service.assignment.update", {"id": str(a.id), "custom_duration": 45}),
        locks_an_assignment,
    ),
    "removing her assignment": (
        lambda w: Assignment.objects.create(service=w.spare, member=w.ana),
        lambda w, a: run("service.assignment.remove", {"id": str(a.id)}),
        locks_an_assignment,
    ),
}


@pytest.mark.parametrize("how", ADMIN_DELETIONS)
@pytest.mark.parametrize("written", sorted(WRITTEN_ABOUT_A_PROFESSIONAL))
def test_a_write_on_a_professional_while_the_hub_admin_deletes_them_never_waits_in_a_circle(world, written, how):
    setup, call, after = WRITTEN_ABOUT_A_PROFESSIONAL[written]
    assignment = setup(world)
    with admin_deleting(world.ana, how, after) as deletions:
        outcome = attempt(lambda: call(world, assignment))
    # The deletion waited for the write, which went through, and then took her and all she performed.
    assert deleted(deletions) == ["ok"]
    assert not isinstance(outcome, OperationError), outcome
    assert not Member.objects.filter(pk=world.ana.pk).exists()
    assert not Assignment.objects.exists()


# The details: a deletion that lands in the middle of a read

#: Each detail, the row of the world it shows, the field that names it, how it says it is not found and the
#: deletions that take that row away from it: the business's «Delete» of a category (the row stays, marked)
#: and the Hub admin's of any of them (the row goes). Archiving a service or deleting a voucher of the
#: catalog keeps it in its detail, so neither takes it away in the middle of the read.
DETAILS = {
    "service.service.get": ("spare", "service", "service.service_not_found", ["row"]),
    "service.category.get": ("colour", "category", "service.category_not_found", ["operation", "row"]),
    "service.package.get": ("bono", "package", "service.package_not_found", ["row"]),
}
DETAIL_CASES = [(detail, how) for detail, (*_, ways) in DETAILS.items() for how in ways]


@contextmanager
def deleted_after_the_first_read_of(target, how: str):
    """Commits the deletion of ``target`` (``how``, as ``remove``) in another session right after the first
    statement of this one that reads its table: a deletion landing in the middle of a read, every time."""
    table = f'FROM "{type(target)._meta.db_table}"'
    deletions: list = []

    def wrapper(execute, sql, params, many, context):
        result = execute(sql, params, many, context)
        if not deletions and sql.lstrip().upper().startswith("SELECT") and table in sql:
            deletions.extend(at_once(lambda: delete(target, how)))
        return result

    with connection.execute_wrapper(wrapper):
        yield deletions


@pytest.mark.parametrize(("detail", "how"), DETAIL_CASES)
def test_a_row_deleted_while_its_detail_is_read_is_never_a_server_error(world, detail, how):
    # The detail found the row and then loaded it by its id in a second read: a deletion committed between
    # the two raised DoesNotExist (a 500). In one read it is the row as it was read.
    attribute, _, missing, _ = DETAILS[detail]
    row = getattr(world, attribute)
    with deleted_after_the_first_read_of(row, how) as deletions:
        shown = run(detail, {"id": str(row.pk)})
    assert deleted(deletions) == ["ok"]
    assert (shown.id, shown.name) == (row.pk, row.name)
    # What the deletion's event runs next: not found, and the open sheet closes.
    gone = attempt(lambda: run(detail, {"id": str(row.pk)}))
    assert isinstance(gone, OperationError), gone
    assert (gone.status, gone.code) == (404, missing)


@pytest.mark.parametrize(("detail", "how"), DETAIL_CASES)
def test_a_row_deleted_between_its_name_and_its_detail_is_not_found(world, detail, how):
    attribute, said, missing, _ = DETAILS[detail]
    row = getattr(world, attribute)
    with deleted_after_the_first_read_of(row, how) as deletions:
        outcome = attempt(lambda: run(detail, {said: row.name}))
    assert deleted(deletions) == ["ok"]
    assert isinstance(outcome, OperationError), outcome
    assert (outcome.status, outcome.code) == (404, missing)
