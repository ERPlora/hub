"""The departments of the open price and the quick notes of the line-note sheet."""

from collections.abc import Iterable
from uuid import UUID

from django.utils import translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict, InvalidPayload, NotFound
from live.operations import AI, operation

from apps.sale.models import Department, OrderLine, QuickNote
from apps.sale.queries.rows import held
from apps.sale.schemas import DepartmentListIn, DepartmentPage, OpenLineFields, QuickNoteListIn, QuickNotePage
from apps.tax.models import TaxCategory
from apps.tax.queries import business_jurisdiction, business_today, category_by_reference, current_rates
from base.ordering import list_order

DEPARTMENT_NOT_FOUND = _(
    "That section is no longer in this business. Reload the list and try again."
)
DEPARTMENT_AMBIGUOUS = _(
    "Several sections match «%(said)s»: %(names)s. Say which one."
)
QUICK_NOTE_NOT_FOUND = _(
    "That quick note is no longer in this business. Reload the list and try again."
)
QUICK_NOTE_AMBIGUOUS = _(
    "Several quick notes match «%(said)s»: %(names)s. Say which one."
)
TAX_CATEGORY_UNKNOWN = _("That tax category does not exist in Taxes.")


def department_row(department: Department, rates: dict) -> dict:
    resolution = rates.get(department.tax_category_id)
    return {
        "id": department.id,
        "name": department.name,
        "tax_category_key": department.tax_category.key,
        "tax_category_name": department.tax_category.display_name,
        "tax_rate_pct": resolution.rate_pct if resolution else None,
        "sort_order": department.sort_order,
    }


def department_rates(departments: list[Department]) -> dict:
    categories = list({d.tax_category_id: d.tax_category for d in departments}.values())
    return current_rates(categories, *business_jurisdiction(), business_today())


def _find_named(  # noqa: PLR0913
    rows, item_id, said, field: str, *, missing, ambiguous, code: str, lock: bool
):
    rows = rows.filter(is_deleted=False)
    if lock:
        rows = rows.select_for_update()
    if item_id is not None:
        found = rows.filter(pk=item_id).first()
    else:
        exact = list(rows.filter(**{f"{field}__iexact": said.strip()})[:2])
        found_rows = exact or list(
            rows.filter(**{f"{field}__icontains": said.strip()})[:6]
        )
        if len(found_rows) > 1:
            names = ", ".join(getattr(row, field) for row in found_rows[:5])
            raise Conflict(
                str(ambiguous) % {"said": said, "names": names},
                code=f"sale.{code}_ambiguous",
            )
        found = found_rows[0] if found_rows else None
    if found is None:
        raise NotFound(str(missing), code=f"sale.{code}_not_found")
    return found


def find_department(
    department_id: UUID | None, said: str | None, *, lock: bool = False
) -> Department:
    return _find_named(
        Department.objects.select_related("tax_category"),
        department_id,
        said,
        "name",
        missing=DEPARTMENT_NOT_FOUND,
        ambiguous=DEPARTMENT_AMBIGUOUS,
        code="department",
        lock=lock,
    )


def hold_departments(lines: Iterable[tuple[OpenLineFields, OrderLine]]) -> None:
    """Holds the departments of the open-price ``lines`` (each with the input that named it) in id order
    (``held``) until the write that adds them ends; one deleted since it was read is refused as one that never was.
    The business's own «Delete» only retires one (lines keep it), so a retired one is still there to hold."""
    named = {line.department_id: data for data, line in lines if line.department_id is not None}
    if not named:
        return
    kept = {row.pk for row in held(Department.objects.filter(pk__in=named).order_by("id"))}
    for department_id, data in named.items():
        if department_id not in kept:
            raise _department_refused(data, str(DEPARTMENT_NOT_FOUND))


def find_quick_note(
    note_id: UUID | None, said: str | None, *, lock: bool = False
) -> QuickNote:
    return _find_named(
        QuickNote.objects.all(),
        note_id,
        said,
        "text",
        missing=QUICK_NOTE_NOT_FOUND,
        ambiguous=QUICK_NOTE_AMBIGUOUS,
        code="quick_note",
        lock=lock,
    )


def find_tax_category(reference: str, field: str = "tax_category_key") -> TaxCategory:
    """An active tax category by its key, its name or an alias; else a 422 on ``field``."""
    category = category_by_reference(reference)
    if category is None or not category.is_active:
        raise InvalidPayload(
            str(TAX_CATEGORY_UNKNOWN),
            code="invalid_field",
            fields={field: str(TAX_CATEGORY_UNKNOWN)},
        )
    return category


@operation(
    "sale.department.list",
    kind="query",
    permission="sale.view_sale",
    input=DepartmentListIn,
    output=DepartmentPage,
    ai=AI(
        description="List the departments of the till's open price, in the order they are shown, with the tax category "
        "each one charges at and its rate today.",
        asks={
            "en": (
                "what sections do we have for open prices?",
                "which VAT does the drinks section charge?",
            ),
            "es": (
                "¿qué secciones tengo para el precio libre?",
                "¿a qué IVA va la sección de bebidas?",
            ),
        },
    ),
)
def list_departments(ctx: OperationContext, params: DepartmentListIn) -> dict:
    with translation.override(ctx.language):
        departments = Department.objects.filter(is_deleted=False).select_related(
            "tax_category"
        )
        if params.search:
            departments = departments.filter(name__icontains=params.search.strip())
        ordered = departments.order_by(
            *list_order(params.sort, "name", descending=params.dir == "desc")
        )
        page = list(ordered[params.offset : params.offset + params.limit])
        rates = department_rates(page)
        return {
            "rows": [department_row(department, rates) for department in page],
            "total": departments.count(),
            "limit": params.limit,
            "offset": params.offset,
        }


def quick_note_row(note: QuickNote) -> dict:
    return {"id": note.id, "text": note.text, "sort_order": note.sort_order}


@operation(
    "sale.quick_note.list",
    kind="query",
    permission="sale.view_sale",
    input=QuickNoteListIn,
    output=QuickNotePage,
    ai=AI(
        description="List the quick notes the line-note sheet of the till offers, in the order they are shown.",
        asks={
            "en": (
                "what notes can waiters pick for a dish?",
                "show me the kitchen notes we have",
            ),
            "es": (
                "¿qué notas pueden elegir los camareros?",
                "enséñame las notas de cocina que tenemos",
            ),
        },
    ),
)
def list_quick_notes(ctx: OperationContext, params: QuickNoteListIn) -> dict:
    notes = QuickNote.objects.filter(is_deleted=False)
    if params.search:
        notes = notes.filter(text__icontains=params.search.strip())
    page = notes.order_by(*list_order(params.sort, "text", descending=params.dir == "desc"))[
        params.offset : params.offset + params.limit
    ]
    return {
        "rows": [quick_note_row(note) for note in page],
        "total": notes.count(),
        "limit": params.limit,
        "offset": params.offset,
    }


def _department_refused(data: OpenLineFields, message: str) -> InvalidPayload:
    """The 422 of an open-price line whose department is not there, on the field that named it."""
    field = "department_id" if data.department_id is not None else "department"
    return InvalidPayload(message, code="invalid_field", fields={field: message})
