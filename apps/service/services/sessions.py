"""Sessions of the till (SERVICE-F22 to F27). Sales runs them by name, with the seller's context, inside its own
transaction: they lock the vouchers' rows first (in id order when there are several) and then the sessions, as every
write on a voucher does, so two tills on the same voucher go one after the other.
"""

import datetime as dt

from django.db import IntegrityError
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, NotFound
from live.operations import atomic, operation
from live.outbox import record_event

from apps.service import events
from apps.service.models.grants import Grant, Redemption
from apps.service.queries.catalog import find_service
from apps.service.queries.grant_checks import redeem_refusal
from apps.service.queries.grants import SESSION_NOT_FOUND, balance, find_grant, session_rows, lock_grant, session_value
from apps.service.queries.reads import SYSTEM
from apps.service.schemas.fields import NoIn
from apps.service.schemas.sessions import ExpiredOut, HoldIn, ReturnIn, SessionOut, SessionRefIn, SessionsOut, SettleIn
from apps.service.services.grants import REDEEM_REFUSALS
from apps.service.services.writes import _actor

LINE_ALREADY_HELD = _("That line already holds a session of a voucher.")
HOLD_LOST = _(
    "The session held from «%(name)s» is no longer held (its day passed or it was released). Take the voucher "
    "off the line and apply it again."
)
HOLD_CUSTOMER_MISMATCH = _(
    "The voucher «%(name)s» belongs to another customer: charge the sale to its owner or take the voucher off "
    "the line."
)
SESSION_SETTLED = _(
    "That voucher session can no longer be released: the sale is charged. Giving it back is a refund."
)
SESSION_NOT_SETTLED = _("That session was never charged, so there is nothing to give back.")
SESSION_ALREADY_RETURNED = _("That session was already given back by another refund.")
#: How long a session held at the till waits to be charged (SERVICE-F25).
HOLD_DURATION = dt.timedelta(days=1)

HELD = Redemption.Status.HELD
CONSUMED = Redemption.Status.CONSUMED


def _unique(ids) -> list:
    return list(dict.fromkeys(ids))


def _lock_sessions(ids) -> dict:
    """The sessions ``ids``, their vouchers locked first and then themselves (``NotFound`` if one is missing)."""
    wanted = _unique(ids)
    owners = set(
        Redemption.objects.filter(pk__in=wanted).values_list("grant_id", flat=True)
    )
    list(Grant.objects.select_for_update().filter(pk__in=owners).order_by("id"))
    sessions = {
        session.id: session
        for session in Redemption.objects.select_for_update()
        .filter(pk__in=wanted)
        .order_by("id")
    }
    if len(sessions) != len(wanted):
        raise NotFound(str(SESSION_NOT_FOUND), code="service.session_not_found")
    return sessions


def _owner_name(session: Redemption) -> str:
    return Grant.objects.select_related("package").get(pk=session.grant_id).package.name


@operation(
    "service.session.hold",
    kind="command",
    permission="service.redeem_package",
    input=HoldIn,
    output=SessionOut,
    ai={
        "description": "Sales' step when a line of an open check is paid with a customer's voucher: reserve one session "
        "of that voucher for that line for one day (it counts as used). To pay a line with a voucher, use "
        "sale.order.apply_voucher, which calls this.",
        "risk": "normal",
        "asks": {
            "en": (
                "hold a session of Inés's voucher for her manicure",
                "keep a session of Pilar's voucher on hold for her colour",
            ),
            "es": (
                "aparta una sesión del bono de Inés para su manicura",
                "deja retenida una sesión del bono de Pilar para su tinte",
            ),
        },
    },
)
def hold_session(ctx: OperationContext, data: HoldIn) -> dict:
    service = find_service(data.service_id, None)
    lock_grant(data.grant_id)
    now = timezone.now()
    # A hold of this very line whose day passed frees the line first (the hourly task may not have run).
    Redemption.objects.filter(
        order_line_id=data.order_line_id, status=HELD, hold_until__lte=now
    ).update(
        status=Redemption.Status.EXPIRED, ended_at=F("hold_until"), ended_by="system"
    )
    if Redemption.objects.filter(
        order_line_id=data.order_line_id, status__in=Redemption.LIVE
    ).exists():
        raise Conflict(str(LINE_ALREADY_HELD), code="service.line_already_held")
    grant = find_grant(data.grant_id)
    refusal = redeem_refusal(grant, balance(grant, now), service)
    if refusal:
        code, message = REDEEM_REFUSALS[refusal]
        raise Conflict(str(message), code=code)
    try:
        with atomic():
            session = Redemption.objects.create(
                grant=grant,
                service=service,
                status=HELD,
                order_line_id=data.order_line_id,
                hold_until=now + HOLD_DURATION,
                redeemed_at=now,
                actor=_actor(ctx),
            )
    except IntegrityError:
        # The same line held at once with another voucher: the database keeps one.
        raise Conflict(str(LINE_ALREADY_HELD), code="service.line_already_held") from None
    record_event(
        ctx, events.SESSION_RESERVED, {"id": str(session.id), "grant_id": str(grant.id)}
    )
    return session_rows([session.id])[0]


