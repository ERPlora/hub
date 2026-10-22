"""Where the website keeps its images in the hub file store (``storages["hub_files"]``, ``base.storage``).

An image's key is ``hub-<hex>/website/img/<first 16 hex of its sha256>.<ext>``: under its hub's prefix, named by its
content, so the same file uploaded twice is one object and its URL can be cached for a year (``base.media``). Key
builders only; ``services.upload_image`` writes the bytes.
"""

import uuid

from base.storage import hub_prefix, media_url

#: The file extension of each image type the website takes.
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
#: How many hex characters of the sha256 name the file (64 bits: no collision in one hub's images).
HASH_CHARS = 16


def image_key(hub_id: uuid.UUID, sha256: str, content_type: str) -> str:
    """The key of an image of ``hub_id`` whose content hashes to ``sha256``; ``KeyError`` for another type."""
    return f"{hub_prefix(hub_id)}/website/img/{sha256[:HASH_CHARS]}.{EXTENSIONS[content_type]}"


def image_url(hub_id: uuid.UUID, key: str) -> str:
    """Where the Hub serves ``key`` on ``hub_id``'s host; ``ValueError`` for a key outside that hub's prefix."""
    prefix = f"{hub_prefix(hub_id)}/"
    if not key.startswith(prefix):
        raise ValueError(f"{key!r} is not a file of hub {hub_id}.")
    return media_url(hub_id, key.removeprefix(prefix))
