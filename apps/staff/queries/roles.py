"""The catalogue of roles with their active members, and the role a write names (STAFF-F01, F04, F23)."""

from uuid import UUID

from django.db.models import Count, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import InvalidPayload, NotFound
from live.operations import INTERNAL, operation

from apps.staff.models import Member, Role
from apps.staff.schemas.fields import ByIdIn
from apps.staff.schemas.roles import RoleListIn, RoleOut, RolePage, RoleResolveIn, RoleResolveOut
from base.ordering import list_order_for
from base.text_search import contains_text

from .reads import _page

ROLE_NOT_FOUND = _("That role does not exist in this business.")

ROLE_ORDER = {
    "name": ("name",),
    "description": ("description",),
    "color": ("color",),
    "order": ("order",),
    "is_active": ("is_active",),
    "member_count": ("member_count",),
    "id": (),
}

ROLE_UNAVAILABLE = _(
    "That role is not available: it does not exist in this business, or it has been deleted or retired."
)


def active_role(role_id: UUID | None, name: str | None) -> Role | None:
    """The active role ``role_id`` names, else the one called ``name`` (in any case); ``None`` when there is none."""
    roles = Role.objects.filter(is_active=True)
    if role_id is not None:
        return roles.filter(pk=role_id).first()
    return roles.filter(name__iexact=name).first()


def role_for(role_id: UUID | None, name: str | None) -> Role | None:
    """The active role given by id or by name, ``None`` when none is given; 422 on that field when there is none."""
    if role_id is None and not name:
        return None
    role = active_role(role_id, name)
    if role is None:
        field = "role_id" if role_id is not None else "role"
        raise InvalidPayload(str(ROLE_UNAVAILABLE), fields={field: str(ROLE_UNAVAILABLE)})
    return role


# Not an assistant tool: what the assistant reads to check a new member's role before its card (``check``).
@operation(
    "staff.role.resolve",
    kind="query",
    permission="staff.add_member",
    input=RoleResolveIn,
    output=RoleResolveOut,
    ai=INTERNAL,
)
def resolve_role(ctx: OperationContext, params: RoleResolveIn) -> dict:
    """STAFF-F01 (hub#538): the role a new member would take, refused as staff.member.create refuses it."""
    role = role_for(params.role_id, params.role)
    return {"id": role.id if role else None, "name": role.name if role else None}


@operation(
    "staff.role.list",
    kind="query",
    permission="staff.view",
    input=RoleListIn,
    output=RolePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what roles does the business have?",
                "list the roles with how many people hold each",
                "which roles can I give a new employee?",
            ),
            "es": (
                "muéstrame los roles que tengo creados",
                "lista los roles con cuánta gente tiene cada uno",
                "¿qué roles puedo darle a un empleado nuevo?",
            ),
        },
        "description": "Lists the roles of the business (catalogue labels such as stylist or waiter; "
        "they grant no permission) with how many active people hold each."
    },
)
def list_roles(ctx: OperationContext, params: RoleListIn) -> dict:
    roles = with_member_count(Role.objects.all())
    if params.search:
        roles = roles.filter(contains_text(params.search, "name", "description"))
    if params.is_active is not None:
        roles = roles.filter(is_active=params.is_active)
    if params.color:
        roles = roles.filter(color__iexact=params.color)
    if params.member_count_min is not None:
        roles = roles.filter(member_count__gte=params.member_count_min)
    if params.member_count_max is not None:
        roles = roles.filter(member_count__lte=params.member_count_max)
    return _page(roles.order_by(*list_order_for(params.sort, columns=ROLE_ORDER, nulls_last=True)), params)


# Not an assistant tool: what names a role on the card of a write (``schemas.fields.A_ROLE``), retired too, since a retired
# one can be brought back; the model finds them in ``staff.role.list``.
@operation(
    "staff.role.detail",
    kind="query",
    permission="staff.view",
    input=ByIdIn,
    output=RoleOut,
    ai=INTERNAL,
)
def role_detail(ctx: OperationContext, data: ByIdIn) -> Role:
    role = load_role(data.id)
    if role is None:
        raise NotFound(str(ROLE_NOT_FOUND))
    return role


def load_role(role_id: UUID) -> Role | None:
    return with_member_count(Role.objects.filter(pk=role_id)).first()


def with_member_count(roles: QuerySet[Role]) -> QuerySet[Role]:
    return roles.annotate(
        member_count=Count("members", filter=Q(members__status=Member.Status.ACTIVE))
    )
