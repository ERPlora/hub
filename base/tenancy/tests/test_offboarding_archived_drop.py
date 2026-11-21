"""A business with fiscal documents goes after its 90 days as any other, once they are in the fiscal archive.

Its final copy first, then the archive of its documents, made after that copy (so it holds whatever was written while
the copy was made), then the drop. Without the archive, or with one that fails, nothing goes and the row says why; and a
final copy made long ago is never what a business goes with. Real databases and a real S3 (moto's), as the rest of the
way out.
"""

import datetime as dt
import json
import uuid

from django.utils import timezone

from base import services
from base.tenancy import dumps, ops
from base.tenancy.context import use_hub
from base.tenancy.tests import s3
from base.tenancy.tests import test_offboarding as leaving
from base.tenancy.tests.s3 import body, objects
from base.tenancy.tests.test_offboarding import (
    KEEP_FISCAL_DOCUMENTS,
    databases,
    fresh,
    one_card_sale,
    one_cash_movement,
    one_payment,
    one_record,
    one_sale,
    one_shop_order,
    run_pass,
)
from control.models import Hub, HubDump

# The fixtures these tests share with the rest of the way out of a business.
moto_s3, aws_test_credentials, dumps_bucket = s3.moto_s3, s3.aws_test_credentials, s3.dumps_bucket
fiscal_archive_bucket, no_fiscal_archive_bucket = s3.fiscal_archive_bucket, s3.no_fiscal_archive_bucket
business = leaving.business


def manifests(endpoint: str, bucket: str) -> list[str]:
    return sorted(key for key in objects(endpoint, bucket) if key.endswith("/manifest.json"))


def archived(endpoint: str, bucket: str) -> dict:
    [key] = manifests(endpoint, bucket)
    return json.loads(body(endpoint, bucket, key))


def every_document():
    one_sale()
    one_record()
    one_payment()
    one_cash_movement()
    one_shop_order()
    one_card_sale()


def an_old_final_copy(hub: Hub, days_ago: int) -> HubDump:
    """A copy of ``hub`` on leaving, made ``days_ago`` days ago (after its 90 days): only its row, as the night keeps it."""
    made = timezone.now() - dt.timedelta(days=days_ago)
    return HubDump.objects.create(
        hub=hub, kind=HubDump.Kind.OFFBOARDING, key=f"{hub.id.hex}/old-{uuid.uuid4().hex}.dump", bytes=1, created_at=made
    )


def test_a_business_with_fiscal_documents_goes_once_they_are_archived_after_its_final_copy(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        every_document()
    real, seen = ops.drop_database, []

    def spied(name, **kwargs):
        seen.append((name, fresh(hub).status, manifests(moto_s3, fiscal_archive_bucket), HubDump.objects.filter(hub=hub).count()))
        return real(name, **kwargs)

    monkeypatch.setattr(ops, "drop_database", spied)
    before = databases()

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.purged_at is not None) == ("purged", True)
    assert databases() == before - {hub.db_name}
    [(name, status, archive, copies)] = seen
    assert (name, status, len(archive), copies) == (hub.db_name, "dropping", 1, 1)
    assert archived(moto_s3, fiscal_archive_bucket)["apps"] == sorted(KEEP_FISCAL_DOCUMENTS)
    copy = HubDump.objects.get(hub=hub)
    assert copy.created_at >= hub.cancelled_at + dt.timedelta(days=90)
    assert hub.fiscal_archived_at >= copy.created_at.replace(microsecond=0)


def test_a_document_written_while_the_final_copy_is_made_goes_to_the_archive_too(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    from apps.sale.models import Sale

    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    real = dumps.dump_hub

    def a_sale_meanwhile(row, **kwargs):
        made = real(row, **kwargs)
        with use_hub(row):
            Sale.objects.create(number="20261014-0002", business_day=leaving.DAY, sequence=2, idempotency_key="key-2", total=1)
        return made

    monkeypatch.setattr(dumps, "dump_hub", a_sale_meanwhile)

    run_pass()

    assert fresh(hub).status == "purged"
    assert archived(moto_s3, fiscal_archive_bucket)["models"]["sale.sale"] == 2


def test_an_archive_made_before_the_final_copy_is_made_again_after_it(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3
):
    hub = business(left_days_ago=120)
    with use_hub(hub):
        one_sale()
    # Archived after its 90 days, while it was kept with its database, and before any final copy: whatever it wrote
    # since is in no archive.
    Hub.objects.filter(pk=hub.pk).update(fiscal_archived_at=hub.cancelled_at + dt.timedelta(days=91))

    run_pass()

    hub = fresh(hub)
    assert hub.status == "purged"
    assert len(manifests(moto_s3, fiscal_archive_bucket)) == 1
    assert hub.fiscal_archived_at >= HubDump.objects.get(hub=hub).created_at.replace(microsecond=0)


def test_without_the_archive_a_business_with_documents_keeps_everything_and_says_why(
    business, dumps_bucket, no_fiscal_archive_bucket, moto_s3
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    now = timezone.now()

    run_pass(now)

    hub = fresh(hub)
    assert (hub.status, hub.purged_at, hub.last_error) == ("cancelled", None, "fiscal_archive_missing: sale")
    assert hub.db_name in databases()
    assert hub.next_attempt_at == now + dt.timedelta(days=1)


def test_an_old_final_copy_is_never_what_a_business_goes_with(business, dumps_bucket, moto_s3, monkeypatch):
    hub = business(left_days_ago=130)
    an_old_final_copy(hub, days_ago=35)

    def broken(row, **kwargs):
        raise dumps.DumpFailed("the bucket said no")

    monkeypatch.setattr(dumps, "dump_hub", broken)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.last_error) == ("archiving", "dump_failed: the bucket said no")
    assert hub.db_name in databases()


def test_a_business_kept_after_its_final_copy_makes_a_new_one_before_it_goes(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3
):
    hub = business(left_days_ago=200)
    with use_hub(hub):
        one_sale()
    old = an_old_final_copy(hub, days_ago=100)

    run_pass()

    hub = fresh(hub)
    assert hub.status == "purged"
    new = HubDump.objects.filter(hub=hub).exclude(pk=old.pk).get()
    assert new.created_at > timezone.now() - services.offboarding.FINAL_COPY_FRESH
    assert hub.fiscal_archived_at >= new.created_at.replace(microsecond=0)


def test_an_archive_made_before_the_90_days_end_is_not_one_of_this_leaving():
    left = timezone.now() - dt.timedelta(days=120)
    ends = left + services.offboarding.OFFBOARDING_RETENTION

    assert not services.offboarding.fiscal_archive_kept(Hub(cancelled_at=left, fiscal_archived_at=ends - dt.timedelta(days=1)))
    assert services.offboarding.fiscal_archive_kept(Hub(cancelled_at=left, fiscal_archived_at=ends + dt.timedelta(days=1)))
