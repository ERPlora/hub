"""The SKU a product created without one gets: the next number of the catalog's own, from 10000."""

from live.errors import Conflict

from apps.inventory.models import Product
from apps.inventory.schemas.fields import ProductRefIn
from apps.inventory.schemas.products import ProductIn
from apps.inventory.services import skus
from apps.inventory.tests.test_services import TAX, create, general, refused, run

from .conftest import HUB_DB

#: The general tax category every product of these tests takes, created before each test.
__all__ = ["general"]

pytestmark = HUB_DB


def without_sku(name, sku=None, **fields):
    """``inventory.product.create`` as the form sends it with the SKU left empty (or as ``sku`` says)."""
    data = {"name": name, "price": 450, "tax_category_key": TAX, **fields}
    return run("inventory.product.create", ProductIn(**data) if sku is None else ProductIn(sku=sku, **data))


def test_a_product_created_without_sku_gets_the_next_number_from_10000():
    first, second = without_sku("Cheesecake"), without_sku("Flan")

    assert (first.sku, second.sku) == ("10000", "10001")
    assert dict(Product.objects.values_list("name", "sku")) == {"Cheesecake": "10000", "Flan": "10001"}


def test_an_empty_or_blank_sku_is_numbered_the_same():
    assert [without_sku("Cheesecake", sku="").sku, without_sku("Flan", sku="   ").sku] == ["10000", "10001"]


def test_a_typed_sku_is_kept_and_the_numbers_go_on_after_it():
    typed = without_sku("Tart", sku="10041")

    assert (typed.sku, without_sku("Flan").sku) == ("10041", "10042")


def test_a_deleted_product_keeps_its_number_from_being_given_again():
    """So that bringing it back (INVENTORY-F34) never finds its SKU taken by a product numbered after it."""
    gone = without_sku("Cheesecake")
    run("inventory.product.delete", ProductRefIn(id=gone.id))

    assert without_sku("Flan").sku == "10001"


def test_codes_that_are_not_the_catalog_s_own_numbers_do_not_move_the_count():
    """A code with letters, one with a leading zero, a short one and a barcode used as SKU (EAN-13, UPC) are not numbers
    of the catalog's own: the next one is still 10000."""
    for sku in ("CAF-1", "012345", "123", "8410000000005", "036000291452", "1000000000"):
        create(f"Item {sku}", sku)

    assert without_sku("Cheesecake").sku == "10000"


def test_a_number_taken_meanwhile_moves_to_the_following_one(monkeypatch):
    """Another write that took the number between reading it and saving (two people creating at once) does not fail
    the save: the product takes the next number."""
    create("Taken", "10000")
    numbers = iter(["10000"])
    real = skus.next_sku
    monkeypatch.setattr(skus, "next_sku", lambda: next(numbers, None) or real())

    assert without_sku("Cheesecake").sku == "10001"
    assert Product.objects.filter(name="Cheesecake").count() == 1


def test_another_refusal_is_not_hidden_behind_a_new_number(monkeypatch):
    """A taken EAN-13 says so the first time, under its own field: another number would not mend it."""
    create("Water", "WAT-1", ean13="8410000000009")
    given = []
    real = skus.next_sku
    monkeypatch.setattr(skus, "next_sku", lambda: given.append(real()) or given[-1])

    exc = refused(Conflict, lambda: without_sku("Cheesecake", ean13="8410000000009"))

    assert (exc.code, given) == ("inventory.ean13_taken", ["10000"])
    assert not Product.objects.filter(name="Cheesecake").exists()


def test_a_number_that_keeps_being_taken_ends_in_the_refusal_of_a_taken_sku(monkeypatch):
    """Bounded: a number that keeps being taken refuses as a typed one would, never loops."""
    create("Taken", "10000")
    monkeypatch.setattr(skus, "next_sku", lambda: "10000")

    assert refused(Conflict, lambda: without_sku("Cheesecake")).code == "inventory.sku_taken"
