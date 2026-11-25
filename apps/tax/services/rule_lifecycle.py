"""What happens to a tax rule that exists: its end (TAX-F07), and deactivating and bringing it back (TAX-F08)."""

from collections.abc import Callable

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from live.outbox import record_event

from apps.tax import events
from apps.tax.models import TaxRule
from apps.tax.queries.jurisdiction import business_today
from apps.tax.queries.naming import category_by_reference
from apps.tax.queries.rules import RULE_NOT_FOUND, load_rule, rule_row
from apps.tax.schemas.rules import RuleEndIn, RuleOut, RuleRefIn
from apps.tax.services.overlaps import _lock, _refuse_overlap

RULE_END_INVALID = _("That rule cannot end before the day it starts.")
RULE_ALREADY_ACTIVE = _("That rule is already active.")
RULE_ALREADY_INACTIVE = _("That rule is already deactivated.")


def _named_rule(
    reference: RuleRefIn, pick: Callable[[list[TaxRule]], TaxRule | None]
) -> TaxRule:
    """The rule a person names, locked with its category: by its id, or by its slot through ``pick``."""
    if reference.id is not None:
        rule = load_rule(reference.id)
    else:
        category = category_by_reference(reference.tax_category_key)
        slot = TaxRule.objects.select_related("category").filter(
            parent__isnull=True,
            country_code=reference.country_code,
            region_code=reference.region_code or "",
            category=category,
        )
        rule = pick(list(slot)) if category else None
    if rule is None:
        raise NotFound(RULE_NOT_FOUND)
    _lock([rule.category])
    return (
        # ``of=self``: the category is locked by ``_lock`` alone, the one place that orders the locks.
        TaxRule.objects.select_for_update(of=("self",)).select_related("category").get(pk=rule.pk)
    )


def _newest(rules: list[TaxRule]) -> TaxRule | None:
    """The one with the newest start (an empty start is the oldest), then the lowest id."""
    return min(
        rules,
        key=lambda r: (-(r.valid_from.toordinal() if r.valid_from else 0), r.id.int),
        default=None,
    )


def _in_force_today(rules: list[TaxRule]) -> TaxRule | None:
    today = business_today()
    return _newest(
        [rule for rule in rules if rule.is_active and rule.in_force_on(today)]
    )


def _latest_deactivated(rules: list[TaxRule]) -> TaxRule | None:
    """The one deactivated most recently (its last change, ``updated_at``), then the highest id."""
    deactivated = [rule for rule in rules if not rule.is_active]
    return max(deactivated, key=lambda rule: (rule.updated_at, rule.id.int), default=None)


@operation(
    "tax.rule.end",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=RuleEndIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "end the 10 % VAT rule on 31 December",
                "set an end date on the tax rule for books",
                "the reduced rate stops applying after 30 June: end its tax rule",
            ),
            "es": (
                "pon fecha de fin a la regla del IVA de los libros",
                "en España el tipo reducido de hostelería vale hasta el 30 de junio: ponle fecha de fin a su regla",
                "la regla del IVA de la comida no se aplica después del 31 de diciembre: termínala ese día",
            ),
        },
        "description": "Set the last day (inclusive) a tax rule applies, named by its id or by its country, "
        "region and category (the rule in force today). This is how a rate change is scheduled: end the current "
        "rule the day before the new rate starts, then create the new rule from that day. Issued invoices do "
        "not change.",
        "risk": "high",
    },
)
def end_rule(ctx: OperationContext, data: RuleEndIn) -> dict:
    rule = _named_rule(data, _in_force_today)
    if rule.valid_from is not None and data.valid_to < rule.valid_from:
        raise Conflict(
            RULE_END_INVALID,
            code="tax.rule_end_invalid",
            fields={"valid_to": str(RULE_END_INVALID)},
        )
    if rule.valid_to != data.valid_to:
        rule.valid_to = data.valid_to
        _refuse_overlap(rule, "valid_to")
        rule.save(update_fields=["valid_to", "updated_at"])
        record_event(
            ctx,
            events.RULE_ENDED,
            {"id": str(rule.id), "valid_to": data.valid_to.isoformat()},
        )
    return rule_row(rule)


def _switch(ctx: OperationContext, rule: TaxRule, active: bool) -> dict:
    if rule.is_active == active:
        message, code = (
            (RULE_ALREADY_ACTIVE, "tax.rule_already_active")
            if active
            else (RULE_ALREADY_INACTIVE, "tax.rule_already_inactive")
        )
        raise Conflict(message, code=code)
    rule.is_active = active
    if active:
        _refuse_overlap(rule, None)
    rule.save(update_fields=["is_active", "updated_at"])
    record_event(
        ctx,
        events.RULE_ACTIVATED if active else events.RULE_DEACTIVATED,
        {"id": str(rule.id)},
    )
    return rule_row(rule)


@operation(
    "tax.rule.deactivate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=RuleRefIn,
    output=RuleOut,
    ai={
        "asks": {
            "en": (
                "deactivate the tax rule for books",
                "stop applying the 10 % VAT rule for now",
                "deactivate the Portuguese tax rule for food for a while",
            ),
            "es": (
                "desactiva la regla de IVA de los libros",
                "deja de aplicar por ahora la regla fiscal del 10 %",
                "desactiva de momento la regla de impuestos de España para la comida",
            ),
        },
        "description": "Deactivate a tax rule so it no longer applies to new operations, named by its id or by its "
        "country, region and category (the rule in force today). Its rate, dates and components are kept and "
        "issued invoices do not change; tax.rule.activate brings it back.",
        "risk": "high",
    },
)
def deactivate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch(ctx, _named_rule(data, _in_force_today), active=False)


@operation(
    "tax.rule.activate",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="tax.manage",
    input=RuleRefIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "reactivate the tax rule for books",
                "turn the 10 % VAT rule back on",
                "bring back the deactivated tax rule of Portugal",
            ),
            "es": (
                "reactiva la regla de IVA de los libros",
                "vuelve a poner en marcha en España la regla de impuestos de la comida",
                "recupera la regla fiscal de Portugal que está desactivada",
            ),
        },
        "description": "Bring a deactivated tax rule back so it applies to new operations again, named by its id "
        "or by its country, region and category (the most recent deactivated one). Refused if it would now "
        "overlap another active rule of the same country, region and category.",
        "risk": "high",
    },
)
def activate_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return _switch(ctx, _named_rule(data, _latest_deactivated), active=True)
