"""The image of a row an app sells (round 2026-10-30, «blueprints con imágenes»): what Inventory, Services and Combos
share to show a product, a service or a set menu on the till, in its form and in its list.

A row keeps one reference, never a URL (a ``.blueprint.zip`` never changes; a URL baked into it rots):

- ``catalog:<folder>/<name>``: an image of the shared library (``base.image_catalog``), one copy for every hub;
- ``file:<app>/<folder>/<uuid7 hex>.webp``: a photo of its own, under its hub's prefix of the hub file store
  (``hub-<hex>/``, ``base.storage``), in the folder its app declares in ``members_media`` (``base.media`` serves it to
  the hub's sessions only);
- empty: no image (the till shows its initials).

A photo comes in as a JPG, PNG or WebP of :data:`MAX_UPLOAD_BYTES` at most, in base64 (:func:`decode`), of
:data:`MAX_PIXELS` at most (checked before its pixels are decoded), and is kept as a WebP of :data:`SIDE` ×
:data:`SIDE`, the middle of it cropped to a square (cover), turned upright as the phone took it, quality :data:`QUALITY`
and without what the camera wrote in it (:func:`to_webp`); a WebP that already is one, with nothing written in it, whose
pixels decode and with nothing after its end, is kept as it came (an exported blueprint's photo loses nothing when it is
loaded again). Each upload is a file of its own, named by a new UUIDv7 (:func:`keep_photo`), counted against the plan's
space as Files counts its own (``base.queries.refuse_past_the_plans_space``). The photo a row lets go is deleted once
its change is saved (:func:`let_go`): only its upload writes a ``file:`` reference (:func:`check` refuses one set by
hand), so no two rows share a photo. No ORM here: the apps' ``services.py`` and ``queries.py`` call these.
"""

import base64
import binascii
import io
import logging
import re
import uuid
from collections.abc import Callable

from botocore.exceptions import BotoCoreError, ClientError
from django.core.files.base import ContentFile
from django.core.files.storage import storages
from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext, Scope
from live.errors import InvalidPayload, OperationError
from live.operations import on_commit
from PIL import Image as PILImage
from PIL import ImageOps, UnidentifiedImageError

from base import image_catalog
from base.operations import hub_id
from base.storage import hub_prefix, media_url

logger = logging.getLogger(__name__)

#: The heaviest photo taken, before it is converted (what the person picks).
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
#: The longest base64 an upload's input takes: 2 MB of photo is 2 796 204 characters, and somewhat more still reaches
#: :func:`decode`, so the person reads that the photo weighs too much, not a length of text; past it, the route's body
#: ceiling (2 900 000) answers first.
MAX_UPLOAD_BASE64 = 2_890_000
#: The side of every photo kept: the till's tile, the form and the list show it at most this big.
SIDE = 512
QUALITY = 85
#: The longest side a photo may have, checked before its pixels are decoded (a small file can unfold into a huge
#: picture): a phone's camera takes up to 8064 × 6048.
MAX_SIDE = 10_000
#: The most pixels a photo may have, checked before they are decoded too: a flat 10 000 × 10 000 PNG weighs some 300 KB
#: and unfolds into 400 MB, and Pillow's own guard lets it through (it warns past 89 MP, refuses past 179 MP).
#: 40 MP × 4 bytes a pixel (Pillow keeps RGB in 4) ≈ 160 MB at worst for one decode. A 12 MP phone photo (4000 × 3000)
#: fits; a full 48 MP one (8064 × 6048) weighs far more than :data:`MAX_UPLOAD_BYTES` and is refused before.
MAX_PIXELS = 40_000_000
#: The formats taken, as Pillow names them.
FORMATS = ("JPEG", "PNG", "WEBP")

NONE, CATALOG, FILE = "", "catalog", "file"
#: A photo of its own: the folder of its app, then its name.
FILE_RE = re.compile(r"^file:((?:[a-z][a-z0-9_]*/){2})([0-9a-f]{32})\.webp$")

