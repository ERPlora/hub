"""Cards imported from a CSV file (CUSTOMER-F08)."""

import pydantic
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.ninja import FIELD_MESSAGES
from live.operations import operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.countries import country_from_text
from apps.customer.models import Customer
from apps.customer.phones import InvalidPhone, to_e164
from apps.customer.queries import business_country, has_live_twin
from apps.customer.schemas.cards import CustomerIn
from apps.customer.schemas.importing import ImportIn, ImportOut, ImportRowIn
from apps.customer.services.writes import PHONE_INVALID
from base.assistant import file_rows

COUNTRY_IMPORTED_EMPTY = _(
    "Country not recognised: imported without country, check it on the card."
)
ALREADY_IMPORTED = _(
    "There is already a card with this name, phone and email: it is not created again."
)
#: What the export put in front of a cell a spreadsheet would run (queries.FORMULA_STARTS).
EXPORT_GUARD = ("'=", "'+", "'-", "'@")


def _field_message(error: dict) -> str:
    """One pydantic error of a row as the 422 of the API words it (``live.ninja.FIELD_MESSAGES``)."""
    context = error.get("ctx") or {}
    if error.get("type") in ("value_error", "assertion_error"):
        return str(context.get("error") or error.get("msg"))
    template = FIELD_MESSAGES.get(error.get("type"))
    try:
        return (
            str(template % context) if template is not None else str(error.get("msg"))
        )
    except KeyError, TypeError, ValueError:
        return str(error.get("msg"))


def _import_row(
    row: ImportRowIn, ctx: OperationContext
) -> tuple[dict, dict[str, str], dict[str, str]]:
    """A CSV row as a new card's values, or why it is skipped, and what to review; a blank cell is a missing column."""
    raw = {
        field: value[1:] if value.startswith(EXPORT_GUARD) else value
        for field, value in row.model_dump().items()
    }
    warnings: dict[str, str] = {}
    # A code or a name in Spanish or English, as the screen reads it (countries.country_from_text).
    written = raw["country"].strip()
    country = country_from_text(written)
    if written and not country:
        warnings["country"] = str(COUNTRY_IMPORTED_EMPTY)
    stage = raw["lifecycle_stage"].strip().lower()
    candidate = {
        **{field: value for field, value in raw.items() if value.strip()},
        "country": country,
        # «customer» is how the product's older files called an active customer.
        "lifecycle_stage": "active" if stage in ("", "customer") else stage,
        "source": raw["source"].strip().lower() or Customer.Source.IMPORT,
        "preferred_channel": raw["preferred_channel"].strip().lower()
        or Customer.PreferredChannel.NONE,
        "birthday": raw["birthday"].strip() or None,
        "anniversary": raw["anniversary"].strip() or None,
    }
    try:
        values = CustomerIn.model_validate(candidate).model_dump()
    except pydantic.ValidationError as exc:
        errors: dict[str, str] = {}
        for error in exc.errors():
            errors.setdefault(
                str(error["loc"][0]) if error["loc"] else "name", _field_message(error)
            )
        return {}, errors, warnings
    try:
        values["phone"] = to_e164(values["phone"], business_country(ctx))
    except InvalidPhone:
        return {}, {"phone": str(PHONE_INVALID)}, warnings
    return values, {}, warnings


@operation(
    "customer.customer.import",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.manage",
    input=ImportIn,
    output=ImportOut,
    # A dict, not AI(...): AI carries no card summary (base.assistant.cards.card).
    ai={
        "description": "Creates customers in bulk from up to 50 rows of a CSV file: each row is checked on its own, "
        "the bad ones are skipped with their reason and the rest are created without consent.",
        "risk": "high",
        "asks": {
            "en": ("import my customers from this file", "bring in my clients from this CSV"),
            "es": ("súbeme los clientes de este fichero", "carga los clientes de este CSV"),
        },
        "summary": file_rows.by_name,
    },
)
def import_customers(ctx: OperationContext, data: ImportIn) -> dict:
    rows = []
    for index, row in enumerate(data.rows):
        values, errors, warnings = _import_row(row, ctx)
        customer_id = None
        if not errors and has_live_twin(values["name"], values["phone"], values["email"]):
            errors = {"name": str(ALREADY_IMPORTED)}
        if not errors:
            customer = Customer.objects.create(**values)
            record_event(ctx, events.CUSTOMER_CREATED, {"id": str(customer.id)})
            customer_id = customer.id
        rows.append(
            {"index": index, "id": customer_id, "errors": errors, "warnings": warnings}
        )
    created = sum(1 for row in rows if row["id"] is not None)
    return {"created": created, "skipped": len(rows) - created, "rows": rows}
