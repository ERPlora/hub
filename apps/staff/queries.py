"""Read operations of the staff app (``READ ONLY``), and the loaders services.py reuses.

A terminated record is the app's soft delete: no query returns it, nor its schedules or its time
off. «Today» is the business's day, on its clock (``business_today``). A staff member may
be named by id or by name (the assistant speaks names): ``resolve_member``.
"""

import datetime as dt
from decimal import ROUND_HALF_UP, Decimal
from typing import Any
from uuid import UUID

from babel.dates import format_date
from django.db.models import Count, F, Q, QuerySet, Value
from django.db.models.functions import Concat
from django.utils import timezone
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import AppInactive, Conflict, InvalidPayload, NotFound, PermissionDenied
from live.operations import INTERNAL, UnknownOperation, get, operation

from apps.staff.models import Member, Role, Schedule, StaffSettings, TimeOff
from base.business import babel_locale, business_zone
from base.models import HubUser, Membership
from base.queries import hub_user_of
from base.ordering import list_order_for
from apps.staff.schemas import (
    AccountListIn,
    AccountPage,
    AvailabilityIn,
    AvailabilityOut,
    ByIdIn,
    CommissionPage,
    CommissionReportIn,
    CommissionReportOut,
    CommissionSummaryIn,
    CompensationListIn,
    CompensationPage,
    CurrentMemberIn,
    CurrentMemberOut,
    MemberDetailOut,
    MemberListIn,
    MemberPage,
    MemberRefIn,
    MemberStatsIn,
    MemberStatsOut,
    MineIn,
    MineOut,
    MyTimeOffIn,
    PageIn,
    RoleListIn,
    RoleOut,
    RolePage,
    RoleResolveIn,
    RoleResolveOut,
    ScheduleListIn,
    ScheduleDetailOut,
    SchedulePage,
    SettingsGetIn,
    SettingsOut,
    TimeOffDetailOut,
    TimeOffNamedOut,
    TimeOffDetailPage,
    TimeOffListIn,
    TimeOffPage,
    TodayIn,
)

MEMBER_NOT_FOUND = _("That staff member does not exist in this business.")
AMBIGUOUS_MEMBER = _(
    "There are several staff members called “%(name)s”: %(matches)s. Say which one."
)
ROLE_NOT_FOUND = _("That role does not exist in this business.")
SCHEDULE_NOT_FOUND = _("That schedule does not exist in this business.")
TIME_OFF_NOT_FOUND = _("That time-off request does not exist in this business.")

TERMINATED = Member.Status.TERMINATED
#: The time off that blocks a new request, and that Deactivate looks at.
LIVE_TIME_OFF = (TimeOff.Status.PENDING, TimeOff.Status.APPROVED)
#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5

# The model columns behind each sort key of the schemas.
MEMBER_ORDER = {
    "name": ("first_name", "last_name"),
    "first_name": ("first_name",),
    "last_name": ("last_name",),
    "email": ("email",),
    "phone": ("phone",),
    "role_name": ("role__name",),
    "status": ("status",),
    "is_bookable": ("is_bookable",),
    "hire_date": ("hire_date",),
    "color": ("color",),
    "user_id": ("user_id",),
    "id": (),
}
ROLE_ORDER = {
    "name": ("name",),
    "description": ("description",),
    "color": ("color",),
    "order": ("order",),
    "is_active": ("is_active",),
    "member_count": ("member_count",),
    "id": (),
}
TIME_OFF_ORDER = {
    "start_date": ("start_date",),
    "end_date": ("end_date",),
    "member_name": ("member_name",),
    "leave_type": ("leave_type",),
    "status": ("status",),
    "is_full_day": ("is_full_day",),
    "approved_at": ("approved_at",),
    "id": (),
}


# --- Members ---------------------------------------------------------------------------------------


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
    members = filter_members(live_members(), params)
    return _page(members.order_by(*list_order_for(params.sort, columns=MEMBER_ORDER, nulls_last=True)), params)


