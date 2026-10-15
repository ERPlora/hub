"""Read operations of the payment app (``READ ONLY``): the payments, one payment, and the methods.

Every list pages (``limit`` ≤ 100) with ``id`` as the last tie-break, so pages never overlap. The
``find_*`` helpers resolve how a person names a record (assistant, voice): a method by its id, else
its exact name, else the only name that contains it (several → 409 ``payment.method_ambiguous`` naming
them); a payment by its id or its reference. services.py uses them too, inside its own transaction.
"""

from uuid import UUID

from django.db.models import F, Q, QuerySet
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import operation
from stdnum import iban as iban_number

from apps.payment.models import Payment, PaymentMethod
from apps.payment.schemas import (
    MethodListIn,
    MethodOut,
    MethodPage,
    MethodRefIn,
    PaymentListIn,
    PaymentOut,
    PaymentPage,
    PaymentRefIn,
)

#: The business's currency until the Hub keeps its own (the same euro the till charges in).
CURRENCY = "EUR"

METHOD_NOT_FOUND = _("That payment method does not exist in this business.")
METHOD_AMBIGUOUS = _(
    "“%(said)s” matches several payment methods: %(names)s. Say which one."
)
PAYMENT_NOT_FOUND = _("That payment does not exist in this business.")

#: How many names an ambiguous reference lists.
MAX_CANDIDATES = 5

PAYMENT_ORDER = {
    "reference": ("reference",),
    "payment_date": ("payment_date",),
    "beneficiary_name": ("beneficiary_name",),
    "amount": ("amount",),
    "currency": ("currency",),
    "status": ("status",),
    "method_name": ("method__name",),
    "created_at": ("created_at",),
}
METHOD_ORDER = {
    "name": ("name",),
    "method_type": ("method_type",),
    "bank_account_ref": ("bank_account_ref",),
    "is_active": ("is_active",),
}


def business_currency() -> str:
    """The currency a payment is in when it does not say one (the old ``payments.hub_currency``)."""
    return CURRENCY


# --- Shared with services.py, inside the command's own transaction --------------------------------


def find_method(
    method_id: UUID | None, said: str | None, *, lock: bool = False
) -> PaymentMethod:
    """A method by id, or by its name: the exact one, else the only one that contains it."""
    if method_id is None:
        candidates = []
        for lookup in (Q(name__iexact=said), Q(name__icontains=said)):
            candidates = list(
                PaymentMethod.objects.filter(lookup).order_by("name", "id")[
                    : MAX_CANDIDATES + 1
                ]
            )
            if candidates:
                break
        if len(candidates) > 1:
            names = ", ".join(c.name for c in candidates[:MAX_CANDIDATES])
            raise Conflict(
                str(METHOD_AMBIGUOUS) % {"said": said, "names": names},
                code="payment.method_ambiguous",
            )
        method_id = candidates[0].pk if candidates else None
    found = PaymentMethod.objects.filter(pk=method_id)
    method = (found.select_for_update() if lock else found).first()
    if method is None:
        raise NotFound(str(METHOD_NOT_FOUND), code="payment.method_not_found")
    return method


def find_payment(
    payment_id: UUID | None, reference: str | None, *, lock: bool = False
) -> Payment:
    """A payment by its id or its reference (uppercase, as the schema keeps it)."""
    found = Payment.objects.select_related("method")
    found = (
        found.filter(pk=payment_id)
        if payment_id is not None
        else found.filter(reference=reference)
    )
    payment = (found.select_for_update(of=("self",)) if lock else found).first()
    if payment is None:
        raise NotFound(str(PAYMENT_NOT_FOUND), code="payment.payment_not_found")
    return payment


def mask_account(value: str) -> str:
    """An account as a list may show it: an IBAN keeps its country and its last four, in groups of
    four (``ES** **** **** **** **** 1332``); any other text, its last four; four or less, as is."""
    if len(value) <= 4:
        return value
    if iban_number.is_valid(value):
        compact = iban_number.compact(value)
        hidden = compact[:2] + "*" * (len(compact) - 6) + compact[-4:]
        return " ".join(hidden[i : i + 4] for i in range(0, len(hidden), 4))
    return "*" * (len(value) - 4) + value[-4:]


def method_row(method: PaymentMethod, *, whole: bool = False) -> dict:
    """A method; its account masked unless ``whole`` (one method, asked for)."""
    account = method.bank_account_ref
    return {
        "id": method.id,
        "name": method.name,
        "method_type": method.method_type,
        "bank_account_ref": account if whole else mask_account(account),
        "is_active": method.is_active,
        "created_at": method.created_at,
        "updated_at": method.updated_at,
    }


def payment_row(payment: Payment, *, whole: bool = False) -> dict:
    """A payment; the beneficiary's IBAN masked unless ``whole`` (one payment, asked for): a list and
    its live stream never carry a whole IBAN."""
    iban = payment.beneficiary_iban
    return {
        "id": payment.id,
        "reference": payment.reference,
        "method_id": payment.method_id,
        "method_name": payment.method.name,
        "payment_date": payment.payment_date,
        "amount": payment.amount,
        "currency": payment.currency,
        "beneficiary_name": payment.beneficiary_name,
        "beneficiary_iban": iban if whole else mask_account(iban),
        "concept": payment.concept,
        "status": payment.status,
        "supplier_invoice_ref": payment.supplier_invoice_ref,
        "cancel_reason": payment.cancel_reason,
        "approved_by": payment.approved_by,
        "approved_at": payment.approved_at,
        "sent_at": payment.sent_at,
        "completed_at": payment.completed_at,
        "cancelled_by": payment.cancelled_by,
        "cancelled_at": payment.cancelled_at,
        "created_by": payment.created_by,
        "updated_by": payment.updated_by,
        "created_at": payment.created_at,
        "updated_at": payment.updated_at,
    }


