"""The sending of the queue: per chain, its unsent records go together to the AEAT through the gateway, and
the AEAT's answer settles each one."""

import datetime as dt
import hashlib
import uuid

from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.outbox import record_event

from base import operations as platform
from apps.verifactu import aeat, certificates, envelope, events, gateway, producer, xsd
from apps.verifactu.models import Config, Event, Record, SendControl, backoff, wait_reason_text
from apps.verifactu.queries.country import OUTSIDE_SPAIN
from apps.verifactu.queries.route import (
    blockers,
    own_certificate_material,
    presenter,
    route_problem,
    sending_route,
    system_for,
)
from apps.verifactu.schemas.contingency import TransmitOut

from .certificate_proof import note_answer
from .sealing import INVALID_RECORD, _build_xml
from .writes import _config, _event

SENDING = _("This chain is being sent right now: try again in a moment.")
AEAT_WAIT = _("The AEAT asked to wait: it goes out by itself at %(at)s.")
CANNOT_SEND = _(
    "It cannot be sent now: %(why)s. It stays in the queue and goes out as soon as it can."
)

#: The wait of a record the gateway refused (409/413/422): it would be refused again as it is, so it never goes
#: out on a timer, only after a change (``_back_in_the_queue``) or by hand (``verifactu.record.transmit``).
GATEWAY_REFUSAL = "refused"


class _Tally:
    def __init__(self) -> None:
        self.chains = self.sent = self.accepted = self.accepted_with_errors = (
            self.rejected
        ) = self.waiting = 0
        self.reason = ""
        self.detail = ""
        self.changed = False

    def because(self, code: str, detail: str = "") -> None:
        """Why (some of) it did not reach the AEAT, said to whoever asked: never told as a success."""
        self.reason, self.detail = code, detail

    def out(self) -> TransmitOut:
        return TransmitOut(
            chains=self.chains,
            sent=self.sent,
            accepted=self.accepted,
            accepted_with_errors=self.accepted_with_errors,
            rejected=self.rejected,
            waiting=self.waiting,
            reason=self.reason,
            message=wait_reason_text(self.reason, self.detail) if self.reason else "",
        )


def _mark(ctx: OperationContext, records, code: str, detail: str, tally: _Tally) -> int:
    """Records that wait for ``code`` say so (VERIFACTU-F17); a change is told once, not at every pass."""
    queryset = records.exclude(wait_reason=code, wait_detail=detail[:500])
    changed = queryset.update(wait_reason=code, wait_detail=detail[:500])
    if changed:
        tally.changed = True
        _event(
            ctx,
            Event.Kind.DEFERRED,
            "deferred",
            {"count": changed, "reason": code, "detail": detail},
            severity="warning",
        )
    return changed


def _outlast_the_gateway() -> None:
    """A call to the gateway waits inside its operation's transaction, whose locks keep two passes from sending the same
    chain, and it can take longer than the cluster lets a transaction sit idle: without this, the cut comes first and
    what the AEAT answered is lost with the transaction. Said before every call, for that transaction only."""
    platform.allow_idle_wait(gateway.LONGEST_WAIT_SECONDS)


def _unsent(issuer_nif: str | None = None, environment: str | None = None):
    queryset = Record.objects.filter(status__in=Record.UNSENT)
    if issuer_nif is not None:
        queryset = queryset.filter(issuer_nif=issuer_nif, environment=environment)
    return queryset


def _back_in_the_queue(records=None) -> None:
    """What the gateway refused goes out with the next pass: a change that may cure it (the route, the own
    certificate, a new photo of the account) or a person's «Retry»."""
    records = _unsent() if records is None else records
    records.filter(wait_reason=GATEWAY_REFUSAL).update(
        wait_reason="", wait_detail="", next_attempt_at=timezone.now()
    )


def _failed(  # noqa: PLR0913
    ctx,
    batch,
    code: str,
    detail: str,
    now,
    *,
    status: str | None = None,
    severity: str = "warning",
) -> None:
    for record in batch:
        record.attempts += 1
        record.next_attempt_at = now + backoff(record.attempts)
        record.wait_reason = code
        record.wait_detail = detail[:500]
        if status:
            record.status = status
    _event(
        ctx,
        Event.Kind.DEFERRED,
        "deferred",
        {"count": len(batch), "reason": code, "detail": detail},
        severity=severity,
        record=batch[0] if len(batch) == 1 else None,
        environment=batch[0].environment,
    )


