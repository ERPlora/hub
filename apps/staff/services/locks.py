"""The record every write on a person locks first, so two on the same person never interleave."""

from uuid import UUID

from apps.staff.models import Member


def lock_members(ids) -> list[UUID]:
    """Locks the records ``ids`` (terminated ones too) in id order; the ids of those still there.

    Every write on a person locks their record before what hangs from it (their schedules, their time
    off, what other apps keep about them), and so does the Hub admin's «Delete» (admin.py) before Django
    deletes all that and then the record: the other way round, each waited for the other.
    """
    rows = Member.objects.select_for_update().filter(pk__in=ids).order_by("id")
    return list(rows.values_list("id", flat=True))


def _locked_live_member(member_id: UUID) -> Member | None:
    """The member's row locked until the end of the command, if it is still not terminated once locked."""
    return Member.objects.select_for_update().exclude(status=Member.Status.TERMINATED).filter(pk=member_id).first()
