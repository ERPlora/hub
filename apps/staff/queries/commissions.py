"""Whose a commission line is (STAFF-F21): a person's own, and the whole team's with «See pay».

Declared here and not in ``ownership.py``: the team reads every staff record (the directory, the agenda, the clock), so
the record is nobody's to hide; only the pay on it is a person's own. ``tests/test_guardrails_sensitive.py`` holds the
pay of the lines to this declaration."""

from django.db.models import Q

from apps.staff.models import Member
from base.queries.ownership import Owned

COMMISSION_LINES = Owned(
    Member,
    all_permission="staff.view_compensation",
    mine=lambda person: Q(pk__in=person.records),
)
