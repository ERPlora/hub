"""The book's gate (engine.py), asked under the lock of the book's settings row, and its refusals as the form, the API
and the assistant read them.
"""

from dataclasses import replace

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict

from apps.reservation import engine
from apps.reservation.models import Settings
from apps.reservation.queries import (
    blocks_of,
    business_now,
    business_zone,
    engine_blocks,
    hours_of,
    rules_of,
    slots_of,
    table_facts,
)
from apps.table.models import Table
from apps.table.queries import find_table

#: The gate's refusals, by code: their message and the field of the form they belong to.
REFUSALS = {
    "phone_required": (
        _("This business requires a phone number for every reservation."),
        "guest_phone",
    ),
    "email_required": (
        _("This business requires an email address for every reservation."),
        "guest_email",
    ),
    "party_size_exceeded": (
        _(
            "That party size is outside the limits of this business (%(min)s–%(max)s guests)."
        ),
        "party_size",
    ),
    "in_past": (_("That time has already passed."), "time"),
    "too_soon": (
        _("Reservations have to be made at least %(hours)s h in advance."),
        "time",
    ),
    "too_far": (_("Reservations are taken up to %(days)s days ahead."), "date"),
    "date_blocked": (
        _("That date is blocked (holiday or closure): no reservations are taken then."),
        "date",
    ),
    "outside_schedule": (_("The business is closed at that time."), "time"),
    "no_service_day": (
        _("There is no service at that time: no time slot covers it."),
        "time",
    ),
    "no_capacity": (_("That time slot is fully booked for that date."), "time"),
    "table_unavailable": (
        _("Table %(table)s cannot be booked: it is blocked or out of service."),
        "table_id",
    ),
    "table_taken": (
        _("Table %(table)s already has a reservation from %(start)s to %(end)s."),
        "table_id",
    ),
}
OVERBOOK_HINT = _("Send overbook as true to book this full slot anyway.")


def lock_book() -> Settings:
    """The book's settings row, locked until the end of the transaction: every write that books waits
    here for the one before it (created the first time, with its factory rules)."""
    Settings.objects.get_or_create(singleton=True)
    return Settings.objects.select_for_update().get(singleton=True)


def refuse(refusal: engine.Refusal) -> Conflict:
    """The refusal as the 409 the form, the API and the assistant read: its message on its field and, when
    the staff may book it anyway (a full slot), the input that does it (`overbook`)."""
    message, field = REFUSALS[refusal.code]
    params = {key: value for key, value in refusal.params.items() if key != "overbook"}
    text = str(message) % params if params else str(message)
    fields = {field: text}
    if refusal.params.get("overbook"):
        fields["overbook"] = str(OVERBOOK_HINT)
    return Conflict(text, code=f"reservation.{refusal.code}", fields=fields)


def judge(
    ctx: OperationContext,
    settings: Settings,
    request: engine.Request,
    table: Table | None,
    exclude: tuple = (),
) -> None:
    """Raises the first reason that refuses ``request`` (engine.verdict), with what the gate reads: in the
    business's zone, so that what lasts counts real time."""
    request = replace(request, zone=business_zone())
    window = request.window
    verdict = engine.verdict(
        request,
        rules=rules_of(settings),
        now=business_now(),
        blocks=engine_blocks(blocks_of(request.date)),
        hours=hours_of(ctx, request.date),
        slots=slots_of(request.date, exclude),
        table=table_facts(table, window, exclude) if table is not None else None,
    )
    if verdict is not None:
        raise refuse(verdict)


def choose_table(table_id, said: str | None, zone: str | None) -> Table | None:
    if table_id is None and not said:
        return None
    return find_table(table_id, said, zone)
