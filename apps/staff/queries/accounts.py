"""The user accounts a staff record can hang from (STAFF-F03)."""

from django.db.models import Q
from django.utils.translation import gettext
from live.context import OperationContext
from live.errors import PermissionDenied
from live.operations import operation

from apps.staff.schemas.accounts import AccountListIn, AccountPage
from base.models import HubUser, Membership

from .reads import _page

#: Who may read the accounts: whoever adds or edits a record (the «Hub user» selector of the form).
ACCOUNT_PERMISSIONS = ("staff.add_member", "staff.change_member")


@operation(
    "staff.account.list",
    kind="query",
    permission=None,  # either of ACCOUNT_PERMISSIONS, checked below
    input=AccountListIn,
    output=AccountPage,
    ai={"description": "Lists the active user accounts with access to this business, to link one to a staff record."},
)
def list_accounts(ctx: OperationContext, params: AccountListIn) -> dict:
    """STAFF-F03: the accounts a record can hang from, by name: the people of the business's database
    (``base.HubUser``) who are still in it and have access to it (a ``base.Membership`` on the scope's host, which
    control keeps: read first, by username, since a query never joins two databases).
    """
    if not any(ctx.has(permission) for permission in ACCOUNT_PERMISSIONS):
        raise PermissionDenied(
            gettext("Permission “%(permission)s” is required.") % {"permission": ACCOUNT_PERMISSIONS[0]}
        )
    with_access = list(
        Membership.objects.filter(host=ctx.scope.key, user__is_active=True).values_list("user__username", flat=True)
    )
    people = HubUser.objects.filter(username__in=with_access, is_active=True)
    if params.user_id:
        people = people.filter(pk=params.user_id)
    if params.search:
        people = people.filter(Q(name__icontains=params.search) | Q(email__icontains=params.search))
    page = _page(people.order_by("name", "email", "id"), params)
    page["rows"] = [{"user_id": person.pk, "name": person.display_name} for person in page["rows"]]
    return page