def _settle(ctx, batch, answer: aeat.SubmissionAnswer, now, tally: _Tally) -> None:
    """Each record of ``batch`` takes the AEAT's verdict on it; one the answer does not name stays «sent»."""
    verdicts: dict[tuple[str, str], list[aeat.LineVerdict]] = {}
    for line in answer.lines:
        verdicts.setdefault((line.operation.lower(), line.number), []).append(line)
    accepted = []
    for record in batch:
        found = verdicts.get((record.record_type, record.invoice_number))
        if not found:
            record.status = Record.Status.SENT
            record.attempts += 1
            record.next_attempt_at = now + backoff(record.attempts)
            record.wait_reason = "unknown"
            continue
        line = found.pop(0)
        record.status = line.status
        record.aeat_code = line.code[:16]
        record.aeat_message = line.message[:1000]
        record.wait_reason = record.wait_detail = ""
        if line.status in Record.IN_AEAT:
            record.csv = answer.csv[:64]
        notice = {
            "record_id": str(record.id),
            "invoice_number": record.invoice_number,
            "status": line.status,
            "code": line.code,
            "message": line.message,
            "environment": record.environment,
        }
        if line.status == Record.Status.ACCEPTED:
            tally.accepted += 1
            accepted.append(record)
        elif line.status == Record.Status.ACCEPTED_WITH_ERRORS:
            tally.accepted_with_errors += 1
            _event(
                ctx,
                Event.Kind.ACCEPTED_WITH_ERRORS,
                "accepted_with_errors",
                notice,
                severity="warning",
                record=record,
                environment=record.environment,
            )
            record_event(ctx, events.RECORD_ACCEPTED_WITH_ERRORS, notice)
        else:
            tally.rejected += 1
            _event(
                ctx,
                Event.Kind.FAILED,
                "rejected",
                notice,
                severity="error",
                record=record,
                environment=record.environment,
            )
            record_event(ctx, events.RECORD_REJECTED, notice)
    if accepted:
        _event(
            ctx,
            Event.Kind.ACCEPTED,
            "accepted",
            {
                "count": len(accepted),
                "csv": answer.csv,
                "environment": accepted[0].environment,
            },
            record=accepted[0] if len(accepted) == 1 else None,
            environment=accepted[0].environment,
        )


