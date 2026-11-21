"""The option's fields that came after the migration its recovery from a separate copy reads since: a copy made before
one of them still gives its options back, without it."""

from apps.modifier.models import ModifierOption
from base.recovery import held_in_copy

#: Each a column of the option that ``modifier.option.create`` takes, newer than the declarations' ``reads_since``.
LATER_OPTION_FIELDS = ("allergens",)


def later_option_fields(conn) -> tuple[str, ...]:
    """Those of :data:`LATER_OPTION_FIELDS` the copy's option table holds, through ``conn``, its direct connection."""
    return held_in_copy(conn, ModifierOption._meta.db_table, LATER_OPTION_FIELDS)
