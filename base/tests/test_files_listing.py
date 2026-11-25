"""The listing of a folder: the tree of folders, its crumbs and the files right in it (``base.files.listing``)."""

import datetime as dt

from base import files
from base.tests.test_files import A, code_of, disk, names, put, store, tree

__all__ = ["disk", "store"]


def test_an_empty_business_has_no_folders_no_files_and_uses_nothing(store):
    listing = files.listing.listing(store, A, "")
    assert listing == {"folder": "", "crumbs": [], "folders": [], "files": [], "used_bytes": 0}


def test_the_listing_brings_the_whole_tree_and_the_files_of_the_open_folder(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    put(store, A, "Facturas/enero.pdf", b"12345")
    put(store, A, "Contratos/local.pdf")
    files.create.create_folder(store, A, "", "Vacía")

    listing = files.listing.listing(store, A, "Facturas")

    assert tree(listing["folders"]) == [
        ("Contratos", []),
        ("Facturas", [("Facturas/2026", [])]),
        ("Vacía", []),
    ]
    assert names(listing) == ["enero.pdf"]
    [enero] = listing["files"]
    assert (enero["path"], enero["size"]) == ("Facturas/enero.pdf", 5)
    assert isinstance(enero["modified"], dt.datetime)
    assert (enero["content_type"], enero["preview"]) == ("application/pdf", "pdf")
    assert listing["crumbs"] == [{"path": "Facturas", "name": "Facturas"}]


def test_the_crumbs_lead_from_the_root_to_the_open_folder(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    assert files.listing.listing(store, A, "Facturas/2026")["crumbs"] == [
        {"path": "Facturas", "name": "Facturas"},
        {"path": "Facturas/2026", "name": "2026"},
    ]


def test_files_are_listed_by_name_and_folders_too(store):
    for name in ("b.txt", "A.txt", "c.txt"):
        put(store, A, name, b"1")
    for folder in ("zeta", "Alfa"):
        files.create.create_folder(store, A, "", folder)
    listing = files.listing.listing(store, A, "")
    assert names(listing) == ["A.txt", "b.txt", "c.txt"]
    assert [node["name"] for node in listing["folders"]] == ["Alfa", "zeta"]


def test_the_folder_marker_is_never_a_file(store):
    files.create.create_folder(store, A, "", "Vacía")
    assert files.listing.listing(store, A, "Vacía")["files"] == []


def test_a_folder_that_is_not_there_is_not_found(store):
    assert code_of(files.listing.listing, store, A, "Nadie") == "base.file_folder_missing"


def test_on_disk_the_listing_reads_sizes_and_times(disk):
    put(disk, A, "Facturas/marzo.pdf", b"12345")
    listing = files.listing.listing(disk, A, "Facturas")
    assert [(item["name"], item["size"]) for item in listing["files"]] == [("marzo.pdf", 5)]
    assert listing["used_bytes"] == 5