def filter_members(members: QuerySet[Member], params: MemberListIn) -> QuerySet[Member]:
    """The directory's search and filters, shared by the pay sheet so both give the same rows."""
    members = members.annotate(search_name=Concat("first_name", Value(" "), "last_name"))
    if params.search:
        members = members.filter(
            Q(search_name__icontains=params.search)
            | Q(email__icontains=params.search)
            | Q(phone__icontains=params.search)
            | Q(employee_number__icontains=params.search)
            | Q(role__name__icontains=params.search)
        )
    for field in ("first_name", "last_name", "email", "phone"):
        value = getattr(params, field)
        if value:
            members = members.filter(**{f"{field}__icontains": value})
    if params.status:
        members = members.filter(status=params.status)
    if params.role_id:
        members = members.filter(role_id=params.role_id)
    if params.role_name:
        members = members.filter(role__name__iexact=params.role_name)
    if params.is_bookable is not None:
        members = members.filter(is_bookable=params.is_bookable)
    if params.hire_date_from:
        members = members.filter(hire_date__gte=params.hire_date_from)
    if params.hire_date_to:
        members = members.filter(hire_date__lte=params.hire_date_to)
    if params.color:
        members = members.filter(color__iexact=params.color)
    if params.user_id:
        members = members.filter(user_id=params.user_id)
    return members


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
    members = filter_members(live_members(), params)
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


@operation(
    "staff.commission.summary",
    kind="query",
    permission="staff.view_compensation",
    input=CommissionSummaryIn,
    output=CommissionPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "what commission rate does each professional have?",
                "the team's commission sheet with each one's linked user",
                "what percentage does Lucía get as commission?",
            ),
            "es": (
                "¿con qué comisión trabaja cada profesional?",
                "hoja de comisiones del equipo con el usuario vinculado de cada uno",
                "¿qué porcentaje se lleva Lucía de comisión?",
            ),
        },
        "description": "Returns each staff member who can earn a commission (active or on leave) with "
        "their record id, the user id their record hangs from and their commission rate. What each one "
        "earned in a period is staff.commission.report."
    },
)
def commission_summary(ctx: OperationContext, params: CommissionSummaryIn) -> dict:
    members = live_members().exclude(status=Member.Status.INACTIVE)
    if params.search:
        members = members.annotate(
            search_name=Concat("first_name", Value(" "), "last_name")
        ).filter(search_name__icontains=params.search)
    return _page(members.order_by("first_name", "last_name", "id"), params)


#: Sales' figure per professional (SALE-F28), asked by name: Sales is no requirement of Staff.
SALES_BY_STAFF = "sale.sale.by_staff"
#: Who can earn a commission: listed in the report even without sales (STAFF-F21).
EARNING = (Member.Status.ACTIVE, Member.Status.ON_LEAVE)


@operation(
    "staff.commission.report",
    kind="query",
    permission="staff.view_compensation",
    input=CommissionReportIn,
    output=CommissionReportOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "how much commission did each stylist earn this week?",
                "work out the team's commissions for yesterday",
                "sales and commission per professional this month",
            ),
            "es": (
                "¿cuánto ha ganado de comisión cada estilista esta semana?",
                "calcula las comisiones del equipo de ayer",
                "comisiones ganadas por cada profesional en lo que va de mes",
            ),
        },
        "description": "The commission each professional earned in a period of business days: today by "
        "default, yesterday, this week, this month or two days of your own. Per person: what they sold "
        "(refunds and the vouchers they sold taken off, the value of the voucher sessions they did added), their rate and their "
        "commission, in cents, and the totals. Lists everyone "
        "who can earn a commission, also without sales, and whoever sold in the period though no longer "
        "active. Without Sales in the business, sales_available is false and nobody is listed."
    },
)
def commission_report(ctx: OperationContext, params: CommissionReportIn) -> dict:
    """STAFF-F21 step 3: what each professional produced in the period (``sale.sale.by_staff``, refunds and vouchers
    sold taken off, voucher sessions added) times their rate, rounded half up once per person. A sale names its professional by the
    record's id; one with nobody, or with an id of no record, counts for nobody."""
    first, last = report_period(params, business_today())
    sold = _sold_by_staff(ctx, first, last)
    if sold is None:
        return {
            "date_from": first,
            "date_to": last,
            "sales_available": False,
            "rows": [],
            "total_sold": 0,
            "total_commission": 0,
        }
    members = (
        Member.objects.filter(Q(status__in=EARNING) | Q(pk__in=list(sold)))
        .annotate(role_name=F("role__name"))
        .order_by("first_name", "last_name", "id")
    )
    rows = [
        {
            "member_id": member.id,
            "full_name": member.full_name,
            "role_name": member.role_name,
            "status": member.status,
            "commission_rate": member.commission_rate,
            "sold": sold.get(member.id, 0),
            "commission": commission_cents(sold.get(member.id, 0), member.commission_rate),
        }
        for member in members
    ]
    return {
        "date_from": first,
        "date_to": last,
        "sales_available": True,
        "rows": rows,
        "total_sold": sum(row["sold"] for row in rows),
        "total_commission": sum(row["commission"] for row in rows),
    }


