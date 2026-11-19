"""The release notes an image ships: one file per change a business notices, read from ``base/release-notes/``.

A note is named after the day it reached the businesses and says its kind and its title and text in every language of
the deployment. A file that does not is refused with what it lacks, and every note the repository ships is read here,
so a broken one never reaches a business.
"""

import datetime as dt
from pathlib import Path

import pytest
from django.conf import settings

from base import release_notes
from base.release_notes import Note, ReleaseNoteError, Text

LANGUAGES = ("en", "es")

GOOD = """
kind = "new"

[en]
title = "Allergens on every product"
body = "Mark the allergens each product contains."

[es]
title = "Alérgenos en cada producto"
body = "Marca los alérgenos que lleva cada producto."
"""


def write(directory: Path, name: str, content: str = GOOD) -> Path:
    path = directory / name
    path.write_text(content, encoding="utf-8")
    return path


def test_a_note_says_its_day_its_kind_and_its_text_in_each_language(tmp_path):
    note = release_notes.read(write(tmp_path, "2026-11-19-allergens.toml"), LANGUAGES)

    assert note == Note(
        id="2026-11-19-allergens",
        date=dt.date(2026, 11, 19),
        kind="new",
        texts={
            "en": Text("Allergens on every product", "Mark the allergens each product contains."),
            "es": Text("Alérgenos en cada producto", "Marca los alérgenos que lleva cada producto."),
        },
    )


def test_the_newest_note_comes_first_and_two_of_one_day_by_their_name(tmp_path):
    for name in ("2026-11-02-b.toml", "2026-11-19-a.toml", "2026-11-02-c.toml", "2026-10-30-z.toml"):
        write(tmp_path, name)

    shipped = release_notes.notes(tmp_path, LANGUAGES)

    assert [note.id for note in shipped] == ["2026-11-19-a", "2026-11-02-c", "2026-11-02-b", "2026-10-30-z"]


def test_no_notes_is_an_empty_list(tmp_path):
    assert release_notes.notes(tmp_path, LANGUAGES) == ()


def test_a_hidden_file_of_the_system_is_not_a_note(tmp_path):
    write(tmp_path, ".DS_Store", "\x00\x01")
    write(tmp_path, "2026-11-19-allergens.toml")

    assert [note.id for note in release_notes.notes(tmp_path, LANGUAGES)] == ["2026-11-19-allergens"]


@pytest.mark.parametrize(
    "name",
    [
        "allergens.toml",  # no day
        "2026-11-19-allergens.md",  # not TOML
        "2026-11-19-Allergens.toml",  # capitals
        "2026-11-19-allergens_list.toml",  # an underscore
        "2026-11-19.toml",  # no name
        "2026-02-30-allergens.toml",  # not a day of the calendar
    ],
)
def test_a_file_misnamed_is_refused_with_its_name(tmp_path, name):
    write(tmp_path, name)

    with pytest.raises(ReleaseNoteError, match=name):
        release_notes.notes(tmp_path, LANGUAGES)


@pytest.mark.parametrize(
    ("content", "said"),
    [
        ('kind = "new"\n[en]\ntitle = "A"\nbody = "B"\n', "es"),  # a language missing
        ('kind = "news"\n[en]\ntitle = "A"\nbody = "B"\n[es]\ntitle = "A"\nbody = "B"\n', "kind"),
        ('[en]\ntitle = "A"\nbody = "B"\n[es]\ntitle = "A"\nbody = "B"\n', "kind"),
        ('kind = "fixed"\nday = 1\n[en]\ntitle = "A"\nbody = "B"\n[es]\ntitle = "A"\nbody = "B"\n', "day"),
        ('kind = "fixed"\n[en]\ntitle = "A"\nbody = "B"\n[es]\ntitle = "A"\n', "body"),
        ('kind = "fixed"\n[en]\ntitle = " "\nbody = "B"\n[es]\ntitle = "A"\nbody = "B"\n', "title"),
        ('kind = "fixed"\n[en]\ntitle = "A"\nbody = 3\n[es]\ntitle = "A"\nbody = "B"\n', "body"),
        ('kind = "fixed"\n[en]\ntitle = "A"\nbody = "B"\nsubtitle = "C"\n[es]\ntitle = "A"\nbody = "B"\n', "subtitle"),
        ('kind = "fixed"\nen = "A"\n[es]\ntitle = "A"\nbody = "B"\n', "en"),
        ("kind = new", "TOML"),
    ],
)
def test_a_note_that_lacks_what_a_note_says_is_refused_with_what_is_wrong(tmp_path, content, said):
    write(tmp_path, "2026-11-19-allergens.toml", content)

    with pytest.raises(ReleaseNoteError, match=said):
        release_notes.notes(tmp_path, LANGUAGES)


def test_a_title_and_a_text_stay_short(tmp_path):
    long_title = GOOD.replace("Allergens on every product", "A" * (release_notes.TITLE_LENGTH + 1))
    long_body = GOOD.replace("Mark the allergens each product contains.", "B" * (release_notes.BODY_LENGTH + 1))
    write(tmp_path, "2026-11-19-title.toml", long_title)
    write(tmp_path, "2026-11-19-body.toml", long_body)

    for name in ("2026-11-19-title.toml", "2026-11-19-body.toml"):
        with pytest.raises(ReleaseNoteError, match=name):
            release_notes.read(tmp_path / name, LANGUAGES)


def test_the_text_is_kept_as_written_without_its_surrounding_blanks(tmp_path):
    write(tmp_path, "2026-11-19-allergens.toml", GOOD.replace('"Allergens on every product"', '"  Allergens  "'))

    assert release_notes.read(tmp_path / "2026-11-19-allergens.toml", LANGUAGES).texts["en"].title == "Allergens"


def test_every_note_the_repository_ships_is_whole_in_each_language_of_the_deployment():
    languages = tuple(code for code, _ in settings.LANGUAGES)

    shipped = release_notes.notes(release_notes.DIRECTORY, languages)

    assert shipped, "the repository ships at least one note"
    assert all(set(note.texts) == set(languages) for note in shipped)


@pytest.fixture
def unread():
    """No note of the image read yet in this process, before and after the test."""
    release_notes._image_notes.cache_clear()
    yield
    release_notes._image_notes.cache_clear()


def test_the_notes_shipped_are_read_once_per_process_and_on_every_call_while_developing(settings, monkeypatch, unread):
    reads = []
    monkeypatch.setattr(release_notes, "notes", lambda: reads.append(1) or ())
    settings.DEBUG = False

    release_notes.shipped()
    release_notes.shipped()
    assert len(reads) == 1

    settings.DEBUG = True
    release_notes.shipped()
    release_notes.shipped()
    assert len(reads) == 3


def test_by_default_the_notes_are_the_repository_s_in_the_deployment_s_languages(unread):
    assert release_notes.shipped() == release_notes.notes(release_notes.DIRECTORY, ("en", "es"))
