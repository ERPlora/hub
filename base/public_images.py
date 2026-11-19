"""An image a business uploads for anyone to see on its own pages: the website's images, the booking page's logo.

It comes in base64 (``base.schemas.public_images.ImageUploadIn``) as a JPG, PNG or WebP of :data:`MAX_BYTES` and
:data:`MAX_SIDE` pixels a side at most, read whole by Pillow as the type it claims, and is kept as it came in the hub
file store (``base.storage``) under its hub's prefix, in its app's folder (one its app declares in ``public_media``,
which ``base.media`` serves to anyone from the hub's own host), named by the first :data:`HASH_CHARS` hex of its
sha256: the same file uploaded twice is one object, whose URL never changes. A new file must fit in the plan's space
as Files counts it (409 ``base.file_no_space``). No ORM here: the app keeps what it needs of the image.
"""

import base64
import binascii
import hashlib
import io
from dataclasses import dataclass

from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload
from PIL import Image as PILImage
from PIL import UnidentifiedImageError

from base.operations import hub_id
from base.queries.files import refuse_past_the_plans_space
from base.schemas.public_images import ImageUploadIn
from base.storage import hub_prefix, media_url

#: The heaviest image taken, in bytes (before base64).
MAX_BYTES = 5 * 1024 * 1024
#: The longest side of an image taken, in pixels.
MAX_SIDE = 8000
#: The body of an upload's route: 5 MB of image in base64 (6 990 508 characters) and its JSON around it.
MAX_UPLOAD_BODY = 7_100_000
#: The file extension of each type taken.
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
#: What Pillow calls each type taken.
PILLOW_FORMATS = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}
#: How many hex characters of the sha256 name the file (64 bits: no collision in one hub's images).
HASH_CHARS = 16

NOT_BASE64 = _("The file did not arrive whole: choose it again.")
EMPTY_FILE = _("The file is empty.")
TOO_HEAVY = _("The image may weigh 5 MB at most.")
NOT_THAT_TYPE = _("This file is not a %(type)s image.")
TOO_LARGE = _("The image may be %(side)s pixels a side at most.")


@dataclass(frozen=True)
class Kept:
    """An image kept: its key in the store, its own name in its folder, where the Hub serves it, and what it is."""

    key: str
    name: str
    url: str
    sha256: str
    width: int
    height: int
    size: int


def keep(ctx: OperationContext, folder: str, data: ImageUploadIn) -> Kept:
    """Keep the image ``data`` brings in ``folder`` (``<app>/<folder>/``) of ``ctx``'s hub; 422 on ``data_base64``
    for a file that is no such image, 409 ``base.file_no_space`` for a new one past the plan's space."""
    hub = hub_id(ctx.scope)
    raw = _decoded(data)
    width, height = _measured(raw, data.content_type)
    sha = hashlib.sha256(raw).hexdigest()
    name = f"{sha[:HASH_CHARS]}.{EXTENSIONS[data.content_type]}"
    key = f"{hub_prefix(hub)}/{folder}{name}"
    store = storages["hub_files"]
    if not store.exists(key):
        # Files' own check of the plan's space: the hub's prefix already counts its files and its apps' images.
        refuse_past_the_plans_space(ctx, store, len(raw))
        store.save(key, ContentFile(raw))
    return Kept(key, name, media_url(hub, f"{folder}{name}"), sha, width, height, len(raw))


def _refuse_file(message: str) -> InvalidPayload:
    return InvalidPayload(message, fields={"data_base64": message})


def _decoded(data: ImageUploadIn) -> bytes:
    try:
        raw = base64.b64decode(data.data_base64, validate=True)
    except (binascii.Error, ValueError):
        raise _refuse_file(str(NOT_BASE64)) from None
    if not raw:
        raise _refuse_file(str(EMPTY_FILE))
    if len(raw) > MAX_BYTES:
        raise _refuse_file(str(TOO_HEAVY))
    return raw


def _measured(raw: bytes, content_type: str) -> tuple[int, int]:
    """The image's width and height, once Pillow read it whole as the type it claims to be."""
    not_that_type = str(NOT_THAT_TYPE) % {"type": PILLOW_FORMATS[content_type]}
    try:
        with PILImage.open(io.BytesIO(raw)) as image:
            image_format, (width, height) = image.format, image.size
            if image_format != PILLOW_FORMATS[content_type]:
                raise _refuse_file(not_that_type)
            if max(width, height) > MAX_SIDE:
                raise _refuse_file(str(TOO_LARGE) % {"side": MAX_SIDE})
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, PILImage.DecompressionBombError):
        raise _refuse_file(not_that_type) from None
    return width, height
