"""How the till names a person: who serves a check, and on its papers the waiter of a kitchen ticket and the cashier of
a receipt. Kitchen requires Sales, so both read it here; whoever acts is named by ``base.queries.people.actor_name``."""

from collections.abc import Iterable
from uuid import UUID

from django.contrib.auth import get_user_model
from live.context import OperationContext

from apps.sale.queries.other_apps import call_app
from base.queries.people import actor_name, person_label as profile_name


def person_names(usernames: Iterable[str]) -> dict[str, str]:
    """The people the apps keep by their username, by the name a person reads."""
    wanted = {name for name in usernames if name}
    if not wanted:
        return {}
    users = get_user_model()
    found = users.objects.filter(**{f"{users.USERNAME_FIELD}__in": wanted})
    return {user.get_username(): actor_name(user) for user in found}


def cashier_name(username: str) -> str:
    """Who charged, for the paper the customer takes: their name in this business («My profile», else their
    account's). Empty without one: an account without a name is named by its e-mail, and neither that nor the
    username goes on a customer's paper."""
    users = get_user_model()
    user = users.objects.filter(**{users.USERNAME_FIELD: username}).first() if username else None
    if user is None:
        return ""
    name = profile_name(user)
    return "" if "@" in name or name == user.get_username() else name


def member_name(ctx: OperationContext, staff_id: UUID | None) -> str:
    """A member of Staff by their full name, asked to Staff as whoever acts (Sales does not require it): someone not on
    the team is Staff's 404, Staff off or absent ``sale.staff_unavailable``. Empty for nobody («me»)."""
    if staff_id is None:
        return ""
    return call_app(ctx, "staff.member.detail", {"id": staff_id}, "sale.staff_unavailable").full_name
