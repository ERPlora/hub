"""Read operations of the automatic discount rules."""

from django.db.models import Q
from django.db.models.functions import Lower
from live.context import OperationContext
from live.operations import operation

from apps.pricing.queries.reads import _page, find_rule
from apps.pricing.queries.rows import _rules, _status, rule_row
from apps.pricing.schemas import Page, RuleListIn, RuleOut, RuleRefIn
from base import operations as platform
from base.ordering import list_order


@operation(
    "pricing.rule.list",
    kind="query",
    permission="pricing.view",
    input=RuleListIn,
    output=Page[RuleOut],
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "show me the promotions running now",
                "which promotions apply by themselves?",
                "what gets cheaper by itself and for whom?",
            ),
            "es": (
                "enséñame las promociones que hay ahora",
                "¿qué promociones se aplican solas?",
                "¿qué se rebaja solo y para quién?",
            ),
        },
        "description": "List the automatic discount rules (the active ones by default): type and value (a percent, "
        "an amount per unit, buy X get Y, tiers by quantity), what each applies to, its customer group, minimum "
        "quantity, dates and priority. Search by code or name."
    },
)
def list_rules(ctx: OperationContext, params: RuleListIn) -> dict:
    rows = _status(_rules(), params.status)
    if params.search:
        rows = rows.filter(Q(code__icontains=params.search) | Q(name__icontains=params.search))
    for column in ("code", "name"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{f"{column}__icontains": value})
    for column in ("rule_type", "applies_to", "customer_group_id"):
        value = getattr(params, column)
        if value:
            rows = rows.filter(**{column: value})
    rows = rows.order_by(*list_order(params.sort, Lower("code"), descending=params.dir == "desc", nulls_last=True))
    currency = platform.business_currency(ctx.scope)
    return _page(rows, params, lambda rule: rule_row(rule, currency))


@operation(
    "pricing.rule.get",
    kind="query",
    permission="pricing.view",
    input=RuleRefIn,
    output=RuleOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how big is the happy hour discount and how long does it last?",
                "what does the happy hour consist of?",
                "give me the details of the happy hour, PROMO-HH",
            ),
            "es": (
                "¿de cuánto es el descuento de la happy hour y cuánto dura?",
                "¿en qué consiste la happy hour?",
                "dame el detalle de la happy hour, la PROMO-HH",
            ),
        },
        "description": "Get one discount rule, active or not, by its id, its code or its name (e.g. «summer rule»).",
    },
)
def get_rule(ctx: OperationContext, data: RuleRefIn) -> dict:
    return rule_row(find_rule(data.id, data.rule), platform.business_currency(ctx.scope))
