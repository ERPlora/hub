"""Where the website keeps its images in the hub file store (``storages["hub_files"]``, ``base.storage``).

An image's key is ``hub-<hex>/website/img/<first 16 hex of its sha256>.<ext>`` (``base.public_images`` keeps it):
under its hub's prefix, named by its content, so the same file uploaded twice is one object and its URL can be cached
for a year (``base.media``).
"""

import uuid

from base.storage import hub_prefix, media_url

#: The website's folder under its hub's prefix, the one it serves to anyone (``public_media``).
FOLDER = "website/img/"


def image_url(hub_id: uuid.UUID, key: str) -> str:
    """Where the Hub serves ``key`` on ``hub_id``'s host; ``ValueError`` for a key outside that hub's prefix."""
    prefix = f"{hub_prefix(hub_id)}/"
    if not key.startswith(prefix):
        raise ValueError(f"{key!r} is not a file of hub {hub_id}.")
    return media_url(hub_id, key.removeprefix(prefix))
