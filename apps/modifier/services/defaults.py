"""The options a group comes with chosen by default: never more than it takes."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.outbox import record_event

from apps.modifier import events
from apps.modifier.models import ModifierGroup, ModifierOption
from apps.modifier.services.writes import _actor, _option_payload

TOO_MANY_DEFAULTS = _("This group has more options chosen by default than its maximum.")


def _too_many_defaults(field: str) -> Conflict:
    return Conflict(
        str(TOO_MANY_DEFAULTS),
        code="modifier.too_many_defaults",
        fields={field: str(TOO_MANY_DEFAULTS)},
    )


def _make_room_for_a_default(
    ctx: OperationContext, group: ModifierGroup, exclude: ModifierOption | None
) -> None:
    """A new default in a group of one replaces the old one (said as its change); otherwise the defaults
    never pass the maximum. The group's row is locked by the caller."""
    others = group.options.filter(is_default=True)
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if group.max_choices == 1:
        for previous in others:
            previous.is_default, previous.updated_by = False, _actor(ctx)
            previous.save(update_fields=["is_default", "updated_by", "updated_at"])
            record_event(ctx, events.OPTION_UPDATED, _option_payload(previous))
    elif group.max_choices and others.count() + 1 > group.max_choices:
        raise _too_many_defaults("is_default")


def _defaults_in_full(group: ModifierGroup) -> list[str]:
    """The names of ``group``'s options chosen by default when they are as many as it takes, in its order; none while
    it has room for one more. The group's row is locked by the caller."""
    if not group.max_choices:
        return []
    chosen = list(group.options.filter(is_default=True).order_by("sort_order", "name").values_list("name", flat=True))
    return chosen if len(chosen) >= group.max_choices else []
