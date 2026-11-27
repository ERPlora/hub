"""The card of an import of products or categories from a file: its rows by their names (``base.assistant.file_rows``)
and the tax categories they take, once each, as the card said them."""

from apps.inventory.schemas.fields import TAX_CATEGORY
from base.assistant import file_rows

summary = file_rows.rows_named_by("rows", "name", beside={"tax_category_key": TAX_CATEGORY})
