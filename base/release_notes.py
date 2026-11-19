"""The release notes this image ships: what changed for the businesses, written for them, one file per change.

Each note is a TOML file in ``release-notes/`` named ``<YYYY-MM-DD>-<name>.toml``: the day the change reached the
businesses and a name in lowercase words joined by hyphens. It says its kind and its title and text in every language
of the deployment::

    kind = "new"  # new, improved or fixed

    [en]
    title = "Allergens on every product"
    body = "In Products you can mark which allergens each product contains."

    [es]
    title = "Alérgenos en cada producto"
    body = "En Productos puedes marcar qué alérgenos lleva cada producto."

The notes travel inside the image, so the ones a hub reads are always those of the version it runs.
"""

import datetime as dt
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from django.conf import settings

DIRECTORY = Path(__file__).resolve().parent / "release-notes"
KINDS = ("new", "improved", "fixed")
#: A title is read at a glance and a text in a breath: a note is not an article.
TITLE_LENGTH = 80
BODY_LENGTH = 400

_NAME = re.compile(r"(?P<day>\d{4}-\d{2}-\d{2})-[a-z0-9]+(?:-[a-z0-9]+)*\.toml")
_TEXT_KEYS = ("title", "body")


class ReleaseNoteError(ValueError):
    """A note file that does not say what a note needs; the message names the file and what is wrong."""


@dataclass(frozen=True)
class Text:
    title: str
    body: str


@dataclass(frozen=True)
class Note:
    #: The file's name without ``.toml``: unique, and stable while the file keeps its name.
    id: str
    date: dt.date
    kind: str
    texts: Mapping[str, Text]


def deployment_languages() -> tuple[str, ...]:
    return tuple(code for code, _ in settings.LANGUAGES)


def read(path: Path, languages: Sequence[str]) -> Note:
    """The note of ``path``, with its text in each of ``languages``; :class:`ReleaseNoteError` if it lacks anything."""
    date = _day(path.name)
    try:
        content = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise ReleaseNoteError(f"{path.name}: it is not valid TOML: {error}.") from error
    _same_keys(path.name, "the note", set(content), {"kind", *languages})
    if content["kind"] not in KINDS:
        raise ReleaseNoteError(f"{path.name}: its kind is {content['kind']!r}; it is one of {', '.join(KINDS)}.")
    texts = {language: _text(path.name, language, content[language]) for language in languages}
    return Note(id=path.name.removesuffix(".toml"), date=date, kind=content["kind"], texts=texts)


def notes(directory: Path = DIRECTORY, languages: Sequence[str] | None = None) -> tuple[Note, ...]:
    """Every note of ``directory``, newest first and two of one day by their name; a hidden file (``.DS_Store``) is
    not a note, and any other file is read as one."""
    wanted = deployment_languages() if languages is None else languages
    found = (read(path, wanted) for path in directory.iterdir() if path.is_file() and not path.name.startswith("."))
    return tuple(sorted(found, key=lambda note: (note.date, note.id), reverse=True))


@cache
def _image_notes() -> tuple[Note, ...]:
    return notes()


def shipped() -> tuple[Note, ...]:
    """The notes of this image, read once per process: they only change with a new image. With DEBUG, on every call,
    so that a note being written shows at once."""
    return notes() if settings.DEBUG else _image_notes()


def _day(name: str) -> dt.date:
    match = _NAME.fullmatch(name)
    if match is None:
        raise ReleaseNoteError(f"{name}: a note is named <YYYY-MM-DD>-<lowercase-words-with-hyphens>.toml.")
    try:
        return dt.date.fromisoformat(match["day"])
    except ValueError as error:
        raise ReleaseNoteError(f"{name}: {match['day']} is not a day of the calendar.") from error


def _same_keys(name: str, where: str, found: set[str], expected: set[str]) -> None:
    if missing := sorted(expected - found):
        raise ReleaseNoteError(f"{name}: {where} lacks {', '.join(missing)}.")
    if unknown := sorted(found - expected):
        raise ReleaseNoteError(f"{name}: {where} has {', '.join(unknown)}, which a note does not say.")


def _text(name: str, language: str, table: object) -> Text:
    if not isinstance(table, dict):
        raise ReleaseNoteError(f"{name}: {language} is a table with a title and a body.")
    _same_keys(name, f"its {language} text", set(table), set(_TEXT_KEYS))
    title, body = (_line(name, language, key, table[key]) for key in _TEXT_KEYS)
    if len(title) > TITLE_LENGTH or len(body) > BODY_LENGTH:
        raise ReleaseNoteError(
            f"{name}: its {language} title is up to {TITLE_LENGTH} characters and its body up to {BODY_LENGTH}."
        )
    return Text(title, body)


def _line(name: str, language: str, key: str, value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ReleaseNoteError(f"{name}: its {language} {key} is a text that is not empty.")
    return value.strip()