def _send_chain(  # noqa: C901, PLR0912, PLR0913, PLR0915, PLR0917
    ctx,
    config: Config,
    system,
    issuer_nif: str,
    environment: str,
    tally: _Tally,
    *,
    force: bool,
    strict: bool,
) -> None:
    now = timezone.now()
    problem = route_problem(config, environment, ctx.scope)
    route = sending_route(config, environment, ctx.scope)
    certificate = None
    if not problem:
        try:
            certificate = own_certificate_material(route)
        except certificates.CertificateUnreadable:
            problem = "own_certificate_unreadable"
    if problem:
        if strict:
            raise Conflict(
                str(CANNOT_SEND) % {"why": wait_reason_text(problem)},
                code=f"verifactu.{problem}",
            )
        tally.waiting += _unsent(issuer_nif, environment).count()
        tally.reason = problem
        _mark(ctx, _unsent(issuer_nif, environment), problem, "", tally)
        return
    SendControl.objects.bulk_create(
        [SendControl(issuer_nif=issuer_nif, environment=environment)],
        ignore_conflicts=True,
    )
    control = (
        SendControl.objects.select_for_update(skip_locked=True)
        .filter(issuer_nif=issuer_nif, environment=environment)
        .first()
    )
    if control is None:
        if strict:
            raise Conflict(str(SENDING), code="verifactu.sending")
        return
    if control.next_send_at and control.next_send_at > now:
        if strict:
            at = timezone.localtime(control.next_send_at).strftime("%H:%M:%S")
            raise Conflict(str(AEAT_WAIT) % {"at": at}, code="verifactu.aeat_wait")
        tally.waiting += _unsent(issuer_nif, environment).count()
        return
    batch = list(
        _unsent(issuer_nif, environment)
        .select_for_update()
        .order_by("sequence")[: envelope.MAX_RECORDS]
    )
    if batch and not force and batch[0].wait_reason == GATEWAY_REFUSAL:
        # The gateway would refuse it again as it is: it waits for a change or a person, never on a timer. What was
        # sealed behind it waits for the same reason, and says so.
        tally.because(GATEWAY_REFUSAL, batch[0].wait_detail)
        tally.waiting += len(batch)
        _mark(
            ctx,
            _unsent(issuer_nif, environment),
            GATEWAY_REFUSAL,
            batch[0].wait_detail,
            tally,
        )
        return
    if not batch or (not force and batch[0].next_attempt_at > now):
        tally.waiting += len(batch)
        return
    try:
        for record in batch:
            if not record.xml:
                _build_xml(record, system)
        whole = envelope.submission(
            obligado_name=batch[0].issuer_name,
            obligado_nif=issuer_nif,
            registros=[record.xml for record in batch],
            representative=(
                (producer.MANUFACTURER["NombreRazon"], producer.MANUFACTURER["NIF"])
                if route == Config.Route.ERPLORA
                else None
            ),
            incident=any(
                record.attempts
                or record.wait_reason
                or record.status == Record.Status.SENT
                for record in batch
            ),
        )
        xsd.validate(whole)
    except (xsd.SchemaError, envelope.UndeclarableRecord) as error:
        # A defect of ours: the chain stops loudly instead of sending what the AEAT would refuse.
        if strict:
            raise Conflict(
                str(INVALID_RECORD) % {"detail": str(error)},
                code="verifactu.invalid_record",
            ) from None
        # Told once, as every wait: a pass a minute repeats nothing while the defect stays the same.
        tally.because("xml_invalid", str(error))
        if _mark(ctx, _unsent(issuer_nif, environment), "xml_invalid", str(error), tally):
            _event(
                ctx,
                Event.Kind.FAILED,
                "xml_invalid",
                {"invoice_number": batch[0].invoice_number, "detail": str(error)},
                severity="critical",
            )
        tally.waiting += len(batch)
        return
    incident = "<sum1:Incidencia>S</sum1:Incidencia>" in whole
    _outlast_the_gateway()
    reply = gateway.submit(
        hub=presenter(ctx.scope),
        nif=issuer_nif,
        environment=environment,
        route=route,
        envelope=whole,
        certificate=certificate,
    )
    note_answer(ctx, route, environment, reply, certificate)
    transmission = uuid.uuid7()
    digest = hashlib.sha256(whole.encode("utf-8")).hexdigest()
    for record in batch:
        record.transmitted_at = now
        record.transmission_id = transmission
        record.envelope_digest = digest
        record.incident = incident
    tally.changed = True
    if reply.kind in (gateway.ANSWERED, gateway.UNKNOWN):
        # It reached (or may have reached) the AEAT; a refusal of the gateway or no connection never left.
        tally.chains += 1
        tally.sent += len(batch)
    if reply.kind == gateway.ANSWERED:
        try:
            answer = aeat.parse_submission(reply.aeat_body)
        except aeat.UnreadableAnswer as error:
            if reply.aeat_status == 200:
                _failed(
                    ctx, batch, "unknown", str(error), now, status=Record.Status.SENT
                )
                tally.because("unknown", str(error))
            else:
                detail = f"AEAT HTTP {reply.aeat_status}"
                _failed(ctx, batch, "unreachable", detail, now)
                tally.because("unreachable", detail)
            tally.waiting += len(batch)
        else:
            if answer.fault_code:
                # A fault refuses the SENDING, not its records: the AEAT evaluated none of them, so none is
                # «rejected» (a correction of a record it never saw would carry a wrong RechazoPrevio). They
                # wait with the attempt spent; a permanent fault (4102/4104/4116) is told as critical, since
                # sending it again unchanged will not help.
                detail = f"{answer.fault_code}: {answer.fault_message}"
                _failed(
                    ctx,
                    batch,
                    "aeat_fault",
                    detail,
                    now,
                    severity="critical" if answer.permanent_fault else "warning",
                )
                tally.because("aeat_fault", detail)
                tally.waiting += len(batch)
            else:
                _settle(ctx, batch, answer, now, tally)
                tally.waiting += sum(
                    1 for record in batch if record.status in Record.UNSENT
                )
            if answer.wait_seconds is not None:
                control.wait_seconds = answer.wait_seconds
                control.next_send_at = now + dt.timedelta(
                    seconds=answer.wait_seconds
                )
    elif reply.kind == gateway.REFUSED:
        detail = f"{reply.code}: {reply.message}"
        _failed(ctx, batch, GATEWAY_REFUSAL, detail, now)
        tally.because(GATEWAY_REFUSAL, detail)
        tally.waiting += len(batch)
    elif reply.kind == gateway.UNKNOWN:
        _failed(ctx, batch, "unknown", reply.message, now, status=Record.Status.SENT)
        tally.because("unknown", reply.message)
        tally.waiting += len(batch)
    else:
        _failed(ctx, batch, "unreachable", reply.message, now)
        tally.because("unreachable", reply.message)
        tally.waiting += len(batch)
    control.last_sent_at = now
    control.save()
    Record.objects.bulk_update(
        batch,
        [
            "status",
            "attempts",
            "next_attempt_at",
            "wait_reason",
            "wait_detail",
            "transmitted_at",
            "transmission_id",
            "envelope_digest",
            "incident",
            "csv",
            "aeat_code",
            "aeat_message",
            "xml",
            "xml_built_at",
            "updated_at",
        ],
    )
    record_event(
        ctx,
        events.RECORD_TRANSMITTED,
        {
            "record_ids": [str(record.id) for record in batch],
            "transmission_id": str(transmission),
            "environment": environment,
        },
    )


def _send(ctx: OperationContext, *, only: Record | None = None) -> _Tally:
    """One pass of the queue (VERIFACTU-F15, F20, F21), or the chain of ``only`` now (VERIFACTU-F25)."""
    tally = _Tally()
    config = _config(lock=False)
    strict = only is not None
    scope = _unsent(only.issuer_nif, only.environment) if strict else _unsent()
    for code in blockers(
        config, only.environment if strict else config.environment, ctx.scope
    ):
        if code in (OUTSIDE_SPAIN, "gateway_unavailable"):
            if strict:
                raise Conflict(
                    str(CANNOT_SEND) % {"why": wait_reason_text(code)},
                    code=f"verifactu.{code}",
                )
            tally.reason = code
            tally.waiting = scope.count()
            _mark(ctx, scope, code, "", tally)
            return tally
    system = system_for(ctx)
    keys = list(scope.order_by().values_list("issuer_nif", "environment").distinct())
    for issuer_nif, environment in sorted(keys):
        _send_chain(
            ctx,
            config,
            system,
            issuer_nif,
            environment,
            tally,
            force=strict,
            strict=strict,
        )
    return tally
