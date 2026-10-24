"""The business's files (APP-BASE-8, ``base.files``): what the Files screen keeps in the hub file store.

They live under the hub's prefix, in its own folder (``hub-<hex>/files/…``), apart from what the modules keep
(``website/img/``, published by ``/p/media/``): a file of the business is never public. A name is one segment and a
path a chain of them; nothing that could climb out of the folder (``..``, a backslash, a leading ``/``, a NUL)
reaches the store, and one hub never lists, reads, moves nor deletes another's (BASE-G82…G86, saas#972). Writing
never overwrites in silence: a second «a.pdf» is «a (1).pdf» (Google Drive, Dropbox).
"""

import datetime as dt
import re
import unicodedata
import uuid
from pathlib import Path

import boto3
import pytest
from botocore.exceptions import EndpointConnectionError
from botocore.stub import Stubber
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage, InMemoryStorage, storages
from django.utils import translation
from django.utils.translation import gettext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError
from storages.backends.s3 import S3Storage
from storages.utils import clean_name, safe_join

from base import files
from base.storage import hub_prefix

A = uuid.UUID("0199c4b0-0000-7000-8000-00000000000a")
B = uuid.UUID("0199c4b0-0000-7000-8000-00000000000b")
PDF = b"%PDF-1.7\n" + b"x" * 100


class S3NamedInMemoryStorage(InMemoryStorage):
    """In memory, but reading a name as ``S3Storage`` does: backslashes become slashes and ``..`` folds, so
    ``hub-a/files/../../hub-b/x`` would be b's file there (``base/tests/test_media.py``)."""

    def _open(self, name, mode="rb"):
        return super()._open(safe_join("", clean_name(name)), mode)

    def _save(self, name, content):
        return super()._save(safe_join("", clean_name(name)), content)


@pytest.fixture
def store(settings):
    settings.STORAGES = {**settings.STORAGES, "hub_files": {"BACKEND": f"{__name__}.S3NamedInMemoryStorage"}}
    return storages["hub_files"]


def put(store, hub, path, content=PDF):
    store.save(f"{hub_prefix(hub)}/{files.ROOT}/{path}", ContentFile(content))


def names(listing):
    return [item["name"] for item in listing["files"]]


def tree(nodes):
    return [(node["path"], tree(node["children"])) for node in nodes]


def code_of(call, *args, **kwargs):
    with pytest.raises(OperationError) as raised:
        call(*args, **kwargs)
    return raised.value.code


# ── Names and paths ──────────────────────────────────────────────────────────────────────────────────────────


def test_a_name_is_kept_as_typed_trimmed_and_in_one_unicode_form():
    assert files.clean_name("  Factura 2026.pdf ") == "Factura 2026.pdf"
    # macOS hands names decomposed (NFD): «Facturación» typed twice is one name, never two lookalikes.
    decomposed = unicodedata.normalize("NFD", "Facturación")
    assert files.clean_name(decomposed) == unicodedata.normalize("NFC", "Facturación")


@pytest.mark.parametrize(
    "name", ["", "   ", ".", "..", "a/b", "a\\b", "a\x00b", "a\nb", "a\tb", files.MARKER, "x" * 256, "ñ" * 128]
)
def test_a_name_is_one_plain_segment(name):
    assert code_of(files.clean_name, name) == "base.file_invalid_name"


def test_a_name_may_take_255_bytes():
    assert files.clean_name("x" * 255) == "x" * 255


@pytest.mark.parametrize("path", ["", "Facturas", "Facturas/2026", "Facturas/2026/marzo.pdf"])
def test_a_path_is_a_chain_of_names_and_empty_is_the_root(path):
    assert files.clean_path(path) == path


@pytest.mark.parametrize(
    "path", ["/Facturas", "Facturas/", "a//b", "../x", "a/../b", "./a", "a/.", "a\\b", "x\x00", "a/.keep"]
)
def test_a_path_never_leaves_the_business_files(path):
    assert code_of(files.clean_path, path) == "base.file_invalid_path"


def test_a_path_has_a_ceiling():
    deep = "/".join(["carpeta"] * 140)
    assert code_of(files.clean_path, deep) == "base.file_invalid_path"


# ── Listing (BASE-G82) ───────────────────────────────────────────────────────────────────────────────────────


