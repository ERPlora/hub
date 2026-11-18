"""An object loaded from one hub's database, used inside another hub's context.

Django sends a loaded object's own save, delete and refresh, and every relation read or written from it, to the
database the object came from (the router's ``instance`` hint). Inside another hub's context that is the first hub's
database, whatever the context says: the ``TenantRouter`` refuses it (``HubContextMismatch``) before any SQL, so B's
work never reads nor writes A's rows. Inside its own hub's context, on that hub's alias or on its migrator's alias (one
database), and without any context (a migration's ``RunPython``), the object is used as always.

Two hubs with a database of their own (``hub_a``, ``hub_b``), every statement watched by alias.
"""

import pytest
from django.db import connections as django_connections

from apps.demo.models import Item, ItemLine
from base.tenancy import connections, context
from base.tenancy.context import HubContextMismatch
from base.tenancy.router import TenantRouter
from base.tenancy.tests import hubs

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES)]


@pytest.fixture
def item_of_a(hub_a) -> Item:
    """An item of A with one line, loaded from A's database (its lines not cached)."""
    with context.use_hub(hub_a):
        item = Item.objects.create(name="Of A")
        ItemLine.objects.create(item=item, text="Line of A", qty=1, position=1)
        return Item.objects.get(pk=item.pk)


@pytest.fixture
def line_of_a(hub_a, item_of_a) -> ItemLine:
    """The line of :func:`item_of_a`, loaded from A's database (its item not cached)."""
    with context.use_hub(hub_a):
        return ItemLine.objects.get(item_id=item_of_a.pk)


def rows(hub) -> tuple[list[str], list[str]]:
    """The names of ``hub``'s items and the texts of its lines, read inside its own context."""
    with context.use_hub(hub):
        return (
            sorted(Item.objects.values_list("name", flat=True)),
            sorted(ItemLine.objects.values_list("text", flat=True)),
        )


def inside(hub, action):
    """What ``action`` returns inside ``hub``'s context, the refusal it met if any, and every statement by alias."""
    with context.use_hub(hub), hubs.watched() as sent:
        try:
            return action(), None, sent
        except HubContextMismatch as refused:
            return None, refused, sent


# ── Writes ──────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_saving_it_inside_another_hub_is_refused_and_its_own_hub_keeps_its_row(hub_a, hub_b, item_of_a):
    def rename():
        item_of_a.name = "Renamed inside B"
        item_of_a.save()

    _, refused, sent = inside(hub_b, rename)

    assert rows(hub_a) == (["Of A"], ["Line of A"])
    assert rows(hub_b) == ([], [])
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_deleting_it_inside_another_hub_is_refused_and_its_own_hub_keeps_its_rows(hub_a, hub_b, item_of_a):
    _, refused, sent = inside(hub_b, item_of_a.delete)

    assert rows(hub_a) == (["Of A"], ["Line of A"])
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_adding_through_its_relation_inside_another_hub_is_refused(hub_a, hub_b, item_of_a):
    _, refused, sent = inside(hub_b, lambda: item_of_a.lines.create(text="Added inside B", qty=1, position=2))

    assert rows(hub_a) == (["Of A"], ["Line of A"])
    assert rows(hub_b) == ([], [])
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_a_new_object_pointing_to_it_inside_another_hub_is_refused(hub_a, hub_b, item_of_a):
    def add():
        ItemLine(item=item_of_a, text="Added inside B", qty=1, position=2).save()

    _, refused, sent = inside(hub_b, add)

    assert rows(hub_a) == (["Of A"], ["Line of A"])
    assert rows(hub_b) == ([], [])
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


# ── Reads ───────────────────────────────────────────────────────────────────────────────────────────────────────────


def test_following_its_foreign_key_inside_another_hub_is_refused(hub_b, line_of_a):
    read, refused, sent = inside(hub_b, lambda: line_of_a.item)

    assert read is None
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_reading_its_reverse_relation_inside_another_hub_is_refused(hub_b, item_of_a):
    read, refused, sent = inside(hub_b, lambda: list(item_of_a.lines.all()))

    assert read is None
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_refreshing_it_inside_another_hub_is_refused(hub_b, item_of_a):
    item_of_a.name = "Not saved"

    _, refused, sent = inside(hub_b, item_of_a.refresh_from_db)

    assert item_of_a.name == "Not saved"
    assert hubs.HUB_A_ALIAS not in sent
    assert isinstance(refused, HubContextMismatch)


def test_the_refusal_names_both_databases(hub_b, item_of_a):
    _, refused, _ = inside(hub_b, item_of_a.save)

    assert hubs.HUB_A_ALIAS in str(refused)
    assert hubs.HUB_B_ALIAS in str(refused)


# ── What is kept ────────────────────────────────────────────────────────────────────────────────────────────────────


def test_inside_its_own_hub_it_is_read_saved_and_deleted_as_always(hub_a, item_of_a, line_of_a):
    def use():
        item_of_a.name = "Renamed in A"
        item_of_a.save()
        item_of_a.refresh_from_db()
        texts = [line.text for line in item_of_a.lines.all()]
        followed = line_of_a.item.name
        line_of_a.delete()
        return texts, followed

    read, refused, _ = inside(hub_a, use)

    assert refused is None
    assert read == (["Line of A"], "Renamed in A")
    assert rows(hub_a) == (["Renamed in A"], [])


def test_on_the_migrators_alias_of_its_own_hub_it_goes_to_that_alias(hub_a, item_of_a):
    """A migration's ``RunPython`` inside the hub's context: its objects are on ``<db_name>__ddl``, the same database."""
    router = TenantRouter()
    ddl = connections.register_ddl_alias(hub_a.db_name)
    item_of_a._state.db = ddl

    with context.use_hub(hub_a):
        assert router.db_for_read(ItemLine, instance=item_of_a) == ddl
        assert router.db_for_write(Item, instance=item_of_a) == ddl


def test_a_migrators_alias_names_its_database_even_once_forgotten(hub_a, hub_b, item_of_a):
    """The migrator forgets its alias from the settings when it is done, and another thread may forget it while this
    one still works on it: ``<db_name>__ddl`` still says which database it is."""
    router = TenantRouter()
    assert f"{hub_a.db_name}__ddl" not in django_connections.settings

    with context.use_hub(hub_a):
        item_of_a._state.db = f"{hub_a.db_name}__ddl"
        assert router.db_for_write(Item, instance=item_of_a) == f"{hub_a.db_name}__ddl"

        item_of_a._state.db = f"{hub_b.db_name}__ddl"
        with pytest.raises(HubContextMismatch):
            router.db_for_write(Item, instance=item_of_a)


def test_without_a_context_it_goes_to_the_database_it_came_from(item_of_a):
    """A migration's ``RunPython`` runs with no hub's context: the object's own database decides."""
    item_of_a.name = "Not saved"

    with hubs.watched() as sent:
        item_of_a.refresh_from_db()

    assert item_of_a.name == "Of A"
    assert hubs.HUB_A_ALIAS in sent