@operation(
    "service.session.release",
    kind="command",
    permission="service.redeem_package",
    input=SessionRefIn,
    output=SessionOut,
    ai={
        "description": "Sales' step when a line paid with a voucher is undone, removed or voided, or its check voided: the "
        "session held for it goes back to the voucher at once. Releasing one already released or expired changes "
        "nothing; a session already charged is refused (giving it back is a refund). The id of the session a line "
        "holds is that line's voucher_session_id, from sale.order.get.",
        "risk": "normal",
        "asks": {
            "en": ("release the session held for Inés's manicure", "free the session Pilar's voucher had on hold"),
            "es": (
                "suelta la sesión retenida del bono de Inés",
                "libera la sesión que tenía apartada el bono de Pilar",
            ),
        },
    },
)
def release_session(ctx: OperationContext, data: SessionRefIn) -> dict:
    session = _lock_sessions([data.id])[data.id]
    if session.status in (CONSUMED, Redemption.Status.RETURNED):
        raise Conflict(str(SESSION_SETTLED), code="service.session_settled")
    if session.status == HELD:
        Redemption.objects.filter(pk=session.pk).update(
            status=Redemption.Status.RELEASED,
            ended_at=timezone.now(),
            ended_by=_actor(ctx),
        )
        record_event(
            ctx,
            events.SESSION_RELEASED,
            {"id": str(session.id), "grant_id": str(session.grant_id)},
        )
    return session_rows([session.id])[0]


def _owner_matches(session: Redemption, customer_id) -> bool:
    """The sale's customer owns the voucher: its card, or the card it was merged into."""
    if customer_id is None:
        return False
    owner = Grant.objects.select_related("customer").get(pk=session.grant_id).customer
    return customer_id in (owner.id, owner.merged_into_id)


@operation(
    "service.session.settle",
    kind="command",
    permission="service.redeem_package",
    input=SettleIn,
    output=SessionsOut,
    ai={
        "description": "Sales' step when a sale is charged: the sessions held for its lines paid with vouchers are "
        "delivered for good and linked to the sale, each with what it is worth from then on. Refused, delivering none, if one is no longer held (its day "
        "passed, it was released) or the sale's customer does not own the voucher. Repeating it for the same sale "
        "changes nothing.",
        "risk": "high",
        "asks": {
            "en": (
                "the sale is charged: deliver its held voucher sessions",
                "settle the voucher sessions of the sale we just charged",
            ),
            "es": (
                "ya está cobrada: da por gastadas las sesiones retenidas de esa venta",
                "las sesiones de bono de la venta cobrada, márcalas como consumidas",
            ),
        },
    },
)
def settle_sessions(ctx: OperationContext, data: SettleIn) -> dict:
    sessions = _lock_sessions(data.ids)
    now = timezone.now()
    pending = []
    for session_id in _unique(data.ids):
        session = sessions[session_id]
        if session.status == CONSUMED and session.sale_id == data.sale_id:
            continue
        if session.status != HELD or session.hold_until <= now:
            raise Conflict(
                str(HOLD_LOST) % {"name": _owner_name(session)}, code="service.hold_lost"
            )
        if not _owner_matches(session, data.customer_id):
            raise Conflict(
                str(HOLD_CUSTOMER_MISMATCH) % {"name": _owner_name(session)},
                code="service.hold_customer_mismatch",
            )
        pending.append(session)
    for session in pending:
        # One by one, the next one's share read after this one's: the voucher's row is locked (``_lock_sessions``).
        Redemption.objects.filter(pk=session.pk).update(
            status=CONSUMED,
            settled_at=now,
            sale_id=data.sale_id,
            value=session_value(session.grant_id),
        )
        record_event(
            ctx,
            events.SESSION_SETTLED,
            {
                "id": str(session.id),
                "grant_id": str(session.grant_id),
                "sale_id": str(data.sale_id),
            },
        )
    return {"rows": session_rows(data.ids)}


