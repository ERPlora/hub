"""The images of the rows that show one: one of the shared library travels as its reference, a photo of the
row's own inside the file, and loading it copies the photo through the app's own upload.
"""

import base64

import pydantic
from django.utils.translation import gettext_lazy as _
from live.context import OperationContext
from live.errors import OperationError

from base import images
from base.blueprint.calls import ROW_REFUSED, Loaded, _call, _reason

PHOTO_MISSING = _("«%(row)s»: its photo is not in the file, so it loads without it.")

#: The datasets whose rows show an image, and the operations that set one of the library and upload a photo.
IMAGE_OPERATIONS = {
    "inventory.product": ("inventory.product.set_image", "inventory.product.upload_image"),
    "service.service": ("service.service.set_image", "service.service.upload_image"),
}


def export_media(ctx: OperationContext, data: dict[str, list[dict]]) -> dict[str, bytes]:
    """The photos of its own that the rows of ``data`` show, by name, read from ``ctx``'s hub; a row whose photo the
    store no longer has travels without it (its ``image`` dropped), never with a reference the file cannot keep."""
    media = {}
    for key in IMAGE_OPERATIONS:
        for row in data.get(key, []):
            name = images.own_name(row.get("image", ""))
            if name is None:
                continue
            content = images.read_photo(ctx.scope, row["image"])
            if content is None:
                del row["image"]
            else:
                media[name] = content
    return media


def _load_image(ctx: OperationContext, loaded: Loaded, dataset_key: str, pk: str, row: dict, label: str) -> None:  # noqa: PLR0913, PLR0917
    """Show on the row just created the image its file names: one of the library through the app's ``set_image``, a
    photo the file carries through its ``upload_image`` (a copy under a new name, within the plan's space). One that
    cannot be set leaves the row without an image, and the report says why (INVENTORY-F33)."""
    image = row.get("image")
    if not isinstance(image, str) or not image.strip():
        return
    set_image, upload_image = IMAGE_OPERATIONS[dataset_key]
    name = images.own_name(image)
    try:
        if name is None:
            _call(ctx, set_image, id=pk, image=image)
        elif name not in loaded.media:
            loaded.warn(str(PHOTO_MISSING) % {"row": label})
        else:
            _call(ctx, upload_image, id=pk, data_base64=base64.b64encode(loaded.media[name]).decode("ascii"))
    except (OperationError, pydantic.ValidationError) as exc:
        loaded.warn(str(ROW_REFUSED) % {"row": label, "reason": _reason(exc)})
