"""The menu's image (COMBO-F14, base.images): one of the shared library or a photo of its own."""

from typing import Annotated
from uuid import UUID

from django.utils.translation import gettext_noop
from ninja import Field, Schema
from pydantic import StringConstraints

from apps.combo.schemas.references import ComboRefIn
from base.images import MAX_UPLOAD_BASE64
from base.schemas import assistant, catalog_images

#: An image a write sets: the assistant's card names it by its title in the library, never by its reference.
AN_IMAGE = assistant.names("base.catalog_image.get", by="reference", name=("title",))


class ComboImageIn(ComboRefIn):
    image: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] = Field(
        title=gettext_noop("Image"),
        description="The image the menu shows: an image of the shared library by its reference, "
        "catalog:<folder>/<name> (base.catalog_image.search, combo.combo.suggest_image), or empty for none.",
        json_schema_extra=AN_IMAGE,
    )


class ComboImageUploadIn(ComboRefIn):
    data_base64: str = Field(
        max_length=MAX_UPLOAD_BASE64,
        description="The photo, a JPG, PNG or WebP of 2 MB at most, in base64; it is kept as a 512 × 512 WebP.",
    )


class ComboImageSuggestIn(ComboRefIn):
    limit: int = Field(5, ge=1, le=20, description="How many images to propose (1 to 20).")


class ComboImageSuggestOut(Schema):
    combo_id: UUID = Field(description="The menu the images are proposed for.")
    query: str = Field(description="What was looked for in the library: the menu's name.")
    rows: list[catalog_images.CatalogImageOut] = Field(
        description="The library's images that match its name, the best first; none is set until one is chosen."
    )
