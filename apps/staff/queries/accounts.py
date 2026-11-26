"""The user accounts a staff record can hang from (STAFF-F03)."""

from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, PermissionDenied
from live.operations import INTERNAL, operation

from apps.staff.schemas.accounts import AccountCheckIn, AccountCheckOut, AccountListIn, AccountPage
from base.models import HubUser, Membership

from .reads import _page

#: Who may read the accounts: whoever adds or edits a record (the «Hub user» selector of the form). The list asks for
#: the team's view to reach it, since an operation names one permission and an assistant tool needs one.
ACCOUNT_PERMISSIONS = ("staff.add_member", "staff.change_member")

USER_NOT_IN_BUSINESS = _("That Hub user has no access to this business.")


def _require_account_permission(ctx: OperationContext) -> None:
    if not any(ctx.has(permission) for permission in ACCOUNT_PERMISSIONS):
        raise PermissionDenied(
            gettext("Permission “%(permission)s” is required.") % {"permission": ACCOUNT_PERMISSIONS[0]}
        )


def accounts(ctx: OperationContext) -> QuerySet[HubUser]:
    """The people of the business's database (``base.HubUser``) who are still in it and have access to it (a
    ``base.Membership`` on the scope's host, which control keeps: read first, by username, since a query never joins
    two databases)."""
    with_access = list(Membership.objects.team(ctx.scope.key).values_list("user__username", flat=True))
    return HubUser.objects.filter(username__in=with_access, is_active=True)


def account(ctx: OperationContext, user_id: UUID) -> HubUser:
    """The account ``user_id`` of ``accounts``; one that is not refuses the datum, as a record's write refuses it."""
    person = accounts(ctx).filter(pk=user_id).first()
    if person is None:
        raise InvalidPayload(str(USER_NOT_IN_BUSINESS), fields={"user_id": str(USER_NOT_IN_BUSINESS)})
    return person


@operation(
    "staff.account.list",
    kind="query",
    permission="staff.view",  # and either of ACCOUNT_PERMISSIONS, checked below
    input=AccountListIn,
    output=AccountPage,
    ai={
        "asks": {
            "en": (
                "which accounts can I link to a staff record?",
                "who has a user I can attach to the team list?",
                "find Marta's account to hang her record from it",
            ),
            "es": (
                "¿qué cuentas puedo vincular a una ficha del personal?",
                "¿quién tiene usuario para engancharlo a su ficha?",
                "dame el usuario de Marta para vincular su ficha",
            ),
        },
        "description": "Lists the user accounts with access to this business that a staff record can be linked to: "
        "each one's user_id, the id staff.member.create and staff.member.update take, and its name.",
    },
)
def list_accounts(ctx: OperationContext, params: AccountListIn) -> dict:
    """STAFF-F03: the accounts a record can hang from, by name."""
    _require_account_permission(ctx)
    people = accounts(ctx)
    if params.user_id:
        people = people.filter(pk=params.user_id)
    if params.search:
        people = people.filter(Q(name__icontains=params.search) | Q(email__icontains=params.search))
    page = _page(people.order_by("name", "email", "id"), params)
    page["rows"] = [{"user_id": person.pk, "name": person.display_name} for person in page["rows"]]
    return page


# Not an assistant tool: what the assistant reads to check the account of a record before its card (``check``).
@operation(
    "staff.account.check",
    kind="query",
    permission=None,  # either of ACCOUNT_PERMISSIONS, checked below: no more than the writes it checks ask for
    input=AccountCheckIn,
    output=AccountCheckOut,
    ai=INTERNAL,
)
def check_account(ctx: OperationContext, params: AccountCheckIn) -> dict:
    """STAFF-F03: the account a record would hang from, refused as the record's write refuses it."""
    _require_account_permission(ctx)
    if params.user_id is None:
        return {"id": None, "name": ""}
    person = account(ctx, params.user_id)
    return {"id": person.pk, "name": person.display_name}
