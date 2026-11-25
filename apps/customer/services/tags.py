"""Customer tags created, changed and deleted (CUSTOMER-F28)."""

from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.operations import AI, operation
from live.outbox import record_event

from apps.customer import events
from apps.customer.models import CustomerTag
from apps.customer.queries.reads import find_tag
from apps.customer.schemas.fields import DeletedOut, TagRefIn
from apps.customer.schemas.tags import TagIn, TagPatchIn, TagRow
from apps.customer.services.writes import _patched, _save_named, _with_count

TAG_NAME_TAKEN = _("There is already a tag with that name. Choose another name.")


@operation(
    "customer.tag.create",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=TagIn,
    output=TagRow,
    ai=AI(
        "Creates a customer tag (name unique among the active tags, and color).",
        asks={
            "en": ("create a vegan tag", "I need a new tag called regular"),
            "es": ("crea la etiqueta habitual", "nueva etiqueta: vegano"),
        },
    ),
)
def create_tag(ctx: OperationContext, data: TagIn) -> dict:
    tag = CustomerTag(**data.model_dump())
    _save_named(tag, TAG_NAME_TAKEN, "customer.tag_name_taken")
    record_event(ctx, events.TAG_CREATED, {"id": str(tag.id)})
    return _with_count(tag)


@operation(
    "customer.tag.update",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.configure",
    input=TagPatchIn,
    output=TagRow,
    ai=AI(
        "Updates a customer tag, by its id or current name: name, color and whether it is active.",
        asks={
            "en": ("rename the vegan tag to vegetarian", "make the VIP tag green"),
            "es": ("cambia la etiqueta vegano a vegetariano", "ponle color verde a la etiqueta VIP"),
        },
    ),
)
def update_tag(ctx: OperationContext, data: TagPatchIn) -> dict:
    tag = find_tag(data.id, data.tag, lock=True)
    if _patched(tag, data, {"id", "tag"}):
        _save_named(tag, TAG_NAME_TAKEN, "customer.tag_name_taken")
        record_event(ctx, events.TAG_UPDATED, {"id": str(tag.id)})
    return _with_count(tag)


@operation(
    "customer.tag.delete",
    kind="command",
    repeatable=True,  # Only its database: a cut before the COMMIT runs it again (live.database_cut, BASE-F111).
    permission="customer.delete",
    input=TagRefIn,
    output=DeletedOut,
    ai=AI(
        "Deletes a customer tag, by its id or name; the customers that had it lose it.",
        risk="high",
        asks={
            "en": ("delete the vegan tag", "get rid of the regular tag"),
            "es": ("borra la etiqueta vegano", "quita la etiqueta de habitual, ya no la usamos"),
        },
    ),
)
def delete_tag(ctx: OperationContext, data: TagRefIn) -> dict:
    tag = find_tag(data.id, data.tag, lock=True)
    tag_id = tag.id
    tag.delete()
    record_event(ctx, events.TAG_DELETED, {"id": str(tag_id)})
    return {"id": tag_id}
