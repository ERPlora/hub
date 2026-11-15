"""A business that left, once its 90 days are over.

The worker's data pass takes the business from ``cancelled`` through ``archiving`` (its final copy) and ``dropping``
(``DROP DATABASE … WITH (FORCE)``, that one only) to ``purged``, the row left as a tombstone. These tests make real
databases next to the session's (as ``test_provision`` does: no test case, ``django_db_blocker``) and a real S3 (moto's).
"""

import datetime as dt
import logging
import uuid

import pytest
from django.db import connections as django_connections
from django.utils import timezone
from live.context import system_context
from live.errors import Conflict, NotFound
from live.meta import all_live_app_configs
from live.models import OutboxEvent

from apps.sale.apps import SaleConfig
from base import queries, registry, services, worker
from base.events import HUB_PURGED
from base.schemas import HubCancelIn, HubGetIn, HubRegistryIn, HubRestoreIn, HubStateIn
from base.tenancy import connections as tenancy_connections
from base.tenancy import dumps, names, ops, provision
from base.tenancy.context import current_alias, use_control, use_hub
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import (  # noqa: F401
    aws_test_credentials,
    dumps_bucket,
    hub_files_bucket,
    hub_files_entry,
    keep_files,
    moto_s3,
    no_dumps_bucket,
    objects,
    spy_on_the_purge,
)
from control.models import Cluster, Hub, HubDue, HubDump

pytestmark = pytest.mark.usefixtures("no_test_fallback")


def databases() -> set[str]:
    control = tenancy_connections.control_name()
    with hubs._maintenance() as conn:
        return {row[0] for row in conn.execute("SELECT datname FROM pg_database") if row[0].startswith(control)}


def fresh(hub: Hub) -> Hub:
    return Hub.objects.select_related("cluster").get(pk=hub.pk)


@pytest.fixture
def business(django_db_blocker, hub_databases, monkeypatch):
    """``business(left_days_ago=91)``: a business made by the provisioning, with a real database, that left then. Its
    row and its database are gone after the test."""
    monkeypatch.setattr(services, "report_ready", lambda hub_id: None)
    started = timezone.now()
    made: list[Hub] = []

    def make(*, left_days_ago: int | None = 91, **fields) -> Hub:
        hub_id = uuid.uuid7()
        values = {
            "id": hub_id,
            "slug": f"acme-{hub_id.hex[-8:]}",
            "status": Hub.Status.REQUESTED,
            "db_name": names.hub_db_name(tenancy_connections.control_name(), hub_id),
            "vertical": hubs.TEMPLATE_VERTICAL,
        }
        hub = Hub.objects.create(**values)
        made.append(hub)
        assert provision.provision(hub, tell_saas=False) is True
        changes = dict(fields)
        if left_days_ago is not None:
            changes |= {
                "status": Hub.Status.CANCELLED,
                "cancelled_at": timezone.now() - dt.timedelta(days=left_days_ago),
            } | fields
        if changes:
            Hub.objects.filter(pk=hub.pk).update(**changes)
        return fresh(hub)

    with django_db_blocker.unblock():
        yield make
        with hubs._maintenance() as conn:
            for row in made:
                hubs._drop(conn, names.hub_db_name(tenancy_connections.control_name(), row.pk), hub_databases.control)
        HubDump.objects.filter(hub__in=[row.pk for row in made]).delete()
        Hub.objects.filter(pk__in=[row.pk for row in made]).delete()
        with use_control():
            OutboxEvent.objects.filter(created_at__gte=started).delete()


def run_pass(now: dt.datetime | None = None) -> None:
    worker._data(now or timezone.now())


