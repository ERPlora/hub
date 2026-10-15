"""Fixtures of the verifactu tests: contexts per role, the real apps a record is born from (Invoicing's issuer and
its documents, made through Invoicing's own operations, never by hand) and the outbox's delivery to VeriFactu's
reaction, as the relay will in phase 2.

The only stand-in is the SaaS's gateway (``gateway_answers``): its transport is replaced and it answers with the
AEAT's **real** answers kept in ``fixtures/`` (accepted, accepted with errors, duplicate, fault), rewritten only
to name the invoices of the test. Nothing the AEAT says is invented.
"""

import re
from pathlib import Path

import pytest
from django.utils import translation
from live.context import OperationContext, Scope, system_context
from live.meta import all_live_app_configs, permissions_for_role
from live.operations import get

from apps.verifactu import gateway

A = Scope("host", "a")
B = Scope("host", "b")
FIXTURES = Path(__file__).parent / "fixtures"
ISSUER = {
    "legal_name": "Peluquería Ana SL",
    "tax_id": "B12345674",
    "address": "Calle Mayor 1",
    "postal_code": "28001",
    "city": "Madrid",
    "province": "Madrid",
}
RECIPIENT = {
    "customer_name": "Talleres Pérez SL",
    "customer_tax_id": "B12345674",
    "customer_address": "Calle Luna 3, Madrid",
}


def ctx_for(
    role: str = "hub_admin",
    scope: Scope = A,
    actor: str = "tester",
    language: str = "en",
) -> OperationContext:
    """The context a user with ``role`` on ``scope`` gets (owner and admin: every declared permission)."""
    configs = all_live_app_configs()
    if role in ("hub_owner", "hub_admin"):
        permissions = frozenset(p for config in configs for p in config.permissions)
    else:
        permissions = permissions_for_role(configs, role)
    return OperationContext(
        scope=scope, actor=actor, permissions=permissions, language=language
    )


def run(name: str, data: dict | None = None, ctx: OperationContext | None = None):
    """Runs the operation ``name`` with ``data`` as its input (validated as a route would)."""
    op = get(name)
    return op(ctx or ctx_for(), op.input.model_validate(data or {}))


def deliver(name: str, scope: Scope = A, index: int = 0):
    """Hands the ``index``-th newest ``name`` event of the outbox to VeriFactu's reaction, as the relay will."""
    from live.models import OutboxEvent

    from apps.verifactu import events

    event = OutboxEvent.objects.filter(name=name).order_by("-created_at", "-id")[index]
    return events.react(scope, event.name, event.payload)


def manual(lines=None, **more):
    """An invoice issued by hand through Invoicing's own operation (an F1 with a customer, or a ticket F2)."""
    data = {
        "lines": lines
        or [
            {
                "description": "Course",
                "quantity": "1",
                "unit_price": 1000,
                "tax_rate": "21",
            }
        ],
        **more,
    }
    return run("invoice.invoice.create", data)


@pytest.fixture(autouse=True)
def english():
    with translation.override("en"):
        yield


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = "a", role: str = "hub_admin"):
        from django.contrib.auth import get_user_model

        from base.models import Membership

        user = get_user_model().objects.create_user(username=username, password="pw")
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role)
        return user

    return make


@pytest.fixture
def invoice_does_not_seal(monkeypatch):
    """Invoicing's emission finds no VeriFactu to ask (it answers «unavailable»): the invoice is issued without
    its record, which only a direct call or the reaction to its notice seals. The rest of Invoicing is real."""
    from live.operations import UnknownOperation

    from apps.invoice import services as invoicing

    real = invoicing.get_operation

    def get_operation(name):
        if name == invoicing.VERIFACTU_RECORD:
            raise UnknownOperation(name)
        return real(name)

    monkeypatch.setattr(invoicing, "get_operation", get_operation)


@pytest.fixture
def at_emission(monkeypatch):
    """``at_emission(change)``: when Invoicing's emission asks VeriFactu for the record, the invoice's row is first
    changed behind Invoicing's back with ``change(row)`` (in the emission's transaction, outside VeriFactu's
    savepoint), so VeriFactu's real operation sees a document it must refuse right at the emission."""
    from apps.invoice import services as invoicing
    from apps.invoice.models import Invoice

    real = invoicing.get_operation

    def install(change):
        def get_operation(name):
            operation = real(name)
            if name != invoicing.VERIFACTU_RECORD:
                return operation

            def twisted(ctx, data):
                row = Invoice.objects.get(pk=data.invoice_id)
                Invoice.objects.filter(pk=row.pk).update(**change(row))
                return operation(ctx, data)

            twisted.input = operation.input
            return twisted

        monkeypatch.setattr(invoicing, "get_operation", get_operation)

    return install


