"""The shared image library (round 2026-10-30, «blueprints con imágenes»): one copy of ERPlora/blueprints' ``img/`` for
every hub, which a product, a service or a set menu points at with ``catalog:<folder>/<name>``, never with a URL (a
``.blueprint.zip`` never changes, and a URL baked into it rots when a domain, a bucket or a CDN does).

Where it is: with a bucket, under :data:`PREFIX` of the hub file store (``storages["hub_files"]``, ``base.storage``),
which ERPlora/blueprints' ``publish.yml`` fills and no hub writes; without one (local development, the tests), the
folder ``settings.CATALOG_DIR``, by default the ERPlora/blueprints checkout beside this repo. ``CATALOG_DIR`` names the
folder whenever it is set, the bucket included.

``catalog.json`` (``{"version": 1, "images": [{"name", "folder", "title": {"en", "es"}, "tags": {"en", "es"}}]}``) names
each image in English and Spanish with its search words: the files are named in snake_case and in either language
(``cafe_con_leche``), and are never renamed (the seeds and the files exported point at them). An entry without a
folder and a name of the reference's shape, or without its English title, is left out (and logged); a manifest that
cannot be read makes the library unavailable (:class:`LibraryUnavailable`), never empty.

:func:`library` keeps what it read for :data:`TTL_SECONDS` and, on disk, reads it again as soon as the file changes (its
mtime: a stat per call); in the bucket only the time renews it (an ETag would cost a request per read).
:meth:`Library.search` finds an image by what a product is called: accents, case and plurals aside, in either
language whoever asks (a product is named in the business's language), the exact title first, then a title that holds
the words, then a search word, then most of the words. :func:`catalog_image` serves ``/p/catalog/<folder>/<name>.webp``
to anyone, cached for a year: the library is nobody's data, and only what its manifest names is served. No ORM here.
"""

import json
import logging
import re
import time
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO, Any

from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from django.core.files.storage import Storage, storages
from django.http import FileResponse, Http404, HttpRequest
from django.views.decorators.http import require_safe

from base.media import CACHE_CONTROL, FILE_CSP

logger = logging.getLogger(__name__)

#: Where the library lives in the hub file store: beside the hubs' ``hub-<hex>/``, read by every hub.
PREFIX = "shared/catalog/"
#: Its manifest, at the library's top.
MANIFEST = "catalog.json"
#: How long a manifest read is kept before it is read again.
TTL_SECONDS = 600
#: A folder and an image's name, as the library names its files (``hospitality``, ``cafe_con_leche``).
FOLDER_PATTERN = r"[a-z][a-z0-9_]*"
NAME_PATTERN = r"[a-z0-9][a-z0-9_]*"
FOLDER_RE = re.compile(rf"^{FOLDER_PATTERN}$")
NAME_RE = re.compile(rf"^{NAME_PATTERN}$")
#: What a row keeps to show an image of the library.
REFERENCE_RE = re.compile(rf"^catalog:({FOLDER_PATTERN})/({NAME_PATTERN})$")
#: The languages the manifest names each image in; a title is read in English when the reader's is another.
LANGUAGES = ("en", "es")
FALLBACK_LANGUAGE = "en"
EXTENSION = "webp"
CONTENT_TYPE = "image/webp"
#: Words that say nothing of what an image shows («café **con** leche», «glass **of** wine»).
STOPWORDS = frozenset(
    {"a", "al", "an", "and", "con", "de", "del", "el", "en", "la", "las", "los", "of", "the", "to", "with", "y"}
)
#: The tiers of a match, best first: the exact title, a title that holds the words as written, a title with every word,
#: a search word said exactly, the title and the search words between them with every word, most of the words.
EXACT, IN_TITLE, TITLE_WORDS, TAG, ALL_WORDS, MOST_WORDS = range(6)
#: The share of the words a «most of the words» match must have.
MOST = 0.5


class LibraryUnavailable(Exception):
    """The library's manifest cannot be read: missing, unreadable or not a manifest."""


@dataclass(frozen=True)
class _Words:
    """A title and its search words in one language, folded for matching (:func:`fold`)."""

    title: str
    title_tokens: frozenset[str]
    tags: tuple[str, ...]
    tag_tokens: frozenset[str]


