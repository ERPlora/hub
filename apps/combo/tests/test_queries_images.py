"""The images of the library proposed for a menu's photo (COMBO-F14)."""

from apps.combo.queries.images import suggest_image
from apps.combo.schemas.images import ComboImageSuggestIn
from base.tests.test_image_catalog import write_library

from .conftest import HUB_DB, ctx_for, make_combo

pytestmark = HUB_DB


def test_it_proposes_no_more_images_than_asked(settings, tmp_path):
    settings.CATALOG_DIR = str(write_library(tmp_path / "img"))
    combo = make_combo("Café")
    asked = [suggest_image(ctx_for(), ComboImageSuggestIn(id=combo.id, limit=limit)).rows for limit in (1, 20)]
    assert len(asked[0]) == 1 < len(asked[1])
    assert asked[1][0] == asked[0][0]
