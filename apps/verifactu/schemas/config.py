"""The configuration of VeriFactu: its environment, route, producer and blockers, and the ERPlora account's block of
the hub's photo."""

import datetime as dt
from typing import Literal
from uuid import UUID

from ninja import Field, Schema
from pydantic import ConfigDict

from apps.verifactu.schemas.authorisation import RepresentationIn, RepresentationOut
from apps.verifactu.schemas.fields import EnvironmentCode, RouteCode, WaitOut
from apps.verifactu.schemas.own_certificate import CertificateOut


class ProducerOut(Schema):
    name: str = Field(description="NombreRazon of the producer.")
    nif: str = Field(description="NIF of the producer.")
    system_name: str = Field(description="NombreSistemaInformatico.")
    system_id: str = Field(description="IdSistemaInformatico.")
    version: str = Field(description="Version installed.")
    installation: str = Field(description="NumeroInstalacion.")
    only_verifactu: str = Field(description="TipoUsoPosibleSoloVerifactu.")
    multi_ot: str = Field(description="TipoUsoPosibleMultiOT.")
    multiple_ot: str = Field(
        description="IndicadorMultiplesOT (always S: ERPlora serves several taxpayers)."
    )


class ConfigOut(Schema):
    environment: EnvironmentCode = Field(description="testing or production.")
    route: RouteCode = Field(
        description="The route the records go by, never chosen: own while a valid own certificate is uploaded, erplora "
        "(ERPlora files for you) without one; fixed when going live."
    )
    erplora_route_available: bool = Field(
        description="ERPlora's route is open to this business here; if not, only the own certificate goes live."
    )
    production_since: dt.datetime | None = Field(description="When it went live.")
    production_open: bool = Field(description="This server lets a business go live.")
    can_go_back: bool = Field(
        description="It can go back to testing (no production record yet)."
    )
    gateway_configured: bool = Field(description="This server has ERPlora's gateway.")
    issuer_nif: str = Field(description="Invoicing's issuer tax ID.")
    issuer_name: str = Field(description="Invoicing's issuer legal name.")
    producer: ProducerOut = Field(description="SistemaInformatico.")
    declaration_version: str = Field(description="Version of the responsible declaration.")
    declaration_url: str = Field(description="Where to read it.")
    account_url: str = Field(
        description="The ERPlora account, where the signed authorisation is managed."
    )
    own_certificate: CertificateOut = Field(description="The own certificate uploaded in this Hub (never its material).")
    representation: RepresentationOut = Field(
        description="The signed authorisation, as the account says."
    )
    synced_at: dt.datetime | None = Field(
        description="When the account last sent its data."
    )
    route_ready: bool = Field(description="The route can file in this environment.")
    route_ready_for_production: bool = Field(
        description="The route could carry the records to the AEAT of production: the business's own valid "
        "certificate or, without one, ERPlora's with the signed authorisation approved (what the business has to do, "
        "whatever this server lacks)."
    )
    reasons: list[WaitOut] = Field(description="What keeps records from leaving now.")
    issue_blocker: WaitOut | None = Field(
        description="Why new sales and invoices are refused now (production without a way to the AEAT); "
        "none when they are not."
    )
    live_blockers: list[WaitOut] = Field(
        description="What keeps the business from going live now (empty when it can)."
    )


class ConfigSyncOut(Schema):
    applied: bool = Field(description="False when an equal or newer version was kept.")
    version: int | None = Field(description="The version kept.")


class ConfigSyncIn(Schema):
    """The ERPlora account's block of the hub's photo (WORKBOOK «Contrato con el SaaS»). Any other key is ignored,
    never refused: the SaaS still sends the retired ``live_paid`` until it stops (expand/contract)."""

    model_config = ConfigDict(extra="ignore")

    version: int = Field(
        ge=0, description="The photo's version; an equal or older one is ignored."
    )
    hub_id: UUID | None = Field(
        None, description="The business's id in ERPlora (the photo's path)."
    )
    representation: RepresentationIn | None = Field(
        None, description="The signed authorisation's state."
    )
    hub_status: Literal["active", "past_due", "suspended"] | None = Field(
        None, description="The business's commercial status."
    )