@pytest.mark.django_db
def test_nobody_is_retired_before_the_90_days_nor_a_demo_the_platform_or_one_moving():
    now = timezone.now()
    left = {"status": Hub.Status.CANCELLED, "cancelled_at": now - dt.timedelta(days=90, seconds=1), "db_name": "x"}

    assert services.past_retention(Hub(**left), now) is True
    assert services.past_retention(Hub(**left | {"cancelled_at": now - dt.timedelta(days=89)}), now) is False
    assert services.past_retention(Hub(**left | {"is_demo": True}), now) is False
    assert services.past_retention(Hub(**left | {"is_platform": True}), now) is False
    assert services.past_retention(Hub(**left | {"moving_to_id": uuid.uuid7()}), now) is False
    assert services.past_retention(Hub(**left | {"restoring_from_id": uuid.uuid7()}), now) is False
    assert services.past_retention(Hub(status=Hub.Status.READY, db_name="x"), now) is False
    assert services.past_retention(Hub(status=Hub.Status.ARCHIVING, db_name="x"), now) is True
    assert services.past_retention(Hub(status=Hub.Status.DROPPING, db_name="x"), now) is True
    assert services.past_retention(Hub(status=Hub.Status.PURGED, db_name="x"), now) is False


def test_a_business_past_its_90_days_is_copied_dropped_and_purged_and_one_within_them_is_left(
    business, dumps_bucket, moto_s3
):
    over = business(left_days_ago=91)
    within = business(left_days_ago=89)
    before = databases()

    run_pass()
    run_pass()

    over, within = fresh(over), fresh(within)
    assert (over.status, over.purged_at is not None) == ("purged", True)
    copy = HubDump.objects.get(hub=over)
    assert copy.kind == "offboarding"
    assert copy.created_at >= over.cancelled_at + dt.timedelta(days=90)
    assert set(objects(moto_s3, dumps_bucket)) == {copy.key}
    assert databases() == before - {over.db_name}
    assert within.status == "cancelled"
    assert within.purged_at is None
    assert within.db_name in databases()
    assert not HubDump.objects.filter(hub=within).exists()


# ── A business with fiscal documents keeps its database ────────────────────────────────────────────────────────────
# They must be archived for 6 years before the drop, and that archive does not exist yet.

DAY = dt.date(2026, 10, 14)


def one_sale():
    from apps.sale.models import Sale

    Sale.objects.create(number="20261014-0001", business_day=DAY, sequence=1, idempotency_key="key-1", total=100)


def one_invoice():
    from apps.invoice.models import Invoice, InvoiceSeries

    series = InvoiceSeries.objects.create(code="FACT", year=2026, invoice_type="F1", prefix="FACT")
    return Invoice.objects.create(
        series=series,
        series_code="FACT",
        year=2026,
        sequence=1,
        number="FACT-2026-000001",
        invoice_type="F1",
        issue_date=DAY,
        operation_date=DAY,
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
    )


def one_record():
    from apps.verifactu.models import Config, Record

    invoice = one_invoice()  # a record always names its invoice
    Record.objects.create(
        record_type=Record.Type.ALTA,
        environment=Config.Environment.TESTING,
        issuer_nif="B12345674",
        issuer_name="Ana SL",
        sequence=1,
        invoice=invoice,
        invoice_number=invoice.number,
        issue_date=DAY,
        invoice_type="F2",
        base_amount=1000,
        tax_amount=210,
        total_amount=1210,
        generated_at="2026-10-14T10:00:00+02:00",
        generated_on=timezone.now(),
        fingerprint="A" * 64,
        qr_url="https://prewww2.aeat.es/wlpl/TIKE-CONT/ValidarQR?nif=B12345674",
    )


def one_payment():
    from apps.payment.models import Payment, PaymentMethod

    Payment.objects.create(
        reference="PAY-20261014-0001",
        method=PaymentMethod.objects.create(name="Transfer"),
        payment_date=DAY,
        amount=100,
        currency="EUR",
        beneficiary_name="Supplier SL",
    )


def one_cash_movement():
    from apps.cash_register.models import Movement, Session

    session = Session.objects.create(number="S-261014-0001", business_day=DAY, sequence=1, opening_balance=100)
    Movement.objects.create(session=session, type=Movement.Type.OUT, amount=100)


def one_shop_order():
    from apps.cart_checkout.models import Cart, Order

    Order.objects.create(
        cart=Cart.objects.create(session_token="s-1", currency="EUR"),
        order_number="OS-20261014-0001",
        customer_email="ana@example.com",
        total_amount=2500,
        currency="EUR",
    )


def one_card_sale():
    from apps.customer.models import Customer, Purchase

    Purchase.objects.create(customer=Customer.objects.create(name="Ana"), amount=100)


