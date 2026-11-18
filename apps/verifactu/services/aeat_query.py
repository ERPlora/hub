"""What the AEAT holds of an issuer (``verifactu.aeat.query``), asked through ERPlora's gateway page by page."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import aeat, certificates, chain, envelope, events, gateway, producer, xsd
from apps.verifactu.envelope import InvoiceRef
from apps.verifactu.models import AeatRecord, Config, Event, Record, wait_reason_text
from apps.verifactu.queries.aeat_records import aeat_row
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.route import config_row, issuer_identity, own_certificate_material, presenter, sending_route
from apps.verifactu.schemas import AeatQueryIn, AeatQueryOut

from .sending import CANNOT_SEND, _outlast_the_gateway
from .writes import TRANSMIT, _event

AEAT_REFUSED = _("The AEAT refused the query: %(detail)s")
AEAT_UNREACHABLE = _("The AEAT could not be asked: %(detail)s")
SAME_PAGE = _("it named the same page of records again")
TOO_MANY_PAGES = _("it has more than %(pages)s pages of records")
#: A query's pages followed at most (10,000 records each, by the AEAT's web service description, section 6.4.3):
#: far beyond any business's month.
MAX_QUERY_PAGES = 50


def _query_page(  # noqa: PLR0913, PLR0917
    ctx: OperationContext,
    route: str,
    nif: str,
    name: str,
    environment: str,
    year: int,
    month: int,
    represented: bool,
    after: InvoiceRef | None,
    certificate: gateway.Certificate | None,
) -> aeat.QueryPage:
    """One page of the AEAT's records of ``nif`` in a month (after ``after``), asked through the gateway."""
    try:
        body = envelope.query(
            obligado_nif=nif,
            obligado_name=name,
            year=year,
            month=month,
            represented=represented,
            after=after,
        )
        xsd.validate_query(body)
    except (envelope.UndeclarableRecord, xsd.SchemaError) as error:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(error)},
            code="verifactu.aeat_unreachable",
        ) from None
    _outlast_the_gateway()
    reply = gateway.query(
        hub=presenter(ctx.scope),
        nif=nif,
        environment=environment,
        route=route,
        envelope=body,
        certificate=certificate,
    )
    if reply.kind != gateway.ANSWERED:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": reply.message or reply.code},
            code="verifactu.aeat_unreachable",
        )
    try:
        return aeat.parse_query(reply.aeat_body)
    except aeat.AeatFault as fault:
        raise Conflict(
            str(AEAT_REFUSED) % {"detail": fault.message}, code="verifactu.aeat_refused"
        ) from None
    except aeat.UnreadableAnswer as error:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(error)},
            code="verifactu.aeat_unreachable",
        ) from None


def _query_aeat(  # noqa: PLR0913, PLR0917
    ctx, config: Config, nif: str, environment: str, year: int, month: int
) -> list[aeat.QueriedRecord]:
    """Ask the AEAT, through the gateway, for the records of ``nif`` in a month; replace the last photo."""
    if not gateway.configured():
        raise Conflict(
            str(CANNOT_SEND) % {"why": wait_reason_text("gateway_unavailable")},
            code="verifactu.gateway_unavailable",
        )
    route = sending_route(config, environment, ctx.scope)
    try:
        certificate = own_certificate_material(route)
    except certificates.CertificateUnreadable:
        raise Conflict(
            str(CANNOT_SEND) % {"why": wait_reason_text("own_certificate_unreadable")},
            code="verifactu.own_certificate_unreadable",
        ) from None
    latest_name = (
        Record.objects.filter(issuer_nif=nif)
        .order_by("-created_at")
        .values_list("issuer_name", flat=True)
        .first()
    )
    name = latest_name or issuer_identity()[1]
    represented = route == Config.Route.ERPLORA and nif.upper() != producer.MANUFACTURER["NIF"]
    records: list[aeat.QueriedRecord] = []
    after = None
    for _page in range(MAX_QUERY_PAGES):
        page = _query_page(
            ctx, route, nif, name, environment, year, month, represented, after, certificate
        )
        records.extend(page.records)
        if not page.more:
            break
        if page.after == after:
            raise Conflict(
                str(AEAT_UNREACHABLE) % {"detail": str(SAME_PAGE)},
                code="verifactu.aeat_unreachable",
            )
        after = page.after
    else:
        raise Conflict(
            str(AEAT_UNREACHABLE) % {"detail": str(TOO_MANY_PAGES) % {"pages": MAX_QUERY_PAGES}},
            code="verifactu.aeat_unreachable",
        )
    now = timezone.now()
    AeatRecord.objects.filter(issuer_nif=nif, environment=environment).delete()
    AeatRecord.objects.bulk_create(
        [
            AeatRecord(
                issuer_nif=item.issuer_nif or nif,
                environment=environment,
                invoice_number=item.number,
                issue_date=item.issue_date,
                fingerprint=chain.normalize_hash(item.fingerprint),
                state=item.state[:40],
                csv=item.csv[:64],
                generated_on=item.generated_at,
                queried_at=now,
            )
            for item in records
        ]
    )
    _event(
        ctx,
        Event.Kind.AEAT_QUERIED,
        "aeat_queried",
        {"issuer_nif": nif, "count": len(records)},
        environment=environment,
    )
    record_event(ctx, events.AEAT_QUERIED, {"issuer_nif": nif, "count": len(records)})
    return records


@operation(
    "verifactu.aeat.query",
    kind="command",
    permission=TRANSMIT,
    input=AeatQueryIn,
    output=AeatQueryOut,
    ai={
        "description": "Ask the AEAT which records of an issuer (Invoicing's by default) it holds in a month (this one "
        "by default), through ERPlora's gateway; the answer replaces the last photo. It does not touch the chain.",
        "risk": "high",
        "asks": {
            "en": (
                "ask the AEAT what it holds of ours for October",
                "refresh what the AEAT has on file for September",
            ),
            "es": (
                "consulta a la AEAT qué registros nuestros tiene de octubre",
                "pide a Hacienda la relación de lo remitido en octubre",
            ),
        },
    },
)
def query_aeat(ctx: OperationContext, data: AeatQueryIn) -> AeatQueryOut:
    refuse_outside_spain(ctx)
    config = config_row()
    today = timezone.localdate()
    nif = data.issuer_nif or issuer_identity()[0]
    records = _query_aeat(
        ctx,
        config,
        nif,
        config.environment,
        data.year or today.year,
        data.month or today.month,
    )
    rows = AeatRecord.objects.filter(
        issuer_nif=nif, environment=config.environment
    ).order_by("-generated_on", "-id")
    return AeatQueryOut(count=len(records), rows=[aeat_row(row) for row in rows])
