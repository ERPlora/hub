"""Whose a cash shift is (CASH_REGISTER-F11): whoever opened it and whoever closed it. Without «See all register
sessions» a person reads only theirs, and the shift open now: one is open at a time in the whole business, and it is
the drawer everyone at the till charges cash into (Sales asks for it), counts and closes."""

from django.db.models import Q

from apps.cash_register.models import Session
from base.queries.ownership import Owned

SESSIONS = Owned(
    Session,
    all_permission="cash_register.view_all_sessions",
    mine=lambda person: (
        Q(status=Session.Status.OPEN)
        | Q(opened_by_username=person.username)
        | Q(closed_by_username=person.username)
    ),
)