@pytest.mark.parametrize(
    ("write", "apps"),
    [
        (one_shop_order, "cart_checkout"),
        (one_card_sale, "customer"),
        (one_sale, "sale"),
        (one_invoice, "invoice"),
        (one_record, "invoice, verifactu"),
        (one_payment, "payment"),
        (one_cash_movement, "cash_register"),
    ],
)
def test_a_business_with_fiscal_documents_stays_cancelled_with_its_database_and_no_copy(
    business, dumps_bucket, moto_s3, write, apps
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        write()
    now = timezone.now()

    run_pass(now)
    run_pass(now)

    hub = fresh(hub)
    assert (hub.status, hub.purged_at) == ("cancelled", None)
    assert hub.db_name in databases()
    assert hub.last_error == f"fiscal_archive_missing: {apps}"
    assert hub.next_attempt_at == now + dt.timedelta(days=1)
    assert not HubDump.objects.filter(hub=hub).exists()
    assert objects(moto_s3, dumps_bucket) == {}


#: The apps with nothing a tax inspector asks for, each one looked at: a new app has to say which side it is on, or the
#: drop of a business would take its documents away without anyone noticing. ``kitchen.Ticket`` comes from a sale, which
#: is the document; a price in ``service``, ``pricing`` or ``combo`` is a list price, no money that moved;
#: ``inventory.StockMovement`` counts goods, not what was paid for them.
NO_FISCAL_DOCUMENTS = {
    "appointment",
    "attendance",
    "combo",
    "demo",
    "flow",
    "inventory",
    "kitchen",
    "modifier",
    "online_booking",
    "pricing",
    "printing",
    "reservation",
    "schedule",
    "service",
    "staff",
    "table",
    "task",
    "tax",
    "website",
    "whatsapp_inbox",
}
KEEP_FISCAL_DOCUMENTS = {"cart_checkout", "cash_register", "customer", "invoice", "payment", "sale", "verifactu"}


def test_every_app_is_on_one_side_of_the_fiscal_gate():
    apps = {config.label: config for config in all_live_app_configs() if config.kind == "app"}

    assert {label for label, config in apps.items() if hasattr(config, "fiscal_documents_kept")} == KEEP_FISCAL_DOCUMENTS
    assert set(apps) - KEEP_FISCAL_DOCUMENTS == NO_FISCAL_DOCUMENTS


def asking(sql: str):
    """A real answer of the database of the active hub to ``sql``, as an app's own read would hear it."""

    def ask(self) -> bool:
        with django_connections[current_alias()].cursor() as cursor:
            cursor.execute(sql)
        return False

    return ask


def test_an_app_whose_tables_the_database_lacks_has_no_documents_to_keep(business, dumps_bucket, moto_s3, monkeypatch):
    hub = business(left_days_ago=91)
    monkeypatch.setattr(SaleConfig, "fiscal_documents_kept", asking("SELECT 1 FROM a_table_that_is_not_there"))

    run_pass()
    run_pass()

    assert fresh(hub).status == "purged"


def test_an_app_that_cannot_be_read_for_any_other_reason_keeps_the_database(business, dumps_bucket, moto_s3, monkeypatch):
    hub = business(left_days_ago=91)
    monkeypatch.setattr(SaleConfig, "fiscal_documents_kept", asking("SELECT a_column_that_is_not_there FROM sale_sale"))

    run_pass()

    hub = fresh(hub)
    assert hub.status == "cancelled"
    assert hub.db_name in databases()
    assert hub.last_error.startswith("unexpected: ProgrammingError")
    assert hub.attempts == 1
    assert hub.next_attempt_at is not None
    assert not HubDump.objects.filter(hub=hub).exists()


def test_a_fiscal_document_written_while_the_copy_is_made_keeps_the_database(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    real = dumps.dump_hub

    def spied(row, **kwargs):
        made = real(row, **kwargs)
        with use_hub(row):
            one_sale()
        return made

    monkeypatch.setattr(dumps, "dump_hub", spied)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.last_error) == ("cancelled", "fiscal_archive_missing: sale")
    assert hub.db_name in databases()


def test_a_kept_business_is_not_copied_again_and_again_once_the_night_forgets_its_copy(
    business, dumps_bucket, moto_s3
):
    hub = business(left_days_ago=200)
    with use_hub(hub):
        one_sale()
    now = timezone.now()

    for day in range(3):
        run_pass(now + dt.timedelta(days=day, minutes=1))

    hub = fresh(hub)
    assert hub.status == "cancelled"
    assert hub.next_attempt_at > now + dt.timedelta(days=2)
    assert not HubDump.objects.filter(hub=hub).exists()


def test_a_kept_business_due_on_hub_due_all_the_same_waits_for_its_next_attempt(business, dumps_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    now = timezone.now()
    later = now + dt.timedelta(hours=1)
    Hub.objects.filter(pk=hub.pk).update(next_attempt_at=later, last_error="fiscal_archive_missing: sale")
    HubDue.mark_due(fresh(hub), now)

    run_pass(now)

    assert fresh(hub).next_attempt_at == later


# ── The order of the steps, and what fails ─────────────────────────────────────────────────────────────────────────


def test_the_copy_is_made_before_the_drop_and_the_drop_outside_any_transaction_while_dropping(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    real, seen = ops.drop_database, []

    def spied(name, **kwargs):
        seen.append(
            (name, django_connections["default"].in_atomic_block, fresh(hub).status, HubDump.objects.filter(hub=hub).count())
        )
        return real(name, **kwargs)

    monkeypatch.setattr(ops, "drop_database", spied)

    run_pass()

    assert seen == [(hub.db_name, False, "dropping", 1)]
    assert fresh(hub).status == "purged"


def test_a_copy_that_fails_drops_nothing_and_is_tried_again_at_its_next_attempt(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    real = dumps.dump_hub

    def broken(row, **kwargs):
        raise dumps.DumpFailed("the bucket said no")

    monkeypatch.setattr(dumps, "dump_hub", broken)
    now = timezone.now()

    run_pass(now)

    failed = fresh(hub)
    assert failed.status == "archiving"
    assert failed.attempts == 1
    assert failed.last_error == "dump_failed: the bucket said no"
    assert failed.next_attempt_at > now
    assert failed.db_name in databases()

    monkeypatch.setattr(dumps, "dump_hub", real)
    run_pass(now)  # its next attempt has not come
    assert fresh(hub).status == "archiving"

    run_pass(failed.next_attempt_at + dt.timedelta(seconds=1))
    assert fresh(hub).status == "purged"
    assert failed.db_name not in databases()


def test_without_a_bucket_nothing_is_dropped(business, no_dumps_bucket):
    hub = business(left_days_ago=91)

    run_pass()

    hub = fresh(hub)
    assert hub.status == "archiving"
    assert hub.last_error.startswith("dumps_unavailable:")
    assert hub.db_name in databases()


def test_a_worker_that_stops_during_the_copy_drops_nothing_and_counts_no_attempt(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)

    def stopped(row, **kwargs):
        raise dumps.DumpStopped("the worker is stopping")

    monkeypatch.setattr(dumps, "dump_hub", stopped)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.next_attempt_at) == ("archiving", 0, None)
    assert hub.db_name in databases()


def test_a_drop_that_fails_keeps_its_copy_is_tried_again_and_the_pass_over_hub_due_leaves_it(
    business, dumps_bucket, moto_s3, monkeypatch, caplog
):
    hub = business(left_days_ago=91)
    real = ops.drop_database

    def refused(name, **kwargs):
        raise ops.DatabaseOpsError("no")

    monkeypatch.setattr(ops, "drop_database", refused)
    now = timezone.now()

    run_pass(now)

    failed = fresh(hub)
    assert failed.status == "dropping"
    assert failed.last_error == "drop_failed: no"
    assert failed.attempts == 1
    assert not HubDue.objects.filter(pk=hub.pk).exists()

    caplog.clear()
    with caplog.at_level(logging.INFO, logger="base.tenancy.provision"):
        provision.run_due(now + dt.timedelta(days=1))

    # Its own row, state and log, never how many the pass worked on: control holds whatever else its process has.
    # The pass logs every business it works on, by id or slug, even one it then leaves as it was.
    def state(row: Hub) -> tuple:
        return (row.status, row.attempts, row.last_error, row.next_attempt_at, row.updated_at)

    assert state(fresh(hub)) == state(failed)
    assert str(hub.pk) not in caplog.text and hub.slug not in caplog.text
    assert not HubDue.objects.filter(pk=hub.pk).exists()
    assert hub.db_name in databases(), "its database is the data pass's to drop, not the hub_due pass's"

    monkeypatch.setattr(ops, "drop_database", real)
    run_pass(failed.next_attempt_at + dt.timedelta(seconds=1))

    assert fresh(hub).status == "purged"
    assert HubDump.objects.filter(hub=hub).count() == 1, "the copy already made is not made twice"


def test_a_copy_already_made_is_not_made_twice_when_the_worker_comes_back_to_archiving(
    business, dumps_bucket, moto_s3
):
    hub = business(left_days_ago=91)
    dumps.dump_hub(hub, kind=HubDump.Kind.OFFBOARDING)
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ARCHIVING)

    run_pass()

    assert fresh(hub).status == "purged"
    assert HubDump.objects.filter(hub=hub).count() == 1


def test_a_database_already_gone_while_dropping_is_no_failure(business, dumps_bucket, moto_s3):
    hub = business(left_days_ago=91)
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.DROPPING)
    tenancy_connections.close_hub_aliases(hub)
    ops.drop_database(hub.db_name, cluster=None)

    run_pass()

    assert fresh(hub).status == "purged"
    assert not HubDump.objects.filter(hub=hub).exists(), "no copy of what is gone"


def test_a_lease_another_worker_holds_is_left_alone(business, dumps_bucket, moto_s3):
    hub = business(left_days_ago=91)
    now = timezone.now()
    assert services.claim_hub(hub.pk, now, provision.LEASE, owner="another") is not None

    run_pass(now)

    hub = fresh(hub)
    assert (hub.status, hub.attempts) == ("cancelled", 0)
    assert hub.db_name in databases()


def test_a_lease_lost_during_the_copy_leaves_the_business_to_its_new_holder(
    business, dumps_bucket, moto_s3, monkeypatch, caplog
):
    hub = business(left_days_ago=91)
    real = dumps.dump_hub

    def taken_over(row, **kwargs):
        made = real(row, **kwargs)
        HubDue.objects.filter(pk=row.pk).update(lease_owner="another")
        return made

    monkeypatch.setattr(dumps, "dump_hub", taken_over)

    with caplog.at_level(logging.INFO):
        run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.attempts) == ("archiving", 0)
    assert hub.db_name in databases()
    assert not [record.getMessage() for record in caplog.records if record.levelno >= logging.ERROR], (
        "another worker holding it is no failure: nothing to page anyone for"
    )