def report_period(params: CommissionReportIn, today: dt.date) -> tuple[dt.date, dt.date]:
    """The report's first and last business day: the days given, or the period counted up to ``today``
    (a week starts on Monday)."""
    if params.date_from is not None and params.date_to is not None:
        return params.date_from, params.date_to
    if params.period == "yesterday":
        yesterday = today - dt.timedelta(days=1)
        return yesterday, yesterday
    if params.period == "this_week":
        return today - dt.timedelta(days=today.weekday()), today
    if params.period == "this_month":
        return today.replace(day=1), today
    return today, today


def commission_cents(sold: int, rate: Decimal) -> int:
    """``sold`` x ``rate`` / 100 in whole cents, half up (126.5 → 127)."""
    return int((Decimal(sold) * rate / 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _sold_by_staff(ctx: OperationContext, first: dt.date, last: dt.date) -> dict[UUID, int] | None:
    """What each record produced from ``first`` to ``last``, refunds and vouchers sold taken off and voucher sessions added, asked to
    Sales for the caller (its permission applies); ``None`` when the business has no Sales (absent or off)."""
    try:
        op = get(SALES_BY_STAFF)
        page = op(ctx, op.input.model_validate({"date_from": first, "date_to": last}))
    except (UnknownOperation, AppInactive):
        return None
    return {row.staff_id: row.production_total for row in page.rows}


def live_members() -> QuerySet[Member]:
    """Every record that is not terminated, with its role's name as ``role_name``."""
    return Member.objects.exclude(status=TERMINATED).annotate(role_name=F("role__name"))


def load_member(member_id: UUID) -> Member | None:
    """A live record (a ``MemberDetailOut``), or ``None``; services.py returns it after a write."""
    return live_members().filter(pk=member_id).first()


def resolve_member(
    member_id: UUID | None, name: str | None, *, lock: bool = False
) -> Member:
    """The live record named by id, or by name: an exact full name first, then a part of it.

    ``lock`` takes the record's row until the end of the command's transaction. ``NotFound`` when
    nothing matches; 409 ``staff.ambiguous_member`` naming the candidates when several do.
    """
    members = live_members().annotate(
        search_name=Concat("first_name", Value(" "), "last_name")
    )
    if lock:
        members = members.select_for_update(of=("self",))
    if member_id is not None:
        member = members.filter(pk=member_id).first()
    else:
        ordered = members.order_by("first_name", "last_name", "id")
        matches = list(
            ordered.filter(search_name__iexact=name)[: MAX_CANDIDATES + 1]
        ) or list(ordered.filter(search_name__icontains=name)[: MAX_CANDIDATES + 1])
        if len(matches) > 1:
            names = ", ".join(match.full_name for match in matches[:MAX_CANDIDATES])
            raise Conflict(
                str(AMBIGUOUS_MEMBER) % {"name": name, "matches": names},
                code="staff.ambiguous_member",
            )
        member = matches[0] if matches else None
    if member is None:
        raise NotFound(str(MEMBER_NOT_FOUND))
    return member


def actor_user_id(ctx: OperationContext) -> UUID | None:
    """The id of the caller's person in the business's database (``base.HubUser``); ``None`` for the platform itself,
    an API key, an anonymous caller or a person it does not know yet (who has no record hanging from them)."""
    person = hub_user_of(ctx)
    return None if person is None else person.pk


def own_member(ctx: OperationContext) -> Member | None:
    """The live record linked to the caller's user, if any."""
    user_id = actor_user_id(ctx)
    return None if user_id is None else live_members().filter(user_id=user_id).first()


def business_today() -> dt.date:
    """Today in the business's time zone (hub#771)."""
    return timezone.localdate(timezone=business_zone())


# --- Accounts --------------------------------------------------------------------------------------

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


# --- Roles -----------------------------------------------------------------------------------------


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
        roles = roles.filter(
            Q(name__icontains=params.search) | Q(description__icontains=params.search)
        )
    if params.is_active is not None:
        roles = roles.filter(is_active=params.is_active)
    if params.color:
        roles = roles.filter(color__iexact=params.color)
    if params.member_count_min is not None:
        roles = roles.filter(member_count__gte=params.member_count_min)
    if params.member_count_max is not None:
        roles = roles.filter(member_count__lte=params.member_count_max)
    return _page(roles.order_by(*list_order_for(params.sort, columns=ROLE_ORDER, nulls_last=True)), params)


# Not an assistant tool: what names a role on the card of a write (``schemas.A_ROLE``), retired too, since a retired
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


# --- Schedules -------------------------------------------------------------------------------------


@operation(
    "staff.schedule.list",
    kind="query",
    permission="staff.view",
    input=ScheduleListIn,
    output=SchedulePage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "which schedules does Lucía have?",
                "list Pablo's schedules",
                "what schedule is Ana on now?",
            ),
            "es": (
                "¿qué horarios tiene Lucía?",
                "lista los horarios de Pablo",
                "¿con qué horario está Ana ahora?",
            ),
        },
        "description": "Lists the work schedules of a staff member (by id or by name), each with its "
        "weekly working hours and breaks."
    },
)
def list_schedules(ctx: OperationContext, params: ScheduleListIn) -> dict:
    """A member's schedules, the default first, each with its week (STAFF-F13–F15)."""
    member = resolve_member(params.member_id, params.member)
    schedules = (
        live_schedules().filter(member=member).order_by("-is_default", "name", "id")
    )
    return _page(schedules, params)


