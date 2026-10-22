"""``hub_files``: the hub's file store (PLAN-HUB block 7), S3 in AWS and the disk locally.

Terraform hands the Hub's task ``AWS_STORAGE_BUCKET_NAME`` (``erplora-prod-hubs``, ``erplora-pre-hubs``) and
``AWS_REGION`` (``aws/stacks/prod/apps.tf``), and the task role holds Get/Put/Delete on that bucket: no keys. The
bucket stays private (no ACL per object) and the Hub serves what it keeps; keys are content hashes, so a URL never
needs signing and the same key always holds the same bytes.
"""

import io
import uuid
from pathlib import Path

from django.core.files.storage import FileSystemStorage
from storages.backends.s3 import S3Storage

from base.storage import hub_files_storage, hub_prefix, media_url

MEDIA_ROOT = Path("/srv/hub/media")


def test_with_a_bucket_the_hub_files_go_to_s3_with_the_task_role():
    env = {"AWS_STORAGE_BUCKET_NAME": "erplora-prod-hubs", "AWS_REGION": "eu-central-1"}
    assert hub_files_storage(env, MEDIA_ROOT) == {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": "erplora-prod-hubs",
            "default_acl": None,
            "file_overwrite": True,
            "querystring_auth": False,
            "region_name": "eu-central-1",
        },
    }


def test_the_region_is_ireland_unless_the_environment_says_otherwise():
    storage = hub_files_storage({"AWS_STORAGE_BUCKET_NAME": "erplora-pre-hubs"}, MEDIA_ROOT)
    assert storage["OPTIONS"]["region_name"] == "eu-west-1"


def test_the_s3_options_are_ones_django_storages_knows():
    # S3Storage refuses an option it does not know (ImproperlyConfigured); building it touches no network.
    options = hub_files_storage({"AWS_STORAGE_BUCKET_NAME": "erplora-prod-hubs"}, MEDIA_ROOT)["OPTIONS"]
    storage = S3Storage(**options)
    assert (storage.bucket_name, storage.default_acl, storage.file_overwrite, storage.querystring_auth) == (
        "erplora-prod-hubs",
        None,
        True,
        False,
    )
    # No keys of its own: boto3 takes the task role's credentials.
    assert (storage.access_key, storage.secret_key) == (None, None)


def test_without_a_bucket_the_hub_files_stay_on_disk_under_media_root():
    expected = {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": MEDIA_ROOT}}
    assert hub_files_storage({}, MEDIA_ROOT) == expected
    # An empty variable is no bucket (an .env line left blank).
    assert hub_files_storage({"AWS_STORAGE_BUCKET_NAME": ""}, MEDIA_ROOT) == expected


def test_the_disk_store_writes_under_media_root(tmp_path):
    options = hub_files_storage({}, tmp_path)["OPTIONS"]
    storage = FileSystemStorage(**options)
    name = storage.save("hub-0000/website/img/abc.png", io.BytesIO(b"png"))
    assert (tmp_path / name).read_bytes() == b"png"


HUB_ID = uuid.UUID("0199c4b0-0000-7000-8000-00000000abcd")


def test_a_hub_s_files_live_under_its_own_prefix():
    # The id's hex, as the hub databases are named (``hub_<hex>``, PLAN-DB): one prefix per hub, never shared.
    assert hub_prefix(HUB_ID) == "hub-0199c4b000007000800000000000abcd"


def test_a_file_is_served_by_the_hub_at_p_media():
    url = media_url(HUB_ID, "website/img/3f2a9c.png")
    assert url == "/p/media/0199c4b000007000800000000000abcd/website/img/3f2a9c.png"


def test_the_url_of_a_name_with_odd_characters_is_quoted():
    assert media_url(HUB_ID, "docs/a b#1.pdf").endswith("/docs/a%20b%231.pdf")