# --- Lists ----------------------------------------------------------------------------------------


def _sorted(rows: QuerySet, sort: str, columns: dict, tie: tuple[str, ...]) -> QuerySet:
    """``rows`` by ``sort`` (a column, ``-`` first for descending), then ``tie`` and ``id``, all in
    the same direction: the newest payment date first, and on one day the last recorded first."""
    descending = sort.startswith("-")
    fields = columns[sort.removeprefix("-")]
    rest = [field for field in tie if field not in fields]
    return rows.order_by(
        *(
            F(field).desc(nulls_last=True)
            if descending
            else F(field).asc(nulls_last=True)
            for field in (*fields, *rest, "id")
        )
    )


def _page(rows: QuerySet, params, row) -> dict:
    total = rows.count()
    window = rows[params.offset : params.offset + params.limit]
    return {
        "rows": [row(item) for item in window],
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
    }


def _bounds(**bounds) -> dict:
    return {lookup: value for lookup, value in bounds.items() if value is not None}


# --- Payments -------------------------------------------------------------------------------------


@operation(
    "payment.payment.list",
    kind="query",
    permission="payment.view_payment",
    input=PaymentListIn,
    output=PaymentPage,
    expose_api=True,
    ai={
        "description": "List the business's outgoing payments (to suppliers, transfers, refunds that are "
        "not a sale's) with their reference, date, beneficiary, amount in minor units, method and status "
        "(draft, approved, sent, completed, cancelled). Not the till's charges: those are Sales.",
        "risk": "normal",
    },
)
def list_payments(ctx: OperationContext, params: PaymentListIn) -> dict:
    payments = Payment.objects.select_related("method")
    if params.search:
        payments = payments.filter(
            Q(reference__icontains=params.search)
            | Q(beneficiary_name__icontains=params.search)
            | Q(supplier_invoice_ref__icontains=params.search)
        )
    if params.reference:
        payments = payments.filter(reference__icontains=params.reference)
    if params.beneficiary_name:
        payments = payments.filter(beneficiary_name__icontains=params.beneficiary_name)
    if params.concept:
        payments = payments.filter(concept__icontains=params.concept)
    if params.method_id:
        payments = payments.filter(method_id=params.method_id)
    if params.method:
        payments = payments.filter(method__name__iexact=params.method.strip())
    if params.status:
        payments = payments.filter(status=params.status)
    if params.currency:
        payments = payments.filter(currency=params.currency.strip().upper())
    if params.beneficiary_iban:
        payments = payments.filter(
            beneficiary_iban=iban_number.compact(params.beneficiary_iban)
        )
    if params.supplier_invoice_ref:
        payments = payments.filter(
            supplier_invoice_ref__iexact=params.supplier_invoice_ref.strip()
        )
    payments = payments.filter(
        **_bounds(
            payment_date__gte=params.payment_date_from,
            payment_date__lte=params.payment_date_to,
            amount__gte=params.amount_min,
            amount__lte=params.amount_max,
        )
    )
    return _page(
        _sorted(payments, params.sort, PAYMENT_ORDER, ("created_at",)),
        params,
        payment_row,
    )


@operation(
    "payment.payment.get",
    kind="query",
    permission="payment.view_payment",
    input=PaymentRefIn,
    output=PaymentOut,
    expose_api=True,
    ai={
        "description": "Get one outgoing payment with everything it has (method, concept, IBAN, supplier's "
        "invoice, who recorded and changed it), named by its id or its reference (PAY-20261014-0003).",
        "risk": "normal",
    },
)
def get_payment(ctx: OperationContext, data: PaymentRefIn) -> dict:
    return payment_row(find_payment(data.id, data.reference), whole=True)


# --- Methods --------------------------------------------------------------------------------------


@operation(
    "payment.method.list",
    kind="query",
    permission="payment.view_payment",
    input=MethodListIn,
    output=MethodPage,
    expose_api=True,
    ai={
        "description": "List the accounts the business pays its outgoing payments from (bank accounts, "
        "company card, cash drawer), with their type and whether a new payment may use them. Not the "
        "till's tenders: those are Sales' payment methods.",
        "risk": "normal",
    },
)
def list_methods(ctx: OperationContext, params: MethodListIn) -> dict:
    methods = PaymentMethod.objects.all()
    if params.search:
        methods = methods.filter(
            Q(name__icontains=params.search)
            | Q(bank_account_ref__icontains=params.search)
        )
    if params.method_type:
        methods = methods.filter(method_type=params.method_type)
    if params.is_active is not None:
        methods = methods.filter(is_active=params.is_active)
    return _page(
        _sorted(methods, params.sort, METHOD_ORDER, ("name",)), params, method_row
    )


@operation(
    "payment.method.get",
    kind="query",
    permission="payment.view_payment",
    input=MethodRefIn,
    output=MethodOut,
    expose_api=True,
    ai={
        "description": "Get one account the business pays from (named by its id or its name), with its whole "
        "account reference (the lists show it masked).",
        "risk": "normal",
    },
)
def get_method(ctx: OperationContext, data: MethodRefIn) -> dict:
    return method_row(find_method(data.id, data.method), whole=True)