@pytest.fixture
def committed_factory_data(transactional_db):
    """A transactional test starts from a flushed database: tax's factory catalogue and the factory payment
    methods are planted again, as their migrations do (idempotent); then the issuer."""
    from importlib import import_module

    from django.apps import apps as registry
    from django.db import connection

    with connection.schema_editor() as editor:
        for module in (
            "apps.tax.migrations.0002_factory_catalogue",
            "apps.tax.migrations.0005_retail_alcohol",
            "apps.sale.migrations.0002_factory_payment_methods",
        ):
            import_module(module).plant(registry, editor)
    run("invoice.issuer.update", ISSUER)


@pytest.fixture
def db_dsn(django_db_setup):
    """DSN of the test database, for raw psycopg sessions (reading only what is committed)."""
    from django.db import connections
    from psycopg.conninfo import make_conninfo

    params = connections["default"].settings_dict
    return make_conninfo(
        dbname=params["NAME"],
        user=params["USER"],
        password=params["PASSWORD"],
        host=params["HOST"],
        port=params["PORT"],
    )


@pytest.fixture
def issuer(db):
    return run("invoice.issuer.update", ISSUER)


@pytest.fixture
def producer(db):
    """The ERPlora account has said everything VeriFactu needs (IndicadorMultiplesOT), as its photo would."""
    return run(
        "verifactu.config.sync",
        {"version": 1, "multiple_taxpayers": "N"},
        system_context(A),
    )


#: Each record a submission carries: (Alta | Anulacion, its own invoice number), never its RegistroAnterior's.
OWN_RECORD = re.compile(
    r"<sum:RegistroFactura><sum1:Registro(Alta|Anulacion)><sum1:IDVersion>1\.0</sum1:IDVersion><sum1:IDFactura>"
    r"<sum1:IDEmisorFactura(?:Anulada)?>[^<]*</sum1:IDEmisorFactura(?:Anulada)?>"
    r"<sum1:NumSerieFactura(?:Anulada)?>([^<]*)<"
)


def records_of(envelope: str) -> list[tuple[str, str]]:
    return OWN_RECORD.findall(envelope)


def aeat_answer(name: str, records: list[tuple[str, str]] | None = None) -> str:
    """A real answer of the AEAT's preproduction, its line repeated for each (operation, number) of the test."""
    body = FIXTURES.joinpath(name).read_text(encoding="utf-8")
    if not records:
        return body
    found = re.search(r"<tikR:RespuestaLinea>.*?</tikR:RespuestaLinea>", body, re.DOTALL)
    line = found.group(0)
    original = re.search(r"<tik:NumSerieFactura>(.*?)</tik:NumSerieFactura>", line).group(1)
    lines = "".join(
        line.replace(original, number).replace(
            "<tik:TipoOperacion>Alta</tik:TipoOperacion>", f"<tik:TipoOperacion>{operation}</tik:TipoOperacion>"
        )
        for operation, number in records
    )
    return body.replace(line, lines)


def paged(body: str, last: tuple[str, str, str]) -> str:
    """A real query answer as the AEAT gives it when more follow (RespuestaConsultaLR.xsd, §6.4.3):
    ``IndicadorPaginacion`` S and ``ClavePaginacion`` naming its last record (nif, number, dd-mm-yyyy).
    The preproduction never paginated for us (it takes over 10,000 records), so only these two fields change."""
    nif, number, day = last
    key = (
        f"<tikLRRC:ClavePaginacion><tik:IDEmisorFactura>{nif}</tik:IDEmisorFactura>"
        f"<tik:NumSerieFactura>{number}</tik:NumSerieFactura>"
        f"<tik:FechaExpedicionFactura>{day}</tik:FechaExpedicionFactura></tikLRRC:ClavePaginacion>"
    )
    closing = "</tikLRRC:RespuestaConsultaFactuSistemaFacturacion>"
    return body.replace(
        "<tikLRRC:IndicadorPaginacion>N</tikLRRC:IndicadorPaginacion>",
        "<tikLRRC:IndicadorPaginacion>S</tikLRRC:IndicadorPaginacion>",
    ).replace(closing, key + closing)


@pytest.fixture
def gateway_answers(settings, monkeypatch):
    """The SaaS's gateway configured, its transport replaced: ``set(reply)`` fixes what the next calls answer
    (a ``gateway.Reply``, or a callable of the call's payload); ``calls`` keeps what was handed to it."""
    settings.VERIFACTU_GATEWAY_URL = "http://saas.internal:8001"

    class Fake:
        calls: list[tuple[str, dict]] = []
        reply = None

        def set(self, reply):
            self.reply = reply

        def answer(self, path, payload):
            self.calls.append((path, payload))
            reply = self.reply
            return reply(payload) if callable(reply) else reply

    fake = Fake()
    fake.calls = []
    monkeypatch.setattr(gateway, "_reply", fake.answer)
    return fake


def answering(name: str = "desglose_mixed_2026-09-22.xml"):
    """The gateway hands back the AEAT's real answer ``name`` for every record of the submission."""

    def reply(payload):
        return gateway.Reply(
            kind=gateway.ANSWERED, aeat_status=200, aeat_body=aeat_answer(name, records_of(payload["envelope"]))
        )

    return reply


@pytest.fixture
def scope_b():
    return system_context(B)
