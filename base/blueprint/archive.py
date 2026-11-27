"""The ``.blueprint.zip``: its manifest, a file per dataset and the rows' own photos, read with limits and
refused with a reason the person can read.
"""

import base64
import binascii
import io
import json
import re
import zipfile
import zlib
from dataclasses import dataclass, field
from typing import Any

from django.utils.text import slugify
from django.utils.translation import gettext_lazy as _

from base import images
from base.blueprint.datasets import _datasets_by_key, every_dataset

FORMAT = "erplora.blueprint"
FORMAT_VERSION = 1
MANIFEST = "manifest.json"
PURPOSE_BACKUP = "backup"
PURPOSE_TEMPLATE = "template"
PURPOSES = (PURPOSE_BACKUP, PURPOSE_TEMPLATE)
#: The largest file read (what the person uploads), before anything is inflated. A photo travels as the 512 × 512 WebP
#: it was kept as (``base.images``), 20–60 KB and already compressed, so the zip weighs what its photos weigh: 300
#: photos of 60 KB are 18 MB, and the rows' JSON a few hundred KB more.
MAX_FILE_BYTES = 20 * 1024 * 1024
#: The most its members may weigh once inflated: a zip bomb stops here, never in memory. The photos inflate to what
#: they weigh (≤ 20 MB) and the rows' JSON about ten to one: 100 MB holds both with room.
MAX_INFLATED_BYTES = 100 * 1024 * 1024
#: The manifest, a file per dataset and the photos: a thousand photos of 20 KB still fit in :data:`MAX_FILE_BYTES`.
MAX_ENTRIES = 1000
#: The heaviest photo one ``media/`` entry may be: what an upload takes (``base.images``).
MAX_PHOTO_BYTES = images.MAX_UPLOAD_BYTES
MAX_ROWS = 10_000
LABEL_RE = re.compile(r"^[a-z][a-z0-9_]*$")
DATA_FILE_RE = re.compile(r"^data/([a-z][a-z0-9_]*\.[a-z][a-z0-9_]*)\.json$")
#: A photo of a row's own: ``media/`` and its name under the hub's prefix (``inventory/products/<uuid7 hex>.webp``).
MEDIA_FILE_RE = re.compile(r"^media/((?:[a-z][a-z0-9_]*/){2}[0-9a-f]{32}\.webp)$")

REASONS = {
    "too_big": _("The file is larger than 20 MB, or holds more than a blueprint can."),
    "bad_photo": _("The file holds a photo that is not a WebP image of up to 2 MB, so it cannot be read."),
    "not_a_blueprint": _("This is not a .blueprint.zip file."),
    "no_manifest": _("The file has no manifest: it was not made by ERPlora."),
    "unreadable": _("The file is damaged or was changed by hand, so it cannot be read."),
    "too_new": _("The file was made by a newer version of ERPlora. Update this one to load it."),
}


