"""The business's files (``base.files``): what the Files screen keeps in the hub file store.

They live under the hub's prefix, in its own folder (``hub-<hex>/files/…``), apart from what the modules keep
(``website/img/``, published by ``/p/media/``): a file of the business is never public. A name is one segment and a
path a chain of them; nothing that could climb out of the folder (``..``, a backslash, a leading ``/``, a NUL)
reaches the store, and one hub never lists, reads, moves nor deletes another's. Writing never overwrites in silence:
a second «a.pdf» is «a (1).pdf» (Google Drive, Dropbox).
"""

import datetime as dt
import re
import uuid
from pathlib import Path

import boto3
import pytest
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
    store.save(f"{hub_prefix(hub)}/{files.names.ROOT}/{path}", ContentFile(content))


def names(listing):
    return [item["name"] for item in listing["files"]]


def tree(nodes):
    return [(node["path"], tree(node["children"])) for node in nodes]


def code_of(call, *args, **kwargs):
    with pytest.raises(OperationError) as raised:
        call(*args, **kwargs)
    return raised.value.code


# ── One hub never reaches another's (A ≠ B) ──────────────────────────────────────────────────────────────────


def test_a_hub_never_lists_another_s_files(store):
    put(store, B, "Secreto/nominas.pdf")
    listing = files.listing.listing(store, A, "")
    assert (listing["folders"], listing["files"]) == ([], [])
    assert code_of(files.listing.listing, store, A, "Secreto") == "base.file_folder_missing"


def test_what_a_hub_writes_lands_under_its_own_prefix_only(store):
    files.create.upload(store, A, "", "a.pdf", PDF)
    files.create.create_folder(store, A, "", "Carpeta")
    assert store.exists(f"{hub_prefix(A)}/files/a.pdf")
    assert store.exists(f"{hub_prefix(A)}/files/Carpeta/{files.names.MARKER}")
    assert store.listdir("")[0] == [hub_prefix(A)]