@operation(
    "staff.schedule.detail",
    kind="query",
    permission="staff.view",
    input=ByIdIn,
    output=ScheduleDetailOut,
    ai={
        "asks": {
            "en": (
                "show me Lucía's schedule day by day",
                "what time is Pablo's break each day of his schedule?",
                "the hours of Ana's summer schedule",
            ),
            "es": (
                "enséñame el horario de Lucía día por día",
                "¿a qué hora descansa Pablo cada día de su horario?",
                "las horas del horario de verano de Ana",
            ),
        },
        "description": "Returns one work schedule with its weekly working hours.",
    },
)
def schedule_detail(ctx: OperationContext, data: ByIdIn) -> Schedule:
    schedule = load_schedule(data.id)
    if schedule is None:
        raise NotFound(str(SCHEDULE_NOT_FOUND))
    schedule.label = f"{schedule.member.full_name} · {schedule.name}"
    return schedule


def live_schedules() -> QuerySet[Schedule]:
    return Schedule.objects.exclude(member__status=TERMINATED).prefetch_related("days")


def load_schedule(schedule_id: UUID) -> Schedule | None:
    return live_schedules().filter(pk=schedule_id).first()


# --- Availability ----------------------------------------------------------------------------------


@operation(
    "staff.availability.for_member",
    kind="query",
    permission="staff.view",
    input=AvailabilityIn,
    output=AvailabilityOut,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "can Lucía work on Saturday afternoon?",
                "which days is Pablo free this month, counting his vacation?",
                "at what times can Ana see clients on Monday?",
            ),
            "es": (
                "¿Lucía puede trabajar el sábado por la tarde?",
                "¿qué días tiene libres Pablo este mes, contando sus vacaciones?",
                "¿a qué horas puede atender Ana el lunes?",
            ),
        },
        "description": "Returns when a staff member can work on each day of a date range: the shifts of "
        "the schedule that governs the day minus their approved time off. The authoritative answer to "
        "when a professional can work."
    },
)
def member_availability(ctx: OperationContext, data: AvailabilityIn) -> dict:
    """Per day: the governing schedule, its shifts, the approved absences and what is left (STAFF-F16).

    It knows nothing about appointments: it answers «when could this person work»; the caller
    intersects it with the rest. ``schedule_id`` null means no schedule governs that day.
    """
    member = resolve_member(data.member_id, data.member)
    schedules = list(
        Schedule.objects.filter(member=member, is_active=True).prefetch_related("days")
    )
    approved = list(
        TimeOff.objects.filter(
            member=member,
            status=TimeOff.Status.APPROVED,
            start_date__lte=data.date_to,
            end_date__gte=data.date_from,
        )
    )
    days = []
    for offset in range((data.date_to - data.date_from).days + 1):
        day = data.date_from + dt.timedelta(days=offset)
        schedule = governing_schedule(schedules, day)
        shifts = _shifts(schedule, day)
        absences = sorted(
            (
                absence
                for absence in approved
                if absence.start_date <= day <= absence.end_date
            ),
            key=lambda absence: (
                not absence.is_full_day,
                absence.start_time or dt.time.min,
                absence.id,
            ),
        )
        days.append(
            {
                "date": day,
                "schedule_id": schedule.id if schedule else None,
                "shifts": [{"start": start, "end": end} for start, end in shifts],
                "time_off": absences,
                "available": [
                    {"start": start, "end": end}
                    for start, end in _subtract(shifts, absences)
                ],
            }
        )
    return {"member_id": member.id, "days": days}


