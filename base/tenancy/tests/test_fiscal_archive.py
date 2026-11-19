"""The fiscal archive of a business that left with fiscal documents, written before anything of it is dropped.

Its database stays (the drop of such a business is not turned on yet); what changes is that, with
``FISCAL_ARCHIVE_BUCKET`` named, the worker writes every fiscal document there first, whole and verifiable, and notes
it on the row. Real databases and a real S3 (moto's) with Object Lock, as aws's bucket.
"""

import base64
import datetime as dt
import hashlib
import json
import logging

import pytest
from botocore.exceptions import ClientError
from django.utils import timezone
from live.meta import all_live_app_configs

from base.tenancy import fiscal_archive, offboarding
from base.tenancy.context import use_hub
from base.tenancy.tests import s3
from base.tenancy.tests import test_offboarding as leaving
from base.tenancy.tests.s3 import body, client, objects
from base.tenancy.tests.test_offboarding import (
    DAY,
    KEEP_FISCAL_DOCUMENTS,
    databases,
    fresh,
    one_cash_movement,
    one_record,
    one_sale,
    run_pass,
)
from control.models import HubDump

# The fixtures these tests share with the copies and the drop of a business that left.
moto_s3, aws_test_credentials, dumps_bucket = s3.moto_s3, s3.aws_test_credentials, s3.dumps_bucket
fiscal_archive_bucket, no_fiscal_archive_bucket = s3.fiscal_archive_bucket, s3.no_fiscal_archive_bucket
business = leaving.business


def sale(number: int):
    from apps.sale.models import Sale

    return Sale.objects.create(
        number=f"20261014-{number:04d}", business_day=DAY, sequence=number, idempotency_key=f"key-{number}", total=100
    )


def manifest_of(endpoint: str, bucket: str, hub) -> tuple[str, dict]:
    keys = [key for key in objects(endpoint, bucket) if key.endswith("/manifest.json")]
    assert len(keys) == 1, keys
    assert keys[0].startswith(f"{hub.id.hex}/")
    return keys[0], json.loads(body(endpoint, bucket, keys[0]))


def archived_rows(endpoint: str, bucket: str, manifest: dict) -> list[dict]:
    rows = []
    for entry in manifest["files"]:
        content = body(endpoint, bucket, entry["key"])
        rows += [json.loads(line) for line in content.decode().splitlines()]
    return rows


def database_rows(hub, labels: list[str]) -> set[tuple[str, str]]:
    from django.apps import apps as django_apps

    found = set()
    with use_hub(hub):
        for label in labels:
            config = django_apps.get_app_config(label)
            for name in config.fiscal_archive_models:
                model = config.get_model(name)
                found |= {(model._meta.label_lower, str(pk)) for pk in model._base_manager.values_list("pk", flat=True)}
    return found


