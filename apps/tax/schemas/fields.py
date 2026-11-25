"""What the schemas of Taxes share: an empty text, the tax family and the qualification, and the page of a list."""

from typing import Any, Generic, Literal, TypeVar

from ninja import Field, Schema

from apps.tax.models import TaxRule

T = TypeVar("T")


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


TaxType = Literal[*TaxRule.TaxType.values]
OperationClass = Literal[*TaxRule.OperationClass.values]
Direction = Literal["asc", "desc"]

# Descriptions shared by several schemas.
SEARCH = "Free text to search."
DIRECTION = "Sort direction: asc or desc."
TAX_TYPE = "Tax family: vat, igic (Canary Islands), ipsi (Ceuta and Melilla), surcharge, sales_tax, withholding, excise or import_duty."
OPERATION_CLASS = (
    "Fiscal qualification: subject, subject_reverse (reverse charge), exempt, not_subject or "
    "not_subject_location (place of supply rules). Every class but subject charges no tax."
)


# Pages: every list is paginated, limit ≤ 100.


class PageIn(Schema):
    limit: int = Field(50, ge=1, le=100, description="Rows per page, 1 to 100.")
    offset: int = Field(0, ge=0, description="Rows to skip.")


class Page(Schema, Generic[T]):
    rows: list[T] = Field(description="The rows of this page.")
    total: int = Field(description="Rows that match, in every page.")
    limit: int = Field(description="Rows per page asked.")
    offset: int = Field(description="Rows skipped.")
