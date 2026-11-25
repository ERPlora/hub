"""What a name and a path of the business's files may be, and the type a file is served with by its name."""

import unicodedata
import uuid
from typing import Literal

from django.utils.translation import gettext
from live.errors import InvalidPayload

from base.storage import hub_prefix

#: The folder under a hub's prefix that the Files screen shows: its root.
ROOT = "files"
#: What keeps an empty folder in an object store; never listed, never a name.
MARKER = ".keep"
#: The longest name, in UTF-8 bytes (a file name on disk).
MAX_NAME_BYTES = 255
#: The longest path under the root, in UTF-8 bytes: with ``hub-<hex>/files/`` (43), an S3 key's 1024 at most.
MAX_PATH_BYTES = 980
#: Programs a file manager does not keep: they run on whoever opens them (the extensions Gmail blocks).
BLOCKED_EXTENSIONS = frozenset(
    {
        "ade", "adp", "apk", "appx", "appxbundle", "bat", "cab", "chm", "cmd", "com", "cpl", "diagcab",
        "diagcfg", "diagpack", "dll", "dmg", "ex_", "exe", "hta", "img", "ins", "iso", "isp", "jar", "jnlp",
        "js", "jse", "lib", "lnk", "mde", "msc", "msi", "msix", "msixbundle", "msp", "mst", "nsh", "pif",
        "ps1", "scr", "sct", "shb", "sys", "vb", "vbe", "vbs", "vhd", "vxd", "wsc", "wsf", "wsh", "xll",
    }
)  # fmt: skip

Preview = Literal["image", "pdf", "text", "table", "json", "audio", "video", ""]
#: The type a file is served with and how the screen shows it, by extension. Our own table, not ``mimetypes``: the
#: slim image of production has no ``/etc/mime.types``. Markup and scripts are served as their source, as plain text
#: (a browser never runs them); an SVG may carry script and is never shown; what is not here is bytes.
SERVED: dict[str, tuple[str, Preview]] = {
    **{ext: (f"image/{kind}", "image") for ext, kind in (
        ("jpg", "jpeg"), ("jpeg", "jpeg"), ("png", "png"), ("gif", "gif"), ("webp", "webp"), ("bmp", "bmp"),
        ("avif", "avif"),
    )},
    "pdf": ("application/pdf", "pdf"),
    **{ext: ("text/plain", "text") for ext in (
        "txt", "log", "md", "markdown", "ini", "conf", "cfg", "yaml", "yml", "xml", "html", "htm", "xhtml", "css",
        "js", "mjs", "ts", "py", "sql", "sh",
    )},
    **{ext: ("text/plain", "table") for ext in ("csv", "tsv")},
    "json": ("text/plain", "json"),
    **{ext: (kind, "audio") for ext, kind in (
        ("mp3", "audio/mpeg"), ("wav", "audio/wav"), ("ogg", "audio/ogg"), ("oga", "audio/ogg"), ("m4a", "audio/mp4"),
        ("aac", "audio/aac"),
    )},
    **{ext: (kind, "video") for ext, kind in (
        ("mp4", "video/mp4"), ("m4v", "video/mp4"), ("webm", "video/webm"), ("ogv", "video/ogg"),
        ("mov", "video/quicktime"),
    )},
    **{ext: (kind, "") for ext, kind in (
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("xlsm", "application/vnd.ms-excel.sheet.macroEnabled.12"),
        ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("doc", "application/msword"), ("xls", "application/vnd.ms-excel"), ("ppt", "application/vnd.ms-powerpoint"),
        ("odt", "application/vnd.oasis.opendocument.text"), ("ods", "application/vnd.oasis.opendocument.spreadsheet"),
        ("odp", "application/vnd.oasis.opendocument.presentation"), ("rtf", "application/rtf"),
        ("zip", "application/zip"), ("heic", "image/heic"),
    )},
}  # fmt: skip
BYTES = "application/octet-stream"


def clean_name(name: str, *, max_chars: int | None = None) -> str:
    """``name`` trimmed and in one Unicode form (NFC), or 422 ``base.file_invalid_name``."""
    clean = unicodedata.normalize("NFC", (name or "").strip())
    if not _is_name(clean) or (max_chars is not None and len(clean) > max_chars):
        message = gettext("That name is not valid. Use a name without slashes or lone dots.")
        raise InvalidPayload(message, code="base.file_invalid_name", fields={"name": message})
    return clean


def clean_path(path: str) -> str:
    """``path`` (``""`` = the root) in NFC, or 422 ``base.file_invalid_path`` if it could leave the files."""
    clean = unicodedata.normalize("NFC", path or "")
    if clean and (len(clean.encode()) > MAX_PATH_BYTES or not all(_is_name(part) for part in clean.split("/"))):
        raise InvalidPayload(gettext("That file or folder is not in this business's files."), code="base.file_invalid_path")
    return clean


def _is_name(name: str) -> bool:
    return (
        bool(name)
        and name not in (".", "..")
        and name.casefold() != MARKER
        and "/" not in name
        and "\\" not in name
        and not any(unicodedata.category(char) == "Cc" for char in name)
        and len(name.encode()) <= MAX_NAME_BYTES
    )


def served(name: str) -> tuple[str, Preview]:
    """The type ``name`` is served with and how the screen shows it (``""``: it does not, it is downloaded)."""
    return SERVED.get(_extension(name), (BYTES, ""))


def _extension(name: str) -> str:
    stem, dot, extension = name.rpartition(".")
    return extension.lower() if dot and stem else ""


def _join(folder: str, name: str) -> str:
    joined = f"{folder}/{name}" if folder else name
    if len(joined.encode()) > MAX_PATH_BYTES:
        message = gettext("That name is too long for this folder.")
        raise InvalidPayload(message, code="base.file_invalid_name", fields={"name": message})
    return joined


def _base(hub: uuid.UUID) -> str:
    return f"{hub_prefix(hub)}/{ROOT}"


def _key(hub: uuid.UUID, path: str) -> str:
    return f"{_base(hub)}/{path}" if path else _base(hub)


def _refuse_program(name: str) -> None:
    extension = _extension(name)
    if extension in BLOCKED_EXTENSIONS:
        message = gettext("Programs (.%(extension)s) can't be kept in Files: they could harm whoever opens them.") % {
            "extension": extension
        }
        raise InvalidPayload(message, code="base.file_type_refused", fields={"name": message})
