"""The business's own certificate: what the screen shows of it and its upload."""

import datetime as dt
from typing import Literal

from django.utils.translation import gettext_lazy as _
from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import SecretStr, field_validator

from apps.verifactu.models import OwnCertificate


CERTIFICATE_TOO_LARGE = _("The certificate file has to be 1 MB at most.")
#: The largest .p12/.pfx taken (as the screen says, ConfigPage): a larger file is no certificate.
MAX_CERTIFICATE_BYTES = 1024 * 1024


class CertificateOut(Schema):
    loaded: bool = Field(description="An own certificate is loaded in this Hub.")
    holder: str = Field(description="Its holder.")
    holder_tax_id: str = Field(description="Its holder's tax ID.")
    kind: Literal["", *OwnCertificate.Kind.values] = Field(
        description="seal, representative, personal or unknown; empty without one."
    )
    uploaded_at: dt.datetime | None = Field(description="When it was uploaded.")
    expires_at: dt.datetime | None = Field(description="When it expires.")
    expires_in_days: int | None = Field(description="Days left (negative: expired).")
    expires_soon: bool = Field(description="It expires within the notice period and has not expired: the screen warns.")


class CertificateUploadIn(Schema):
    """The business's own certificate: kept sealed in the hub's database, never shown again."""

    p12_base64: SecretStr = Field(
        title=gettext_noop("Business certificate (.p12 / .pfx)"),
        description="The .p12/.pfx file of the certificate, in base64 (at most 1 MB).",
    )
    password: SecretStr = Field(
        SecretStr(""),
        title=gettext_noop("Certificate password"),
        description="The certificate's password.",
    )

    @field_validator("p12_base64")
    @classmethod
    def _at_most_one_mb(cls, value: SecretStr) -> SecretStr:
        """Measured on the base64 itself, before anything is decoded: what it would decode to."""
        text = "".join(value.get_secret_value().split())
        size = len(text) * 3 // 4 - (len(text) - len(text.rstrip("=")))
        if size > MAX_CERTIFICATE_BYTES:
            raise ValueError(str(CERTIFICATE_TOO_LARGE))
        return value