IMAGE_UNKNOWN = _("That image is no longer in the library. Choose another one.")
NOT_AN_IMAGE_REFERENCE = _("Choose an image of the library or upload a photo.")
PHOTO_INVALID = _("That file is not a photo. Upload a JPG, PNG or WebP image.")
PHOTO_TOO_BIG = _("The photo weighs more than 2 MB. Choose a lighter one.")
PHOTO_NOT_SAVED = _("The photo could not be saved. Try again.")


def kind_of(reference: str) -> str | None:
    """:data:`CATALOG`, :data:`FILE` or :data:`NONE` (no image) for what ``reference`` is, ``None`` for anything else."""
    if not reference:
        return NONE
    if image_catalog.parse_reference(reference) is not None:
        return CATALOG
    return FILE if FILE_RE.match(reference) else None


def own_name(reference: str) -> str | None:
    """The name under the hub's prefix of the photo ``reference`` names (``inventory/products/<hex>.webp``), or
    ``None`` when it names none."""
    return reference.removeprefix("file:") if FILE_RE.match(reference or "") else None


class Urls:
    """The URL of each image of one scope's rows: the hub's id read once, and only when a photo of its own needs it."""

    def __init__(self, scope: Scope) -> None:
        self.scope = scope
        self._hub: uuid.UUID | None = None

    def __call__(self, reference: str) -> str:
        parsed = image_catalog.parse_reference(reference or "")
        if parsed is not None:
            return f"/p/catalog/{parsed[0]}/{parsed[1]}.{image_catalog.EXTENSION}"
        name = own_name(reference)
        if name is None:
            return ""
        if self._hub is None:
            self._hub = hub_id(self.scope)
        return media_url(self._hub, name)


def check(ctx: OperationContext, reference: str, *, field: str = "image") -> None:
    """What a person or the assistant may set by hand: an image the library has, or none (empty). Anything else is a
    422 ``base.image_unknown`` on ``field``: an image the library no longer has, and a photo of its own too, which
    only its upload writes (so no row ever points at another's file, nor at a file of another hub)."""
    kind = kind_of(reference)
    with translation.override(ctx.language):
        if kind == NONE:
            return
        if kind != CATALOG:
            raise _unknown(str(NOT_AN_IMAGE_REFERENCE), field)
        if not _in_library(ctx, reference):
            raise _unknown(str(IMAGE_UNKNOWN), field)


def _in_library(ctx: OperationContext, reference: str) -> bool:
    from base.queries import image_library

    return image_library(ctx).get(*image_catalog.parse_reference(reference)) is not None


def _unknown(message: str, field: str) -> InvalidPayload:
    return InvalidPayload(message, code="base.image_unknown", fields={field: message})


def _invalid(message: str, code: str = "base.photo_invalid") -> InvalidPayload:
    return InvalidPayload(message, code=code, fields={"data_base64": message})


def decode(data_base64: str, *, language: str | None = None) -> bytes:
    """The bytes of a photo sent in base64, of :data:`MAX_UPLOAD_BYTES` at most."""
    with translation.override(language or translation.get_language()):
        if len(data_base64) > MAX_UPLOAD_BASE64:
            raise _invalid(str(PHOTO_TOO_BIG), "base.photo_too_big")
        try:
            raw = base64.b64decode(data_base64, validate=True)
        except (binascii.Error, ValueError):
            raise _invalid(str(PHOTO_INVALID)) from None
        if not raw:
            raise _invalid(str(PHOTO_INVALID))
        if len(raw) > MAX_UPLOAD_BYTES:
            raise _invalid(str(PHOTO_TOO_BIG), "base.photo_too_big")
        return raw