def test_an_empty_business_has_no_folders_no_files_and_uses_nothing(store):
    listing = files.listing(store, A, "")
    assert listing == {"folder": "", "crumbs": [], "folders": [], "files": [], "used_bytes": 0}


def test_the_listing_brings_the_whole_tree_and_the_files_of_the_open_folder(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    put(store, A, "Facturas/enero.pdf", b"12345")
    put(store, A, "Contratos/local.pdf")
    files.create_folder(store, A, "", "Vacía")

    listing = files.listing(store, A, "Facturas")

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
    assert files.listing(store, A, "Facturas/2026")["crumbs"] == [
        {"path": "Facturas", "name": "Facturas"},
        {"path": "Facturas/2026", "name": "2026"},
    ]


def test_files_are_listed_by_name_and_folders_too(store):
    for name in ("b.txt", "A.txt", "c.txt"):
        put(store, A, name, b"1")
    for folder in ("zeta", "Alfa"):
        files.create_folder(store, A, "", folder)
    listing = files.listing(store, A, "")
    assert names(listing) == ["A.txt", "b.txt", "c.txt"]
    assert [node["name"] for node in listing["folders"]] == ["Alfa", "zeta"]


def test_the_folder_marker_is_never_a_file(store):
    files.create_folder(store, A, "", "Vacía")
    assert files.listing(store, A, "Vacía")["files"] == []


def test_a_folder_that_is_not_there_is_not_found(store):
    assert code_of(files.listing, store, A, "Nadie") == "base.file_folder_missing"


def test_the_space_used_is_the_whole_prefix_of_the_hub_and_only_its_own(store):
    put(store, A, "a.pdf", b"x" * 10)
    store.save(f"{hub_prefix(A)}/website/img/abc.png", ContentFile(b"y" * 7))
    put(store, B, "b.pdf", b"z" * 1000)
    assert files.listing(store, A, "")["used_bytes"] == 17


def test_the_preview_and_the_type_come_from_the_name_never_from_the_content():
    assert files.served("foto.JPG") == ("image/jpeg", "image")
    assert files.served("informe.pdf") == ("application/pdf", "pdf")
    assert files.served("notas.txt") == ("text/plain", "text")
    assert files.served("ventas.csv") == ("text/plain", "table")
    assert files.served("datos.json") == ("text/plain", "json")
    assert files.served("audio.mp3") == ("audio/mpeg", "audio")
    assert files.served("video.mp4") == ("video/mp4", "video")
    assert files.served("hoja.xlsx") == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "",
    )
    # Markup and scripts are their source, as text: a browser never runs them (saas#968).
    assert files.served("pagina.html") == ("text/plain", "text")
    assert files.served("script.js") == ("text/plain", "text")
    # An SVG may carry script: never shown, downloaded as plain bytes. So is what nobody knows.
    assert files.served("logo.svg") == ("application/octet-stream", "")
    assert files.served("raro.zzz") == ("application/octet-stream", "")
    assert files.served("sin-extension") == ("application/octet-stream", "")


# ── One hub never reaches another's (A ≠ B) ──────────────────────────────────────────────────────────────────


def test_a_hub_never_lists_another_s_files(store):
    put(store, B, "Secreto/nominas.pdf")
    listing = files.listing(store, A, "")
    assert (listing["folders"], listing["files"]) == ([], [])
    assert code_of(files.listing, store, A, "Secreto") == "base.file_folder_missing"


def test_what_a_hub_writes_lands_under_its_own_prefix_only(store):
    files.upload(store, A, "", "a.pdf", PDF)
    files.create_folder(store, A, "", "Carpeta")
    assert store.exists(f"{hub_prefix(A)}/files/a.pdf")
    assert store.exists(f"{hub_prefix(A)}/files/Carpeta/{files.MARKER}")
    assert store.listdir("")[0] == [hub_prefix(A)]


@pytest.mark.parametrize(
    "call",
    [
        lambda store: files.describe(store, A, "Secreto/nominas.pdf"),
        lambda store: files.rename(store, A, "Secreto/nominas.pdf", "x.pdf"),
        lambda store: files.move(store, A, "Secreto/nominas.pdf", ""),
        lambda store: files.delete(store, A, "Secreto/nominas.pdf"),
    ],
)
def test_a_hub_never_reads_moves_nor_deletes_another_s_file(store, call):
    put(store, B, "Secreto/nominas.pdf")
    assert code_of(call, store) == "base.file_missing"
    assert store.exists(f"{hub_prefix(B)}/files/Secreto/nominas.pdf")


