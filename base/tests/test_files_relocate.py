"""Renaming and moving a file or a folder (``base.files.relocate``)."""

import pytest

from base import files
from base.tests.test_files import A, code_of, names, put, store, tree

__all__ = ["store"]


def test_renaming_a_file_keeps_it_in_its_folder(store):
    put(store, A, "Facturas/marzo.pdf", b"bytes")
    assert files.relocate.rename(store, A, "Facturas/marzo.pdf", "abril.pdf") == {
        "path": "Facturas/abril.pdf",
        "name": "abril.pdf",
    }
    assert names(files.listing.listing(store, A, "Facturas")) == ["abril.pdf"]
    with files.read.open_file(store, A, "Facturas/abril.pdf") as moved:
        assert moved.read() == b"bytes"


def test_renaming_a_folder_takes_everything_inside_with_it(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    files.create.create_folder(store, A, "Facturas", "Vacía")
    files.relocate.rename(store, A, "Facturas", "Facturación")
    assert tree(files.listing.listing(store, A, "")["folders"]) == [
        ("Facturación", [("Facturación/2026", []), ("Facturación/Vacía", [])])
    ]
    assert names(files.listing.listing(store, A, "Facturación/2026")) == ["marzo.pdf"]


def test_renaming_to_the_same_name_changes_nothing(store):
    put(store, A, "a.pdf")
    assert files.relocate.rename(store, A, "a.pdf", "a.pdf") == {"path": "a.pdf", "name": "a.pdf"}
    assert names(files.listing.listing(store, A, "")) == ["a.pdf"]


def test_renaming_never_takes_the_name_of_another(store):
    put(store, A, "a.pdf", b"a")
    put(store, A, "b.pdf", b"b")
    assert code_of(files.relocate.rename, store, A, "a.pdf", "b.pdf") == "base.file_exists"
    with files.read.open_file(store, A, "b.pdf") as kept:
        assert kept.read() == b"b"


@pytest.mark.parametrize("name", ["sub/x.pdf", "..", "x\\y"])
def test_a_new_name_is_a_name_never_a_path(store, name):
    # A rename that carried a path would be a move out of its folder.
    put(store, A, "a.pdf")
    assert code_of(files.relocate.rename, store, A, "a.pdf", name) == "base.file_invalid_name"


def test_a_program_name_is_not_given_by_renaming_either(store):
    put(store, A, "a.txt")
    assert code_of(files.relocate.rename, store, A, "a.txt", "a.exe") == "base.file_type_refused"


def test_moving_a_file_into_a_folder(store):
    put(store, A, "a.pdf", b"a")
    files.create.create_folder(store, A, "", "Facturas")
    assert files.relocate.move(store, A, "a.pdf", "Facturas") == {"path": "Facturas/a.pdf", "name": "a.pdf"}
    assert names(files.listing.listing(store, A, "")) == []
    assert names(files.listing.listing(store, A, "Facturas")) == ["a.pdf"]


def test_moving_a_folder_to_the_root(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    assert files.relocate.move(store, A, "Facturas/2026", "") == {"path": "2026", "name": "2026"}
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("2026", []), ("Facturas", [])]
    assert names(files.listing.listing(store, A, "2026")) == ["marzo.pdf"]


def test_moving_to_where_it_already_is_is_refused(store):
    put(store, A, "Facturas/a.pdf")
    assert code_of(files.relocate.move, store, A, "Facturas/a.pdf", "Facturas") == "base.file_already_there"


@pytest.mark.parametrize("into", ["Facturas", "Facturas/2026"])
def test_a_folder_is_never_moved_inside_itself(store, into):
    put(store, A, "Facturas/2026/marzo.pdf")
    assert code_of(files.relocate.move, store, A, "Facturas", into) == "base.file_move_into_itself"


def test_a_folder_named_like_the_start_of_another_is_not_inside_it(store):
    # «Facturas» → «Facturas2026» is a move between siblings, not into itself.
    put(store, A, "Facturas/a.pdf")
    files.create.create_folder(store, A, "", "Facturas2026")
    assert files.relocate.move(store, A, "Facturas", "Facturas2026")["path"] == "Facturas2026/Facturas"


def test_moving_never_overwrites_in_the_destination(store):
    put(store, A, "a.pdf", b"mine")
    put(store, A, "Facturas/a.pdf", b"theirs")
    assert code_of(files.relocate.move, store, A, "a.pdf", "Facturas") == "base.file_exists"
    with files.read.open_file(store, A, "Facturas/a.pdf") as kept:
        assert kept.read() == b"theirs"


def test_moving_into_a_folder_that_is_not_there_is_refused(store):
    put(store, A, "a.pdf")
    assert code_of(files.relocate.move, store, A, "a.pdf", "Nadie") == "base.file_folder_missing"