def governing_schedule(schedules: list[Schedule], day: dt.date) -> Schedule | None:
    """The active schedule that rules ``day``: a non-default one beats the default, then the latest
    «valid from», then the newest (STAFF-F13)."""
    valid = [
        schedule
        for schedule in schedules
        if (schedule.effective_from is None or schedule.effective_from <= day)
        and (schedule.effective_until is None or schedule.effective_until >= day)
    ]
    if not valid:
        return None
    return min(
        valid,
        key=lambda schedule: (
            schedule.is_default,
            schedule.effective_from is None,
            -(schedule.effective_from.toordinal() if schedule.effective_from else 0),
            -schedule.created_at.timestamp(),
            -schedule.id.int,
        ),
    )


def _shifts(schedule: Schedule | None, day: dt.date) -> list[tuple[dt.time, dt.time]]:
    """The working stretches of ``day`` under ``schedule``, split around the break; empty ones dropped."""
    if schedule is None:
        return []
    for working in schedule.days.all():
        if working.weekday == day.weekday():
            if working.break_start is None:
                pieces = [(working.start_time, working.end_time)]
            else:
                pieces = [
                    (working.start_time, working.break_start),
                    (working.break_end, working.end_time),
                ]
            return [(start, end) for start, end in pieces if start < end]
    return []


def _subtract(
    shifts: list[tuple[dt.time, dt.time]], absences: list[TimeOff]
) -> list[tuple[dt.time, dt.time]]:
    """``shifts`` minus the absences: a full day leaves nothing, a part day cuts its hours out.

    By hand: the only interval library of the right size (``portion``) is one person's project, and
    the ones that pass (``sympy``, ``pandas``) are far too big for this.
    """
    if any(absence.is_full_day for absence in absences):
        return []
    free = list(shifts)
    for absence in absences:
        remaining = []
        for start, end in free:
            if absence.end_time <= start or absence.start_time >= end:
                remaining.append((start, end))
                continue
            if start < absence.start_time:
                remaining.append((start, absence.start_time))
            if absence.end_time < end:
                remaining.append((absence.end_time, end))
        free = remaining
    return free


# --- Time off --------------------------------------------------------------------------------------


