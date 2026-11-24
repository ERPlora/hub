"""The directory, a record, a person's own, the pay sheet and the staff figures (STAFF-F08, F09, F20, F21, F23)."""

from functools import reduce
from operator import or_

from django.db.models import Count, Q, QuerySet, Value
from django.db.models.functions import Concat
from live.context import OperationContext
from live.operations import operation

from apps.staff.models import Member, TimeOff
from apps.staff.schemas.fields import MemberRefIn
from apps.staff.schemas.members import (
    CompensationListIn,
    CompensationPage,
    CurrentMemberIn,
    CurrentMemberOut,
    MemberDetailOut,
    MemberListIn,
    MemberPage,
    MemberStatsIn,
    MemberStatsOut,
    MineIn,
    MineOut,
)
from base.ordering import list_order_for
from base.sensitive import VIEW_TEAM_CONTACT

from .reads import _page, business_today, live_members, own_member, resolve_member
from .time_off_reads import _away_on, live_time_off

# The model columns behind each sort key of the schemas.
MEMBER_ORDER = {
    "name": ("first_name", "last_name"),
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "role_name": ("role__name",),
    "status": ("status",),
    "is_bookable": ("is_bookable",),
    "hire_date": ("hire_date",),
    "color": ("color",),
    "user_id": ("user_id",),
    "id": (),
}
# The model lookup behind each filter of the directory; a filter left out keeps every record.
MEMBER_FILTERS = {
    "first_name": "first_name__icontains",
    "last_name": "last_name__icontains",
    "email": "email__icontains",
    "phone": "phone__icontains",
    "status": "status",
    "role_id": "role_id",
    "role_name": "role__name__iexact",
    "is_bookable": "is_bookable",
    "hire_date_from": "hire_date__gte",
    "hire_date_to": "hire_date__lte",
    "color": "color__iexact",
    "user_id": "user_id",
}
NO_FILTER = (None, "")
# The columns the directory's search looks into, and the contact ones only for whoever sees the team's contact.
MEMBER_SEARCH = ("search_name", "employee_number", "role__name")
CONTACT_SEARCH = ("email", "phone")


@operation(
    "staff.member.list",
    kind="query",
    permission="staff.view",
    input=MemberListIn,
    output=MemberPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "who works on the team?",
                "list the active staff",
                "show me the staff with their roles",
            ),
            "es": (
                "¿quién trabaja en el equipo?",
                "lista de empleados activos",
                "muéstrame la plantilla con sus roles",
            ),
        },
        "description": "Lists the staff members (the directory) with their status and role; never their pay."
    },
)
def list_members(ctx: OperationContext, params: MemberListIn) -> dict:
    """The directory with the old table's filters and sorts; never the pay (STAFF-F09)."""
    members = filter_members(live_members(), params, contact=ctx.has(VIEW_TEAM_CONTACT))
    return _page(members.order_by(*list_order_for(params.sort, columns=MEMBER_ORDER, nulls_last=True)), params)


def filter_members(members: QuerySet[Member], params: MemberListIn, *, contact: bool) -> QuerySet[Member]:
    """The directory's search and filters, shared by the pay sheet so both give the same rows. The search looks into
    the email and the phone only when ``contact``: the caller sees the team's contact details."""
    members = members.annotate(search_name=Concat("first_name", Value(" "), "last_name"))
    if params.search:
        columns = MEMBER_SEARCH + (CONTACT_SEARCH if contact else ())
        members = members.filter(reduce(or_, (Q(**{f"{column}__icontains": params.search}) for column in columns)))
    given = {name: getattr(params, name) for name in MEMBER_FILTERS}
    return members.filter(**{MEMBER_FILTERS[name]: value for name, value in given.items() if value not in NO_FILTER})


@operation(
    "staff.member.detail",
    kind="query",
    permission="staff.view",
    input=MemberRefIn,
    output=MemberDetailOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "Lucía's staff record: role, status and phone",
                "Pablo's contact details",
                "what role does Ana have and is she still active?",
            ),
            "es": (
                "¿qué datos tiene la ficha de Lucía?",
                "datos de contacto de Pablo",
                "¿qué rol tiene Ana y sigue activa?",
            ),
        },
        "description": "Returns the record of one staff member, by id or by name; never their pay."
    },
)
def member_detail(ctx: OperationContext, data: MemberRefIn) -> Member:
    return resolve_member(data.id, data.member)


