"""Creating tax rules, one by one or in a batch (TAX-F04, F05, F06, F11, F12): no rate on a class that charges no tax,
coherent components and one root per first day."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from live.errors import Conflict, InvalidPayload
from live.models import OutboxEvent
from live.operations import get
from live.outbox import channel_for

from apps.tax import events
from apps.tax.models import TaxAlias, TaxCategory, TaxRule
from apps.tax.schemas.rules import RuleBulkIn, RuleRefIn
from apps.tax.services.rules import bulk_create_rules, create_rule as create_rule_operation

from base.tenancy.context import use_hub

from .conftest import (
    HUB_DB,
    HUB_DB_COMMITTED,
    QUIET,
    A,
    B,
    category,
    create_rule,
    outbox,
    received,
    refused,
    run,
)

# tax.rule.create (TAX-F04, F05, F06, F11)


@HUB_DB
def test_create_a_root_rule(no_seed):
    assert get("tax.rule.create") is create_rule_operation
    generic = category()
    created = create_rule(valid_from="2026-01-01")
    rule = TaxRule.objects.get()
    assert (rule.category, rule.country_code, rule.region_code, rule.rate_pct) == (
        generic,
        "ES",
        "",
        Decimal("21.00"),
    )
    assert (
        created.id,
        created.tax_category_key,
        created.valid_from,
        created.is_active,
    ) == (
        rule.id,
        "product.generic",
        date(2026, 1, 1),
        True,
    )
    assert outbox() == [
        (
            events.RULE_CREATED,
            A.key,
            {
                "id": str(rule.id),
                "country_code": "ES",
                "region_code": None,
                "tax_category_key": "product.generic",
                "rate_pct": "21.00",
            },
        )
    ]
    assert OutboxEvent.objects.get().actor == "tester"


@HUB_DB
def test_the_category_of_a_rule_is_found_by_name_or_alias(no_seed):
    food = category("restaurant.food", "Restaurant — food", system=True)
    TaxAlias.objects.create(alias="meal", category=food)
    create_rule(
        tax_category_key="Restauración — comida", rate_pct="10", valid_to="2025-12-31"
    )
    create_rule(tax_category_key="meal", rate_pct="10", valid_from="2026-01-01")
    assert (
        list(TaxRule.objects.values_list("category__key", flat=True))
        == ["restaurant.food"] * 2
    )


@HUB_DB
def test_a_rule_of_an_unknown_category_is_refused_on_its_field(no_seed):
    error = refused(
        InvalidPayload, lambda: create_rule(tax_category_key="nothing.here")
    )
    assert error.fields == {"tax_category_key": "This tax category does not exist."}
    assert not TaxRule.objects.exists() and outbox() == []


@HUB_DB
def test_an_exempt_rule_keeps_its_cause_and_another_class_drops_it(no_seed):
    category("service.health"), category()
    exempt = create_rule(
        tax_category_key="service.health",
        rate_pct="0",
        operation_class="exempt",
        exempt_reason="e1",
        regime_key="01",
    )
    assert (exempt.operation_class, exempt.exempt_reason, exempt.regime_key) == (
        "exempt",
        "E1",
        "01",
    )
    subject = create_rule(country_code="PT", exempt_reason="E1")
    assert (
        subject.exempt_reason is None
    )  # a cause only means something on an exempt rule


@HUB_DB
def test_a_regional_rule_with_its_tax_family(no_seed):
    category()
    canary = create_rule(region_code="ES-CN", rate_pct="7", tax_type="igic")
    assert (canary.region_code, canary.tax_type) == ("ES-CN", "igic")


@HUB_DB
def test_a_rule_without_its_tax_family_takes_the_one_of_its_territory(no_seed):
    # TAX-F11: said by voice or through the API without «IGIC», a Canary rule is still IGIC;
    # a family said out loud is kept.
    category()
    canary = create_rule(region_code="ES-CN", rate_pct="7")
    melilla = create_rule(region_code="ES-ML", rate_pct="4")
    national = create_rule(rate_pct="21")
    said = create_rule(region_code="ES-CE", rate_pct="4", tax_type="vat")
    assert [rule.tax_type for rule in (canary, melilla, national, said)] == ["igic", "ipsi", "vat", "vat"]


# Components


@HUB_DB
def test_a_component_hangs_from_a_coherent_root(no_seed):
    category()
    root = create_rule()
    surcharge = create_rule(
        rate_pct="5.2",
        tax_type="surcharge",
        parent_id=root.id,
        component_label="Recargo de equivalencia",
    )
    assert (surcharge.parent_id, surcharge.component_label) == (
        root.id,
        "Recargo de equivalencia",
    )


@HUB_DB
def test_an_incoherent_component_is_refused(no_seed):
    generic, food = category(), category("restaurant.food")
    root = TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("21")
    )
    component = TaxRule.objects.create(
        category=generic, country_code="ES", rate_pct=Decimal("1"), parent=root
    )
    exempt_root = TaxRule.objects.create(
        category=food,
        country_code="ES",
        rate_pct=Decimal("0"),
        operation_class="exempt",
    )
    OutboxEvent.objects.all().delete()
    cases = [
        {"parent_id": uuid.uuid7()},  # no such rule
        {"parent_id": component.id},  # a component of a component
        {"parent_id": root.id, "country_code": "PT"},  # another country
        {"parent_id": root.id, "region_code": "ES-CN"},  # another region
        {
            "parent_id": root.id,
            "tax_category_key": "restaurant.food",
        },  # another category
        # A rate under a root that charges no tax would add a quota to a tax-free operation.
        {
            "parent_id": exempt_root.id,
            "tax_category_key": "restaurant.food",
            "rate_pct": "5.2",
        },
    ]
    for case in cases:
        error = refused(Conflict, lambda case=case: create_rule(**case))
        assert (error.status, error.code) == (409, "tax.rule_incoherent"), case
        assert list(error.fields) == ["parent_id"]
    assert TaxRule.objects.count() == 3 and outbox() == []
    # At 0 % under the tax-free root it is legitimate.
    create_rule(
        parent_id=exempt_root.id, tax_category_key="restaurant.food", rate_pct="0"
    )


@HUB_DB
def test_a_twin_of_a_deactivated_rule_is_refused_on_its_first_day(no_seed):
    # Review (the current product's natural key): the deactivated rule keeps its key; bring it back
    # or start the new one another day.
    category()
    old = create_rule(valid_from="2026-01-01")
    run("tax.rule.deactivate", RuleRefIn(id=old.id))
    OutboxEvent.objects.all().delete()
    error = refused(Conflict, lambda: create_rule(rate_pct="22", valid_from="2026-01-01"))
    assert (error.status, error.code) == (409, "tax.rule_exists")
    assert error.fields == {
        "valid_from": "There is already a rule of this country, region and category from that day, perhaps "
        "deactivated: reactivate it or start this one another day."
    }
    assert TaxRule.objects.count() == 1 and outbox() == []
    create_rule(rate_pct="22", valid_from="2026-01-02")  # another first day is another rule


# tax.rule.bulk_create (TAX-F12): every check of a single rule, all or none


@HUB_DB
def test_bulk_creates_every_rule(no_seed):
    assert get("tax.rule.bulk_create") is bulk_create_rules
    for key in ("product.generic", "product.reduced", "product.super_reduced"):
        category(key)
    rows = [
        {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
        {"country_code": "es", "tax_category_key": "product.reduced", "rate_pct": "10"},
        {
            "country_code": "ES",
            "tax_category_key": "product.super_reduced",
            "rate_pct": "4",
        },
    ]
    created = run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    assert [(r.tax_category_key, r.rate_pct) for r in created.rules] == [
        ("product.generic", Decimal("21.00")),
        ("product.reduced", Decimal("10.00")),
        ("product.super_reduced", Decimal("4.00")),
    ]
    assert [name for name, _scope, _payload in outbox()] == [events.RULE_CREATED] * 3


@HUB_DB
def test_bulk_with_an_unknown_category_saves_nothing(no_seed):
    category()
    rows = [
        {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
        {"country_code": "ES", "tax_category_key": "nothing.here", "rate_pct": "10"},
    ]
    error = refused(
        InvalidPayload, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    )
    assert error.fields == {
        "rules.1.tax_category_key": "This tax category does not exist."
    }
    assert not TaxRule.objects.exists() and outbox() == []


@HUB_DB
def test_bulk_overlapping_an_existing_rule_or_itself_saves_nothing(no_seed):
    category(), category("restaurant.food")
    create_rule(country_code="PT", rate_pct="23")
    OutboxEvent.objects.all().delete()
    rows = [
        {"country_code": "ES", "tax_category_key": "restaurant.food", "rate_pct": "10"},
        {
            "country_code": "PT",
            "tax_category_key": "product.generic",
            "rate_pct": "25",
            "valid_from": "2027-01-01",
        },
        {
            "country_code": "ES",
            "tax_category_key": "restaurant.food",
            "rate_pct": "12",
            "valid_from": "2030-01-01",
        },
    ]
    error = refused(
        Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows))
    )
    assert (error.code, sorted(error.fields)) == (
        "tax.rule_overlaps",
        ["rules.1.valid_from", "rules.2.valid_from"],
    )
    assert TaxRule.objects.count() == 1 and outbox() == []


@HUB_DB
def test_a_batch_with_a_twin_saves_nothing(no_seed):
    category()
    TaxRule.objects.create(
        category=TaxCategory.objects.get(), country_code="PT", rate_pct=Decimal("23"), is_active=False
    )
    rows = [{"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
            {"country_code": "PT", "tax_category_key": "product.generic", "rate_pct": "23"}]  # fmt: skip
    error = refused(Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows)))
    assert (error.code, list(error.fields)) == ("tax.rule_exists", ["rules.1.valid_from"])
    assert TaxRule.objects.count() == 1


@HUB_DB
def test_a_batch_with_twin_rows_is_refused_as_an_overlap_not_a_crash(no_seed):
    # Two identical rows (or a row identical to an active rule) overlap: refused with its field,
    # never a database error on the natural key.
    category()
    create_rule(country_code="PT", rate_pct="23")
    rows = [{"country_code": "PT", "tax_category_key": "product.generic", "rate_pct": "23"},
            {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"},
            {"country_code": "ES", "tax_category_key": "product.generic", "rate_pct": "21"}]  # fmt: skip
    error = refused(Conflict, lambda: run("tax.rule.bulk_create", RuleBulkIn(rules=rows)))
    assert (error.code, sorted(error.fields)) == ("tax.rule_overlaps", ["rules.0.valid_from", "rules.2.valid_from"])
    assert TaxRule.objects.count() == 1


# Notifications: after the COMMIT, on the channel of the command's scope only


@HUB_DB_COMMITTED
def test_a_rule_saved_in_b_notifies_the_channel_of_b_only(listen, hub_b):
    on_a, on_b = listen(A), listen(B)

    with use_hub(hub_b):
        TaxCategory.objects.create(key="product.notify", name="Notify")
        create_rule(country_code="FR", tax_category_key="product.notify", scope=B)
        assert [(name, scope) for name, scope, _ in outbox()] == [(events.RULE_CREATED, B.key)]

    assert received(on_b, stop_after=1) == [
        (channel_for(B), {"events": [events.RULE_CREATED]})
    ]
    assert received(on_a, timeout=QUIET) == []


@HUB_DB_COMMITTED
def test_a_refused_rule_notifies_nobody(listen, hub_b):
    with use_hub(hub_b):
        TaxCategory.objects.create(key="product.notify", name="Notify")
        create_rule(country_code="FR", tax_category_key="product.notify", scope=B)
        on_b = listen(B)

        with pytest.raises(Conflict):
            create_rule(
                country_code="FR", tax_category_key="product.notify", rate_pct="25", scope=B
            )

    assert received(on_b, timeout=QUIET) == []