@operation(
    "staff.time_off.list",
    kind="query",
    permission="staff.view_time_off",
    input=TimeOffListIn,
    output=TimeOffPage,
    ai={
        "asks": {
            "en": (
                "list all the time off",
                "which vacations are there this month?",
                "Lucía's pending time off",
            ),
            "es": (
                "lista todas las ausencias",
                "vacaciones de este mes",
                "ausencias pendientes de Lucía",
            ),
        },
        "description": "Lists the time-off requests of the staff (without their reason), filtered by "
        "person, status, type or dates."
    },
)
def list_time_off(ctx: OperationContext, params: TimeOffListIn) -> dict:
    time_off = live_time_off()
    if params.search:
        time_off = time_off.filter(member_name__icontains=params.search)
    if params.member_id:
        time_off = time_off.filter(member_id=params.member_id)
    if params.status:
        time_off = time_off.filter(status=params.status)
    if params.leave_type:
        time_off = time_off.filter(leave_type=params.leave_type)
    if params.is_full_day is not None:
        time_off = time_off.filter(is_full_day=params.is_full_day)
    if params.approved_by_id:
        time_off = time_off.filter(approved_by_id=params.approved_by_id)
    if params.date_from:
        time_off = time_off.filter(end_date__gte=params.date_from)
    if params.date_to:
        time_off = time_off.filter(start_date__lte=params.date_to)
    for field, lookup in (
        ("start_date_from", "start_date__gte"),
        ("start_date_to", "start_date__lte"),
        ("end_date_from", "end_date__gte"),
        ("end_date_to", "end_date__lte"),
    ):
        value = getattr(params, field)
        if value:
            time_off = time_off.filter(**{lookup: value})
    return _page(time_off.order_by(*list_order_for(params.sort, columns=TIME_OFF_ORDER, nulls_last=True)), params)


@operation(
    "staff.time_off.detail",
    kind="query",
    permission="staff.view_time_off_detail",
    input=ByIdIn,
    output=TimeOffDetailOut,
    ai={
        "asks": {
            "en": (
                "open Pablo's time off and tell me who approved it",
                "what reason and notes does Ana's vacation have?",
                "why is Lucía absent on Monday?",
            ),
            "es": (
                "¿quién aprobó las vacaciones de Pablo?",
                "¿qué motivo y notas tiene la ausencia de Ana?",
                "¿por qué falta Lucía el lunes?",
            ),
        },
        "description": "Returns one time-off request with its reason, notes and who approved it."
    },
)
def time_off_detail(ctx: OperationContext, data: ByIdIn) -> TimeOff:
    time_off = load_time_off(data.id)
    if time_off is None:
        raise NotFound(str(TIME_OFF_NOT_FOUND))
    return time_off


# Not an assistant tool: what names a request on the card of a write (``schemas.A_TIME_OFF``). The detail holds its
# reason and needs a right an employee withdrawing their own does not have; this says what their list already shows.
@operation(
    "staff.time_off.get",
    kind="query",
    permission="staff.view_time_off",
    input=ByIdIn,
    output=TimeOffNamedOut,
    ai=INTERNAL,
)
def get_time_off(ctx: OperationContext, data: ByIdIn) -> TimeOff:
    time_off = live_time_off().filter(pk=data.id).first()
    if time_off is None:
        raise NotFound(str(TIME_OFF_NOT_FOUND))
    days = _days_of(time_off, ctx.language)
    time_off.label = f"{time_off.member_name} · {time_off.leave_type_label} · {days}"
    return time_off


def _days_of(time_off: TimeOff, language: str) -> str:
    """Its days as the card writes a date: the one day, or the first and the last."""
    locale = babel_locale(language)
    first = format_date(time_off.start_date, "medium", locale=locale)
    if time_off.end_date == time_off.start_date:
        return first
    return f"{first} – {format_date(time_off.end_date, 'medium', locale=locale)}"


@operation(
    "staff.time_off.today",
    kind="query",
    permission="staff.view_time_off",
    input=TodayIn,
    output=TimeOffPage,
    ai={
        "asks": {
            "en": (
                "who is off today?",
                "who is away today on approved leave?",
                "is anyone on vacation today?",
            ),
            "es": (
                "¿quién falta hoy?",
                "¿quién libra hoy?",
                "¿hay alguien de vacaciones hoy?",
            ),
        },
        "description": "Lists the approved time off covering today: who is away today."
    },
)
def away_today(ctx: OperationContext, params: TodayIn) -> dict:
    """Approved time off covering today: whole days first, then by name (STAFF-F20)."""
    time_off = _away_on(business_today()).order_by(
        "-is_full_day", "member__first_name", "member__last_name", "start_time", "id"
    )
    return _page(time_off, params)


