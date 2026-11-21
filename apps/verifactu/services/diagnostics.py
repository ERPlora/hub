"""The connection test (``verifactu.diagnostic.run``) and the test invoice
(``verifactu.test_invoice.create``)."""


from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import get as get_operation
from live.operations import operation
from live.outbox import record_event

from apps.verifactu import events, gateway
from apps.verifactu.models import Environment, Event
from apps.verifactu.queries.country import refuse_outside_spain
from apps.verifactu.queries.records import find_invoice, summary
from apps.verifactu.queries.route import (
    blockers,
    config_row,
    effective_environment,
    issuer_configured,
    issuer_identity,
    own_certificate_material,
    presenter,
    route_problem,
    sending_route,
    wait,
)
from apps.verifactu.schemas.diagnostics import DiagnosticOut, TestInvoiceOut
from apps.verifactu.schemas.fields import NoInput

from .sealing import _seal_alta
from .sending import _outlast_the_gateway
from .writes import CONFIGURE, TRANSMIT, _config, _event

TESTING_ONLY = _("The test invoice is only for the test environment.")
#: Line of the test invoice (VERIFACTU-F11): a fiscal document's text, in the AEAT's language.
TEST_LINE = "Prueba VeriFactu"


@operation(
    "verifactu.diagnostic.run",
    kind="command",
    permission=TRANSMIT,
    input=NoInput,
    output=DiagnosticOut,
    ai={
        "description": "Test whether this business can send VeriFactu records now, presenting nothing to the AEAT: the "
        "issuer, the producer's details, the route and, with ERPlora's gateway, its own answer.",
        "risk": "normal",
        "asks": {
            "en": (
                "test the connection to the AEAT without filing anything",
                "run a VeriFactu sending diagnostic",
            ),
            "es": (
                "prueba si la conexión con la AEAT funciona sin enviar nada",
                "comprueba si podríamos remitir registros, sin mandar nada",
            ),
        },
    },
)
def run_diagnostic(ctx: OperationContext, data: NoInput) -> DiagnosticOut:
    refuse_outside_spain(ctx)
    config = config_row()
    nif = issuer_identity()[0]
    codes = blockers(config, config.environment, ctx.scope)
    route = sending_route(config, config.environment, ctx.scope)
    gateway_ready, gateway_detail, refusal = None, "", ""
    if gateway.configured() and "own_certificate_unreadable" not in codes:
        _outlast_the_gateway()
        reply = gateway.probe(
            hub=presenter(ctx.scope),
            nif=nif,
            environment=config.environment,
            route=route,
            certificate=own_certificate_material(route),
        )
        gateway_ready = reply.kind == gateway.ANSWERED and reply.ready
        gateway_detail = reply.message or reply.code
        # A refusal is kept as a record keeps it, so a known one is told in the reader's language.
        refusal = (
            f"{reply.code}: {reply.message}"
            if reply.kind == gateway.REFUSED
            else gateway_detail
        )
        if not gateway_ready:
            codes.append("refused")
    details = {"refused": refusal}
    result = {
        "ran_at": timezone.now(),
        "environment": config.environment,
        "route": route,
        "issuer_ready": issuer_configured(),
        "route_ready": not route_problem(config, config.environment, ctx.scope),
        "gateway_configured": gateway.configured(),
        "gateway_ready": gateway_ready,
        "gateway_detail": gateway_detail,
        "can_send": not codes and issuer_configured(),
        "reasons": [{"code": code, "detail": details.get(code, "")} for code in codes],
    }
    stored = {**result, "ran_at": result["ran_at"].isoformat()}
    if result["can_send"]:
        key, params = "connection_ok", {"environment": config.environment}
    else:
        first = codes[0] if codes else "issuer"
        key, params = (
            "connection_blocked",
            {
                "environment": config.environment,
                "reason": first,
                "detail": details.get(first, ""),
            },
        )
    _event(
        ctx,
        Event.Kind.CONNECTION_TEST,
        key,
        {**params, "result": stored},
        severity="info" if result["can_send"] else "warning",
    )
    record_event(ctx, events.DIAGNOSTIC_RUN, {"can_send": result["can_send"]})
    return DiagnosticOut(
        **{
            **result,
            "reasons": [
                wait(item["code"], item["detail"]) for item in result["reasons"]
            ],
        }
    )


@operation(
    "verifactu.test_invoice.create",
    kind="command",
    permission=CONFIGURE,
    input=NoInput,
    output=TestInvoiceOut,
    ai={
        "description": "Create the VeriFactu test invoice (only in the test environment): a real ticket (F2) of one line "
        "«Prueba VeriFactu», 1.00 € plus 21 % VAT, issued by Invoicing in its TICKET series, and its record.",
        "risk": "high",
        "asks": {
            "en": (
                "run the one-euro VeriFactu trial in testing",
                "issue VeriFactu's official trial in testing",
            ),
            "es": (
                "lanza la prueba de un euro de VeriFactu",
                "emite la prueba oficial de VeriFactu en el entorno de pruebas",
            ),
        },
    },
)
def create_test_invoice(ctx: OperationContext, data: NoInput) -> TestInvoiceOut:
    refuse_outside_spain(ctx)
    config = _config(lock=False)
    environment = effective_environment(ctx, config)
    if environment != Environment.TESTING:
        raise Conflict(str(TESTING_ONLY), code="verifactu.testing_only")
    issue = get_operation("invoice.invoice.create")
    invoice_out = issue(
        ctx,
        issue.input.model_validate(
            {
                "series_code": "TICKET",
                "lines": [
                    {
                        "description": TEST_LINE,
                        "quantity": "1",
                        "unit_price": 100,
                        "tax_rate": "21",
                    }
                ],
            }
        ),
    )
    invoice = find_invoice(invoice_out.id, None)
    record, _already = _seal_alta(ctx, config, invoice, environment=environment)
    return TestInvoiceOut(
        invoice_id=invoice.id, number=invoice.number, record=summary(record)
    )