class BlueprintInvalid(Exception):
    """A file that is no blueprint this hub can read: ``reason`` is its code, ``str()`` the sentence for the person."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def __str__(self) -> str:
        return str(REASONS[self.reason])


@dataclass
class Bundle:
    """A blueprint read into memory: its manifest, the rows of each dataset it brings, and what was dropped."""

    manifest: dict
    data: dict[str, list[dict]]
    dropped: list[str] = field(default_factory=list)
    #: The rows' own photos it carries, by their name under the hub's prefix (``media/<name>`` in the zip).
    media: dict[str, bytes] = field(default_factory=dict)


def read_base64(text: str) -> Bundle:
    """A blueprint uploaded in base64 (the upload's JSON body)."""
    if len(text) > (MAX_FILE_BYTES // 3 + 1) * 4:
        raise BlueprintInvalid("too_big")
    try:
        content = base64.b64decode(text, validate=True)
    except (binascii.Error, ValueError):
        raise BlueprintInvalid("not_a_blueprint") from None
    return read_zip(content)


def read_zip(content: bytes) -> Bundle:  # noqa: C901
    """The blueprint in ``content``, or :class:`BlueprintInvalid` with the reason it cannot be read."""
    if len(content) > MAX_FILE_BYTES:
        raise BlueprintInvalid("too_big")
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except (zipfile.BadZipFile, zipfile.LargeZipFile, ValueError, OSError):
        raise BlueprintInvalid("not_a_blueprint") from None
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_ENTRIES:
            raise BlueprintInvalid("unreadable")
        if sum(info.file_size for info in members) > MAX_INFLATED_BYTES:
            raise BlueprintInvalid("too_big")
        names = [info.filename for info in members]
        if any(name != MANIFEST and not DATA_FILE_RE.match(name) and not MEDIA_FILE_RE.match(name) for name in names):
            raise BlueprintInvalid("unreadable")
        if MANIFEST not in names:
            raise BlueprintInvalid("no_manifest")
        if any(MEDIA_FILE_RE.match(info.filename) and info.file_size > MAX_PHOTO_BYTES for info in members):
            raise BlueprintInvalid("bad_photo")
        budget = [MAX_INFLATED_BYTES]
        manifest = _manifest(_member_json(archive, MANIFEST, budget))
        media = {
            match.group(1): _member_photo(archive, name, budget)
            for name in names
            if (match := MEDIA_FILE_RE.match(name)) is not None
        }
        data: dict[str, list[dict]] = {}
        dropped = []
        for name in names:
            match = DATA_FILE_RE.match(name)
            if match is None:
                continue
            key = match.group(1)
            rows = _rows(_member_json(archive, name, budget))
            if key in _datasets_by_key():
                data[key] = rows
            else:
                dropped.append(key)
    return Bundle(manifest=manifest, data=_in_order(data), dropped=sorted(dropped), media=media)


def write_zip(bundle: Bundle) -> bytes:
    """The ``.blueprint.zip`` of ``bundle``: its manifest, a file per dataset and its photos, stored as they are (a
    WebP is already compressed)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps(bundle.manifest, ensure_ascii=False, indent=2))
        for key, rows in _in_order(bundle.data).items():
            archive.writestr(f"data/{key}.json", json.dumps(rows, ensure_ascii=False, indent=1))
        for name, content in sorted(bundle.media.items()):
            archive.writestr(f"media/{name}", content, compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def file_name(name: str, language: str) -> str:
    """``{name}_{language}.blueprint.zip``, the name made safe for any disk (the old hub's)."""
    return f"{slugify(name) or 'blueprint'}_{slugify(language) or 'xx'}.blueprint.zip"


def manifest(*, name: str, language: str, country: str, purpose: str, created_at: str, vertical: str, apps: list[str],  # noqa: PLR0913
             version: str = "") -> dict:
    """A manifest of this format."""
    return {
        "format": FORMAT,
        "format_version": FORMAT_VERSION,
        "name": name,
        "language": language,
        "country": country,
        "purpose": purpose,
        "created_at": created_at,
        "vertical": vertical,
        "version": version,
        "apps": list(apps),
    }


def _member_bytes(archive: zipfile.ZipFile, name: str, budget: list[int]) -> bytes:
    """A member's bytes, read in chunks against what is left of the inflated budget; one damaged after it was written
    (a CRC that does not match, a broken or short deflate stream, encrypted, compressed in a way zip readers do not
    know) makes the file unreadable."""
    chunks = []
    try:
        with archive.open(name) as member:
            while chunk := member.read(65536):
                budget[0] -= len(chunk)
                if budget[0] < 0:
                    raise BlueprintInvalid("too_big")
                chunks.append(chunk)
    except (zipfile.BadZipFile, zlib.error, RuntimeError, NotImplementedError):
        raise BlueprintInvalid("unreadable") from None
    return b"".join(chunks)


def _member_json(archive: zipfile.ZipFile, name: str, budget: list[int]) -> Any:
    """A member parsed as JSON, read against what is left of the inflated budget."""
    try:
        return json.loads(_member_bytes(archive, name, budget).decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise BlueprintInvalid("unreadable") from None


def _member_photo(archive: zipfile.ZipFile, name: str, budget: list[int]) -> bytes:
    """A ``media/`` member: a WebP (a RIFF container of the WEBP kind) of :data:`MAX_PHOTO_BYTES` at most; the app's
    upload reads it whole when the row loads (``base.images.to_webp``)."""
    content = _member_bytes(archive, name, budget)
    if len(content) > MAX_PHOTO_BYTES or content[:4] != b"RIFF" or content[8:12] != b"WEBP":
        raise BlueprintInvalid("bad_photo")
    return content


def _manifest(raw: Any) -> dict:
    if not isinstance(raw, dict):
        raise BlueprintInvalid("unreadable")
    if raw.get("format") != FORMAT:
        raise BlueprintInvalid("not_a_blueprint")
    version = raw.get("format_version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise BlueprintInvalid("unreadable")
    if version > FORMAT_VERSION:
        raise BlueprintInvalid("too_new")
    texts = {"name": 120, "language": 8, "country": 2, "created_at": 40, "vertical": 63, "version": 32}
    values = {key: raw.get(key, "") for key in texts}
    if any(not isinstance(value, str) or len(value) > texts[key] for key, value in values.items()):
        raise BlueprintInvalid("unreadable")
    if not values["name"].strip() or raw.get("purpose") not in PURPOSES:
        raise BlueprintInvalid("unreadable")
    apps = raw.get("apps", [])
    if not isinstance(apps, list) or len(apps) > 200 or any(not isinstance(app, str) or not LABEL_RE.match(app) for app in apps):
        raise BlueprintInvalid("unreadable")
    return manifest(purpose=raw["purpose"], apps=list(dict.fromkeys(apps)), **values)


def _rows(raw: Any) -> list[dict]:
    """A dataset's rows: a list of objects, at most ``MAX_ROWS``."""
    if not isinstance(raw, list) or len(raw) > MAX_ROWS or any(not isinstance(row, dict) for row in raw):
        raise BlueprintInvalid("unreadable")
    return raw


def _in_order(data: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """The datasets in their load order (a category before the products that name it)."""
    return {dataset.key: data[dataset.key] for dataset in every_dataset() if dataset.key in data}
