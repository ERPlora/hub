"""The signed representation authorisation: its state, its steps, what was sent and the official model."""

import datetime as dt
from typing import Literal

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import SecretStr

from apps.verifactu.schemas.fields import RepresentationCode, _text


DocumentName = Literal[
    "signed_model", "id_copy", "signature_sample", "representation_proof"
]


class RepresentationSubmissionOut(Schema):
    """The last authorisation sent from this Hub: what was sent, never its content."""

    version: int = Field(description="Its number at ERPlora.")
    submitted_at: dt.datetime | None = Field(description="When ERPlora received it.")
    document_type: Literal["dni", "nie"] = Field(
        description="The signer's identity document: dni or nie."
    )
    documents: list[DocumentName] = Field(
        description="The documents sent: signed_model, id_copy, signature_sample, representation_proof."
    )


class RepresentationStepOut(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    at: dt.datetime = Field(description="When it happened.")
    version: int | None = Field(description="The authorisation's number, when sent from here.")
    reason: str = Field(description="The reviewer's note.")


class RepresentationOut(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    updated_at: dt.datetime | None = Field(description="When it last changed.")
    reason: str = Field(description="The reviewer's note.")
    linked: bool = Field(
        False,
        description="ERPlora's account has linked this business: the authorisation can be sent from here.",
    )
    company: bool = Field(
        False,
        description="Invoicing's issuer is a company: who signs for it and the proof of representation are asked.",
    )
    submission: RepresentationSubmissionOut | None = Field(
        None, description="The last authorisation sent from this Hub."
    )
    history: list[RepresentationStepOut] = Field(
        default_factory=list, description="Its steps, newest first."
    )


class RepresentationIn(Schema):
    status: RepresentationCode = Field(
        description="none, submitted, approved, returned or revoked."
    )
    updated_at: dt.datetime | None = Field(None, description="When it last changed.")
    reason: _text(500) = Field("", description="The reviewer's note.")


class RepresentationSubmitIn(Schema):
    """The signed representation authorisation (Anexo I of Convenio 17) and its documents, each a PDF in base64 of
    5 MB at most. Who owes the tax is Invoicing's issuer; a self-employed business signs itself."""

    signer_tax_id: _text(16) = Field(
        "",
        title=gettext_noop("ID number of the person signing"),
        description="Tax ID (DNI or NIE) of whoever signs; for a self-employed business, left empty: its own.",
    )
    signer_name: _text(200) = Field(
        "",
        title=gettext_noop("Full name of the person signing"),
        description="Full name of whoever signs; for a self-employed business, left empty: its own.",
    )
    signer_document_type: Literal["dni", "nie"] = Field(
        title=gettext_noop("Identity document"),
        description="The signer's identity document: dni or nie.",
    )
    signed_model_base64: SecretStr = Field(
        title=gettext_noop("Signed model"),
        description="The official model, signed by hand and scanned or with AutoFirma: a PDF in base64.",
    )
    id_copy_base64: SecretStr = Field(
        title=gettext_noop("Copy of the identity document"),
        description="Copy of the signer's identity document: a PDF in base64.",
    )
    signature_sample_base64: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Signature sample"),
        description="A sheet with the signer's handwritten signature, required with a NIE: a PDF in base64.",
    )
    representation_proof_base64: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Proof of representation"),
        description="The document that names who may sign for a company, required for one: a PDF in base64.",
    )


class RepresentationModelOut(Schema):
    filename: str = Field(description="The file's name.")
    content_type: str = Field(description="The file's type: application/pdf.")
    content_base64: str = Field(
        description="The official model (Anexo I of Convenio 17) with Invoicing's issuer written in, a PDF in base64."
    )
