"""The sale lines that fell in no shift: where they are, which they are, and how many and their cash."""

import datetime as dt

from django.db.models import Count as CountOf
from django.db.models import Exists, OuterRef, Q, Sum
from django.db.models.functions import Coalesce
from live.context import OperationContext

from apps.cash_register.models import Movement, Session, Settings
from apps.cash_register.queries.auto_close import auto_close_due_at
from apps.cash_register.queries.lines import CASH, Line, _between, sale_lines
from apps.cash_register.queries.ownership import SESSIONS
from apps.sale.models.payments import SalePayment
from apps.sale.models.refunds import RefundPayment
from apps.sale.models.sales import Sale

Window = tuple[dt.datetime, dt.datetime | None]


def open_session_now(ctx: OperationContext) -> Session | None:
    return (
        SESSIONS.visible(ctx).select_related("register")
        .filter(status=Session.Status.OPEN)
        .first()
    )


def unassigned_window(
    session: Session | None, settings: Settings, now: dt.datetime
) -> Window | None:
    """Where the sale lines that fell in no shift are (CASH_REGISTER-F17):

    - an open session past its daily cut-off: what came after the cut (its auto-close leaves it out);
    - an open session: the stragglers of the previous one (confirmed while it was closing);
    - the drawer closed: everything since the last closed session opened, stragglers included.

    None before the first shift ever closed (a hub's history before Cash register is no one's)."""
    if session is not None:
        cut = auto_close_due_at(session, settings, now)
        if cut is not None:
            return cut, None
        previous = (
            Session.objects.filter(
                status=Session.Status.CLOSED, opened_at__lt=session.opened_at
            )
            .order_by("-opened_at", "-id")
            .first()
        )
        return (previous.opened_at, previous.closed_at) if previous else None
    latest = (
        Session.objects.filter(status=Session.Status.CLOSED)
        .order_by("-opened_at", "-id")
        .first()
    )
    return (latest.opened_at, None) if latest else None


def unassigned_lines(ctx: OperationContext, settings: Settings, now: dt.datetime) -> list[Line]:
    window = unassigned_window(open_session_now(ctx), settings, now)
    return sale_lines(*window) if window else []


def unassigned_totals(window: Window) -> tuple[int, int]:
    """How many sale lines of ``window`` no session copied, and their cash: counted in SQL, never listed."""
    start, end = window
    cash = Q(method_type=CASH)

    def tally(rows) -> tuple[int, int]:
        totals = rows.aggregate(
            n=CountOf("id"), cash=Coalesce(Sum("amount", filter=cash), 0)
        )
        return totals["n"], totals["cash"]

    def copied_as(kind: str):
        return Movement.objects.filter(sale_payment=OuterRef("pk"), type=kind)

    charged = tally(
        SalePayment.objects.filter(_between("sale__created_at", start, end)).exclude(
            Exists(copied_as("sale"))
        )
    )
    voided = tally(
        SalePayment.objects.filter(_between("sale__voided_at", start, end)).exclude(
            Exists(copied_as("void"))
        )
    )
    refunded = tally(
        RefundPayment.objects.filter(_between("refund__created_at", start, end)).exclude(
            Exists(Movement.objects.filter(refund_payment=OuterRef("pk")))
        )
    )
    comps = (
        Sale.objects.filter(_between("created_at", start, end), gift_total__gt=0)
        .exclude(Exists(SalePayment.objects.filter(sale=OuterRef("pk"))))
        .exclude(
            Exists(
                Movement.objects.filter(
                    sale=OuterRef("pk"), type="sale", sale_payment__isnull=True
                )
            )
        )
        .count()
    )
    return (
        charged[0] + voided[0] + refunded[0] + comps,
        charged[1] - voided[1] - refunded[1],
    )
