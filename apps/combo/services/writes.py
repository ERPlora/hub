"""What the writes of menus, courses and choices share: the platform's own permission, the place a new row takes, a
save that may lose a uniqueness to another writer, a course as the writes return it, and a new order."""

from uuid import UUID

from django.db import IntegrityError
from django.db.models import Max
from django.utils.translation import gettext_lazy as _
from live.errors import Conflict
from live.operations import atomic

from apps.combo.models import ChoiceGroup
from apps.combo.queries.offers import takeaway_targets
from apps.combo.queries.rows import group_row

REORDER_MISMATCH = _(
    "The new order has to list every one of them, once, and nothing else."
)

#: Run only by the platform (events.py, and the recovery from a separate copy): no role holds it, so no person and no
#: API key reaches it.
SYSTEM = "combo.system"


def _next_order(rows) -> int:
    last = rows.aggregate(last=Max("sort_order"))["last"]
    return 0 if last is None else last + 1


def _saved(write, conflict) -> None:
    """Runs ``write`` in a savepoint; a uniqueness lost to another writer anyway (the database's last net)
    becomes the 409 ``conflict`` raises, never a raw error."""
    try:
        with atomic():
            write()
    except IntegrityError:
        conflict()
        raise


def _group_out(group_id: UUID) -> dict:
    group = ChoiceGroup.objects.select_related("combo").prefetch_related("options__product__tax_category").get(pk=group_id)
    return group_row(group, takeaway_targets())


def _reordered(rows, wanted: list[UUID]) -> None:
    """Each row of ``rows`` to its place in ``wanted``, which must list every one of them, once."""
    current = {row.id: row for row in rows}
    if set(current) != set(wanted) or len(current) != len(wanted):
        raise Conflict(str(REORDER_MISMATCH), code="combo.reorder_mismatch")
    for position, row_id in enumerate(wanted):
        row = current[row_id]
        if row.sort_order != position:
            row.sort_order = position
            row.save(update_fields=["sort_order", "updated_at"])
