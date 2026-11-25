"""An existing category is named by its key, its name or an alias: the assistant is used by voice."""

from apps.tax.schemas.categories import CategoryGetIn
from apps.tax.schemas.references import CATEGORY_REF
from apps.tax.schemas.rules import RuleIn

from .schema_checks import RULE, invalid_fields


def test_the_category_of_a_rule_may_be_said_by_name():
    # By voice: «Restauración — comida» or an alias; the operation finds the category.
    assert (
        RuleIn(
            **{**RULE, "tax_category_key": " Restauración — comida "}
        ).tax_category_key
        == "Restauración — comida"
    )
    assert invalid_fields(RuleIn, **{**RULE, "tax_category_key": " "}) == {
        "tax_category_key"
    }


def test_a_category_is_looked_up_by_key_name_or_alias():
    assert CategoryGetIn(key=" Restauración — comida ").key == "Restauración — comida"
    assert invalid_fields(CategoryGetIn, key=" ") == {"key"}
    assert CategoryGetIn.model_fields["key"].description == CATEGORY_REF
