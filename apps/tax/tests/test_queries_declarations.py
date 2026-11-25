"""What every read of the tax app declares, and who may run them."""

import pytest
from live.errors import PermissionDenied
from live.operations import get

from apps.tax.schemas.aliases import AliasListIn, AliasPage, AliasResolveIn, AliasResolveOut
from apps.tax.schemas.calculation import CalculateIn, CalculationOut
from apps.tax.schemas.categories import CategoryGetIn, CategoryListIn, CategoryOut, CategoryPage
from apps.tax.schemas.rules import (
    RuleCountriesIn,
    RuleCountriesOut,
    RuleListIn,
    RulePage,
    RuleParentIn,
    RuleStatusIn,
    RuleStatusOut,
)
from apps.tax.schemas.settings import SettingsGetIn, TaxSettingsOut

from .conftest import HUB_DB, category, run

pytestmark = HUB_DB


# Declarations


@pytest.mark.parametrize(
    ("name", "input", "output", "expose_api"),
    [
        # expose_api as in the current product's manifest: the calculation and the status were not.
        ("tax.category.list", CategoryListIn, CategoryPage, True),
        ("tax.category.get", CategoryGetIn, CategoryOut, True),
        ("tax.rule.list", RuleListIn, RulePage, True),
        ("tax.rule.status", RuleStatusIn, RuleStatusOut, False),
        # The pickers of the rules screen: the roots a component may hang from, the countries in use.
        ("tax.rule.parent_candidates", RuleParentIn, RulePage, False),
        ("tax.rule.countries", RuleCountriesIn, RuleCountriesOut, False),
        ("tax.alias.list", AliasListIn, AliasPage, True),
        ("tax.alias.resolve", AliasResolveIn, AliasResolveOut, True),
        ("tax.rate.calculate", CalculateIn, CalculationOut, False),
        # The business's tax region (TAX-F11): what every calculation reads when it names no country.
        ("tax.settings.get", SettingsGetIn, TaxSettingsOut, False),
    ],
)
def test_declarations(name, input, output, expose_api):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "query",
        "tax.view",
        input,
        output,
        expose_api,
    )
    # The assistant sees every read, with what a person says to ask for it (hub#1094); a read carries no risk.
    assert isinstance(op.ai, dict) and op.ai["description"].strip() and set(op.ai) == {"asks", "description"}


def test_an_employee_reads_and_a_role_without_tax_does_not(no_seed):
    category()
    assert run("tax.category.list", CategoryListIn(), role="hub_employee").total == 1
    with pytest.raises(PermissionDenied):
        run("tax.category.list", CategoryListIn(), role="nobody")
