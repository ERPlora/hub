"""Whose a staff record is, for the apps that count a person's own (``base.queries.ownership``)."""

from uuid import UUID

from apps.staff.models import Member


def records_of(username: str) -> frozenset[UUID]:
    """The staff record of the person the business knows as ``username`` (``HubUser.username``), unless terminated."""
    found = Member.objects.exclude(status=Member.Status.TERMINATED).filter(user__username=username)
    return frozenset(found.values_list("pk", flat=True)[:1])