@pytest.mark.parametrize(
    "climb", [f"../../{hub_prefix(B)}/files/Secreto/nominas.pdf", f"..\\..\\{hub_prefix(B)}\\files\\x.pdf"]
)
def test_a_path_that_climbs_is_refused_before_the_store_sees_it(store, climb):
    # The S3 store folds «..»: a's prefix + «../../hub-b/…» would BE b's file there.
    put(store, B, "Secreto/nominas.pdf")
    for call in (files.describe, files.delete):
        assert code_of(call, store, A, climb) == "base.file_invalid_path"
    assert code_of(files.upload, store, A, climb, "x.pdf", PDF) == "base.file_invalid_path"
    assert store.exists(f"{hub_prefix(B)}/files/Secreto/nominas.pdf")


# ── Upload and new folder (BASE-G83) ─────────────────────────────────────────────────────────────────────────


def test_an_upload_keeps_the_bytes_in_the_open_folder(store):
    files.create_folder(store, A, "", "Facturas")
    saved = files.upload(store, A, "Facturas", "marzo.pdf", PDF)
    assert saved == {"path": "Facturas/marzo.pdf", "name": "marzo.pdf", "size": len(PDF)}
    with store.open(f"{hub_prefix(A)}/files/Facturas/marzo.pdf") as stored:
        assert stored.read() == PDF


def test_an_upload_never_overwrites_it_numbers_the_copy(store):
    assert files.upload(store, A, "", "a.pdf", b"1")["name"] == "a.pdf"
    assert files.upload(store, A, "", "a.pdf", b"2")["name"] == "a (1).pdf"
    assert files.upload(store, A, "", "a.pdf", b"3")["name"] == "a (2).pdf"
    assert files.upload(store, A, "", "notas", b"4")["name"] == "notas"
    assert files.upload(store, A, "", "notas", b"5")["name"] == "notas (1)"
    with store.open(f"{hub_prefix(A)}/files/a.pdf") as first:
        assert first.read() == b"1"


def test_a_file_never_takes_the_name_of_a_folder(store):
    files.create_folder(store, A, "", "Facturas")
    assert files.upload(store, A, "", "Facturas", b"1")["name"] == "Facturas (1)"


def test_an_empty_file_is_a_file(store):
    assert files.upload(store, A, "", "vacío.txt", b"")["size"] == 0


@pytest.mark.parametrize("name", ["virus.exe", "VIRUS.EXE", "script.bat", "macro.vbs", "app.msi", "x.ps1"])
def test_a_program_is_not_uploaded(store, name):
    assert code_of(files.upload, store, A, "", name, b"MZ") == "base.file_type_refused"


def test_a_file_past_the_ceiling_is_not_uploaded(store, monkeypatch):
    monkeypatch.setattr(files, "MAX_FILE_BYTES", 10)
    assert files.upload(store, A, "", "diez.txt", b"x" * 10)["size"] == 10
    assert code_of(files.upload, store, A, "", "once.txt", b"x" * 11) == "base.file_too_large"


def test_an_upload_past_the_plan_s_space_is_refused(store):
    put(store, A, "a.pdf", b"x" * 60)
    assert code_of(files.upload, store, A, "", "b.pdf", b"x" * 41, limit_bytes=100) == "base.file_no_space"
    assert files.upload(store, A, "", "b.pdf", b"x" * 40, limit_bytes=100)["size"] == 40
    # Without a limit in the plan, there is none.
    assert files.upload(store, A, "", "c.pdf", b"x" * 500, limit_bytes=None)["size"] == 500


def test_an_upload_into_a_folder_that_is_not_there_is_refused(store):
    assert code_of(files.upload, store, A, "Nadie", "a.pdf", PDF) == "base.file_folder_missing"


def test_a_new_folder_is_there_empty(store):
    assert files.create_folder(store, A, "", "Facturas") == {"path": "Facturas", "name": "Facturas"}
    assert files.create_folder(store, A, "Facturas", "2026") == {"path": "Facturas/2026", "name": "2026"}
    assert tree(files.listing(store, A, "")["folders"]) == [("Facturas", [("Facturas/2026", [])])]


def test_a_folder_name_takes_100_characters_at_most(store):
    assert files.create_folder(store, A, "", "x" * 100)["name"] == "x" * 100
    assert code_of(files.create_folder, store, A, "", "y" * 101) == "base.file_invalid_name"