# ── Whose database ─────────────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("name_of", ["another_business", "a_demo"])
def test_a_row_that_names_a_database_not_its_own_drops_nothing(business, dumps_bucket, moto_s3, name_of):
    hub = business(left_days_ago=91)
    other = business(left_days_ago=None)
    control = tenancy_connections.control_name()
    alien = other.db_name if name_of == "another_business" else names.demo_db_name(control, other.pk)
    Hub.objects.filter(pk=hub.pk).update(db_name=alien)
    before = databases()

    run_pass()

    hub = fresh(hub)
    assert hub.status == "cancelled"
    assert hub.last_error.startswith("invalid_database_name:")
    assert databases() == before


@pytest.mark.parametrize(
    "fields",
    [{"is_platform": True}, {"is_demo": True}],
    ids=["the_platform", "a_demo"],
)
def test_the_platform_and_a_demo_are_never_taken_this_way(business, dumps_bucket, moto_s3, fields):
    hub = business(left_days_ago=91, **fields)

    run_pass()

    hub = fresh(hub)
    assert hub.status == "cancelled"
    assert hub.db_name in databases()
    assert not HubDump.objects.filter(hub=hub).exists()


@pytest.mark.parametrize("copying", ["moving_to", "restoring_from"])
def test_a_business_whose_database_is_copied_is_left_until_its_copy_ends(business, dumps_bucket, moto_s3, copying):
    hub = business(left_days_ago=91)
    cluster = Cluster.objects.create(name=f"elsewhere-{uuid.uuid7().hex[-8:]}", host="127.0.0.1", port=5432, is_open=False)
    try:
        Hub.objects.filter(pk=hub.pk).update(**{copying: cluster})

        run_pass()

        hub = fresh(hub)
        assert hub.status == "cancelled"
        assert hub.db_name in databases()
    finally:
        Hub.objects.filter(**{copying: cluster}).update(**{copying: None})
        cluster.delete()


