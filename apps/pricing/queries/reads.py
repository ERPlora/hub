"""What the reads of the pricing app share, and services/ too: how a person names a price list or a discount
rule, the prices that count and how a list pages.
"""

from uuid import UUID

from django.db.models import Q, QuerySet
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict, NotFound

from apps.pricing.models import DiscountRule, PriceItem, PriceList
from base.text_search import contains_text

#: Candidates named when a text matches several.
MAX_CANDIDATES = 5

LIST_NOT_FOUND = _("This price list does not exist.")
LIST_AMBIGUOUS = _("“%(said)s” matches several price lists: %(names)s. Say which one.")
RULE_NOT_FOUND = _("This discount rule does not exist.")
RULE_AMBIGUOUS = _("“%(said)s” matches several discount rules: %(names)s. Say which one.")
ITEM_NOT_FOUND = _("That price no longer exists.")


def _page(rows: QuerySet, params, to_row) -> dict:
    page = list(rows[params.offset : params.offset + params.limit])
    return {"rows": [to_row(row) for row in page], "total": rows.count(), "limit": params.limit, "offset": params.offset}


def _named(rows: QuerySet, said: str, *, missing, missing_code: str, ambiguous, ambiguous_code: str):  # noqa: PLR0913
    """The one row whose code or name is ``said`` (any case), else the one whose name holds it."""
    text = said.strip()
    for lookup in (Q(code__iexact=text), Q(name__iexact=text), contains_text(text, "name", "code")):
        candidates = list(rows.filter(lookup).order_by(Lower("code"), "id")[: MAX_CANDIDATES + 1])
        if len(candidates) == 1:
            return candidates[0]
        if candidates:
            names = ", ".join(f"{row.name} ({row.code})" for row in candidates[:MAX_CANDIDATES])
            raise Conflict(str(ambiguous) % {"said": text, "names": names}, code=ambiguous_code)
    raise NotFound(str(missing), code=missing_code)


def find_list(list_id: UUID | None, said: str | None, *, lock: bool = False, rows=None) -> PriceList:
    """A price list by its id, or by its code or name as a person says it (active or not). It comes from
    ``rows`` when given (e.g. with what its detail shows): one read, so a deletion committed meanwhile is
    either not seen yet or not found, never a row that vanished between two reads. Never with ``lock``:
    those rows are grouped (the count of prices) and Postgres refuses ``FOR UPDATE`` on a grouped query."""
    if lock and rows is not None:
        raise TypeError("find_list: rows= and lock=True are exclusive (FOR UPDATE is not allowed with GROUP BY)")
    lists = PriceList.objects.all()
    if list_id is None:
        list_id = _named(
            lists,
            said or "",
            missing=LIST_NOT_FOUND,
            missing_code="pricing.price_list_not_found",
            ambiguous=LIST_AMBIGUOUS,
            ambiguous_code="pricing.ambiguous_price_list",
        ).pk
    found = (lists if rows is None else rows).filter(pk=list_id)
    price_list = (found.select_for_update() if lock else found).first()
    if price_list is None:
        raise NotFound(str(LIST_NOT_FOUND), code="pricing.price_list_not_found")
    return price_list


def find_rule(rule_id: UUID | None, said: str | None, *, lock: bool = False) -> DiscountRule:
    """A discount rule by its id, or by its code or name as a person says it (active or not)."""
    rows = DiscountRule.objects.all()
    if rule_id is None:
        rule_id = _named(
            rows,
            said or "",
            missing=RULE_NOT_FOUND,
            missing_code="pricing.rule_not_found",
            ambiguous=RULE_AMBIGUOUS,
            ambiguous_code="pricing.ambiguous_rule",
        ).pk
    found = rows.filter(pk=rule_id)
    rule = (found.select_for_update() if lock else found).first()
    if rule is None:
        raise NotFound(str(RULE_NOT_FOUND), code="pricing.rule_not_found")
    return rule


def live_items() -> QuerySet:
    """The prices that count: of a service, or of a product Inventory has not deleted."""
    return PriceItem.objects.filter(Q(product__isnull=True) | Q(product__is_deleted=False))
