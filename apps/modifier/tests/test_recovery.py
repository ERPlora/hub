"""What Modifiers gives back from a separate copy of the business (BASE-F114, MODIFIER-F10).

The copy is no business, so it has no alias and the ORM never reaches it: the platform reads it through a direct,
read-only connection, and Modifiers answers with its own SQL over its models' names. Its groups hung from a product:
each one of a live product that the business no longer has is hung again by ``modifier.link.attach``, the group
sheet's own, unless the business hung that group from that product again. Modifiers goes after Inventory (its
``requires``), so a deleted product is back, the same, before its groups are hung.

Then, end to end on real databases (``hubs.CopiedHubs``): the business's own and its copy, a clone of it.
"""

import uuid

import pytest
from django.apps import apps
from django.db import connection
from live.models import OutboxEvent

from apps.inventory.models import Product
from apps.inventory.tests.test_recovery import (
    CATEGORIES,
    LINKS,
    PRODUCTS,
    a_tax_key,
    gone_altogether,
    made_by_a_recovery,
)
from apps.modifier import queries
from apps.modifier.models import ModifierLink
from base.recovery import actor_of
from base.tenancy.context import use_hub
from base.tenancy.tests.test_recovery import Recoveries, fields_held_since, fresh, run, run_in

from .conftest import make_category, make_product
from .conftest import run as run_here


def direct():
    """The raw connection of the tests' database, as the platform's direct one reads the copy."""
    connection.ensure_connection()
    return connection.connection


def a_group(name: str):
    return run_here("modifier.group.create", {"name": name})


def hang(group, *, product=None, category=None) -> ModifierLink:
    target = {"product_id": str(product.id)} if product else {"category_id": str(category.id)}
    return ModifierLink.objects.get(pk=run_here("modifier.link.attach", {"group_id": str(group.id), **target}).id)


@pytest.mark.django_db
def test_the_copy_gives_each_group_hung_from_a_live_product_with_what_its_attach_takes():
    burger, fries = make_product("Burger", "BUR"), make_product("Fries", "FRI")
    sauces, extras = a_group("Sauces"), a_group("Extras")
    on_burger = hang(sauces, product=burger)
    extra_burger = hang(extras, product=burger)
    on_fries = hang(sauces, product=fries)
    # A category's groups are not a product's: none is read.
    hang(extras, category=make_category("Mains"))
    # Nor a deleted product's, whose groups its deletion lets go of (before the relay's tick, still there).
    old = make_product("Old", "OLD")
    hang(sauces, product=old)
    run_here("inventory.product.delete", {"id": str(old.id)})

    read = queries.links_in_copy(direct())

    # With each product's SKU there, the article's identity, to find the one made again if the business lost it.
    assert read == [
        {"id": on_burger.id, "group_id": sauces.id, "product_id": burger.id, "sku": "BUR"},
        {"id": extra_burger.id, "group_id": extras.id, "product_id": burger.id, "sku": "BUR"},
        {"id": on_fries.id, "group_id": sauces.id, "product_id": fries.id, "sku": "FRI"},
    ]


@pytest.mark.django_db
def test_a_copy_without_the_apps_table_gives_nothing():
    with connection.cursor() as cursor:
        # Undone with the test's transaction.
        cursor.execute("DROP TABLE modifier_modifierlink CASCADE")

    assert queries.links_in_copy(direct()) == []


def a_link_of_the_copy(group, product) -> dict:
    return {"id": uuid.uuid7(), "group_id": group.id, "product_id": product.id, "sku": product.sku}


def a_link_of_a_product_gone(group, sku: str, product_id=None) -> dict:
    """A link of the copy whose product the business no longer holds at all: only its SKU says which article it was."""
    return {"id": uuid.uuid7(), "group_id": group.id, "product_id": product_id or uuid.uuid7(), "sku": sku}


@pytest.mark.django_db
def test_lacking_is_a_group_the_business_no_longer_hangs_from_that_product():
    burger, fries = make_product("Burger", "BUR"), make_product("Fries", "FRI")
    sauces, extras, sizes = a_group("Sauces"), a_group("Extras"), a_group("Sizes")
    # Still in the business: it is the business's, nothing lacks.
    held = hang(sizes, product=fries)
    still = a_link_of_the_copy(sizes, fries) | {"id": held.id}
    # Hung again by the business since, under another id: the business's stays, never a second one.
    hang(sauces, product=burger)
    hung_again = a_link_of_the_copy(sauces, burger)
    # Lacking: the same product with another group, and the same group on another product.
    other_group = a_link_of_the_copy(extras, burger)
    other_product = a_link_of_the_copy(sauces, fries)

    lacking = queries.links_not_in_business([still, hung_again, other_group, other_product])

    # As the group sheet's attach takes each, with its id in the copy: the group and the product.
    assert lacking == [
        {"id": other_group["id"], "group_id": extras.id, "product_id": burger.id},
        {"id": other_product["id"], "group_id": sauces.id, "product_id": fries.id},
    ]