def test_a_business_whose_database_was_never_finished_goes_without_copy_or_gate(business, dumps_bucket, moto_s3):
    never = business(left_days_ago=91, ready_at=None)
    empty = business(left_days_ago=91, ready_at=None)
    Hub.objects.filter(pk=empty.pk).update(db_name="")

    run_pass()
    run_pass()
    run_pass()
    run_pass()

    assert fresh(empty).status == "purged"
    assert fresh(never).status == "purged"
    assert not HubDump.objects.filter(hub__in=[never.pk, empty.pk]).exists()


# ── Its files, right after the drop ────────────────────────────────────────────────────────────────────────────────

def test_a_business_past_its_90_days_goes_with_its_files_and_every_other_keeps_theirs(
    business, dumps_bucket, hub_files_bucket, moto_s3
):
    gone, within, neighbour = business(left_days_ago=91), business(left_days_ago=89), business(left_days_ago=None)
    keep_files(gone)
    kept = keep_files(within) | keep_files(neighbour)

    run_pass()
    run_pass()

    assert (fresh(gone).status, fresh(within).status, fresh(neighbour).status) == ("purged", "cancelled", "ready")
    assert set(objects(moto_s3, hub_files_bucket)) == kept
    assert set(objects(moto_s3, dumps_bucket)) == {HubDump.objects.get(hub=gone).key}, "its final copy is not its files"