def test_a_folder_is_never_made_twice_nor_over_a_file(store):
    files.create_folder(store, A, "", "Facturas")
    put(store, A, "notas.txt", b"1")
    assert code_of(files.create_folder, store, A, "", "Facturas") == "base.file_exists"
    assert code_of(files.create_folder, store, A, "", "notas.txt") == "base.file_exists"


def test_a_new_folder_inside_one_that_is_not_there_is_refused(store):
    assert code_of(files.create_folder, store, A, "Nadie", "x") == "base.file_folder_missing"


# ── Read (BASE-G84) ──────────────────────────────────────────────────────────────────────────────────────────


def test_a_file_is_described_by_its_name_size_and_type(store):
    put(store, A, "Facturas/marzo.pdf")
    assert files.describe(store, A, "Facturas/marzo.pdf") == {
        "path": "Facturas/marzo.pdf",
        "name": "marzo.pdf",
        "size": len(PDF),
        "content_type": "application/pdf",
        "preview": "pdf",
    }


def test_a_folder_is_no_file_to_read(store):
    files.create_folder(store, A, "", "Facturas")
    assert code_of(files.describe, store, A, "Facturas") == "base.file_missing"
    assert code_of(files.describe, store, A, "") == "base.file_invalid_path"


def test_the_bytes_of_a_file_are_opened_from_its_hub_s_prefix(store):
    put(store, A, "a.pdf", b"own")
    with files.open_file(store, A, "a.pdf") as opened:
        assert opened.read() == b"own"


# ── Rename and move (BASE-G85) ───────────────────────────────────────────────────────────────────────────────


def test_renaming_a_file_keeps_it_in_its_folder(store):
    put(store, A, "Facturas/marzo.pdf", b"bytes")
    assert files.rename(store, A, "Facturas/marzo.pdf", "abril.pdf") == {
        "path": "Facturas/abril.pdf",
        "name": "abril.pdf",
    }
    assert names(files.listing(store, A, "Facturas")) == ["abril.pdf"]
    with files.open_file(store, A, "Facturas/abril.pdf") as moved:
        assert moved.read() == b"bytes"


