"""Another name of a tax category, learned from a person or an import (TAX-F14)."""

from live.errors import Conflict, InvalidPayload
from live.operations import get

from apps.tax import events
from apps.tax.models import TaxAlias
from apps.tax.schemas.aliases import AliasIn
from apps.tax.services.aliases import create_alias

from .conftest import HUB_DB, A, category, outbox, refused, run

# tax.alias.create (TAX-F14)


@HUB_DB
def test_create_an_alias_naming_the_category_by_voice(no_seed):
    assert get("tax.alias.create") is create_alias
    food = category("restaurant.food", "Restaurant — food", system=True)
    created = run(
        "tax.alias.create",
        AliasIn(alias="  Comida  Casera ", tax_category_key="Restauración — comida"),
    )
    alias = TaxAlias.objects.get()
    assert (alias.alias, alias.category, alias.source, alias.is_active) == (
        "comida casera",
        food,
        "learned",
        True,
    )
    assert (created.alias, created.tax_category_key, created.source) == (
        "comida casera",
        "restaurant.food",
        "learned",
    )
    assert outbox() == [
        (
            events.ALIAS_CREATED,
            A.key,
            {
                "id": str(alias.id),
                "alias": "comida casera",
                "tax_category_key": "restaurant.food",
            },
        )
    ]


@HUB_DB
def test_a_repeated_alias_is_refused_on_its_field(no_seed):
    food = category("restaurant.food")
    TaxAlias.objects.create(alias="beer", category=food)
    error = refused(
        Conflict,
        lambda: run(
            "tax.alias.create",
            AliasIn(alias="BEER", tax_category_key="restaurant.food"),
        ),
    )
    assert (error.code, error.fields) == (
        "tax.alias_exists",
        {"alias": "That alias already exists."},
    )
    assert outbox() == []


@HUB_DB
def test_an_alias_of_an_unknown_category_is_refused_on_its_field(no_seed):
    error = refused(
        InvalidPayload,
        lambda: run(
            "tax.alias.create", AliasIn(alias="beer", tax_category_key="nothing")
        ),
    )
    assert (error.status, error.code) == (422, "invalid_field")
    assert error.fields == {"tax_category_key": "This tax category does not exist."}
    assert not TaxAlias.objects.exists()