@pytest.mark.django_db
def test_a_product_gone_gets_its_groups_on_the_one_a_recovery_made_again_with_its_sku():
    sauces, extras = a_group("Sauces"), a_group("Extras")
    burger = made_by_a_recovery("Burger", "BUR")
    # Hung again by the business on the one made again, after the recovery made it: the business's stays.
    hang(sauces, product=burger)
    hung_again = a_link_of_a_product_gone(sauces, "BUR")
    lacking_one = a_link_of_a_product_gone(extras, "BUR", hung_again["product_id"])
    # Made again by hand with its SKU: the business's own, set up as it chose; it keeps the copy's product, which the
    # attach refuses as not found: not created, and why.
    make_product("Fries", "FRI")
    by_hand = a_link_of_a_product_gone(sauces, "FRI")

    lacking = queries.links_not_in_business([hung_again, lacking_one, by_hand])

    assert lacking == [
        {"id": lacking_one["id"], "group_id": extras.id, "product_id": burger.id},
        {"id": by_hand["id"], "group_id": sauces.id, "product_id": by_hand["product_id"]},
    ]


def test_with_nothing_read_nothing_is_lacking():
    assert queries.links_not_in_business([]) == []


def test_the_app_declares_its_groups_of_products_hung_again_by_the_group_sheets_attach():
    [links] = apps.get_app_config("modifier").recoverable_from_copy()

    assert (links.read, links.missing, links.create, links.deleted, links.restore) == (
        queries.links_in_copy,
        queries.links_not_in_business,
        "modifier.link.attach",
        None,
        "",
    )
    assert (str(links.label), links.reads_since) == ("Modifier groups of products", "0001_initial")
    # A copy that far back holds what the read takes: the link's columns, and of its product, those of Inventory's
    # migration that one depends on.
    assert {"id", "group", "product"} <= fields_held_since("modifier", "modifierlink", links.reads_since)
    assert {"sku", "is_deleted"} <= fields_held_since("inventory", "product", "0001_initial")


# ── End to end: the business's own database and its copy ────────────────────────────────────────────────────────────


@pytest.fixture
def recoveries(django_db_blocker, hub_databases):
    with django_db_blocker.unblock():
        made = Recoveries(hub_databases.template)
        yield made
        made.clean()


GROUPS = {
    "app": "modifier", "label": "Modifier groups of products", "restored": 0, "created": 0, "not_created": 0,
    "reasons": [], "refused": "",
}


def said(row) -> tuple[str, list[dict]]:
    """``row``'s status and what each thing it gave back gave, by the keys these tests read."""
    keys = ("app", "label", "restored", "created", "not_created", "reasons", "refused")
    row = fresh(row)
    return row.status, [{key: result[key] for key in keys} for result in row.results]


def hung(hub) -> list[tuple]:
    """The business's groups hung from a product: group name and product id, by group name."""
    with use_hub(hub):
        return list(
            ModifierLink.objects.filter(product__isnull=False)
            .order_by("group__name")
            .values_list("group__name", "product_id")
        )


def attached(hub) -> int:
    with use_hub(hub):
        return OutboxEvent.objects.filter(name="modifier.link.attached").count()


