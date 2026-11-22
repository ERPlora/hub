"""Seating a reservation's party at its table (RESERVATION-F11): Tables opens the table's session, and its check opens
in Sales.
"""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict

from apps.customer.models import Customer
from apps.reservation import engine
from apps.reservation.models import Reservation
from apps.reservation.queries import in_service
from apps.reservation.services.gate import refuse
from apps.reservation.services.other_apps import call_app
from apps.table.models import Hold, Table
from apps.table.queries import floor, seatable

TABLE_NOT_FREE = _(
    "Table %(table)s is taken right now: free it, or move the reservation to another table before seating it."
)


def seat_at_table(ctx: OperationContext, reservation: Reservation):
    """Seats the party at its table in Tables (its check opens in Sales); the id of the table's check.

    Market (duda 3): one gesture seats the reservation and the table; a table out of service is refused,
    and so is one that is taken, to be freed or the reservation moved — unless this very reservation's
    hold was already spent by seating its table from the floor plan (TABLE-F28) and no other reservation
    owns the check sitting there: then the party is there, and its check is the table's. Seating from
    here names the reservation, so Tables spends its hold alone; the floor plan names none and spends
    every hold of the table inside the hour, so a spent hold alone proves nothing: the party of another
    reservation seated there from the plan also spends it.
    """
    now = timezone.now()
    table = Table.objects.select_related("zone").get(pk=reservation.table_id)
    if not in_service(table):
        raise refuse(engine.Refusal("table_unavailable", {"table": floor.table_label(table)}))
    holds = Hold.objects.filter(source=Hold.Source.RESERVATION, source_ref=str(reservation.pk))
    if not seatable(table, now):
        sitting = floor.live_sessions().filter(table=table).order_by("opened_at", "id").first()
        owned = (
            sitting is not None
            and Reservation.objects.filter(table_session_id=sitting.pk, is_deleted=False)
            .exclude(pk=reservation.pk)
            .exists()
        )
        if sitting is not None and not owned and holds.filter(status=Hold.Status.CONSUMED).exists():
            return sitting.pk
        text = str(TABLE_NOT_FREE) % {"table": floor.table_label(table)}
        raise Conflict(text, code="reservation.table_not_free")
    seat = {
        "table_id": str(table.pk),
        "guests_count": reservation.party_size,
        "reservation_id": str(reservation.pk),
    }
    if reservation.customer_id and Customer.objects.live().filter(pk=reservation.customer_id).exists():
        seat["customer_id"] = str(reservation.customer_id)
    session_id = call_app(ctx, "table.session.open", seat).id
    if holds.filter(status=Hold.Status.HELD).exists():
        # Seated before its hold's window (more than an hour early): it would paint the table later.
        call_app(ctx, "table.hold.release", {"source": "reservation", "source_ref": str(reservation.pk)})
    return session_id
