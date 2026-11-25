"""A hub's index, kept between operations: one walk of its files for a batch, never a wrong listing
(``base.files.index``).
"""

from django.core.files.base import ContentFile

from base import files
from base.storage import hub_prefix
from base.tests.test_files import A, B, PDF, names, store, tree

__all__ = ["store"]


def walks(monkeypatch):
    """The prefixes ``base.files.store.scan`` walks key by key, for the index and for what the apps keep."""
    seen: list[str] = []
    real = files.store.scan
    for walker in (files.index, files.space):
        monkeypatch.setattr(walker, "scan", lambda store, prefix: seen.append(prefix) or real(store, prefix))
    return seen


def test_a_batch_of_uploads_and_the_listing_after_each_walk_the_business_files_at_most_once(store, monkeypatch):
    # Each upload needs the plan's space and the live listing runs again after each one: without the kept index, a
    # batch of N uploads would walk the hub's whole prefix 2N times.
    seen = walks(monkeypatch)
    for number in range(4):
        files.create.upload(store, A, "", f"factura-{number}.pdf", PDF, limit_bytes=1024**3)
        listing = files.listing.listing(store, A, "")
    assert names(listing) == [f"factura-{number}.pdf" for number in range(4)]
    assert listing["used_bytes"] == 4 * len(PDF)
    assert seen.count(f"{hub_prefix(A)}/{files.names.ROOT}") <= 1
    assert hub_prefix(A) not in seen


def test_listing_a_folder_never_walks_the_others(store, monkeypatch):
    files.create.create_folder(store, A, "", "Facturas")
    files.create.create_folder(store, A, "", "Contratos")
    files.create.upload(store, A, "Contratos", "alquiler.pdf", PDF)
    files.listing.listing(store, A, "")
    seen = walks(monkeypatch)
    assert names(files.listing.listing(store, A, "Facturas")) == []
    assert [prefix for prefix in seen if f"/{files.names.ROOT}" in prefix or prefix == hub_prefix(A)] == []


def test_the_tree_and_the_space_follow_every_write_of_files_and_what_the_apps_keep(store):
    assert files.listing.listing(store, A, "")["used_bytes"] == 0  # kept from here on
    files.create.create_folder(store, A, "", "Facturas")
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("Facturas", [])]
    files.create.upload(store, A, "Facturas", "marzo.pdf", PDF)
    assert files.listing.listing(store, A, "Facturas")["used_bytes"] == len(PDF)
    store.save(f"{hub_prefix(A)}/website/img/logo.png", ContentFile(b"1234567"))  # an app's own file, at once
    assert files.space.used_bytes(store, A) == len(PDF) + 7
    files.relocate.rename(store, A, "Facturas", "Facturación")
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("Facturación", [])]
    files.create.create_folder(store, A, "", "2026")
    files.relocate.move(store, A, "Facturación", "2026")
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("2026", [("2026/Facturación", [])])]
    files.delete.delete(store, A, "2026/Facturación/marzo.pdf")
    assert files.listing.listing(store, A, "2026/Facturación")["used_bytes"] == 7
    files.delete.delete(store, A, "2026")
    listing = files.listing.listing(store, A, "")
    assert (tree(listing["folders"]), listing["used_bytes"]) == ([], 7)
    assert files.listing.listing(store, B, "")["used_bytes"] == 0  # each hub its own


def test_a_walk_a_write_came_during_is_never_kept(store, monkeypatch):
    # Another device makes a folder while this listing walks the files: the walk did not see it and is not kept, so
    # the next listing shows the folder (each write of Files moves the index's generation).
    real = files.store.scan

    def another_device_writes(walked_store, prefix):
        found = real(walked_store, prefix)
        files.create.create_folder(store, A, "", "Nueva")
        return found

    monkeypatch.setattr(files.index, "scan", another_device_writes)
    assert tree(files.listing.listing(store, A, "")["folders"]) == []
    monkeypatch.setattr(files.index, "scan", real)
    assert tree(files.listing.listing(store, A, "")["folders"]) == [("Nueva", [])]


def test_a_cache_that_does_not_answer_costs_a_walk_never_a_wrong_listing(store, monkeypatch):
    from django.core.cache import cache

    def down(*args, **kwargs):
        raise ConnectionError("valkey away")

    for method in ("get_many", "set_many", "add", "incr", "delete_many", "get"):
        monkeypatch.setattr(cache, method, down)
    files.create.upload(store, A, "", "a.pdf", PDF, limit_bytes=1024**3)
    listing = files.listing.listing(store, A, "")
    assert (names(listing), listing["used_bytes"]) == (["a.pdf"], len(PDF))


def test_each_hub_keeps_its_own_index_never_another_s(store):
    # The index is kept per hub in the cache: with one key for every hub, B would list A's folders and count A's
    # bytes as its own space. Judged while A still has files and folders.
    files.create.create_folder(store, A, "", "Facturas")
    files.create.upload(store, A, "Facturas", "marzo.pdf", PDF)
    a = files.listing.listing(store, A, "")
    assert (tree(a["folders"]), a["used_bytes"]) == ([("Facturas", [])], len(PDF))  # kept from here on
    b = files.listing.listing(store, B, "")
    assert (tree(b["folders"]), b["used_bytes"]) == ([], 0)
    files.create.upload(store, B, "", "b.pdf", PDF)
    assert files.listing.listing(store, B, "")["used_bytes"] == len(PDF)
    assert files.listing.listing(store, A, "")["used_bytes"] == len(PDF)


def test_a_write_that_comes_while_the_walk_is_being_kept_is_never_lost(store, monkeypatch):
    # A write of Files landing between reading the index's generation and keeping the walk (one cache round trip)
    # must not leave the kept index without it until it expires (10 minutes): a folder made on another device would
    # say «no longer exists» and an upload's bytes would be missing from the space.
    from django.core.cache import cache

    real_set_many = cache.set_many

    def another_device_writes_then_the_walk_is_kept(mapping, timeout):
        monkeypatch.setattr(cache, "set_many", real_set_many)
        files.create.create_folder(store, A, "", "Nueva")
        files.create.upload(store, A, "Nueva", "a.pdf", PDF)
        return real_set_many(mapping, timeout)

    monkeypatch.setattr(cache, "set_many", another_device_writes_then_the_walk_is_kept)
    files.listing.listing(store, A, "")
    listing = files.listing.listing(store, A, "")
    assert (tree(listing["folders"]), listing["used_bytes"]) == ([("Nueva", [])], len(PDF))
    assert names(files.listing.listing(store, A, "Nueva")) == ["a.pdf"]
