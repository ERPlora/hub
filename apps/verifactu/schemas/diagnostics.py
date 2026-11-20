"""The test of the route to the AEAT and the test invoice."""

import datetime as dt
from uuid import UUID

from ninja import Field, Schema

from apps.verifactu.schemas.fields import EnvironmentCode, RouteCode, WaitOut
from apps.verifactu.schemas.records import RecordSummaryOut


class DiagnosticOut(Schema):
    ran_at: dt.datetime = Field(description="When it ran.")
    environment: EnvironmentCode = Field(description="The environment tested.")
    route: RouteCode = Field(description="The route tested.")
    issuer_ready: bool = Field(description="Invoicing's issuer is set.")
    route_ready: bool = Field(description="The route can file in this environment.")
    gateway_configured: bool = Field(description="This server has ERPlora's gateway.")
    gateway_ready: bool | None = Field(
        description="The gateway's answer: it can present now (none: not asked)."
    )
    gateway_detail: str = Field(description="What the gateway said.")
    can_send: bool = Field(description="Everything is ready to send.")
    reasons: list[WaitOut] = Field(description="What is missing.")


class DiagnosticLastOut(Schema):
    result: DiagnosticOut | None = Field(description="The last test, or none.")


class TestInvoiceOut(Schema):
    invoice_id: UUID = Field(description="Id of the test invoice.")
    number: str = Field(description="Its number.")
    record: RecordSummaryOut = Field(description="Its record.")