def test_renaming_a_folder_takes_everything_inside_with_it(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    files.create_folder(store, A, "Facturas", "Vacía")
    files.rename(store, A, "Facturas", "Facturación")
    assert tree(files.listing(store, A, "")["folders"]) == [
        ("Facturación", [("Facturación/2026", []), ("Facturación/Vacía", [])])
    ]
    assert names(files.listing(store, A, "Facturación/2026")) == ["marzo.pdf"]


def test_renaming_to_the_same_name_changes_nothing(store):
    put(store, A, "a.pdf")
    assert files.rename(store, A, "a.pdf", "a.pdf") == {"path": "a.pdf", "name": "a.pdf"}
    assert names(files.listing(store, A, "")) == ["a.pdf"]


def test_renaming_never_takes_the_name_of_another(store):
    put(store, A, "a.pdf", b"a")
    put(store, A, "b.pdf", b"b")
    assert code_of(files.rename, store, A, "a.pdf", "b.pdf") == "base.file_exists"
    with files.open_file(store, A, "b.pdf") as kept:
        assert kept.read() == b"b"


@pytest.mark.parametrize("name", ["sub/x.pdf", "..", "x\\y"])
def test_a_new_name_is_a_name_never_a_path(store, name):
    # A rename that carried a path would be a move out of its folder.
    put(store, A, "a.pdf")
    assert code_of(files.rename, store, A, "a.pdf", name) == "base.file_invalid_name"


def test_a_program_name_is_not_given_by_renaming_either(store):
    put(store, A, "a.txt")
    assert code_of(files.rename, store, A, "a.txt", "a.exe") == "base.file_type_refused"


def test_moving_a_file_into_a_folder(store):
    put(store, A, "a.pdf", b"a")
    files.create_folder(store, A, "", "Facturas")
    assert files.move(store, A, "a.pdf", "Facturas") == {"path": "Facturas/a.pdf", "name": "a.pdf"}
    assert names(files.listing(store, A, "")) == []
    assert names(files.listing(store, A, "Facturas")) == ["a.pdf"]


def test_moving_a_folder_to_the_root(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    assert files.move(store, A, "Facturas/2026", "") == {"path": "2026", "name": "2026"}
    assert tree(files.listing(store, A, "")["folders"]) == [("2026", []), ("Facturas", [])]
    assert names(files.listing(store, A, "2026")) == ["marzo.pdf"]


def test_moving_to_where_it_already_is_is_refused(store):
    put(store, A, "Facturas/a.pdf")
    assert code_of(files.move, store, A, "Facturas/a.pdf", "Facturas") == "base.file_already_there"


@pytest.mark.parametrize("into", ["Facturas", "Facturas/2026"])
def test_a_folder_is_never_moved_inside_itself(store, into):
    put(store, A, "Facturas/2026/marzo.pdf")
    assert code_of(files.move, store, A, "Facturas", into) == "base.file_move_into_itself"


def test_a_folder_named_like_the_start_of_another_is_not_inside_it(store):
    # «Facturas» → «Facturas2026» is a move between siblings, not into itself.
    put(store, A, "Facturas/a.pdf")
    files.create_folder(store, A, "", "Facturas2026")
    assert files.move(store, A, "Facturas", "Facturas2026")["path"] == "Facturas2026/Facturas"


def test_moving_never_overwrites_in_the_destination(store):
    put(store, A, "a.pdf", b"mine")
    put(store, A, "Facturas/a.pdf", b"theirs")
    assert code_of(files.move, store, A, "a.pdf", "Facturas") == "base.file_exists"
    with files.open_file(store, A, "Facturas/a.pdf") as kept:
        assert kept.read() == b"theirs"


def test_moving_into_a_folder_that_is_not_there_is_refused(store):
    put(store, A, "a.pdf")
    assert code_of(files.move, store, A, "a.pdf", "Nadie") == "base.file_folder_missing"


# ── Delete (BASE-G86) ────────────────────────────────────────────────────────────────────────────────────────


def test_deleting_a_file(store):
    put(store, A, "a.pdf")
    put(store, A, "b.pdf")
    assert files.delete(store, A, "a.pdf") == {"path": "a.pdf", "folder": False}
    assert names(files.listing(store, A, "")) == ["b.pdf"]


def test_deleting_a_folder_deletes_everything_inside(store):
    put(store, A, "Facturas/2026/marzo.pdf")
    files.create_folder(store, A, "Facturas", "Vacía")
    put(store, A, "Contratos/x.pdf")
    assert files.delete(store, A, "Facturas") == {"path": "Facturas", "folder": True}
    assert tree(files.listing(store, A, "")["folders"]) == [("Contratos", [])]
    assert files.listing(store, A, "")["used_bytes"] == len(PDF)


def test_the_root_is_never_deleted(store):
    assert code_of(files.delete, store, A, "") == "base.file_invalid_path"


def test_what_is_not_there_is_not_deleted(store):
    assert code_of(files.delete, store, A, "a.pdf") == "base.file_missing"


# ── On disk (local development) ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def disk(tmp_path):
    return FileSystemStorage(location=tmp_path)


def test_on_disk_a_folder_moved_or_deleted_leaves_no_empty_directory_behind(disk, tmp_path):
    put(disk, A, "Facturas/2026/marzo.pdf")
    files.rename(disk, A, "Facturas", "Facturación")
    root = tmp_path / hub_prefix(A) / files.ROOT
    assert sorted(path.name for path in root.iterdir()) == ["Facturación"]
    files.delete(disk, A, "Facturación")
    assert list(root.iterdir()) == []


def test_on_disk_the_listing_reads_sizes_and_times(disk):
    put(disk, A, "Facturas/marzo.pdf", b"12345")
    listing = files.listing(disk, A, "Facturas")
    assert [(item["name"], item["size"]) for item in listing["files"]] == [("marzo.pdf", 5)]
    assert listing["used_bytes"] == 5


# ── On S3: one listing per thousand keys, never a request per file ───────────────────────────────────────────


@pytest.fixture
def s3(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    storage = S3Storage(bucket_name="erplora-test-hubs", region_name="eu-west-1", default_acl=None)
    storage._connections.connection = boto3.session.Session().resource("s3", region_name="eu-west-1")
    stubber = Stubber(storage.connection.meta.client)
    with stubber:
        yield storage, stubber


def objects(*pairs):
    when = dt.datetime(2026, 10, 24, 9, 30, tzinfo=dt.UTC)
    return {
        "IsTruncated": False,
        "KeyCount": len(pairs),
        "Contents": [{"Key": key, "Size": size, "LastModified": when} for key, size in pairs],
    }


def test_on_s3_the_listing_and_the_space_come_from_one_listing_of_the_hub_s_prefix(s3):
    storage, stubber = s3
    prefix = hub_prefix(A)
    stubber.add_response(
        "list_objects_v2",
        objects(
            (f"{prefix}/files/Facturas/{files.MARKER}", 0),
            (f"{prefix}/files/Facturas/marzo.pdf", 300),
            (f"{prefix}/files/a.pdf", 20),
            (f"{prefix}/website/img/abc.png", 7),
        ),
        {"Bucket": "erplora-test-hubs", "Prefix": f"{prefix}/"},
    )
    listing = files.listing(storage, A, "Facturas")
    stubber.assert_no_pending_responses()
    assert tree(listing["folders"]) == [("Facturas", [])]
    assert [(item["name"], item["size"]) for item in listing["files"]] == [("marzo.pdf", 300)]
    assert listing["used_bytes"] == 327


def test_a_store_that_does_not_answer_is_said_so_never_taken_for_empty(s3, monkeypatch):
    storage, stubber = s3
    stubber.add_client_error("list_objects_v2", service_error_code="InternalError", http_status_code=500)
    error = pytest.raises(OperationError, files.listing, storage, A, "").value
    assert (error.status, error.code) == (503, "base.file_store_unavailable")


@pytest.mark.parametrize("failure", [OSError("disk full"), EndpointConnectionError(endpoint_url="https://s3")])
def test_a_write_the_store_refuses_is_said_so(store, monkeypatch, failure):
    def refuse(*args, **kwargs):
        raise failure

    monkeypatch.setattr(store, "save", refuse)
    error = pytest.raises(OperationError, files.upload, store, A, "", "a.pdf", PDF).value
    assert (error.status, error.code) == (503, "base.file_store_unavailable")


def test_the_refusals_are_the_api_s_statuses():
    # The operations hand them on as they are: 422 for a bad name or path, 404 for what is not there, 409 for a clash.
    assert isinstance(pytest.raises(InvalidPayload, files.clean_name, "a/b").value, InvalidPayload)
    assert isinstance(pytest.raises(NotFound, files.listing, InMemoryStorage(), A, "Nadie").value, NotFound)
    storage = InMemoryStorage()
    files.create_folder(storage, A, "", "x")
    assert isinstance(pytest.raises(Conflict, files.create_folder, storage, A, "", "x").value, Conflict)


# ── Every sentence in Spanish too ─────────────────────────────────────────────────────────────────────────────

#: The sentences the refusals of Files say, as written in its code (``gettext("…")`` in ``base/files.py`` and in the
#: Files block of ``base/services.py``); the API and the assistant pass them on to the person, so each one has its
#: Spanish.
_SERVICES = Path(files.__file__).with_name("services.py").read_text().split("── Files (APP-BASE-8) ──", 1)[1]
SENTENCES = sorted(
    set(re.findall(r'gettext\(\s*"((?:[^"\\]|\\.)*)"', Path(files.__file__).read_text() + _SERVICES.split("\n# ── ", 1)[0]))
)


def test_files_says_its_refusals_in_some_words():
    assert len(SENTENCES) >= 10


@pytest.mark.parametrize("sentence", SENTENCES)
def test_every_refusal_of_files_reads_in_spanish(sentence):
    with translation.override("es"):
        assert gettext(sentence) != sentence


def test_a_refusal_reaches_a_spanish_person_in_spanish(store):
    with translation.override("es"):
        message = str(pytest.raises(InvalidPayload, files.upload, store, A, "", "setup.exe", b"MZ").value)
    assert message == "Los programas (.exe) no se pueden guardar en Archivos: podrían dañar a quien los abra."


# ── No ORM: the store only ────────────────────────────────────────────────────────────────────────────────────


def test_files_touches_no_model_nor_database():
    """``base/files.py`` is in ``ORM_EXCEPTIONS`` (tests/test_guardrails.py) for its Storage ``save``/``delete``: it
    keeps no metadata, so it imports no model, no ``django.db`` and no ``live.models``; the ORM stays in the doors."""
    import ast

    tree = ast.parse(Path(files.__file__).read_text())
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    assert not {name for name in imported if name and (name.startswith("django.db") or name.endswith("models"))}
    assert "objects" not in {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
