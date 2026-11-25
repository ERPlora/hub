"""What the writes of groups, options and links share."""

from django.db import IntegrityError
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import atomic

from apps.modifier.models import ACTOR_MAX_LENGTH, ModifierOption

GROUP_NAME_TAKEN = _("There is already a group with that name.")
OPTION_NAME_TAKEN = _("This group already has an option with that name.")
OWN_LINE_NOT_POSITIVE = _(
    "An option with its own tax category is billed on a line of its own: its supplement must be more than zero."
)
LINK_EXISTS = _("This group already applies there.")

#: Run only by the platform (events.py, and the recovery from a separate copy): no role holds it, so no person and no
#: API key reaches it.
SYSTEM = "modifier.system"

_CONSTRAINTS = {
    "modifier_group_name_unique": (
        "name",
        GROUP_NAME_TAKEN,
        "modifier.group_name_taken",
    ),
    "modifier_option_name_unique_in_group": (
        "name",
        OPTION_NAME_TAKEN,
        "modifier.option_name_taken",
    ),
    "modifier_link_product_unique": ("__all__", LINK_EXISTS, "modifier.link_exists"),
    "modifier_link_category_unique": ("__all__", LINK_EXISTS, "modifier.link_exists"),
}
#: The database's own rules that are a 422 of a field, not a 409.
_CHECKS = {
    "modifier_option_own_line_positive": ("price_delta", OWN_LINE_NOT_POSITIVE),
}


def _actor(ctx: OperationContext) -> str:
    return str(ctx.actor)[:ACTOR_MAX_LENGTH]


def _save(row, **options) -> None:
    """Save in a savepoint, so that a name or a link another save took at the same time, or a rule the
    database holds, says so on its field."""
    try:
        with atomic():
            row.save(**options)
    except IntegrityError as exc:
        for constraint, (field, message, code) in _CONSTRAINTS.items():
            if constraint in str(exc):
                raise Conflict(
                    str(message), code=code, fields={field: str(message)}
                ) from exc
        for constraint, (field, message) in _CHECKS.items():
            if constraint in str(exc):
                raise InvalidPayload(str(message), code="invalid_field", fields={field: str(message)}) from exc
        raise


def _option_payload(option: ModifierOption) -> dict:
    return {
        "id": str(option.id),
        "group_id": str(option.group_id),
        "name": option.name,
        "price_delta": option.price_delta,
    }