@pytest.mark.usefixtures("no_test_fallback")
class TestGroupsComeBack:
    def a_business(self, recoveries, every_app_on):
        """A business with a burger that asks for «Sauces» and «Extras», by their screens' operations: the hub, the
        burger's id and the groups' ids."""
        hub, _ = recoveries.business(every_app_on)
        burger = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                        tax_category_key=a_tax_key(hub)).id
        groups = {}
        for name in ("Sauces", "Extras"):
            groups[name] = run_in(hub, "modifier.group.create", name=name).id
            run_in(hub, "modifier.link.attach", group_id=groups[name], product_id=burger)
        return hub, burger, groups

    def deleted(self, hub, product) -> None:
        """``product`` deleted in the business, and its groups let go as the relay hands its deletion to Modifiers."""
        run_in(hub, "inventory.product.delete", id=product)
        run_in(hub, "modifier.link.drop_product", id=product)
        assert hung(hub) == []

    def test_a_deleted_product_comes_back_asking_for_its_groups(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        before = attached(hub)
        row = recoveries.ask(copy, "modifier", "inventory")

        assert run() == 1

        # Inventory first, whatever the order asked: the product is back, the same, before its groups are hung.
        assert said(row) == ("done", [CATEGORIES, PRODUCTS | {"restored": 1}, LINKS, GROUPS | {"created": 2}])
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]
        with use_hub(hub):
            assert set(ModifierLink.objects.values_list("created_by", flat=True)) == {actor_of(row.pk)}
        assert attached(hub) == before + 2
        # Asked again, nothing is hung twice.
        again = recoveries.ask(copy, "inventory", "modifier")
        assert run() == 1
        assert said(again) == ("done", [CATEGORIES, PRODUCTS, LINKS, GROUPS])
        assert len(hung(hub)) == 2

    def test_a_product_gone_altogether_comes_back_as_a_new_one_asking_for_its_groups(self, recoveries, every_app_on):
        hub, burger, _ = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        row = recoveries.ask(copy, "modifier", "inventory")

        assert run() == 1

        assert said(row) == ("done", [CATEGORIES, PRODUCTS | {"created": 1}, LINKS, GROUPS | {"created": 2}])
        with use_hub(hub):
            [made] = Product.objects.filter(sku="BUR").values_list("pk", flat=True)
        assert made != burger
        assert hung(hub) == [("Extras", made), ("Sauces", made)]
        # Asked again, nothing is hung twice: its groups are in their place on the one made again.
        again = recoveries.ask(copy, "inventory", "modifier")
        assert run() == 1
        assert said(again) == ("done", [CATEGORIES, PRODUCTS, LINKS, GROUPS])
        assert len(hung(hub)) == 2

    def test_a_product_gone_the_business_made_again_by_hand_keeps_its_own_groups(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        gone_altogether(hub, burger)
        # Made again by hand with its SKU, the business hung only «Extras» from it.
        made = run_in(hub, "inventory.product.create", name="Burger", sku="BUR", price=900,
                      tax_category_key=a_tax_key(hub)).id
        run_in(hub, "modifier.link.attach", group_id=groups["Extras"], product_id=made)
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        status, results = said(row)
        assert (status, results[1]["created"], results[-1]["created"], results[-1]["not_created"]) == ("done", 0, 0, 2)
        assert [reason["reason"].split(":")[0] for reason in results[-1]["reasons"]] == ["not_found", "not_found"]
        assert hung(hub) == [("Extras", made)]

    def test_a_group_the_business_hung_again_stays_as_it_is(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        recoveries.ask(copy, "inventory")
        assert run() == 1
        # The product back without its groups, the business hung «Sauces» again by hand.
        run_in(hub, "modifier.link.attach", group_id=groups["Sauces"], product_id=burger)
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        assert said(row) == ("done", [GROUPS | {"created": 1}])
        assert hung(hub) == [("Extras", burger), ("Sauces", burger)]
        with use_hub(hub):
            assert ModifierLink.objects.get(group_id=groups["Sauces"]).created_by == "system"

    def test_a_group_that_cannot_hang_now_does_not_come_back_and_says_why(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        self.deleted(hub, burger)
        # Without Products asked, the burger stays deleted: as the group sheet, nothing is hung from it.
        row = recoveries.ask(copy, "modifier")

        assert run() == 1

        status, [result] = said(row)
        assert (status, result["created"], result["not_created"], result["refused"]) == ("done", 0, 2, "")
        assert [reason["reason"].split(":")[0] for reason in result["reasons"]] == ["not_found", "not_found"]
        assert hung(hub) == []

    def test_a_group_the_business_deleted_since_does_not_come_back_and_says_which(self, recoveries, every_app_on):
        hub, burger, groups = self.a_business(recoveries, every_app_on)
        copy = recoveries.copy_of(hub)
        with use_hub(hub):
            sauces_link = ModifierLink.objects.get(group_id=groups["Sauces"]).id
        self.deleted(hub, burger)
        run_in(hub, "modifier.group.delete", id=groups["Sauces"])
        row = recoveries.ask(copy, "inventory", "modifier")

        assert run() == 1

        status, results = said(row)
        assert (status, results[-1]["created"], results[-1]["not_created"]) == ("done", 1, 1)
        assert [(reason["id"], reason["reason"].split(":")[0]) for reason in results[-1]["reasons"]] == [
            (str(sauces_link), "not_found")
        ]
        assert hung(hub) == [("Extras", burger)]