def test_a_business_with_documents_is_archived_whole_before_anything_goes_and_keeps_its_database(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
        one_record()
        one_cash_movement()
    now = timezone.now()

    run_pass(now)

    hub = fresh(hub)
    assert (hub.status, hub.purged_at) == ("cancelled", None)
    assert hub.db_name in databases()
    assert hub.last_error == "fiscal_archived: cash_register, invoice, sale, verifactu"
    assert hub.fiscal_archived_at is not None
    assert hub.next_attempt_at == now + dt.timedelta(days=1)
    assert not HubDump.objects.filter(hub=hub).exists()

    manifest_key, manifest = manifest_of(moto_s3, fiscal_archive_bucket, hub)
    assert manifest["business"]["id"] == str(hub.id)
    assert manifest["apps"] == ["cash_register", "invoice", "sale", "verifactu"]
    kept = objects(moto_s3, fiscal_archive_bucket)
    assert set(kept) == {entry["key"] for entry in manifest["files"]} | {manifest_key}
    for entry in manifest["files"]:
        content = body(moto_s3, fiscal_archive_bucket, entry["key"])
        assert entry["bytes"] == len(content) == kept[entry["key"]]
        assert entry["sha256"] == hashlib.sha256(content).hexdigest()
        assert entry["rows"] == len(content.splitlines())
    rows = archived_rows(moto_s3, fiscal_archive_bucket, manifest)
    assert {(row["model"], row["pk"]) for row in rows} == database_rows(hub, manifest["apps"])
    assert sum(manifest["models"].values()) == len(rows) == manifest["total"]["rows"]
    assert manifest["total"]["files"] == len(manifest["files"])


def test_a_record_is_archived_as_it_is_stored_never_rebuilt(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_record()
        from apps.verifactu.models import Record

        Record.objects.update(xml="<sf:RegistroAlta>as it was sent</sf:RegistroAlta>")
        stored = Record.objects.values("id", "fingerprint", "xml", "qr_url").get()

    run_pass()

    _, manifest = manifest_of(moto_s3, fiscal_archive_bucket, hub)
    [record] = [row for row in archived_rows(moto_s3, fiscal_archive_bucket, manifest) if row["model"] == "verifactu.record"]
    assert record["pk"] == str(stored["id"])
    assert {name: record["fields"][name] for name in ("fingerprint", "xml", "qr_url")} == {
        name: stored[name] for name in ("fingerprint", "xml", "qr_url")
    }


def test_each_document_is_locked_by_the_bucket_and_written_once_with_its_checksum_the_manifest_last(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
        one_record()
    s3, puts = client(moto_s3), []
    s3.meta.events.register("provide-client-params.s3.PutObject", lambda params, **kwargs: puts.append(dict(params)))
    monkeypatch.setattr(fiscal_archive, "client", lambda: s3)

    run_pass()

    manifest_key, manifest = manifest_of(moto_s3, fiscal_archive_bucket, hub)
    assert [put["Key"] for put in puts][-1] == manifest_key
    assert len(puts) == len(manifest["files"]) + 1
    for put in puts:
        assert put["ChecksumAlgorithm"] == "SHA256"
        assert put["ChecksumSHA256"] == base64.b64encode(hashlib.sha256(put["Body"]).digest()).decode()
        assert put["IfNoneMatch"] == "*"
        assert not {"ObjectLockMode", "ObjectLockRetainUntilDate", "ObjectLockLegalHoldStatus"} & set(put)
        head = s3.head_object(Bucket=fiscal_archive_bucket, Key=put["Key"])
        assert head["ObjectLockMode"] == "COMPLIANCE"


def test_a_large_table_goes_in_parts_read_a_page_at_a_time_and_none_is_lost(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    from apps.sale.models import Sale

    from base.services import fiscal_archive as reads

    hub = business(left_days_ago=91)
    with use_hub(hub):
        for number in range(1, 8):
            sale(number)
        longest = max(len(line) for line in reads.rows(Sale))
    # Two rows fill a part, so the last of the 7 goes alone; read 3 at a time, a page ends inside a part.
    monkeypatch.setattr(fiscal_archive, "PART_BYTES", 2 * longest - 1)
    monkeypatch.setattr(reads, "PAGE_ROWS", 3)

    run_pass()

    _, manifest = manifest_of(moto_s3, fiscal_archive_bucket, hub)
    sales = [entry for entry in manifest["files"] if entry["model"] == "sale.sale"]
    assert [entry["rows"] for entry in sales] == [2, 2, 2, 1]
    assert len({entry["key"] for entry in manifest["files"]}) == len(manifest["files"])
    assert manifest["models"]["sale.sale"] == 7
    rows = archived_rows(moto_s3, fiscal_archive_bucket, manifest)
    assert {(row["model"], row["pk"]) for row in rows} == database_rows(hub, ["sale"])


def test_the_archive_of_one_business_holds_nothing_of_another(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    leaving, other = business(left_days_ago=91), business(left_days_ago=None)
    with use_hub(leaving):
        sale(1)
    with use_hub(other):
        sale(2)
        sale(3)

    run_pass()

    _, manifest = manifest_of(moto_s3, fiscal_archive_bucket, leaving)
    rows = archived_rows(moto_s3, fiscal_archive_bucket, manifest)
    assert {(row["model"], row["pk"]) for row in rows} == database_rows(leaving, ["sale"])
    assert all(key.startswith(f"{leaving.id.hex}/") for key in objects(moto_s3, fiscal_archive_bucket))


def test_an_archived_business_is_not_archived_again(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    now = timezone.now()
    run_pass(now)
    archived, written = fresh(hub).fiscal_archived_at, objects(moto_s3, fiscal_archive_bucket)

    run_pass(now + dt.timedelta(days=1, minutes=1))

    hub = fresh(hub)
    assert (hub.status, hub.fiscal_archived_at, hub.last_error) == ("cancelled", archived, "fiscal_archived: sale")
    assert objects(moto_s3, fiscal_archive_bucket) == written


def test_an_archive_made_in_the_very_second_the_90_days_end_is_not_made_again(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    # The 90 days end 900 ms into a second and the pass comes 50 ms later: the archive's time, kept to the second, is
    # earlier than that end.
    ends = timezone.now().replace(microsecond=900_000)
    type(hub).objects.filter(pk=hub.pk).update(cancelled_at=ends - dt.timedelta(days=90))
    now = ends + dt.timedelta(milliseconds=50)
    with monkeypatch.context() as clock:
        clock.setattr(timezone, "now", lambda: now)
        run_pass(now)
    archived, written = fresh(hub).fiscal_archived_at, objects(moto_s3, fiscal_archive_bucket)
    assert archived is not None

    run_pass(now + dt.timedelta(days=1, minutes=1))

    hub = fresh(hub)
    assert (hub.fiscal_archived_at, hub.last_error) == (archived, "fiscal_archived: sale")
    assert objects(moto_s3, fiscal_archive_bucket) == written


def test_an_archive_of_an_earlier_leaving_does_not_count(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    type(hub).objects.filter(pk=hub.pk).update(fiscal_archived_at=hub.cancelled_at - dt.timedelta(days=30))

    run_pass()

    assert fresh(hub).fiscal_archived_at > hub.cancelled_at
    manifest_of(moto_s3, fiscal_archive_bucket, hub)


def test_without_the_archive_bucket_nothing_changes(business, dumps_bucket, no_fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.last_error, hub.fiscal_archived_at) == ("cancelled", "fiscal_archive_missing: sale", None)
    assert hub.db_name in databases()


def failing_on(monkeypatch, endpoint: str, operation: str, after: int):
    """The archive's S3, whose ``operation`` fails from its ``after + 1``-th call on."""
    s3, calls = client(endpoint), []

    def fail(**kwargs):
        calls.append(kwargs)
        if len(calls) > after:
            raise ClientError({"Error": {"Code": "InternalError", "Message": "We encountered an internal error"}}, "x")

    s3.meta.events.register(f"before-call.s3.{operation}", lambda **kwargs: fail())
    monkeypatch.setattr(fiscal_archive, "client", lambda: s3)


@pytest.mark.parametrize(("operation", "after"), [("PutObject", 1), ("HeadObject", 0)])
def test_an_archive_that_fails_marks_nothing_writes_no_manifest_and_says_why(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch, caplog, operation, after
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
        one_cash_movement()
    failing_on(monkeypatch, moto_s3, operation, after)
    now = timezone.now()

    with caplog.at_level(logging.WARNING, logger="base.tenancy.offboarding"):
        run_pass(now)

    hub = fresh(hub)
    assert (hub.status, hub.fiscal_archived_at) == ("cancelled", None)
    assert hub.db_name in databases()
    assert hub.last_error.startswith("fiscal_archive_failed: ")
    assert "InternalError" in hub.last_error
    assert hub.next_attempt_at == now + dt.timedelta(days=1)
    assert not [key for key in objects(moto_s3, fiscal_archive_bucket) if key.endswith("/manifest.json")]
    assert any("fiscal_archive_failed" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize("altered_file", [".jsonl", "/manifest.json"], ids=["a-table", "the-manifest"])
def test_a_document_that_does_not_read_back_as_written_marks_nothing(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch, altered_file
):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    s3, read = client(moto_s3), []
    s3.meta.events.register("provide-client-params.s3.HeadObject", lambda params, **kwargs: read.append(params["Key"]))

    def altered(http_response, parsed, **kwargs):
        if read[-1].endswith(altered_file):
            parsed["ChecksumSHA256"] = base64.b64encode(hashlib.sha256(b"something else").digest()).decode()

    s3.meta.events.register("after-call.s3.HeadObject", altered)
    monkeypatch.setattr(fiscal_archive, "client", lambda: s3)

    run_pass()

    hub = fresh(hub)
    assert read[-1].endswith(altered_file)
    assert (hub.status, hub.fiscal_archived_at) == ("cancelled", None)
    assert hub.last_error.startswith("fiscal_archive_failed: ")
    manifests = [key for key in objects(moto_s3, fiscal_archive_bucket) if key.endswith("/manifest.json")]
    assert bool(manifests) == (altered_file == "/manifest.json")


def test_the_lease_is_renewed_after_each_file_of_the_archive(
    business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch
):
    from base import services

    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    renewed, renew = [], services.reset.renew_lease
    monkeypatch.setattr(services.reset, "renew_lease", lambda hub_id, lease: renewed.append(hub_id) or renew(hub_id, lease))

    run_pass()

    _, manifest = manifest_of(moto_s3, fiscal_archive_bucket, hub)
    assert renewed == [hub.pk] * (len(manifest["files"]) + 1)


def test_a_failed_archive_is_written_whole_the_next_day(business, dumps_bucket, fiscal_archive_bucket, moto_s3, monkeypatch):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()
    now = timezone.now()
    with monkeypatch.context() as failing:
        failing_on(failing, moto_s3, "PutObject", 0)
        run_pass(now)

    run_pass(now + dt.timedelta(days=1, minutes=1))

    hub = fresh(hub)
    assert (hub.last_error, hub.fiscal_archived_at is not None) == ("fiscal_archived: sale", True)
    manifest_of(moto_s3, fiscal_archive_bucket, hub)


def test_records_still_waiting_for_the_aeat_are_not_archived_yet(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_record()
        from apps.verifactu.models import Config, Record

        Record.objects.update(environment=Config.Environment.PRODUCTION, status=Record.Status.PENDING)

    run_pass()

    hub = fresh(hub)
    assert (hub.status, hub.fiscal_archived_at) == ("cancelled", None)
    assert hub.last_error == "fiscal_archive_waiting: verifactu"
    assert objects(moto_s3, fiscal_archive_bucket) == {}


def test_a_worker_that_stops_during_the_archive_marks_nothing(business, dumps_bucket, fiscal_archive_bucket, moto_s3):
    hub = business(left_days_ago=91)
    with use_hub(hub):
        one_sale()

    with pytest.raises(fiscal_archive.ArchiveStopped):
        offboarding.retire(hub.pk, timezone.now(), cancelled=lambda: True)

    hub = fresh(hub)
    assert (hub.status, hub.fiscal_archived_at, hub.attempts) == ("cancelled", None, 0)
    assert not [key for key in objects(moto_s3, fiscal_archive_bucket) if key.endswith("/manifest.json")]


#: The models of the apps with fiscal documents that are no document: each one looked at, so a model added to one of
#: these apps has to say which side it is on, or the archive would miss it without anyone noticing. Settings, numbering
#: counters and the AEAT's queue are no document; the business's own certificate is a secret and never leaves its
#: database; ``AeatRecord`` is only the last photo of what the AEAT holds; an open order (``sale.Order``) is no sale
#: yet; and a customer's card, consents and health notes are the customer's, not the purchase's.
NOT_ARCHIVED = {
    "sale": {"Department", "Order", "OrderLine", "PaymentMethod", "QuickNote", "SaleCounter", "Settings", "VoucherSession"},
    "invoice": set(),
    "verifactu": {"AeatRecord", "Config", "OwnCertificate", "SendControl"},
    "payment": {"PaymentCounter"},
    "cash_register": {"SessionCounter", "Settings"},
    "cart_checkout": {"OrderCounter"},
    "customer": {
        "Activity",
        "Consent",
        "CustomField",
        "CustomFieldValue",
        "Customer",
        "CustomerGroup",
        "CustomerTag",
        "HealthRecord",
        "OrderLink",
    },
}


def test_every_model_of_an_app_with_fiscal_documents_is_on_one_side_of_the_archive():
    configs = {config.label: config for config in all_live_app_configs() if config.kind == "app"}

    declared = {label for label, config in configs.items() if hasattr(config, "fiscal_archive_models")}
    assert declared == KEEP_FISCAL_DOCUMENTS == set(NOT_ARCHIVED)
    for label in declared:
        archived = set(configs[label].fiscal_archive_models)
        assert archived, label
        assert not archived & NOT_ARCHIVED[label], label
        assert archived | NOT_ARCHIVED[label] == {model.__name__ for model in configs[label].get_models()}, label