@operation(
    "staff.member.mine",
    kind="query",
    permission="staff.view",
    input=MineIn,
    output=MineOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what is my own staff record?",
                "how much do I earn per hour and what is my commission?",
                "my details linked to my user",
            ),
            "es": (
                "¿qué ficha de empleado es la mía?",
                "mi comisión y lo que gano por hora",
                "mis datos vinculados a mi usuario",
            ),
        },
        "description": "Returns the staff record of the current user, with their own hourly rate and "
        "commission; empty when the user has no record."
    },
)
def my_record(ctx: OperationContext, data: MineIn) -> dict:
    return {"member": own_member(ctx)}


@operation(
    "staff.member.current",
    kind="query",
    # No Staff permission: whoever holds the session may know their own record, and a cashier who does
    # not see the team still sells as herself (SALE-F16). Only the id and the name: never the pay.
    permission=None,
    input=CurrentMemberIn,
    output=CurrentMemberOut,
    ai={
        "description": "Returns the id and name of the current user's own staff record: who a sale is "
        "attributed to when nobody else is named. Empty when the user has no record."
    },
)
def current_record(ctx: OperationContext, data: CurrentMemberIn) -> dict:
    return {"member": own_member(ctx)}


@operation(
    "staff.member.compensation",
    kind="query",
    permission="staff.view_compensation",
    input=CompensationListIn,
    output=CompensationPage,
    ai={
        "asks": {
            "en": (
                "how much does each person earn per hour?",
                "hourly rates and HR notes",
                "show me Pablo's hourly rate, commission and private notes",
            ),
            "es": (
                "¿cuánto gana por hora cada persona?",
                "lo que gana cada uno por hora y sus notas internas",
                "enséñame el sueldo y las notas privadas de Pablo",
            ),
        },
        "description": "Lists the hourly rate, commission and private HR notes of the staff members."
    },
)
def compensation(ctx: OperationContext, params: CompensationListIn) -> dict:
    """Pay and HR notes of each record, with both ids a person's sales can carry (STAFF-F21). Same
    filters, sort and pages as the directory: a screen reads the pay of exactly the rows it shows."""
    members = filter_members(live_members(), params, contact=ctx.has(VIEW_TEAM_CONTACT))
    if params.id:
        members = members.filter(pk=params.id)
    return _page(members.order_by(*list_order_for(params.sort, columns=MEMBER_ORDER, nulls_last=True)), params)


@operation(
    "staff.member.stats",
    kind="query",
    permission="staff.view",
    input=MemberStatsIn,
    output=MemberStatsOut,
    ai={
        "asks": {
            "en": (
                "how many active staff are there?",
                "summary: active, on leave and away today",
                "how many time-off requests are waiting for approval?",
            ),
            "es": (
                "¿cuántos empleados activos hay?",
                "resumen: activos, de baja y ausentes hoy",
                "¿cuántas ausencias faltan por aprobar?",
            ),
        },
        "description": "Returns staff statistics: members by status, members away today and time-off "
        "requests waiting for an answer."
    },
)
def member_stats(ctx: OperationContext, data: MemberStatsIn) -> dict:
    """Head count by status, who is away today and how many requests wait (STAFF-F20, STAFF-F23)."""
    counts = live_members().aggregate(
        total=Count("id"),
        active=Count("id", filter=Q(status=Member.Status.ACTIVE)),
        on_leave=Count("id", filter=Q(status=Member.Status.ON_LEAVE)),
        inactive=Count("id", filter=Q(status=Member.Status.INACTIVE)),
    )
    away = _away_on(business_today()).values("member_id").distinct().count()
    pending = live_time_off().filter(status=TimeOff.Status.PENDING).count()
    return {**counts, "absent_today": away, "pending_time_off": pending}
