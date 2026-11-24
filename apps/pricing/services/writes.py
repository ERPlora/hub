"""What the pricing writes share: who wrote a row, the constraint behind a refused save, and how a write finds
another app's row it names, holds it until it ends and refuses it under its field."""

from typing import Any
from uuid import UUID

from django.db import IntegrityError
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound, OperationError

from apps.customer import queries as customer_queries
from apps.customer.models import CustomerGroup
from apps.customer.queries.reads import find_group
from apps.inventory import queries as inventory_queries
from apps.inventory.models import Product
from apps.inventory.queries.reads import find_product, held
from apps.pricing.models import ACTOR_MAX_LENGTH, DiscountRule


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _constraint(error: IntegrityError) -> str | None:
    return getattr(getattr(error.__cause__, "diag", None), "constraint_name", None)


def _field_error(error: OperationError, field: str):
    """Another app's refusal of a reference, said under the field it came from."""
    if isinstance(error, NotFound):
        return InvalidPayload(error.message, code="invalid_field", fields={field: error.message})
    return Conflict(error.message, code=error.code, fields={field: error.message})


def _held_one(rows, gone) -> Any:
    """The row of ``rows`` (one at most), held until this write ends (``held``); ``NotFound`` with ``gone``
    when it is no longer there, as one deleted before."""
    found = held(rows)
    if not found:
        raise NotFound(str(gone))
    return found[0]


def _held_product(product_id: UUID | None, said: str | None) -> Product:
    """The live product named by its id, or by its SKU or name (Inventory's lookup), held until this write ends."""
    product = find_product(product_id, said)
    # Inventory's own refusal (its text, in its catalog), as for one deleted before.
    return _held_one(Product.objects.filter(pk=product.pk, is_deleted=False), inventory_queries.reads.PRODUCT_NOT_FOUND)


def _group_id(group_id: UUID | None, said: str | None) -> UUID | None:
    """The id of the customer group named by its id or its name (Customers' lookup), held until this write
    ends; none = no group."""
    if group_id is None and said is None:
        return None
    try:
        group = find_group(group_id, said)
        # Customers' own refusal (its text, in its catalog), as for one deleted before.
        return _held_one(CustomerGroup.objects.filter(pk=group.pk), customer_queries.reads.GROUP_UNAVAILABLE).id
    except (NotFound, Conflict) as error:
        raise _field_error(error, "customer_group_id" if group_id is not None else "customer_group") from None


def _group_held(rule: DiscountRule) -> bool:
    """Whether ``rule`` may be on as for its group: none, or one Customers still has. A deleted group's rule would apply
    to nobody, or, without the group, to everybody. Held when it is there, so its deletion waits for the rule to be on
    (and switches it off after)."""
    group = rule.customer_group_id
    return group is None or bool(held(CustomerGroup.objects.filter(pk=group)))
