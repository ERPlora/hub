"""Reading a file: what it is and its bytes, from its hub's prefix (``base.files.read``)."""

from base import files
from base.tests.test_files import A, PDF, code_of, put, store

__all__ = ["store"]


def test_a_file_is_described_by_its_name_size_and_type(store):
    put(store, A, "Facturas/marzo.pdf")
    assert files.read.describe(store, A, "Facturas/marzo.pdf") == {
        "path": "Facturas/marzo.pdf",
        "name": "marzo.pdf",
        "size": len(PDF),
        "content_type": "application/pdf",
        "preview": "pdf",
    }


def test_a_folder_is_no_file_to_read(store):
    files.create.create_folder(store, A, "", "Facturas")
    assert code_of(files.read.describe, store, A, "Facturas") == "base.file_missing"
    assert code_of(files.read.describe, store, A, "") == "base.file_invalid_path"


def test_the_bytes_of_a_file_are_opened_from_its_hub_s_prefix(store):
    put(store, A, "a.pdf", b"own")
    with files.read.open_file(store, A, "a.pdf") as opened:
        assert opened.read() == b"own"
