"""The input of saying later which sale charged a voucher sold (SERVICE-F36)."""

from uuid import UUID

from django.utils.translation import gettext_lazy as _
from ninja import Field
from pydantic import model_validator

from apps.service.schemas.fields import A_SALE, A_SALE_LINE
from apps.service.schemas.grants import GrantRefIn

SAY_WHICH_SALE = _("Say which sale charged the voucher.")


class GrantSaleIn(GrantRefIn):
    sale_id: UUID | None = Field(
        None,
        description="The sale that charged it (Sales): from now on its sessions count for whoever does them.",
        json_schema_extra=A_SALE,
    )
    sale_line_id: UUID | None = Field(
        None,
        description="The line of that sale that charged it; only needed when the sale charged several (Sales).",
        json_schema_extra=A_SALE_LINE,
    )

    @model_validator(mode="after")
    def _said(self):
        if self.sale_id is None and self.sale_line_id is None:
            raise ValueError(str(SAY_WHICH_SALE))
        return self