def to_webp(raw: bytes, *, language: str | None = None) -> bytes:
    """``raw`` (a JPG, PNG or WebP) as the WebP kept: :data:`SIDE` × :data:`SIDE`, its middle, upright, no metadata."""
    with translation.override(language or translation.get_language()):
        try:
            with PILImage.open(io.BytesIO(raw)) as image:
                width, height = image.size
                if image.format not in FORMATS or max(width, height) > MAX_SIDE or width * height > MAX_PIXELS:
                    raise _invalid(str(PHOTO_INVALID))
                if image.format == "JPEG":
                    # Decoded at the smallest scale (1/2, 1/4, 1/8) still past twice the side kept: less memory.
                    image.draft("RGB", (SIDE * 2, SIDE * 2))
                # Decoded whole before anything is kept: a header that reads is no proof its pixels do.
                image.load()
                if _kept_as_it_came(image, raw):
                    return raw
                # Turned upright and into its mode without a copy of what was decoded (only a turn or a new mode
                # makes one): the decoded pixels stay the most memory a photo takes.
                ImageOps.exif_transpose(image, in_place=True)
                mode = "RGBA" if "A" in image.getbands() or "transparency" in image.info else "RGB"
                pixels = image if image.mode == mode else image.convert(mode)
                square = ImageOps.fit(pixels, (SIDE, SIDE), method=PILImage.Resampling.LANCZOS)
                buffer = io.BytesIO()
                square.save(buffer, "WEBP", quality=QUALITY)
                return buffer.getvalue()
        except (UnidentifiedImageError, OSError, SyntaxError, ValueError, PILImage.DecompressionBombError):
            raise _invalid(str(PHOTO_INVALID)) from None


def _kept_as_it_came(image: PILImage.Image, raw: bytes) -> bool:
    """A WebP already as it would be kept, that ends where its RIFF header says (nothing hidden after its end)."""
    return (
        image.format == "WEBP"
        and image.size == (SIDE, SIDE)
        and len(raw) == int.from_bytes(raw[4:8], "little") + 8
        and not getattr(image, "is_animated", False)
        and not image.info.get("exif")
        and not image.info.get("xmp")
    )


def keep_photo(ctx: OperationContext, folder: str, webp: bytes) -> str:
    """Keep ``webp`` (what :func:`to_webp` made) under ``ctx``'s hub's prefix in ``folder``, by a new UUIDv7, within the
    plan's space (409 ``base.file_no_space`` otherwise, nothing kept); its ``file:`` reference."""
    from base.queries import refuse_past_the_plans_space

    store = storages["hub_files"]
    refuse_past_the_plans_space(ctx, store, len(webp))
    name = f"{folder}{uuid.uuid7().hex}.webp"
    try:
        store.save(f"{hub_prefix(hub_id(ctx.scope))}/{name}", ContentFile(webp))
    except (OSError, BotoCoreError, ClientError):
        logger.exception("images: the photo %s could not be kept", name)
        with translation.override(ctx.language):
            raise OperationError(str(PHOTO_NOT_SAVED), code="base.photo_not_saved", status=503) from None
    return f"file:{name}"


def let_go(ctx: OperationContext, reference: str) -> None:
    """Delete the photo ``reference`` names from ``ctx``'s hub once the change that let it go is saved (rolled back:
    it stays); called by the running operation (``live.operations.on_commit``). An image of the library, or none,
    deletes nothing."""
    name = own_name(reference)
    if name is None:
        return
    key = f"{hub_prefix(hub_id(ctx.scope))}/{name}"
    # On the operation's own transaction (phase 2: the hub's database), never ``default``'s, where it would run at once.
    on_commit(_deleter(key))


def _deleter(key: str) -> Callable[[], None]:
    """Delete ``key`` once the change is saved; a store that fails then is logged and never undoes what was saved (the
    photo is left over in the store)."""

    def delete() -> None:
        try:
            storages["hub_files"].delete(key)
        except (OSError, BotoCoreError, ClientError):
            logger.exception("images: the photo %s could not be deleted", key)

    return delete


def read_photo(scope: Scope, reference: str) -> bytes | None:
    """The bytes of the photo ``reference`` names in ``scope``'s hub, or ``None`` when it is not there."""
    name = own_name(reference)
    if name is None:
        return None
    try:
        with storages["hub_files"].open(f"{hub_prefix(hub_id(scope))}/{name}", "rb") as file:
            return file.read()
    except (OSError, BotoCoreError, ClientError):
        return None