@dataclass(frozen=True)
class CatalogImage:
    """An image of the library: where it is, and what it shows in each language of the manifest."""

    folder: str
    name: str
    titles: dict[str, str] = field(hash=False)
    words: dict[str, _Words] = field(hash=False, repr=False)

    @property
    def reference(self) -> str:
        return f"catalog:{self.folder}/{self.name}"

    @property
    def url(self) -> str:
        return f"/p/catalog/{self.folder}/{self.name}.{EXTENSION}"

    def title_in(self, language: str) -> str:
        """Its title in ``language`` (``es-ES`` reads ``es``), else in English."""
        return self.titles.get(_language(language)) or self.titles[FALLBACK_LANGUAGE]

    def row(self, language: str) -> dict:
        """What the operations answer of it, titled in ``language``."""
        return {
            "reference": self.reference,
            "folder": self.folder,
            "name": self.name,
            "title": self.title_in(language),
            "url": self.url,
        }


class Library:
    """The images of one read of the manifest."""

    def __init__(self, images: list[CatalogImage]) -> None:
        self._by_key: dict[tuple[str, str], CatalogImage] = {}
        for image in images:
            self._by_key.setdefault((image.folder, image.name), image)
        self.images: tuple[CatalogImage, ...] = tuple(self._by_key.values())

    def get(self, folder: str, name: str) -> CatalogImage | None:
        return self._by_key.get((folder, name))

    def search(self, query: str, language: str, *, folder: str | None = None) -> list[CatalogImage]:
        """The images that match ``query``, the best first (:data:`EXACT` … :data:`MOST_WORDS`), titled and tied in
        ``language``'s favour; no words: every image, by its title in ``language``."""
        language = _language(language)
        images = [image for image in self.images if folder is None or image.folder == folder]
        folded = fold(query)
        if not folded:
            return sorted(images, key=lambda image: (fold(image.title_in(language)), image.folder, image.name))
        tokens = _tokens(folded)
        ranked = []
        for image in images:
            ranks = [
                (*match, 0 if lang == language else 1)
                for lang, words in image.words.items()
                if (match := _match(folded, tokens, words)) is not None
            ]
            if ranks:
                ranked.append((min(ranks), fold(image.title_in(language)), image.folder, image.name, image))
        return [entry[-1] for entry in sorted(ranked, key=lambda entry: entry[:-1])]


def parse_reference(reference: str) -> tuple[str, str] | None:
    """The folder and the name a ``catalog:<folder>/<name>`` reference names, or ``None`` for anything else."""
    match = REFERENCE_RE.match(reference or "")
    return (match.group(1), match.group(2)) if match else None


def exists(reference: str) -> bool:
    """Whether ``reference`` names an image of the library (:class:`LibraryUnavailable` when it cannot be read)."""
    parsed = parse_reference(reference)
    return parsed is not None and library().get(*parsed) is not None


def fold(text: str) -> str:
    """``text`` as it is matched: no accents, no case, words split by anything that is no letter or digit."""
    decomposed = unicodedata.normalize("NFKD", text or "")
    plain = "".join(char for char in decomposed if not unicodedata.combining(char)).casefold()
    return " ".join(re.sub(r"[^0-9a-z]+", " ", plain).split())


def _tokens(folded: str) -> frozenset[str]:
    """The words of a folded text that say something, each without its plural «s» («patatas» is «patata»)."""
    return frozenset(
        word[:-1] if len(word) > 3 and word.endswith("s") else word
        for word in folded.split()
        if len(word) > 1 and word not in STOPWORDS
    )


def _match(folded: str, tokens: frozenset[str], words: _Words) -> tuple[int, float] | None:
    """How well ``words`` match the query (its tier and, among «most of the words», minus the share matched)."""
    if folded == words.title:
        return EXACT, 0.0
    if folded in words.title:
        return IN_TITLE, 0.0
    if tokens and tokens <= words.title_tokens:
        return TITLE_WORDS, 0.0
    if folded in words.tags:
        return TAG, 0.0
    every = words.title_tokens | words.tag_tokens
    if any(folded in tag for tag in words.tags) or (tokens and tokens <= every):
        return ALL_WORDS, 0.0
    share = len(tokens & every) / len(tokens) if tokens else 0.0
    return (MOST_WORDS, -share) if share >= MOST else None


def _language(language: str) -> str:
    return (language or FALLBACK_LANGUAGE).split("-")[0].lower()


# ── Where the library is, and the read kept ─────────────────────────────────────────────────────────────────────