@operation(
    "service.session.expire",
    kind="command",
    permission=SYSTEM,
    input=NoIn,
    output=ExpiredOut,
    ai={
        "description": "Platform task, every hour: the sessions held at the till whose day passed without the sale being "
        "charged are marked expired (the balance already stopped counting them at the deadline).",
        "risk": "normal",
    },
)
def expire_holds(ctx: OperationContext, data: NoIn) -> dict:
    # Locked in id order, as every other step of a session takes them; one notice per session, saying which
    # session of which voucher, and none when nothing lapsed.
    lapsed = list(
        Redemption.objects.select_for_update()
        .filter(status=HELD, hold_until__lte=timezone.now())
        .order_by("id")
        .values_list("id", "grant_id")
    )
    if lapsed:
        Redemption.objects.filter(id__in=[session_id for session_id, _ in lapsed]).update(
            status=Redemption.Status.EXPIRED, ended_at=F("hold_until"), ended_by="system"
        )
    for session_id, grant_id in lapsed:
        record_event(
            ctx, events.SESSION_EXPIRED, {"id": str(session_id), "grant_id": str(grant_id)}
        )
    return {"expired": len(lapsed)}


@operation(
    "service.session.return",
    kind="command",
    permission="service.return_session",
    input=ReturnIn,
    output=SessionsOut,
    ai={
        "description": "Sales' step when a sale is voided or refunded: the sessions spent in it (or in the lines that come "
        "back) return to their vouchers, even an expired one, with the document and the reason. The same document "
        "again gives nothing back twice; a session given back by another document is refused.",
        "risk": "high",
        "asks": {
            "en": (
                "the sale was refunded: give the voucher sessions back",
                "put the sessions of the voided sale back on their vouchers",
            ),
            "es": (
                "se ha devuelto la venta: reintegra las sesiones a sus bonos",
                "la venta del masaje se anuló, que la sesión vuelva al bono",
            ),
        },
    },
)
def return_sessions(ctx: OperationContext, data: ReturnIn) -> dict:
    sessions = _lock_sessions(data.ids)
    pending = []
    for session_id in _unique(data.ids):
        session = sessions[session_id]
        if session.status == Redemption.Status.RETURNED:
            if session.return_reference != data.reference:
                raise Conflict(
                    str(SESSION_ALREADY_RETURNED),
                    code="service.session_already_returned",
                )
            continue
        if session.status != CONSUMED:
            raise Conflict(
                str(SESSION_NOT_SETTLED), code="service.session_not_settled"
            )
        pending.append(session)
    now = timezone.now()
    for session in pending:
        Redemption.objects.filter(pk=session.pk).update(
            status=Redemption.Status.RETURNED,
            ended_at=now,
            ended_by=_actor(ctx),
            return_reference=data.reference,
            return_reason=data.reason,
        )
        record_event(
            ctx,
            events.SESSION_RETURNED,
            {
                "id": str(session.id),
                "grant_id": str(session.grant_id),
                "reference": str(data.reference),
            },
        )
    return {"rows": session_rows(data.ids)}
