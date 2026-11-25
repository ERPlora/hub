"""What every write of the tax app declares, and who may run them."""

import pytest
from live.errors import PermissionDenied
from live.models import OutboxEvent
from live.operations import get

from apps.tax.models import TaxAlias, TaxCategory, TaxRule
from apps.tax.schemas.aliases import AliasIn, AliasOut
from apps.tax.schemas.categories import CategoryIn, CategoryOut
from apps.tax.schemas.rules import RuleBulkIn, RuleBulkOut, RuleEndIn, RuleIn, RuleOut, RuleRefIn
from apps.tax.schemas.settings import TaxSettingsIn, TaxSettingsOut

from .conftest import HUB_DB, category, create_rule, outbox, refused, run

# Declarations: the assistant sees every write, and how risky it is


@pytest.mark.parametrize(
    ("name", "input", "output", "expose_api", "risk"),
    [
        ("tax.category.create", CategoryIn, CategoryOut, False, "normal"),
        ("tax.alias.create", AliasIn, AliasOut, False, "normal"),
        # A rule decides what is charged and declared: fiscal, so high.
        ("tax.rule.create", RuleIn, RuleOut, False, "high"),
        ("tax.rule.bulk_create", RuleBulkIn, RuleBulkOut, False, "high"),
        ("tax.rule.end", RuleEndIn, RuleOut, True, "high"),
        ("tax.rule.deactivate", RuleRefIn, RuleOut, False, "high"),
        ("tax.rule.activate", RuleRefIn, RuleOut, True, "high"),
        # The business's region decides which rate every sale charges and declares (TAX-F11).
        ("tax.settings.update", TaxSettingsIn, TaxSettingsOut, False, "high"),
    ],
)
def test_declarations(name, input, output, expose_api, risk):
    op = get(name)
    assert (op.kind, op.permission, op.input, op.output, op.expose_api) == (
        "command",
        "tax.manage",
        input,
        output,
        expose_api,
    )
    # asks: what a person says to ask for it; does: what its name does not say (a rule created sets a rate).
    does = {"does"} if name == "tax.rule.create" else set()
    assert op.ai["description"].strip() and op.ai["risk"] == risk
    assert set(op.ai) == {"asks", "description", "risk"} | does


# Permissions


@HUB_DB
def test_an_employee_cannot_write(no_seed):
    category()
    rule = create_rule()
    OutboxEvent.objects.all().delete()
    attempts = [
        ("tax.category.create", CategoryIn(key="product.x", name="X")),
        ("tax.alias.create", AliasIn(alias="x", tax_category_key="product.generic")),
        (
            "tax.rule.create",
            RuleIn(
                country_code="PT", tax_category_key="product.generic", rate_pct="23"
            ),
        ),
        (
            "tax.rule.bulk_create",
            RuleBulkIn(
                rules=[
                    {
                        "country_code": "PT",
                        "tax_category_key": "product.generic",
                        "rate_pct": "23",
                    }
                ]
            ),
        ),
        ("tax.rule.end", RuleEndIn(id=rule.id, valid_to="2030-01-01")),
        ("tax.rule.deactivate", RuleRefIn(id=rule.id)),
        ("tax.rule.activate", RuleRefIn(id=rule.id)),
    ]
    for name, data in attempts:
        refused(
            PermissionDenied,
            lambda name=name, data=data: run(name, data, role="hub_employee"),
        )
    assert (
        TaxCategory.objects.count(),
        TaxRule.objects.count(),
        TaxAlias.objects.count(),
    ) == (1, 1, 0)
    assert TaxRule.objects.get().is_active and outbox() == []