class _Folder:
    """The library on disk (``CATALOG_DIR``)."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.key = ("folder", str(root))

    def stamp(self) -> Any:
        try:
            return (self.root / MANIFEST).stat().st_mtime_ns
        except OSError:
            return None

    def manifest(self) -> bytes:
        return (self.root / MANIFEST).read_bytes()

    def open(self, folder: str, name: str) -> IO[bytes]:
        return (self.root / folder / f"{name}.{EXTENSION}").open("rb")


class _Store:
    """The library in the hub file store, under :data:`PREFIX`."""

    def __init__(self, store: Storage) -> None:
        self.store = store
        self.key = ("store", id(store))

    def stamp(self) -> Any:
        return None

    def manifest(self) -> bytes:
        with self.store.open(f"{PREFIX}{MANIFEST}", "rb") as file:
            return file.read()

    def open(self, folder: str, name: str) -> IO[bytes]:
        key = f"{PREFIX}{folder}/{name}.{EXTENSION}"
        # S3 opens lazily and fails on the first read, in the middle of the answer: asked first, it is a 404.
        if not self.store.exists(key):
            raise FileNotFoundError(key)
        return self.store.open(key, "rb")


#: The last read of each place: (its stamp, when it was read, the library).
_kept: dict[tuple, tuple[Any, float, Library]] = {}


def _now() -> float:
    return time.monotonic()


def _source() -> _Folder | _Store:
    folder = getattr(settings, "CATALOG_DIR", "")
    return _Folder(Path(folder)) if folder else _Store(storages["hub_files"])


def library() -> Library:
    """The library as its manifest says it now, read again after :data:`TTL_SECONDS` or when its file changed."""
    source = _source()
    stamp, now = source.stamp(), _now()
    kept = _kept.get(source.key)
    if kept is not None and kept[0] == stamp and now - kept[1] < TTL_SECONDS:
        return kept[2]
    try:
        raw = source.manifest()
    except (OSError, BotoCoreError, ClientError) as exc:
        raise LibraryUnavailable(f"No manifest at {source.key}: {exc}") from None
    read = _parse(raw)
    _kept[source.key] = (stamp, now, read)
    return read


def open_image(image: CatalogImage) -> IO[bytes]:
    """The file of ``image`` (one of the library's), opened to read; ``FileNotFoundError`` when it is not there."""
    return _source().open(image.folder, image.name)


def _parse(raw: bytes) -> Library:
    try:
        manifest = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise LibraryUnavailable("The manifest is not JSON.") from None
    entries = manifest.get("images") if isinstance(manifest, dict) else None
    if not isinstance(entries, list):
        raise LibraryUnavailable("The manifest has no list of images.")
    images = []
    for entry in entries:
        image = _image(entry)
        if image is None:
            logger.warning("image library: an entry of the manifest is left out: %r", entry)
            continue
        images.append(image)
    return Library(images)


def _image(entry: Any) -> CatalogImage | None:
    """The image an entry of the manifest names, or ``None`` when it names none."""
    if not isinstance(entry, dict):
        return None
    folder, name, titles, tags = entry.get("folder"), entry.get("name"), entry.get("title"), entry.get("tags")
    if not (isinstance(folder, str) and FOLDER_RE.match(folder) and isinstance(name, str) and NAME_RE.match(name)):
        return None
    titles = {lang: text.strip() for lang, text in (titles or {}).items() if lang in LANGUAGES and isinstance(text, str)} \
        if isinstance(titles, dict) else {}
    if not titles.get(FALLBACK_LANGUAGE):
        return None
    tags = tags if isinstance(tags, dict) else {}
    words = {}
    for lang, title in titles.items():
        said = [fold(tag) for tag in tags.get(lang, []) if isinstance(tag, str)] if isinstance(tags.get(lang), list) else []
        said = tuple(tag for tag in said if tag)
        words[lang] = _Words(
            title=fold(title),
            title_tokens=_tokens(fold(title)),
            tags=said,
            tag_tokens=frozenset().union(*(_tokens(tag) for tag in said)),
        )
    return CatalogImage(folder=folder, name=name, titles={lang: text for lang, text in titles.items() if text}, words=words)


# ── /p/catalog/<folder>/<name>.webp ─────────────────────────────────────────────────────────────────────────────


@require_safe
def catalog_image(request: HttpRequest, folder: str, name: str) -> FileResponse:
    """An image of the library, to anyone, cached for a year; what its manifest does not name is not found."""
    stem, dot, extension = name.rpartition(".")
    if not dot or extension != EXTENSION:
        raise Http404("No such image.")
    try:
        image = library().get(folder, stem)
    except LibraryUnavailable:
        raise Http404("No such image.") from None
    if image is None:
        raise Http404("No such image.")
    try:
        file = open_image(image)
    except (OSError, BotoCoreError, ClientError):
        raise Http404("No such image.") from None
    response = FileResponse(file, content_type=CONTENT_TYPE)
    response["Cache-Control"] = CACHE_CONTROL
    response._csp_config = FILE_CSP
    return response
