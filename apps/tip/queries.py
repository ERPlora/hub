"""Read operations of the tips app (``READ ONLY``): its settings and the tips, which can be followed live (live.py); and
the finders services/ reuses: the settings row, a tip by its id or its sale's number, and a tip as a row."""

import datetime as dt
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation

from apps.sale.models import PaymentMethod
from apps.sale.schemas.fields import EmptyIn
from apps.tip.models import Settings, Tip
from apps.tip.schemas import SettingsOut, TipListIn, TipPage, TipRefIn
from base.business import business_zone
from base.operations import call


TIP_NOT_FOUND = _("That tip no longer exists.")
SEVERAL_TIPS = _("The sale %(number)s has several tips: say which one by its id.")

#: A payment method's suggestions from the factory: 3 %, 5 % and 10 % (what is usual in Spain, the WORKBOOK says).
FACTORY_SUGGESTIONS = [{"kind": "percent", "value": value} for value in (3, 5, 10)]
#: Staff's answer to «whose record is the caller's?»: what an employee's own tips are.
CURRENT_MEMBER = "staff.member.current"


def current_settings() -> Settings:
    """The business's row, or an unsaved one with the factory values."""
    return Settings.objects.first() or Settings()


def settings_row(settings: Settings) -> dict:
    methods = PaymentMethod.objects.filter(is_active=True).order_by("sort_order", "name", "id")
    return {
        "enabled": settings.enabled,
        "allow_custom": settings.allow_custom,
        "preselected": settings.preselected,
        "methods": [
            {
                "method_id": method.id,
                "method_name": method.display_name,
                "method_type": method.type,
                "suggestions": settings.suggestions.get(str(method.id), FACTORY_SUGGESTIONS),
            }
            for method in methods
        ],
    }


@operation(
    "tip.settings.get",
    kind="query",
    permission="tip.view_tip",
    input=EmptyIn,
    output=SettingsOut,
    expose_api=True,
    ai={
        "asks": {
            "en": ("show me the tip settings", "which tip suggestions does the card payment offer?"),
            "es": ("enséñame los ajustes de las propinas", "¿qué propinas sugiere el cobro con tarjeta?"),
        },
        "description": "The tip settings: whether a tip is asked for at the charge (off from the factory), which of the "
        "three suggestions comes chosen (0: «No tip»), whether another amount is allowed, and each active payment "
        "method's three suggestions, each a percentage of the check's total before discounts or an amount in cents.",
    },
)
def get_settings(ctx: OperationContext, params: EmptyIn) -> dict:
    return settings_row(current_settings())


def tips() -> QuerySet[Tip]:
    return Tip.objects.select_related("sale", "member")


def tip_row(tip: Tip) -> dict:
    return {
        "id": tip.id,
        "sale_id": tip.sale_id,
        "sale_number": tip.sale.number if tip.sale else "",
        "pool": tip.pool,
        "member_id": tip.member_id,
        "member_name": tip.member.full_name if tip.member else "",
        "method_id": tip.method_id,
        "method_name": tip.method_name,
        "method_type": tip.method_type,
        "amount": tip.amount,
        "status": tip.status,
        "created_at": tip.created_at,
        "created_by": tip.created_by,
        "adjusted_at": tip.adjusted_at,
        "adjusted_by": tip.adjusted_by,
        "adjust_reason": tip.adjust_reason,
        "voided_at": tip.voided_at,
        "voided_by": tip.voided_by,
        "void_reason": tip.void_reason,
    }


def find_tip(ref: TipRefIn, *, lock: bool = False) -> Tip:
    """The tip ``ref`` names: by its id, else the one tip of its sale (409 ``tip.tip_ambiguous`` with several)."""
    found = Tip.objects.select_for_update(of=("self",)) if lock else Tip.objects.all()
    if ref.id is not None:
        found = found.filter(pk=ref.id)
    else:
        found = found.filter(sale__number=ref.sale)
    rows = list(found.order_by("-created_at", "id")[:2])
    if not rows:
        raise NotFound(str(TIP_NOT_FOUND), code="tip.tip_not_found")
    if len(rows) > 1:
        raise Conflict(str(SEVERAL_TIPS) % {"number": ref.sale}, code="tip.tip_ambiguous")
    return tips().get(pk=rows[0].pk)


def own_member_id(ctx: OperationContext) -> UUID | None:
    """The caller's own record of the team, asked of Staff; ``None`` without one."""
    current = call(ctx, CURRENT_MEMBER, {})
    return current.member.id if current.member else None


def _day_start(day: dt.date) -> dt.datetime:
    return dt.datetime.combine(day, dt.time.min, tzinfo=business_zone())


def _filtered(params: TipListIn) -> QuerySet[Tip]:
    rows = tips()
    if params.search:
        rows = rows.filter(
            Q(sale__number__icontains=params.search)
            | Q(member__first_name__icontains=params.search)
            | Q(member__last_name__icontains=params.search)
        )
    for field in ("member_id", "method_type", "status"):
        if getattr(params, field) is not None:
            rows = rows.filter(**{field: getattr(params, field)})
    if params.date_from is not None:
        rows = rows.filter(created_at__gte=_day_start(params.date_from))
    if params.date_to is not None:
        rows = rows.filter(created_at__lt=_day_start(params.date_to + dt.timedelta(days=1)))
    return rows


@operation(
    "tip.tip.list",
    kind="query",
    permission="tip.view_tip",
    input=TipListIn,
    output=TipPage,
    expose_api=True,
    ai={
        "asks": {
            "en": ("what tips were left today?", "show me Bea's tips by card this week"),
            "es": ("¿qué propinas han dejado hoy?", "enséñame las propinas con tarjeta de Bea de esta semana"),
        },
        "description": "Lists the tips, newest first, a page at a time: each with its sale's number (none: to the pool), "
        "who it belongs to, its payment method, its amount in cents and whether it is active or voided, with who "
        "adjusted or voided it and why. Searches by a piece of the sale's number or of the person's name and filters by "
        "person, payment type, status and business days. An employee sees only their own.",
    },
)
def list_tips(ctx: OperationContext, params: TipListIn) -> dict:
    rows = _filtered(params)
    if not ctx.has("tip.manage"):
        own = own_member_id(ctx)
        rows = rows.filter(member_id=own) if own is not None else rows.none()
    rows = rows.order_by("-created_at", "id")
    return {
        "rows": [tip_row(tip) for tip in rows[params.offset : params.offset + params.limit]],
        "total": rows.count(),
        "limit": params.limit,
        "offset": params.offset,
    }