def test_the_files_go_right_after_the_drop_outside_any_transaction_and_before_the_tombstone(
    business, dumps_bucket, hub_files_bucket, monkeypatch
):
    hub = business(left_days_ago=91)
    seen = spy_on_the_purge(monkeypatch, lambda: fresh(hub).status)

    run_pass()

    assert seen == ["drop", ("files", hub.pk, False, "dropping")]
    assert fresh(hub).status == "purged"


def test_a_store_that_fails_leaves_it_dropping_noted_and_tried_again_never_purged(
    business, dumps_bucket, hub_files_bucket, moto_s3, settings, caplog
):
    hub = business(left_days_ago=91)
    keep_files(hub)
    settings.STORAGES = {**settings.STORAGES, "hub_files": hub_files_entry(moto_s3, "erplora-test-no-such-bucket")}
    now = timezone.now()

    with caplog.at_level(logging.WARNING, logger="base.tenancy.offboarding"):
        run_pass(now)

    failed = fresh(hub)
    assert (failed.status, failed.purged_at) == ("dropping", None), "a purge that left files behind is not done"
    assert failed.last_error.startswith("files_purge_failed: ")
    assert failed.attempts == 1
    assert failed.next_attempt_at > now
    assert failed.db_name not in databases(), "the database went first"
    assert "files_purge_failed" in caplog.text

    run_pass(now)
    assert fresh(hub).attempts == 1, "nothing before its next attempt"

    settings.STORAGES = {**settings.STORAGES, "hub_files": hub_files_entry(moto_s3, hub_files_bucket)}
    run_pass(failed.next_attempt_at + dt.timedelta(seconds=1))

    purged = fresh(hub)
    assert (purged.status, purged.last_error, purged.attempts) == ("purged", "", 0)
    assert objects(moto_s3, hub_files_bucket) == {}
    assert HubDump.objects.filter(hub=hub).count() == 1, "the copy already made is not made twice"


def test_a_drop_that_fails_keeps_its_files(business, dumps_bucket, hub_files_bucket, moto_s3, monkeypatch):
    hub = business(left_days_ago=91)
    kept = keep_files(hub)

    def refused(name, **kwargs):
        raise ops.DatabaseOpsError("no")

    monkeypatch.setattr(ops, "drop_database", refused)

    run_pass()

    assert fresh(hub).status == "dropping"
    assert set(objects(moto_s3, hub_files_bucket)) == kept