@pytest.mark.parametrize(
    "call",
    [
        lambda store: files.read.describe(store, A, "Secreto/nominas.pdf"),
        lambda store: files.relocate.rename(store, A, "Secreto/nominas.pdf", "x.pdf"),
        lambda store: files.relocate.move(store, A, "Secreto/nominas.pdf", ""),
        lambda store: files.delete.delete(store, A, "Secreto/nominas.pdf"),
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
    for call in (files.read.describe, files.delete.delete):
        assert code_of(call, store, A, climb) == "base.file_invalid_path"
    assert code_of(files.create.upload, store, A, climb, "x.pdf", PDF) == "base.file_invalid_path"
    assert store.exists(f"{hub_prefix(B)}/files/Secreto/nominas.pdf")


# ── On disk (local development) ──────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def disk(tmp_path):
    return FileSystemStorage(location=tmp_path)


def test_on_disk_a_folder_moved_or_deleted_leaves_no_empty_directory_behind(disk, tmp_path):
    put(disk, A, "Facturas/2026/marzo.pdf")
    files.relocate.rename(disk, A, "Facturas", "Facturación")
    root = tmp_path / hub_prefix(A) / files.names.ROOT
    assert sorted(path.name for path in root.iterdir()) == ["Facturación"]
    files.delete.delete(disk, A, "Facturación")
    assert list(root.iterdir()) == []


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


def folder_page(*pairs, folders=()):
    """A ``ListObjectsV2`` page with ``Delimiter``: the keys right in the folder and its sub-folders' prefixes."""
    return {**objects(*pairs), "CommonPrefixes": [{"Prefix": prefix} for prefix in folders]}


def test_on_s3_a_listing_reads_the_open_folder_alone_and_walks_the_files_once_for_the_tree_and_the_space(s3):
    # Walking the hub's whole prefix on every listing would cost a request per thousand keys for the tree and the
    # space. The tree of folders and what the business's files take are kept (``base.files`` index) and the open
    # folder is read alone (``Delimiter``); what the apps keep is added at once, so the space stays exact for the
    # plan's limit.
    storage, stubber = s3
    prefix, bucket = hub_prefix(A), "erplora-test-hubs"
    walk_files = {"Bucket": bucket, "Prefix": f"{prefix}/files/"}
    read_folder = {"Bucket": bucket, "Prefix": f"{prefix}/files/Facturas/", "Delimiter": "/"}
    read_hub = {"Bucket": bucket, "Prefix": f"{prefix}/", "Delimiter": "/"}
    walk_website = {"Bucket": bucket, "Prefix": f"{prefix}/website/"}
    folder = folder_page((f"{prefix}/files/Facturas/{files.names.MARKER}", 0), (f"{prefix}/files/Facturas/marzo.pdf", 300))
    hub = folder_page(folders=[f"{prefix}/files/", f"{prefix}/website/"])
    website = objects((f"{prefix}/website/img/abc.png", 7))
    # The first listing walks the business's files once: the tree and what they take.
    stubber.add_response(
        "list_objects_v2",
        objects(
            (f"{prefix}/files/Facturas/{files.names.MARKER}", 0),
            (f"{prefix}/files/Facturas/marzo.pdf", 300),
            (f"{prefix}/files/a.pdf", 20),
        ),
        walk_files,
    )
    for _listing in range(2):  # then each listing reads the open folder and what the apps keep, never the rest
        stubber.add_response("list_objects_v2", folder, read_folder)
        stubber.add_response("list_objects_v2", hub, read_hub)
        stubber.add_response("list_objects_v2", website, walk_website)
    for _listing in range(2):
        listing = files.listing.listing(storage, A, "Facturas")
        assert tree(listing["folders"]) == [("Facturas", [])]
        assert [(item["name"], item["size"]) for item in listing["files"]] == [("marzo.pdf", 300)]
        assert listing["used_bytes"] == 327
    stubber.assert_no_pending_responses()


def test_the_refusals_are_the_api_s_statuses():
    # The operations hand them on as they are: 422 for a bad name or path, 404 for what is not there, 409 for a clash.
    assert isinstance(pytest.raises(InvalidPayload, files.names.clean_name, "a/b").value, InvalidPayload)
    assert isinstance(pytest.raises(NotFound, files.listing.listing, InMemoryStorage(), A, "Nadie").value, NotFound)
    storage = InMemoryStorage()
    files.create.create_folder(storage, A, "", "x")
    assert isinstance(pytest.raises(Conflict, files.create.create_folder, storage, A, "", "x").value, Conflict)


# ── Every sentence in Spanish too ─────────────────────────────────────────────────────────────────────────────

#: The modules of Files, ``base/files/``.
SOURCES = sorted(Path(files.__file__).parent.glob("*.py"))
#: The sentences the refusals of Files say, as written in its code (``gettext("…")`` in ``base/files/`` and in
#: ``base/services/files.py``); the API and the assistant pass them on to the person, so each one has its Spanish.
_SERVICES = (Path(files.__file__).parent.parent / "services" / "files.py").read_text()
_CODE = "".join(path.read_text() for path in SOURCES) + _SERVICES
SENTENCES = sorted(set(re.findall(r'gettext\(\s*"((?:[^"\\]|\\.)*)"', _CODE)))


def test_files_says_its_refusals_in_some_words():
    assert len(SENTENCES) >= 10


@pytest.mark.parametrize("sentence", SENTENCES)
def test_every_refusal_of_files_reads_in_spanish(sentence):
    with translation.override("es"):
        assert gettext(sentence) != sentence


def test_a_refusal_reaches_a_spanish_person_in_spanish(store):
    with translation.override("es"):
        message = str(pytest.raises(InvalidPayload, files.create.upload, store, A, "", "setup.exe", b"MZ").value)
    assert message == "Los programas (.exe) no se pueden guardar en Archivos: podrían dañar a quien los abra."


# ── No ORM: the store only ────────────────────────────────────────────────────────────────────────────────────


def test_files_touches_no_model_nor_database():
    """The modules of ``base/files/`` that write are in ``ORM_EXCEPTIONS`` (tests/test_guardrails.py) for their Storage
    ``save``/``delete``: Files keeps no metadata, so it imports no model, no ``django.db`` and no ``live.models``; the ORM
    stays in the doors."""
    import ast

    tree = ast.Module(body=[node for path in SOURCES for node in ast.parse(path.read_text()).body], type_ignores=[])
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    assert not {name for name in imported if name and (name.startswith("django.db") or name.endswith("models"))}
    assert "objects" not in {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
