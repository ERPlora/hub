"""Uploading a file and making a new folder, never over what is there (``base.files.create``)."""

import pytest
from botocore.stub import ANY
from live.errors import OperationError

from base import files
from base.storage import hub_prefix
from base.tests.test_files import A, PDF, code_of, disk, put, s3, store, tree

__all__ = ["disk", "s3", "store"]


def test_an_upload_keeps_the_bytes_in_the_open_folder(store):
    files.create.create_folder(store, A, "", "Facturas")
    saved = files.create.upload(store, A, "Facturas", "marzo.pdf", PDF)
    assert saved == {"path": "Facturas/marzo.pdf", "name": "marzo.pdf", "size": len(PDF)}
    with store.open(f"{hub_prefix(A)}/files/Facturas/marzo.pdf") as stored:
        assert stored.read() == PDF


def test_an_upload_never_overwrites_it_numbers_the_copy(store):
    assert files.create.upload(store, A, "", "a.pdf", b"1")["name"] == "a.pdf"
    assert files.create.upload(store, A, "", "a.pdf", b"2")["name"] == "a (1).pdf"
    assert files.create.upload(store, A, "", "a.pdf", b"3")["name"] == "a (2).pdf"
    assert files.create.upload(store, A, "", "notas", b"4")["name"] == "notas"
    assert files.create.upload(store, A, "", "notas", b"5")["name"] == "notas (1)"
    with store.open(f"{hub_prefix(A)}/files/a.pdf") as first:
        assert first.read() == b"1"


def test_a_file_never_takes_the_name_of_a_folder(store):
    files.create.create_folder(store, A, "", "Facturas")
    assert files.create.upload(store, A, "", "Facturas", b"1")["name"] == "Facturas (1)"


def test_an_empty_file_is_a_file(store):
    assert files.create.upload(store, A, "", "vacío.txt", b"")["size"] == 0


@pytest.mark.parametrize("name", ["virus.exe", "VIRUS.EXE", "script.bat", "macro.vbs", "app.msi", "x.ps1"])
def test_a_program_is_not_uploaded(store, name):
    assert code_of(files.create.upload, store, A, "", name, b"MZ") == "base.file_type_refused"


def test_a_file_past_the_ceiling_is_not_uploaded(store, monkeypatch):
    monkeypatch.setattr(files.create, "MAX_FILE_BYTES", 10)
    assert files.create.upload(store, A, "", "diez.txt", b"x" * 10)["size"] == 10
    assert code_of(files.create.upload, store, A, "", "once.txt", b"x" * 11) == "base.file_too_large"


def test_an_upload_past_the_plan_s_space_is_refused(store):
    put(store, A, "a.pdf", b"x" * 60)
    assert code_of(files.create.upload, store, A, "", "b.pdf", b"x" * 41, limit_bytes=100) == "base.file_no_space"
    assert files.create.upload(store, A, "", "b.pdf", b"x" * 40, limit_bytes=100)["size"] == 40
    # Without a limit in the plan, there is none.
    assert files.create.upload(store, A, "", "c.pdf", b"x" * 500, limit_bytes=None)["size"] == 500


def test_an_upload_into_a_folder_that_is_not_there_is_refused(store):
    assert code_of(files.create.upload, store, A, "Nadie", "a.pdf", PDF) == "base.file_folder_missing"


def test_a_new_folder_is_there_empty(store):
    assert files.create.create_folder(store, A, "", "Facturas") == {"path": "Facturas", "name": "Facturas"}
    assert files.create.create_folder(store, A, "Facturas", "2026") == {"path": "Facturas/2026", "name": "2026"}
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("Facturas", [("Facturas/2026", [])])]


def test_a_folder_name_takes_100_characters_at_most(store):
    assert files.create.create_folder(store, A, "", "x" * 100)["name"] == "x" * 100
    assert code_of(files.create.create_folder, store, A, "", "y" * 101) == "base.file_invalid_name"


def test_a_folder_is_never_made_twice_nor_over_a_file(store):
    files.create.create_folder(store, A, "", "Facturas")
    put(store, A, "notas.txt", b"1")
    assert code_of(files.create.create_folder, store, A, "", "Facturas") == "base.file_exists"
    assert code_of(files.create.create_folder, store, A, "", "notas.txt") == "base.file_exists"


def test_a_new_folder_inside_one_that_is_not_there_is_refused(store):
    assert code_of(files.create.create_folder, store, A, "Nadie", "x") == "base.file_folder_missing"


def stale_free_name(monkeypatch, *names):
    """Two uploads of one name at once: each works out the free name before either writes, so the second one's first
    answer is the name the first one is writing now (``names``); then the real one."""
    real, stale = files.create._free_name, iter(names)
    monkeypatch.setattr(files.create, "_free_name", lambda *args: next(stale, None) or real(*args))


def test_on_disk_two_uploads_of_one_name_at_once_never_write_over_each_other(disk, tmp_path, monkeypatch):
    # Checking the free name and then writing over it (``file_overwrite``) would let the second upload take the
    # first's name and lose the first file: the write itself refuses a name that is taken, and the upload takes the
    # next.
    put(disk, A, "a.pdf", b"first")
    stale_free_name(monkeypatch, "a.pdf")
    saved = files.create.upload(disk, A, "", "a.pdf", b"second")
    assert (saved["path"], saved["name"]) == ("a (1).pdf", "a (1).pdf")
    root = tmp_path / hub_prefix(A) / files.names.ROOT
    assert sorted(path.name for path in root.iterdir()) == ["a (1).pdf", "a.pdf"]
    assert ((root / "a.pdf").read_bytes(), (root / "a (1).pdf").read_bytes()) == (b"first", b"second")


def put_if_free(stubber, key, *, taken=False):
    """S3's conditional write (``If-None-Match: *``): written only if nobody has ``key``; else 412."""
    expected = {"Bucket": "erplora-test-hubs", "Key": key, "Body": ANY, "ContentType": ANY, "IfNoneMatch": "*"}
    if taken:
        stubber.add_client_error(
            "put_object", service_error_code="PreconditionFailed", http_status_code=412, expected_params=expected
        )
    else:
        stubber.add_response("put_object", {"ETag": '"e"'}, expected)


def test_on_s3_an_upload_writes_only_where_nobody_has_written_and_takes_the_next_name_if_somebody_just_did(
    s3, monkeypatch
):
    storage, stubber = s3
    base = f"{hub_prefix(A)}/{files.names.ROOT}"
    stale_free_name(monkeypatch, "a.pdf", "a (1).pdf")
    put_if_free(stubber, f"{base}/a.pdf", taken=True)  # another upload of «a.pdf» wrote it a moment ago
    put_if_free(stubber, f"{base}/a (1).pdf")
    saved = files.create.upload(storage, A, "", "a.pdf", PDF)
    stubber.assert_no_pending_responses()
    assert (saved["path"], saved["name"], saved["size"]) == ("a (1).pdf", "a (1).pdf", len(PDF))


def test_on_s3_a_conditional_write_the_store_fails_is_said_so(s3, monkeypatch):
    storage, stubber = s3
    stale_free_name(monkeypatch, "a.pdf")
    stubber.add_client_error("put_object", service_error_code="InternalError", http_status_code=500)
    error = pytest.raises(OperationError, files.create.upload, storage, A, "", "a.pdf", PDF).value
    assert (error.status, error.code) == (503, "base.file_store_unavailable")
