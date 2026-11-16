"""``manage.py delete_leftover_hub_files``: what the hubs gone before hub#781 left in the store, deleted once (hub#785).

Since hub#781 a purge deletes the hub's files after its database (``base.files.delete_hub_files``), but a row already
``purged`` never goes through the purge again, so its prefix stayed. The command finds those prefixes in the hub file
store (a real S3, moto's, versioned as prod's, and the disk of local development) and only lists them unless
``--delete``; a hub that is not gone, ``shared/``, the inventory's ``_inventory/`` and anything that is not a hub's
prefix are never touched, nor is any hub's database (the two of the session, real).
"""

import datetime as dt
import uuid
from io import StringIO

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from base import files
from base.storage import hub_prefix
from base.tenancy.tests import hubs
from base.tenancy.tests.s3 import aws_test_credentials, hub_files_bucket, moto_s3  # noqa: F401
from control.models import Hub

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES), pytest.mark.usefixtures("no_test_fallback")]

#: What a hub keeps: its Files and what its apps write beside them.
KEPT = ("files/contract.pdf", "files/Holidays/photo.jpg", "website/img/3f2a9c.webp")
#: What sits at the top of the bucket and is no hub's: the blueprints' catalog, S3's inventory, other shapes.
NO_HUB_S = ("shared/catalog/img/coffee.webp", "_inventory/erplora-prod-hubs/data/1.csv.gz", "hub-notahex/files/a.pdf")


@pytest.fixture(params=["s3", "disk"])
def store(request, settings, tmp_path):
    if request.param == "s3":
        request.getfixturevalue("hub_files_bucket")
    else:
        disk = {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path / "hubs"}}
        settings.STORAGES = {**settings.STORAGES, "hub_files": disk}
    return storages["hub_files"]


def keep(store, hub_id: uuid.UUID) -> None:
    for name in KEPT:
        store.save(f"{hub_prefix(hub_id)}/{name}", ContentFile(b"bytes"))


def held(store, hub_id: uuid.UUID) -> set[str]:
    return {item.key for item in files.scan(store, hub_prefix(hub_id))}


def registry_row(status: str, **fields) -> Hub:
    hub_id = uuid.uuid7()
    return Hub.objects.create(id=hub_id, slug=f"{status}-{hub_id.hex[-8:]}", status=status, **fields)


def run(*args: str) -> str:
    out = StringIO()
    call_command("delete_leftover_hub_files", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def leftovers(store):
    """A demo and a business purged before hub#781, with their files, and a prefix whose row was forgotten."""
    purged_at = timezone.now() - dt.timedelta(days=40)
    demo = registry_row(Hub.Status.PURGED, is_demo=True, purged_at=purged_at)
    business = registry_row(Hub.Status.PURGED, purged_at=purged_at)
    forgotten = uuid.uuid7()
    for hub_id in (demo.pk, business.pk, forgotten):
        keep(store, hub_id)
    return demo.pk, business.pk, forgotten


def test_by_default_it_lists_each_leftover_and_deletes_nothing(store, leftovers, hub_a):
    keep(store, hub_a.pk)

    output = run()

    for hub_id in leftovers:
        assert hub_prefix(hub_id) in output
        assert held(store, hub_id) == set(KEPT)
    assert hub_prefix(hub_a.pk) not in output
    assert held(store, hub_a.pk) == set(KEPT)


def test_delete_takes_the_purged_and_the_forgotten_and_never_a_hub_that_is_not_gone(store, leftovers, hub_a, hub_b):
    # Every status but purged keeps its files: on its way (requested…), served (ready), restorable (cancelled),
    # still being dropped (expired, archiving, dropping: its own purge deletes them, and retries).
    not_gone = [hub_a.pk, hub_b.pk] + [
        registry_row(status).pk for status in Hub.Status.values if status != Hub.Status.PURGED
    ]
    for hub_id in not_gone:
        keep(store, hub_id)
    for key in NO_HUB_S:
        store.save(key, ContentFile(b"bytes"))
    # A prefix that starts as a gone hub's is another one.
    store.save(f"{hub_prefix(leftovers[0])}0/files/contract.pdf", ContentFile(b"bytes"))

    with hubs.watched() as sent:
        output = run("--delete")

    for hub_id in leftovers:
        assert held(store, hub_id) == set(), hub_prefix(hub_id)
        assert hub_prefix(hub_id) in output
    for hub_id in not_gone:
        assert held(store, hub_id) == set(KEPT), Hub.objects.get(pk=hub_id).status
    for key in (*NO_HUB_S, f"{hub_prefix(leftovers[0])}0/files/contract.pdf"):
        assert store.exists(key), key
    assert set(sent) <= {"default"}, "no hub's database is reached, only control's registry"


def test_a_second_run_finds_nothing_left(store, leftovers):
    run("--delete")

    output = run("--delete")

    for hub_id in leftovers:
        assert hub_prefix(hub_id) not in output


def test_an_empty_store_is_no_failure(store):
    run()
    run("--delete")


def test_a_hub_made_while_the_store_is_listed_keeps_its_files(store, leftovers, monkeypatch):
    # The store is listed before the registry is read: a hub's row exists before its first file, so a hub made in
    # between is either not listed or found in the registry, never taken for gone.
    real, made = files.hubs_in_store, []

    def listed_while_a_hub_is_made(store_):
        hub = registry_row(Hub.Status.READY)
        keep(store_, hub.pk)
        made.append(hub.pk)
        return real(store_)

    monkeypatch.setattr(files, "hubs_in_store", listed_while_a_hub_is_made)

    run("--delete")

    assert held(store, made[0]) == set(KEPT)
    assert all(held(store, hub_id) == set() for hub_id in leftovers)


def test_a_store_that_cannot_be_listed_deletes_nothing_and_fails(hub_files_bucket):
    store = storages["hub_files"]
    gone = registry_row(Hub.Status.PURGED)
    keep(store, gone.pk)
    store.bucket_name = "erplora-test-no-such-bucket"

    with pytest.raises(CommandError, match="base.file_store_unavailable"):
        run("--delete")

    store.bucket_name = hub_files_bucket
    assert held(store, gone.pk) == set(KEPT)


def test_a_prefix_that_fails_does_not_stop_the_others_and_the_run_fails(store, leftovers, monkeypatch):
    refused, real = leftovers[1], files.delete_hub_files

    def refusing(store_, hub_id):
        if hub_id == refused:
            raise files.HubFilesNotDeleted(f"{hub_prefix(hub_id)}: AccessDenied")
        return real(store_, hub_id)

    monkeypatch.setattr(files, "delete_hub_files", refusing)

    with pytest.raises(CommandError, match=hub_prefix(refused)):
        run("--delete")

    assert held(store, refused) == set(KEPT)
    assert held(store, leftovers[0]) == set() and held(store, leftovers[2]) == set()
