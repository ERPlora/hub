"""What every read of the customer app shares, and services/ too inside the command's own transaction: how a person
names a card (by its id, else by its email, phone or name), a group, a tag or a custom field (by its name), the country
a phone without prefix belongs to, and how a list pages, sorts and counts its cards."""

from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound

from apps.customer.models import Customer, CustomerGroup, CustomerTag, CustomField
from apps.customer.schemas.fields import PageIn
from base import operations as platform
from base.ordering import list_order

from . import naming

CUSTOMER_UNAVAILABLE = _("This customer is no longer available.")
NO_CUSTOMER_MATCHES = _("No customer matches “%(reference)s”.")
SEVERAL_CUSTOMERS_MATCH = _(
    "Several customers match “%(reference)s”: %(matches)s. Say which one, or give their id, phone or email."
)
GROUP_UNAVAILABLE = _("That group no longer exists.")
TAG_UNAVAILABLE = _("That tag no longer exists.")
FIELD_UNAVAILABLE = _("That field no longer exists.")
SEVERAL_MATCH = _("Several match “%(reference)s”: give the id.")

CUSTOMER_UNAVAILABLE_CODE = "customer.customer_unavailable"
CUSTOMER_AMBIGUOUS_CODE = "customer.customer_ambiguous"


def business_country(ctx: OperationContext) -> str:
    """The country a phone without prefix belongs to (CUSTOMER-F10, F11): ``ctx``'s business's, as erplora.com
    registered it, Spain without one (``base.operations.business_country``). Saving a card and every lookup by its
    phone, in this app and in the others (``find_customer``), read it here, so the two never part (hub#527)."""
    return platform.business_country(ctx.scope)


def find_customer(
    ctx: OperationContext,
    customer_id: UUID | None,
    reference: str | None,
    *,
    lock: bool = False,
    live: bool = True,
) -> Customer:
    """The card ``customer_id`` names or, without it, the one live card ``reference`` names (``naming.matching``: its
    exact email, phone or name, else as the Customers list finds it), a phone read in ``ctx``'s business's country as
    the card's was saved (``business_country``).

    ``lock`` locks its row until the end of the command's transaction; ``live=False`` also finds a
    deleted, merged or erased card, by its id only. ``NotFound`` (``customer.customer_unavailable``)
    when there is none and ``Conflict`` (``customer.customer_ambiguous``), naming them, when the
    reference fits several cards.
    """
    if customer_id is None:
        found = naming.matching(ctx, reference or "", business_country(ctx))
        if not found:
            raise NotFound(
                NO_CUSTOMER_MATCHES % {"reference": reference},
                code=CUSTOMER_UNAVAILABLE_CODE,
            )
        if len(found) > 1:
            raise Conflict(
                SEVERAL_CUSTOMERS_MATCH % {"reference": reference, "matches": naming.names(found, ctx.language)},
                code=CUSTOMER_AMBIGUOUS_CODE,
            )
        customer_id = found[0][0]
    cards = Customer.objects.live() if live else Customer.objects.all()
    if lock:
        cards = cards.select_for_update()
    customer = cards.filter(pk=customer_id).first()
    if customer is None:
        raise NotFound(CUSTOMER_UNAVAILABLE, code=CUSTOMER_UNAVAILABLE_CODE)
    return customer


def _by_id(rows: QuerySet, item_id: UUID, *, missing, code: str):
    """The row of ``rows`` with ``item_id``; ``NotFound`` (``code``) when there is none."""
    found = rows.filter(pk=item_id).first()
    if found is None:
        raise NotFound(missing, code=code)
    return found


def _find_named(  # noqa: PLR0913
    model, item_id: UUID | None, name: str | None, *, missing, code: str, lock: bool
):
    rows = model.objects.select_for_update() if lock else model.objects.all()
    if item_id is not None:
        return _by_id(rows, item_id, missing=missing, code=code)
    matches = list(rows.filter(name__iexact=(name or "").strip()))
    active = [row for row in matches if row.is_active]
    chosen = active or matches
    if not chosen:
        raise NotFound(missing, code=code)
    if len(chosen) > 1:
        raise Conflict(
            SEVERAL_MATCH % {"reference": name},
            code=code.replace("_unavailable", "_ambiguous"),
        )
    return chosen[0]


def named(model, name: str):
    """The group, tag or custom field the business has under ``name``, the case aside: the active one first, as a
    card's selection by name takes it (``set_groups``, ``set_tags``); ``None`` when it has none."""
    return model.objects.filter(name__iexact=name.strip()).order_by("-is_active", "id").first()


def lost_since_copy(model, items: list) -> list:
    """Those of ``items``, groups, tags or custom fields of a card of a separate copy, the business deleted since: it
    holds none of its ``model`` by their id there. One it still has, renamed or deactivated, is its own (hub#1356)."""
    held = set(model.objects.filter(pk__in=[item.id for item in items if item.id]).values_list("pk", flat=True))
    return [item for item in items if item.id not in held]


def find_group(
    group_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomerGroup:
    return _find_named(
        CustomerGroup,
        group_id,
        name,
        missing=GROUP_UNAVAILABLE,
        code="customer.group_unavailable",
        lock=lock,
    )


def find_tag(
    tag_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomerTag:
    return _find_named(
        CustomerTag,
        tag_id,
        name,
        missing=TAG_UNAVAILABLE,
        code="customer.tag_unavailable",
        lock=lock,
    )


def find_field(
    field_id: UUID | None, name: str | None, *, lock: bool = False
) -> CustomField:
    return _find_named(
        CustomField,
        field_id,
        name,
        missing=FIELD_UNAVAILABLE,
        code="customer.field_unavailable",
        lock=lock,
    )


def page(rows: QuerySet, params: PageIn) -> dict:
    """One page of ``rows`` (already ordered with the id as the tie-break) and how many there are."""
    return {
        "rows": list(rows[params.offset : params.offset + params.limit]),
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _ordered(rows: QuerySet, column: str, descending: bool) -> QuerySet:
    """``rows`` by ``column``, empties last, the id in the list's direction as the tie-break."""
    return rows.order_by(*list_order(column, descending=descending, nulls_last=True))


def _customer_count(relation: str) -> Count:
    return Count(
        relation, filter=Q(**{f"{relation}__deleted_at__isnull": True}), distinct=True
    )
