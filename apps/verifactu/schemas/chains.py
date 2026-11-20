"""The chains of records of each issuer: their state, their validation and their recovery."""

import datetime as dt
from typing import Any

from django.utils.translation import gettext_lazy as _
from ninja import Field, Schema
from pydantic import field_validator

from apps.verifactu import chain
from apps.verifactu.schemas.fields import EnvironmentCode, IssuerIn, _text


FINGERPRINT_INVALID = _("The fingerprint must be 64 hexadecimal characters.")


class ChainOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="testing or production.")
    sequence: int = Field(description="Last sequence given.")
    last_number: str = Field(
        description="Invoice of the last record (or of the anchor)."
    )
    last_issue_date: dt.date | None = Field(description="Its date.")
    last_fingerprint: str = Field(description="Its fingerprint.")
    anchored_at: dt.datetime | None = Field(
        description="When the chain was last anchored (recovery, migration)."
    )
    anchor_source: str = Field(description="aeat or manual.")
    validated_at: dt.datetime | None = Field(description="When it was last validated.")
    valid: bool | None = Field(
        description="The last verdict: intact, broken, or not validated."
    )
    total: int = Field(description="Records the last validation checked.")
    first_invalid_sequence: int | None = Field(description="Where it broke, if it did.")


class ChainStatusOut(Schema):
    issuer_nif: str = Field(
        description="The issuer asked for (Invoicing's by default)."
    )
    environment: EnvironmentCode = Field(description="The environment now.")
    chains: list[ChainOut] = Field(description="That issuer's chains.")


class ChainValidationOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="The chain's environment.")
    valid: bool = Field(description="Every fingerprint recomputes and chains.")
    total: int = Field(description="Records checked.")
    first_invalid_sequence: int | None = Field(description="Where it breaks.")


class RecoveryOut(Schema):
    issuer_nif: str = Field(description="Issuer's tax ID.")
    environment: EnvironmentCode = Field(description="The chain's environment.")
    sequence: int = Field(
        description="The chain's last sequence (the next record takes the following one)."
    )
    invoice_number: str = Field(description="The invoice the chain continues after.")
    fingerprint: str = Field(description="The fingerprint the next record chains to.")
    found: int = Field(description="Records the AEAT returned (0 for a manual anchor).")


class ChainValidateIn(IssuerIn):
    """The chain of an issuer in the current environment."""


class RecoverFromAeatIn(IssuerIn):
    """Anchor the chain on the last record the AEAT holds this month."""


class RecoverManualIn(IssuerIn):
    fingerprint: str = Field(
        description="The last fingerprint of the previous application, 64 hexadecimal characters."
    )
    invoice_number: _text(60, min_length=1) = Field(description="Its invoice number.")
    issue_date: dt.date = Field(description="Its invoice's issue date (YYYY-MM-DD).")

    @field_validator("fingerprint", mode="before")
    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        text = chain.normalize_hash(value) if isinstance(value, str) else ""
        if not chain.is_valid_hash(text):
            raise ValueError(str(FINGERPRINT_INVALID))
        return text
