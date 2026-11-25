"""Deleting a file, or a folder with everything in it (``base.files.delete``)."""

from base import files
from base.tests.test_files import A, PDF, code_of, names, put, store, tree

__all__ = ["store"]


def test_deleting_a_file(store):
    put(store, A, "a.pdf")
    put(store, A, "b.pdf")
    assert files.delete.delete(store, A, "a.pdf") == {"path": "a.pdf", "folder": False}
    assert names(files.listing.listing(store, A, "")) == ["b.pdf"]


def test_deleting_a_folder_deletes_everything_inside(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    files.create.create_folder(store, A, "Facturas", "Vacía")
    put(store, A, "Contratos/x.pdf")
    assert files.delete.delete(store, A, "Facturas") == {"path": "Facturas", "folder": True}
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("Contratos", [])]
    assert files.listing.listing(store, A, "")["used_bytes"] == len(PDF)


def test_the_root_is_never_deleted(store):
    assert code_of(files.delete.delete, store, A, "") == "base.file_invalid_path"


def test_what_is_not_there_is_not_deleted(store):
    assert code_of(files.delete.delete, store, A, "a.pdf") == "base.file_missing"
