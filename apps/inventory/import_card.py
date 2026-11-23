"""The card of an import of products or categories from a file: its rows by their names (``base.assistant.file_rows``)
and the tax categories they take, once each, as the card said them."""

from django.utils.translation import gettext
from live.assistant import NAMED
from live.context import OperationContext

from apps.inventory.schemas.fields import TAX_CATEGORY
from base.assistant import file_rows


def _tax_categories(fields: list[dict]) -> list[str]:
    """The tax categories the rows take, as the card said each (by the name the Taxes screens give it, or as the file
    wrote it when no category bears it), in their order and without repeats."""
    rows = next((field["value"] for field in fields if field["name"] == "rows"), None)
    said = [row.get("tax_category_key") for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    return list(dict.fromkeys(text for text in said if isinstance(text, str) and text.strip()))


def summary(ctx: OperationContext, arguments: dict, fields: list[dict]) -> list[dict]:
    shown = file_rows.by_name(ctx, arguments, fields)
    categories = _tax_categories(fields)
    if not categories:
        return shown
    line = {"name": "tax_category_key", "label": gettext(TAX_CATEGORY), "kind": "list", "value": categories, NAMED: True}
    return [*shown, line]