@operation(
    "staff.time_off.mine",
    kind="query",
    permission="staff.view_time_off",
    input=MyTimeOffIn,
    output=TimeOffDetailPage,
    expose_api=True,
    ai={
        "asks": {
            "en": (
                "my time-off requests",
                "have they approved my vacation?",
                "what state are my days off in?",
            ),
            "es": (
                "¿cómo están mis ausencias?",
                "estado de mis vacaciones y días libres",
                "¿me han aprobado mis días libres?",
            ),
        },
        "description": "Lists the time-off requests of the current user, with their reason and notes."
    },
)
def my_time_off(ctx: OperationContext, params: MyTimeOffIn) -> dict:
    """The caller's own time off; empty without a linked record (STAFF-F08)."""
    member = own_member(ctx)
    if member is None:
        return {"rows": [], "total": 0, "limit": params.limit, "offset": params.offset}
    page = _page(
        _with_approver(live_time_off().filter(member=member)).order_by(
            "-start_date", "id"
        ),
        params,
    )
    _name_approvers(page["rows"])
    return page


def live_time_off() -> QuerySet[TimeOff]:
    """Time off of records that are not terminated, with ``member_name``."""
    return TimeOff.objects.exclude(member__status=TERMINATED).annotate(
        member_name=Concat("member__first_name", Value(" "), "member__last_name")
    )


def load_time_off(time_off_id: UUID) -> TimeOff | None:
    """A time off of a live record with its reason and its approver's name (a ``TimeOffDetailOut``)."""
    time_off = _with_approver(live_time_off().filter(pk=time_off_id)).first()
    if time_off is not None:
        _name_approvers([time_off])
    return time_off


def overlapping_time_off(
    member: Member,
    start_date: dt.date,
    end_date: dt.date,
    start_time: dt.time | None,
    end_time: dt.time | None,
    statuses: tuple[str, ...] = LIVE_TIME_OFF,
    exclude_id: UUID | None = None,
) -> QuerySet[TimeOff]:
    """The member's time off in ``statuses`` that shares a day and, when both are part days, an hour.

    The same hours repeat on every day of a range, so two part days clash only if their hours do.
    """
    clashes = TimeOff.objects.filter(
        member=member,
        status__in=statuses,
        start_date__lte=end_date,
        end_date__gte=start_date,
    )
    if start_time is not None and end_time is not None:
        clashes = clashes.filter(
            Q(is_full_day=True) | Q(start_time__lt=end_time, end_time__gt=start_time)
        )
    if exclude_id is not None:
        clashes = clashes.exclude(pk=exclude_id)
    return clashes


def _away_on(day: dt.date) -> QuerySet[TimeOff]:
    return live_time_off().filter(
        status=TimeOff.Status.APPROVED, start_date__lte=day, end_date__gte=day
    )


def _with_approver(time_off: QuerySet[TimeOff]) -> QuerySet[TimeOff]:
    return time_off.select_related("approved_by")


def _name_approvers(rows: list[TimeOff]) -> None:
    for row in rows:
        person = row.approved_by
        row.approved_by_name = (person.name or person.username) if person is not None else None


# --- Settings --------------------------------------------------------------------------------------


@operation(
    "staff.settings.get",
    kind="query",
    permission="staff.view",
    input=SettingsGetIn,
    output=SettingsOut,
    ai={
        "asks": {
            "en": (
                "what working day does a new schedule propose by default?",
                "what are the default shift hours?",
                "which break does a new schedule suggest?",
            ),
            "es": (
                "¿qué jornada propone por defecto un horario nuevo?",
                "¿cuál es el horario por defecto de los turnos?",
                "¿cuánto descanso trae por defecto un turno recién creado?",
            ),
        },
        "description": "Returns the default working day that a new schedule proposes (start, end and break)."
    },
)
def get_settings(ctx: OperationContext, data: SettingsGetIn) -> dict:
    """The saved settings, or the defaults while the business has saved none (STAFF-F22)."""
    return settings_out(StaffSettings.objects.first() or StaffSettings())


def settings_out(row: StaffSettings) -> dict:
    """The settings as the screen shows them: hours as HH:MM, never with seconds."""
    return {
        **{field: getattr(row, field) for field in SettingsOut.model_fields},
        "default_work_start": row.default_work_start.strftime("%H:%M"),
        "default_work_end": row.default_work_end.strftime("%H:%M"),
    }


# --- Pages and sorts -------------------------------------------------------------------------------


def _page(rows: QuerySet[Any], params: PageIn) -> dict:
    return {
        "rows": list(rows[params.offset : params.offset + params.limit]),
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
