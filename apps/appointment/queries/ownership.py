"""Whose an appointment or a repeating appointment is (APPOINTMENT-F27): the professional's it is booked with. Without
«See the whole agenda» a person reads and touches only those of their own staff record; a caller that is not a person
has none of its own, so what its permission opens is the whole team's."""

from uuid import UUID

from django.db.models import Q
from live.context import OperationContext

from apps.appointment.models import Appointment, Recurring
from base.queries.ownership import Me, Owned, me

VIEW_ALL = "appointment.view_appointment"


def booked_with_them(person: Me) -> Q:
    return Q(staff_id__in=person.records)


APPOINTMENTS = Owned(Appointment, all_permission=VIEW_ALL, mine=booked_with_them)
SERIES = Owned(Recurring, all_permission=VIEW_ALL, mine=booked_with_them)


def is_own(ctx: OperationContext, staff_id: UUID | None) -> bool:
    """Whether «their own» appointments take those of the professional ``staff_id``, by the same rule as the reads. A
    caller that is not a person takes the whole team's, as the customer books with any professional, and is judged by
    her rules."""
    person = me(ctx)
    return person is None or staff_id in person.records


def sees_whose(ctx: OperationContext, staff_id: UUID) -> bool:
    """Whether the caller is told whose the appointments of the professional ``staff_id`` are when a time is taken:
    with «See the whole agenda», or a person's own. Hearing a time is taken opens no appointment by itself."""
    person = me(ctx)
    return ctx.has(VIEW_ALL) or (person is not None and staff_id in person.records)