def test_a_business_with_fiscal_documents_keeps_its_files(business, dumps_bucket, hub_files_bucket, moto_s3):
    hub = business(left_days_ago=91)
    kept = keep_files(hub)
    with use_hub(hub):
        one_sale()

    run_pass()

    assert fresh(hub).status == "cancelled"
    assert set(objects(moto_s3, hub_files_bucket)) == kept


def test_a_row_that_names_a_database_not_its_own_keeps_its_files(business, dumps_bucket, hub_files_bucket, moto_s3):
    hub, other = business(left_days_ago=91), business(left_days_ago=None)
    kept = keep_files(hub)
    Hub.objects.filter(pk=hub.pk).update(db_name=other.db_name)

    run_pass()

    assert fresh(hub).last_error.startswith("invalid_database_name:")
    assert set(objects(moto_s3, hub_files_bucket)) == kept


def test_a_business_whose_database_was_never_made_goes_with_its_files_too(
    business, dumps_bucket, hub_files_bucket, moto_s3
):
    empty = business(left_days_ago=91, ready_at=None)
    keep_files(empty)
    Hub.objects.filter(pk=empty.pk).update(db_name="")

    run_pass()
    run_pass()

    assert fresh(empty).status == "purged"
    assert objects(moto_s3, hub_files_bucket) == {}


# ── The way back, and the doors of the SaaS meanwhile ──────────────────────────────────────────────────────────────


def internal():
    return system_context(registry.REGISTRY_SCOPE)


def registered(hub: Hub) -> HubRegistryIn:
    return HubRegistryIn(id=hub.pk, slug=hub.slug, name="Back again", vertical=hub.vertical)


def test_a_business_that_comes_back_during_its_final_copy_keeps_its_database(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    real = dumps.dump_hub

    def back(row, **kwargs):
        made = real(row, **kwargs)
        services.hub_restore(internal(), HubRestoreIn(id=row.pk))
        return made

    monkeypatch.setattr(dumps, "dump_hub", back)

    run_pass()

    hub = fresh(hub)
    assert hub.status == "ready"
    assert hub.db_name in databases()
    with use_hub(hub):
        assert current_alias()


def test_a_copy_that_fails_after_the_business_came_back_notes_nothing_on_it(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)

    def back_and_broken(row, **kwargs):
        services.hub_restore(internal(), HubRestoreIn(id=row.pk))
        raise dumps.DumpFailed("the bucket said no")

    monkeypatch.setattr(dumps, "dump_hub", back_and_broken)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.last_error, hub.next_attempt_at) == ("ready", 0, "", None)


def test_a_fiscal_document_found_after_the_business_came_back_leaves_it_ready(
    business, dumps_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    real = dumps.dump_hub

    def back_with_a_sale(row, **kwargs):
        made = real(row, **kwargs)
        services.hub_restore(internal(), HubRestoreIn(id=row.pk))
        with use_hub(row):
            one_sale()
        return made

    monkeypatch.setattr(dumps, "dump_hub", back_with_a_sale)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.last_error, hub.next_attempt_at) == ("ready", "", None)


