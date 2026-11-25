"""A tax category a business creates (TAX-F02)."""

from live.errors import Conflict
from live.operations import get

from apps.tax import events
from apps.tax.models import TaxCategory
from apps.tax.schemas.categories import CategoryIn
from apps.tax.services.categories import create_category

from .conftest import HUB_DB, A, category, outbox, refused, run

# tax.category.create (TAX-F02)


@HUB_DB
def test_create_an_own_category(no_seed):
    assert get("tax.category.create") is create_category
    created = run(
        "tax.category.create",
        CategoryIn(key="product.books", name="Libros", description="Papel"),
    )
    books = TaxCategory.objects.get()
    assert created.model_dump() == {
        "id": books.id,
        "key": "product.books",
        "name": "Libros",
        "description": "Papel",
        "display_name": "Libros",
        "display_description": "Papel",
        "is_system": False,
        "is_active": True,
    }
    assert outbox() == [
        (events.CATEGORY_CREATED, A.key, {"id": str(books.id), "key": "product.books"})
    ]


@HUB_DB
def test_a_category_may_be_marked_as_system(no_seed):
    assert (
        run(
            "tax.category.create", CategoryIn(key="product.x", name="X", is_system=True)
        ).is_system
        is True
    )


@HUB_DB
def test_a_repeated_key_is_refused_on_its_field(no_seed):
    category("product.books")
    error = refused(
        Conflict,
        lambda: run(
            "tax.category.create", CategoryIn(key="product.books", name="Other")
        ),
    )
    assert (error.status, error.code) == (409, "tax.category_exists")
    assert error.fields == {"key": "There is already a tax category with that key."}
    assert TaxCategory.objects.count() == 1 and outbox() == []
