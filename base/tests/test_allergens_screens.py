"""The list of allergens the screens paint (@erplora/ui) is the server's: same codes, same order, same names."""

import json
import re
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import translation

from base import allergens

SELECTOR = Path(settings.BASE_DIR) / "packages/ui/src/components/AllergenSelect"


def test_the_screens_list_the_codes_of_the_server_in_its_order():
    source = (SELECTOR / "allergens.ts").read_text()
    listed = re.search(r"ALLERGEN_CODES = \[(.*?)\] as const", source, re.DOTALL)
    assert listed is not None
    assert re.findall(r"'([a-z_]+)'", listed.group(1)) == list(allergens.CODES)


@pytest.mark.parametrize("language", ["en", "es"])
def test_the_screens_name_each_allergen_as_the_server_does(language):
    names = json.loads((SELECTOR / f"locales/{language}.json").read_text())["allergens"]
    with translation.override(language):
        assert names == {code: str(name) for code, name in allergens.ALLERGENS}
