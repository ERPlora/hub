"""What comes back from a separate copy of the business (BASE-F114, MODIFIER-F10)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload
from live.operations import INTERNAL, operation

from apps.modifier.queries.reads import find_group, load_group, load_option
from apps.modifier.schemas.groups import GroupIn, GroupRecoveredOut, GroupRecoverIn
from apps.modifier.schemas.options import OptionIn, OptionRecoveredOut
from apps.modifier.services.defaults import _defaults_in_full
from apps.modifier.services.groups import create_group
from apps.modifier.services.options import create_option
from apps.modifier.services.writes import SYSTEM
from base.recovery import LeftOut

#: What a group made again from a separate copy came back without, said by the option's name and why its create
#: refused it (``modifier.group.recover``).
OPTION_LEFT = _('came back without its option "%(option)s": %(why)s')
#: Why an option chosen by default in a separate copy came back not chosen: its group already comes with as many as
#: it takes, the business's own (``modifier.option.recover``).
DEFAULT_KEPT = _('came back not chosen by default: its group already comes with "%(chosen)s"')


# Not an assistant tool: its one door is the recovery from a separate copy (BASE-F114, MODIFIER-F10), for a group the
# business no longer has at all (deleting one deletes it with its options).
@operation(
    "modifier.group.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=GroupRecoverIn,
    output=GroupRecoveredOut,
    ai=INTERNAL,
)
def recover_group(ctx: OperationContext, data: GroupRecoverIn) -> dict:
    """A group of a separate copy made again by ``modifier.group.create`` with its options there, each added by
    ``modifier.option.create``, all in one; an option its create refuses today does not come back, and the output says
    which and why (``left_out``)."""
    made = create_group(ctx, GroupIn.model_validate(data.model_dump(include=set(GroupIn.model_fields))))
    left_out = []
    for option in data.options:
        try:
            create_option(ctx, OptionIn.model_validate(option.model_dump() | {"group_id": made.id}))
        except (InvalidPayload, Conflict) as refused:
            message = OPTION_LEFT % {"option": option.name, "why": refused.message}
            left_out.append(LeftOut(code=refused.code, message=message))
    return load_group(made.id) | {"left_out": left_out}


# Not an assistant tool: its one door is the recovery from a separate copy (BASE-F114, MODIFIER-F10), for an option a
# group the business keeps no longer has.
@operation(
    "modifier.option.recover",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission=SYSTEM,
    input=OptionIn,
    output=OptionRecoveredOut,
    ai=INTERNAL,
)
def recover_option(ctx: OperationContext, data: OptionIn) -> dict:
    """An option of a separate copy added again by ``modifier.option.create``. One chosen by default there comes back
    chosen only while its group has room for one more: it never takes it from those the business chose, and the output
    says why it came back without (``left_out``)."""
    group = find_group(data.group_id, data.group, lock=True)
    chosen = _defaults_in_full(group) if data.is_default else []
    left_out = []
    if chosen:
        data = data.model_copy(update={"is_default": False})
        left_out.append(LeftOut(code="modifier.default_kept", message=DEFAULT_KEPT % {"chosen": ", ".join(chosen)}))
    made = create_option(ctx, data)
    return load_option(made.id) | {"left_out": left_out}
