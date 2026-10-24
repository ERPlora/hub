"""The hub's file store, ``STORAGES["hub_files"]`` (PLAN-HUB block 7): what the modules keep as files.

In AWS it is the Hub's S3 bucket, the one Terraform names in ``AWS_STORAGE_BUCKET_NAME`` (``erplora-prod-hubs``,
``erplora-pre-hubs``; ``aws/stacks/prod/apps.tf``) in ``AWS_REGION``, with the task role's credentials (no keys).
The bucket stays private: no ACL per object, no signed URLs (the Hub serves what it keeps), and a key that already
exists is written over, because the modules name their files by a hash of their content (Files' uploads, named by the
person, are written only where nobody has written: ``base.files``). Without a bucket (local
development, the tests) the files go to ``MEDIA_ROOT`` on disk. Every access goes through
``django.core.files.storage.storages["hub_files"]``; every key starts with its hub's :func:`hub_prefix`, and the Hub
serves a file at :func:`media_url` (``base.media``).
"""

import uuid
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import quote

#: The region of the bucket when the environment names none: ERPlora runs in Ireland.
DEFAULT_REGION = "eu-west-1"


def hub_files_storage(env: Mapping[str, str], media_root: Path) -> dict:
    """The ``STORAGES`` entry of ``hub_files``: S3 when ``env`` names a bucket, else the disk under ``media_root``."""
    bucket = env.get("AWS_STORAGE_BUCKET_NAME", "")
    if not bucket:
        return {"BACKEND": "django.core.files.storage.FileSystemStorage", "OPTIONS": {"location": media_root}}
    return {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "bucket_name": bucket,
            "default_acl": None,
            "file_overwrite": True,
            "querystring_auth": False,
            "region_name": env.get("AWS_REGION") or DEFAULT_REGION,
        },
    }


def hub_prefix(hub_id: uuid.UUID) -> str:
    """Where ``hub_id``'s files live in the store: ``hub-<hex>``, the id's hex as in its database's name."""
    return f"hub-{hub_id.hex}"


def media_url(hub_id: uuid.UUID, name: str) -> str:
    """The URL the Hub serves ``hub_id``'s file ``name`` at (relative to :func:`hub_prefix`), on that hub's host.

    A plain path, not ``reverse``: the script prefix comes from the client's own header behind Daphne, and these
    URLs end up in pages that are cached and shared."""
    return f"/p/media/{hub_id.hex}/{quote(name)}"