def test_a_kept_business_that_comes_back_is_ready_and_clean(business, dumps_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    run_pass()
    hub = fresh(hub)
    assert (hub.status, hub.last_error.split(":")[0]) == ("cancelled", "fiscal_archive_missing")
    assert hub.next_attempt_at is not None

    services.hub_restore(internal(), HubRestoreIn(id=hub.pk))

    hub = fresh(hub)
    assert (hub.status, hub.attempts, hub.last_error, hub.next_attempt_at) == ("ready", 0, "", None)
    assert hub.db_name in databases()


def test_a_business_whose_database_is_going_never_comes_back(business):
    hub = business(left_days_ago=91, status=Hub.Status.DROPPING)

    for door, data in (
        (services.hub_restore, HubRestoreIn(id=hub.pk)),
        (services.hub_cancel, HubCancelIn(id=hub.pk)),
        (services.hub_register, registered(hub)),
    ):
        with pytest.raises(Conflict) as refused:
            door(internal(), data)
        assert refused.value.code == "hub_purged"
    assert fresh(hub).status == "dropping"


def test_a_cancel_while_archiving_does_not_count_the_90_days_again(business):
    hub = business(left_days_ago=91, status=Hub.Status.ARCHIVING)

    services.hub_cancel(internal(), HubCancelIn(id=hub.pk))

    after = fresh(hub)
    assert (after.status, after.cancelled_at) == ("archiving", hub.cancelled_at)


def test_a_register_while_archiving_asks_to_restore_first(business):
    hub = business(left_days_ago=91, status=Hub.Status.ARCHIVING)

    with pytest.raises(Conflict) as refused:
        services.hub_register(internal(), registered(hub))

    assert refused.value.code == "base.hub_cancelled"


def photo(hub: Hub, version: int) -> HubStateIn:
    return HubStateIn(id=hub.pk, version=version, photo={"plan": "starter"})


@pytest.mark.parametrize("status", ["dropping", "purged"])
def test_a_late_photo_of_a_business_whose_database_went_is_ignored(business, status):
    hub = business(left_days_ago=91, status=status)

    answer = services.hub_state_apply(internal(), photo(hub, hub.state_version + 1))

    assert answer.applied is False
    assert fresh(hub).state == hub.state


def test_a_photo_of_a_business_that_left_is_still_applied(business):
    hub = business(left_days_ago=10)

    answer = services.hub_state_apply(internal(), photo(hub, hub.state_version + 1))

    assert answer.applied is True


def test_the_saas_still_lists_the_copies_while_archiving_and_finds_nothing_once_purged(business, dumps_bucket, moto_s3):
    hub = business(left_days_ago=91)
    copy = dumps.dump_hub(hub, kind=HubDump.Kind.OFFBOARDING)
    Hub.objects.filter(pk=hub.pk).update(status=Hub.Status.ARCHIVING)

    listed = queries.hub_dump_list(internal(), HubGetIn(id=hub.pk))

    assert listed.available is True
    assert [row.id for row in listed.dumps] == [copy.key]

    run_pass()

    assert fresh(hub).status == "purged"
    with pytest.raises(NotFound):
        queries.hub_dump_list(internal(), HubGetIn(id=hub.pk))


def test_the_purge_is_only_for_a_business_being_dropped(business):
    hub = business(left_days_ago=91)

    with pytest.raises(Conflict) as refused:
        services.hub_purge(internal(), HubGetIn(id=hub.pk))

    assert refused.value.code == "base.hub_not_dropping"


def test_the_tombstone_keeps_nothing_of_the_business(business, dumps_bucket, moto_s3):
    from django.contrib.auth import get_user_model

    from base.models import Membership

    hub = business(left_days_ago=91, name="Peluquería Ana", state={"plan": "starter"})
    person = get_user_model().objects.create(username=f"saas:{uuid.uuid7().hex}")
    Membership.objects.create(user=person, host=hub.slug, role="hub_owner")
    try:
        run_pass()

        after = fresh(hub)
        assert after.status == "purged"
        assert (after.name, after.state, after.cluster_id) == ("", {}, None)
        assert after.slug == hub.slug, "its address stays taken"
        assert not Membership.objects.filter(host=hub.slug).exists()
        assert get_user_model().objects.filter(pk=person.pk).exists(), "the person's account is not the business's"
        assert registry.refusal(after).status == 410
        with use_control():
            assert OutboxEvent.objects.filter(name=HUB_PURGED, payload__id=str(hub.pk)).exists()
    finally:
        get_user_model().objects.filter(pk=person.pk).delete()


def test_a_tombstone_does_not_keep_its_cluster_from_being_deleted(business):
    from control import services as control_services
    from control.schemas import ClusterIdIn

    hub = business(left_days_ago=91, status=Hub.Status.DROPPING)
    cluster = Cluster.objects.create(name=f"old-{uuid.uuid7().hex[-8:]}", host="127.0.0.1", port=5432, is_open=False)
    try:
        Hub.objects.filter(pk=hub.pk).update(cluster=cluster)

        services.hub_purge(internal(), HubGetIn(id=hub.pk))
        control_services.cluster_delete(internal(), ClusterIdIn(id=cluster.pk))

        assert not Cluster.objects.filter(pk=cluster.pk).exists()
    finally:
        Hub.objects.filter(cluster=cluster).update(cluster=None)
        Cluster.objects.filter(pk=cluster.pk).delete()
