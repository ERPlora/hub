"""The lines of a shift: the movements a session stored, and the charges, voids and refunds read from sale by
their time."""

import datetime as dt
from dataclasses import dataclass, replace
from uuid import UUID

from django.db.models import Q

from apps.cash_register.models import Movement, Session
from apps.sale.models import RefundPayment, Sale

CASH = "cash"


@dataclass(frozen=True)
class Line:
    """A line of a shift: a movement written by hand or by another app (``app``), or a charge, void or refund of sale."""

    key: str
    session_id: UUID | None
    type: str
    amount: int
    method_type: str
    method_name: str
    created_at: dt.datetime
    created_by: str
    description: str = ""
    app: str = ""
    sale_id: UUID | None = None
    sale_number: str = ""
    document_type: str = ""
    gift_total: int = 0
    sale_payment_id: UUID | None = None
    refund_payment_id: UUID | None = None

    @property
    def signed_amount(self) -> int:
        return -self.amount if self.type in Movement.OUTFLOWS else self.amount

    @property
    def cash(self) -> int:
        """What the line puts in (or takes out of) the drawer."""
        return self.signed_amount if self.method_type == CASH else 0


def movement_key(movement: Movement) -> str:
    """The stable key of a stored line: a copy keeps the key it had while it was read from sale."""
    if movement.type in (Movement.Type.SALE, Movement.Type.VOID):
        if movement.sale_payment_id is None:
            return f"gift-{movement.sale_id}"
        return f"{movement.type}-{movement.sale_payment_id}"
    if movement.type == Movement.Type.REFUND:
        return f"refund-{movement.refund_payment_id}"
    return str(movement.id)


def stored_line(movement: Movement) -> Line:
    return Line(
        key=movement_key(movement),
        session_id=movement.session_id,
        type=movement.type,
        amount=movement.amount,
        method_type=movement.method_type,
        method_name=movement.method_name,
        created_at=movement.created_at,
        created_by=movement.created_by,
        description=movement.description,
        app=movement.app,
        sale_id=movement.sale_id,
        sale_number=movement.sale_number,
        document_type=movement.document_type,
        gift_total=movement.gift_total,
        sale_payment_id=movement.sale_payment_id,
        refund_payment_id=movement.refund_payment_id,
    )


def _between(field: str, start: dt.datetime, end: dt.datetime | None) -> Q:
    window = Q(**{f"{field}__gte": start})
    return window & Q(**{f"{field}__lt": end}) if end is not None else window


def sale_lines(start: dt.datetime, end: dt.datetime | None = None) -> list[Line]:
    """The lines sale wrote in ``[start, end)`` and no session copied yet: every tender of a charge (and a
    sale of comps only, once), every tender of a void, every leg of a refund."""
    lines: list[Line] = []
    charged = Sale.objects.filter(_between("created_at", start, end)).prefetch_related(
        "payments"
    )
    for sale in charged:
        payments = list(sale.payments.all())
        common = {
            "session_id": None,
            "created_at": sale.created_at,
            "created_by": sale.created_by,
            "sale_id": sale.id,
            "sale_number": sale.number,
            "document_type": sale.document_type,
        }
        if not payments and sale.gift_total:
            lines.append(
                Line(
                    key=f"gift-{sale.id}",
                    type="sale",
                    amount=0,
                    method_type="other",
                    method_name="",
                    gift_total=sale.gift_total,
                    **common,
                )
            )
        for position, payment in enumerate(payments):
            lines.append(
                Line(
                    key=f"sale-{payment.id}",
                    type="sale",
                    amount=payment.amount,
                    method_type=payment.method_type,
                    method_name=payment.method_name,
                    gift_total=sale.gift_total if position == 0 else 0,
                    sale_payment_id=payment.id,
                    **common,
                )
            )
    voided = Sale.objects.filter(_between("voided_at", start, end)).prefetch_related(
        "payments"
    )
    for sale in voided:
        for payment in sale.payments.all():
            lines.append(
                Line(
                    key=f"void-{payment.id}",
                    session_id=None,
                    type="void",
                    amount=payment.amount,
                    method_type=payment.method_type,
                    method_name=payment.method_name,
                    created_at=sale.voided_at,
                    created_by=sale.voided_by,
                    sale_id=sale.id,
                    sale_number=sale.number,
                    document_type=sale.document_type,
                    sale_payment_id=payment.id,
                )
            )
    refunded = RefundPayment.objects.filter(
        _between("refund__created_at", start, end)
    ).select_related("refund__sale")
    for leg in refunded:
        lines.append(
            Line(
                key=f"refund-{leg.id}",
                session_id=None,
                type="refund",
                amount=leg.amount,
                method_type=leg.method_type,
                method_name=leg.method_name,
                created_at=leg.refund.created_at,
                created_by=leg.refund.created_by,
                sale_id=leg.refund.sale_id,
                sale_number=leg.refund.sale.number,
                document_type=leg.refund.sale.document_type,
                refund_payment_id=leg.id,
            )
        )
    return [line for line in lines if line.key not in _copied(lines)]


def _copied(lines: list[Line]) -> set[str]:
    """The keys of ``lines`` some session already copied, looked up by their sources (unique indexes)."""
    payments = [line.sale_payment_id for line in lines if line.sale_payment_id]
    refunds = [line.refund_payment_id for line in lines if line.refund_payment_id]
    comps = [line.sale_id for line in lines if line.key.startswith("gift-")]
    copied: set[str] = set()
    if payments:
        copied |= {
            f"{kind}-{payment}"
            for kind, payment in Movement.objects.filter(
                sale_payment_id__in=payments
            ).values_list("type", "sale_payment_id")
        }
    if refunds:
        copied |= {
            f"refund-{leg}"
            for leg in Movement.objects.filter(refund_payment_id__in=refunds).values_list(
                "refund_payment_id", flat=True
            )
        }
    if comps:
        copied |= {
            f"gift-{sale}"
            for sale in Movement.objects.filter(
                sale_id__in=comps, type="sale", sale_payment__isnull=True
            ).values_list("sale_id", flat=True)
        }
    return copied


def session_lines(session: Session, *, until: dt.datetime | None = None) -> list[Line]:
    """Every line of ``session``: its stored movements and, while it is open, sale's lines since it opened
    (up to ``until``: the cut-off of a forgotten session, which its auto-close will freeze)."""
    lines = [stored_line(movement) for movement in session.movements.all()]
    if session.is_open:
        lines += [
            replace(line, session_id=session.id)
            for line in sale_lines(session.opened_at, until)
        ]
    return lines
