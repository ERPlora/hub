"""The sale app's settings, payment methods, departments and quick notes."""


from django.db import IntegrityError
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import Conflict
from live.operations import AI, atomic, operation
from live.outbox import record_event

from apps.sale import events
from apps.sale.models import Department, PaymentMethod, QuickNote, Settings
from apps.sale.queries.business import actor
from apps.sale.queries.departments import (
    department_rates,
    department_row,
    find_department,
    find_quick_note,
    find_tax_category,
    quick_note_row,
)
from apps.sale.queries.payment_methods import allowed_types, payment_method_row
from apps.sale.queries.settings import current_settings, settings_row
from apps.sale.schemas import (
    DepartmentIn,
    DepartmentOut,
    DepartmentRefIn,
    DepartmentUpdateIn,
    PaymentMethodIn,
    PaymentMethodOut,
    QuickNoteIn,
    QuickNoteOut,
    QuickNoteRefIn,
    QuickNoteUpdateIn,
    SettingsOut,
    SettingsPatchIn,
)

METHOD_EXISTS = _("There is already a payment method with that name.")


# ── Settings ─────────────────────────────────────────────────────────────────────────────────────


def _locked_settings(ctx: OperationContext) -> Settings:
    """The business's settings row, locked; created with the factory values the first time."""
    settings = Settings.objects.select_for_update().first()
    if settings is not None:
        return settings
    try:
        with atomic():
            return Settings.objects.create(updated_by=actor(ctx))
    except IntegrityError:
        return Settings.objects.select_for_update().get()


@operation(
    "sale.settings.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=SettingsPatchIn,
    output=SettingsOut,
    ai=AI(
        description="Change the till settings field by field: which payment types charge, products and services shown, "
        "customer required, discounts and their cap (in %, per discount), parked checks, prices with VAT, the default "
        "document (ticket or invoice) and the receipt's texts. What is not sent is kept.",
        risk="normal",
        asks={
            "en": (
                "make the customer mandatory to charge",
                "cap discounts at 15%",
                "invoices by default from now on",
            ),
            "es": (
                "que no se pueda cobrar sin cliente",
                "pon el descuento máximo en un 15 %",
                "que cada venta salga con factura por defecto",
                "cambia el texto del pie del ticket",
            ),
        },
    ),
)
def update_settings(ctx: OperationContext, data: SettingsPatchIn) -> dict:
    settings = _locked_settings(ctx)
    sent = data.model_dump(exclude_unset=True, exclude_none=True)
    changes = {
        field: value
        for field, value in sent.items()
        if getattr(settings, field) != value
    }
    if changes:
        for field, value in changes.items():
            setattr(settings, field, value)
        settings.updated_by = actor(ctx)
        settings.save(update_fields=[*changes, "updated_by", "updated_at"])
        record_event(ctx, events.SETTINGS_UPDATED, {"fields": sorted(changes)})
    return settings_row(settings)


# ── Payment methods ──────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.payment_method.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.add_paymentmethod",
    input=PaymentMethodIn,
    output=PaymentMethodOut,
    ai=AI(
        description="Add a payment method to the charge sheet (Bizum, bank transfer, vouchers…), saying its type: cash, "
        "card, transfer or other. Without a type it is cash (it counts in the till and is limited from 1,000 €).",
        risk="normal",
        asks={
            "en": (
                "add Bizum as a way to pay",
                "let customers pay by bank transfer",
                "we take meal vouchers now",
            ),
            "es": (
                "añade Bizum como forma de pago",
                "quiero cobrar también por transferencia",
                "mete los cheques restaurante como forma de pago",
            ),
        },
    ),
)
def create_payment_method(ctx: OperationContext, data: PaymentMethodIn) -> dict:
    taken = {
        name.casefold() for name in PaymentMethod.objects.values_list("name", flat=True)
    }
    if data.name.casefold() in taken:
        raise Conflict(
            str(METHOD_EXISTS),
            code="sale.payment_method_exists",
            fields={"name": str(METHOD_EXISTS)},
        )
    method = PaymentMethod.objects.create(
        name=data.name,
        type=data.type,
        sort_order=data.sort_order,
        created_by=actor(ctx),
    )
    record_event(
        ctx, events.PAYMENT_METHOD_CREATED, {"id": str(method.id), "type": method.type}
    )
    methods = PaymentMethod.objects.filter(is_active=True)
    with translation.override(ctx.language):
        return payment_method_row(method, allowed_types(current_settings(), methods))


# ── Departments ──────────────────────────────────────────────────────────────────────────────────


def _department_out(ctx: OperationContext, department: Department) -> dict:
    with translation.override(ctx.language):
        return department_row(department, department_rates([department]))


@operation(
    "sale.department.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=DepartmentIn,
    output=DepartmentOut,
    ai=AI(
        description="Add a department to the till's open price: the name the cashier reads and the tax category (key, name "
        "or alias) it charges at, at a position.",
        risk="normal",
        asks={
            "en": (
                "add a Bakery section for open prices at the reduced rate",
                "create a section for loose sweets",
            ),
            "es": (
                "crea una sección «Bollería» con el IVA de la comida",
                "añade un departamento para las chuches a granel",
            ),
        },
    ),
)
def create_department(ctx: OperationContext, data: DepartmentIn) -> dict:
    category = find_tax_category(data.tax_category_key)
    department = Department.objects.create(
        name=data.name,
        tax_category=category,
        sort_order=data.sort_order,
        created_by=actor(ctx),
    )
    record_event(ctx, events.DEPARTMENT_CREATED, {"id": str(department.id)})
    return _department_out(ctx, department)


