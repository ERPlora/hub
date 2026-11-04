"""``files.delete_hub_files``: a hub's whole prefix leaves the store and nothing of anyone else's does (hub#613).

What purges a demo (``base.services.purge_demo_data``) and a business past its 90 days (``base.tenancy.offboarding``)
calls it, once its database went (PLAN-DB §6 «Baja», step 4). On S3 (a real server, moto's, with the bucket versioned
as prod's) and on disk (local development); what the store could not do is never taken for «nothing there».
"""

import uuid

import pytest
from django.core.files.base import ContentFile
from django.core.files.storage import storages

from base import files
from base.storage import hub_prefix
from base.tenancy.tests.s3 import aws_test_credentials, client, hub_files_bucket, moto_s3, objects  # noqa: F401

HUB, NEIGHBOUR = uuid.uuid7(), uuid.uuid7()
#: What a business keeps: its Files, folders and the marker of an empty one included, and what its apps write beside them.
KEPT = ("files/contract.pdf", "files/Holidays/2026/photo.jpg", "files/Empty/.keep", "website/img/3f2a9c.webp", "avatars/a.webp")


@pytest.fixture
def on_disk(settings, tmp_path):
    settings.STORAGES = {
        **settings.STORAGES,
        "hub_files": {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": tmp_path}},
    }
    return storages["hub_files"]


@pytest.fixture
def on_s3(hub_files_bucket):
    return storages["hub_files"]


@pytest.fixture(params=["on_s3", "on_disk"])
def store(request):
    return request.getfixturevalue(request.param)


def keep(store, hub: uuid.UUID, *names: str) -> None:
    for name in names:
        store.save(f"{hub_prefix(hub)}/{name}", ContentFile(b"bytes"))


def held(store, hub: uuid.UUID) -> set[str]:
    return {item.key for item in files.scan(store, hub_prefix(hub))}


def test_everything_under_the_hub_s_prefix_goes(store):
    keep(store, HUB, *KEPT)
    assert held(store, HUB) == set(KEPT)

    files.delete_hub_files(store, HUB)

    assert held(store, HUB) == set()
    assert not store.exists(hub_prefix(HUB)), "no folder left behind on disk"


def test_nothing_of_anyone_else_goes(store):
    keep(store, HUB, *KEPT)
    keep(store, NEIGHBOUR, *KEPT)
    # A prefix that starts the same is another one, and the blueprints' catalog is everyone's.
    store.save(f"{hub_prefix(HUB)}0/files/contract.pdf", ContentFile(b"bytes"))
    store.save("shared/catalog/img/coffee.webp", ContentFile(b"bytes"))

    files.delete_hub_files(store, HUB)

    assert held(store, NEIGHBOUR) == set(KEPT)
    assert store.exists(f"{hub_prefix(HUB)}0/files/contract.pdf")
    assert store.exists("shared/catalog/img/coffee.webp")


def test_a_hub_with_nothing_kept_is_no_failure_and_a_second_pass_neither(store):
    files.delete_hub_files(store, HUB)
    keep(store, HUB, *KEPT)
    files.delete_hub_files(store, HUB)
    files.delete_hub_files(store, HUB)
    assert held(store, HUB) == set()


def test_more_keys_than_one_request_takes_go_all_the_same(on_s3, moto_s3, hub_files_bucket, monkeypatch):
    # S3 refuses a DeleteObjects of more than 1000 keys; moto does not, so what is sent is what the test reads.
    s3 = client(moto_s3)
    many = files.S3_DELETE_BATCH + 1
    for number in range(many):
        s3.put_object(Bucket=hub_files_bucket, Key=f"{hub_prefix(HUB)}/files/{number}.txt", Body=b"")
    keep(on_s3, NEIGHBOUR, "files/contract.pdf")
    deleting = on_s3.connection.meta.client
    real, sent = deleting.delete_objects, []

    def counted(**kwargs):
        sent.append(len(kwargs["Delete"]["Objects"]))
        return real(**kwargs)

    monkeypatch.setattr(deleting, "delete_objects", counted)

    files.delete_hub_files(on_s3, HUB)

    assert sent == [files.S3_DELETE_BATCH, 1]
    assert files.S3_DELETE_BATCH == 1000
    assert set(objects(moto_s3, hub_files_bucket)) == {f"{hub_prefix(NEIGHBOUR)}/files/contract.pdf"}


def test_a_bucket_that_cannot_be_listed_is_a_failure_not_an_empty_prefix(on_s3, moto_s3, hub_files_bucket):
    keep(on_s3, HUB, "files/contract.pdf")
    on_s3.bucket_name = "erplora-test-no-such-bucket"

    with pytest.raises(files.HubFilesNotDeleted, match=hub_prefix(HUB)):
        files.delete_hub_files(on_s3, HUB)

    assert set(objects(moto_s3, hub_files_bucket)) == {f"{hub_prefix(HUB)}/files/contract.pdf"}


def test_keys_s3_refuses_inside_a_200_are_a_failure(on_s3, monkeypatch):
    # DeleteObjects answers 200 and lists what it did not delete: boto3 raises nothing.
    keep(on_s3, HUB, "files/contract.pdf", "files/secret-name.pdf")
    s3 = on_s3.connection.meta.client

    def refusing(**kwargs):
        return {"Errors": [{"Key": f"{hub_prefix(HUB)}/files/secret-name.pdf", "Code": "AccessDenied", "Message": "no"}]}

    monkeypatch.setattr(s3, "delete_objects", refusing)

    with pytest.raises(files.HubFilesNotDeleted) as refused:
        files.delete_hub_files(on_s3, HUB)

    assert "AccessDenied" in str(refused.value)
    assert hub_prefix(HUB) in str(refused.value)
    assert "secret-name" not in str(refused.value), "the row it ends on keeps no name of the business's files"


@pytest.mark.parametrize("step", ["listdir", "delete"])
def test_a_disk_that_fails_is_a_failure(on_disk, monkeypatch, step):
    keep(on_disk, HUB, "files/contract.pdf")

    def refusing(*args, **kwargs):
        raise PermissionError("no")

    monkeypatch.setattr(on_disk, step, refusing)

    with pytest.raises(files.HubFilesNotDeleted, match=hub_prefix(HUB)):
        files.delete_hub_files(on_disk, HUB)
