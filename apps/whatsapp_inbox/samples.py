"""The file of a template's header with a photo, a video or a document (WHATSAPP_INBOX-F29): what Meta takes as its
sample and where the Hub keeps it in the hub file store (``storages["hub_files"]``, ``base.storage``).

Meta reviews such a template only with a sample of that file, which erplora.com uploads for it (door 8). The file is
told by its first bytes, never by its name or the type the browser declares (``sniff``): a JPEG or PNG photo and an
MP4 video up to Meta's limits (5 and 16 MB), and a PDF document up to the Hub's ceiling for a file it keeps
(``base.files.MAX_FILE_BYTES``, 25 MB; Meta takes up to 100 MB). Its key is
``hub-<hex>/whatsapp_inbox/samples/<first 16 hex of its sha256>.<ext>``: under its hub's prefix and named by its
content, as the website keeps its images, so the same file chosen twice is one object. Nothing here is public:
``/p/media/`` serves this folder only to a session of the hub (``members_media`` in ``apps.py``, ``base.media``), at
:func:`sample_url`, where the template's sheet shows it. Key builders and rules only; ``services.upload_sample`` writes
the bytes.
"""

import uuid

from base.files import MAX_FILE_BYTES
from base.storage import hub_prefix, media_url

MB = 1024 * 1024
#: The headers that carry a file.
FILE_HEADERS = ("IMAGE", "VIDEO", "DOCUMENT")
#: The heaviest file each takes.
MAX_BYTES = {"IMAGE": 5 * MB, "VIDEO": 16 * MB, "DOCUMENT": MAX_FILE_BYTES}
#: The folder of the samples under a hub's prefix, the one ``members_media`` declares.
FOLDER = "whatsapp_inbox/samples/"
#: The file extension of each type a sample is.
EXTENSIONS = {"image/jpeg": "jpg", "image/png": "png", "video/mp4": "mp4", "application/pdf": "pdf"}
#: How many hex characters of the sha256 name the file (64 bits: no collision in one hub's samples).
HASH_CHARS = 16
#: The MP4 brands of an ``ftyp`` box; a 3GPP file shares the box, but Meta's sample must be MP4.
MP4_BRANDS = (b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"mp41", b"mp42", b"avc1", b"dash", b"M4V ", b"MSNV")


def sniff(head: bytes) -> tuple[str, str] | None:
    """The header kind and the type of a file Meta takes as a sample that these first bytes start, or None."""
    if head.startswith(b"\xff\xd8\xff"):
        return "IMAGE", "image/jpeg"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "IMAGE", "image/png"
    if head.startswith(b"%PDF-"):
        return "DOCUMENT", "application/pdf"
    if head[4:8] == b"ftyp" and head[8:12] in MP4_BRANDS:
        return "VIDEO", "video/mp4"
    return None


def sample_key(hub_id: uuid.UUID, sha256: str, content_type: str) -> str:
    """The key of a sample of ``hub_id`` whose content hashes to ``sha256``; ``KeyError`` for another type."""
    return f"{hub_prefix(hub_id)}/{FOLDER}{sha256[:HASH_CHARS]}.{EXTENSIONS[content_type]}"


def sample_url(key: str) -> str:
    """Where ``/p/media/`` serves the sample kept at ``key`` to a session of its hub (the hub of its prefix, never
    another's: ``base.media`` answers it only on that hub's host); empty for a key that is no hub's sample."""
    prefix, _, name = key.partition("/")
    try:
        hub = uuid.UUID(prefix.removeprefix("hub-"))
    except ValueError:
        return ""
    if prefix != hub_prefix(hub) or not name.startswith(FOLDER):
        return ""
    return media_url(hub, name)