@operation(
    "sale.department.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=DepartmentUpdateIn,
    output=DepartmentOut,
    ai=AI(
        description="Change the name, the tax category (the VAT its products charge: a cheaper reduced rate, the "
        "standard one) or the position of a department of the open price. Pass its current name in department, or its "
        "id when already known; never ask the person for an internal id. What was already sold keeps the name and the "
        "VAT it was charged with.",
        risk="normal",
        asks={
            "en": (
                "move the drinks section to the standard VAT rate",
                "rename the Misc section to Others",
                "put the bakery section first",
                "sweets go at the reduced rate",
            ),
            "es": (
                "pon la sección de bebidas al IVA general",
                "renombra el departamento «Varios» a «Otros»",
                "pon la bollería la primera de las secciones",
                "las chuches pásalas al IVA reducido",
            ),
        },
    ),
)
def update_department(ctx: OperationContext, data: DepartmentUpdateIn) -> dict:
    department = find_department(data.id, data.department, lock=True)
    if data.name is not None:
        department.name = data.name
    if data.tax_category_key is not None:
        department.tax_category = find_tax_category(data.tax_category_key)
    if data.sort_order is not None:
        department.sort_order = data.sort_order
    department.save()
    record_event(ctx, events.DEPARTMENT_UPDATED, {"id": str(department.id)})
    return _department_out(ctx, department)


@operation(
    "sale.department.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=DepartmentRefIn,
    output=DepartmentOut,
    ai=AI(
        description="Retire a department of the open price (named by its id or its name). The lines already sold keep "
        "their name and VAT.",
        risk="normal",
        asks={
            "en": (
                "get rid of the bakery section",
                "delete the Misc department",
            ),
            "es": (
                "quita la sección de bollería",
                "borra el departamento «Varios»",
            ),
        },
    ),
)
def delete_department(ctx: OperationContext, data: DepartmentRefIn) -> dict:
    department = find_department(data.id, data.department, lock=True)
    department.is_deleted = True
    department.deleted_at = timezone.now()
    department.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    record_event(ctx, events.DEPARTMENT_DELETED, {"id": str(department.id)})
    return _department_out(ctx, department)


# ── Quick notes ──────────────────────────────────────────────────────────────────────────────────


@operation(
    "sale.quick_note.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=QuickNoteIn,
    output=QuickNoteOut,
    ai=AI(
        description="Add a quick note to the till (e.g. «no salt»): it becomes a chip of the line-note sheet, at a position.",
        risk="normal",
        asks={
            "en": (
                "add 'no salt' to the dish notes",
                "waiters should be able to tap 'well done'",
            ),
            "es": (
                "añade «sin sal» a las notas de cocina",
                "que los camareros puedan marcar «muy hecho»",
            ),
        },
    ),
)
def create_quick_note(ctx: OperationContext, data: QuickNoteIn) -> dict:
    note = QuickNote.objects.create(
        text=data.text, sort_order=data.sort_order, created_by=actor(ctx)
    )
    record_event(ctx, events.QUICK_NOTE_CREATED, {"id": str(note.id)})
    return quick_note_row(note)


@operation(
    "sale.quick_note.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=QuickNoteUpdateIn,
    output=QuickNoteOut,
    ai=AI(
        description="Change the text or the position of a quick note of the till. Pass its current text in quick_note, "
        "or its id when already known; never ask the person for an internal id.",
        risk="normal",
        asks={
            "en": (
                "change the 'no salt' note to 'low salt'",
                "move 'no ice' to the top of the notes",
                "the note should read 'gluten free' instead of 'no gluten'",
                "where it says 'spicy', put 'hot'",
            ),
            "es": (
                "cambia la nota «sin sal» por «poca sal»",
                "sube «sin hielo» a la primera de las notas",
                "la nota que pone «sin gluten», que diga «apto para celíacos»",
                "escribe «sin lactosa» en vez de «sin leche»",
            ),
        },
    ),
)
def update_quick_note(ctx: OperationContext, data: QuickNoteUpdateIn) -> dict:
    note = find_quick_note(data.id, data.quick_note, lock=True)
    if data.text is not None:
        note.text = data.text
    if data.sort_order is not None:
        note.sort_order = data.sort_order
    note.save()
    record_event(ctx, events.QUICK_NOTE_UPDATED, {"id": str(note.id)})
    return quick_note_row(note)


@operation(
    "sale.quick_note.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="sale.manage_settings",
    input=QuickNoteRefIn,
    output=QuickNoteOut,
    ai=AI(
        description="Retire a quick note of the till (named by its id or its text). The notes already written keep their text.",
        risk="normal",
        asks={
            "en": (
                "drop the 'no ice' note",
                "remove the 'well done' note",
            ),
            "es": (
                "quita la nota «sin hielo»",
                "borra lo de «muy hecho» de las notas",
            ),
        },
    ),
)
def delete_quick_note(ctx: OperationContext, data: QuickNoteRefIn) -> dict:
    note = find_quick_note(data.id, data.quick_note, lock=True)
    note.is_deleted = True
    note.deleted_at = timezone.now()
    note.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
    record_event(ctx, events.QUICK_NOTE_DELETED, {"id": str(note.id)})
    return quick_note_row(note)
