"""The menu's image as an input: what one may be set to, how big a photo may be and how many are proposed."""

import uuid

from apps.combo.schemas.images import ComboImageIn, ComboImageSuggestIn, ComboImageUploadIn
from base.images import MAX_UPLOAD_BASE64

from .schema_checks import ID, refused


def test_an_image_is_a_reference_of_the_library_or_nothing():
    chosen = ComboImageIn.model_validate({"id": ID, "image": "  catalog:hospitality/menu_dia "})
    assert (chosen.id, chosen.image) == (uuid.UUID(ID), "catalog:hospitality/menu_dia")
    assert ComboImageIn.model_validate({"id": ID, "image": ""}).image == ""
    assert "image" in refused(ComboImageIn, {"id": ID, "image": "x" * 201})


def test_a_photo_has_a_top_size():
    assert ComboImageUploadIn.model_validate({"id": ID, "data_base64": "aGk="}).data_base64 == "aGk="
    assert "data_base64" in refused(ComboImageUploadIn, {"id": ID, "data_base64": "x" * (MAX_UPLOAD_BASE64 + 1)})


def test_it_proposes_from_one_to_twenty_images():
    assert ComboImageSuggestIn.model_validate({"id": ID}).limit == 5
    assert "limit" in refused(ComboImageSuggestIn, {"id": ID, "limit": 0})
    assert "limit" in refused(ComboImageSuggestIn, {"id": ID, "limit": 21})
