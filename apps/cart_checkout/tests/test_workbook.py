"""The English WORKBOOK of cart_checkout speaks English: no Spanish date marker survives the translation.

CART_CHECKOUT-F08 step 3 names the order's number; in Spanish its date reads ``AAAAMMDD``, in English
``YYYYMMDD``. The criterion is the one translate_workbooks applies when it writes a translation, written
here on purpose: base's own pattern is private.
"""

import re
from pathlib import Path

from django.apps import apps

WORKBOOK_EN = Path(apps.get_app_config("cart_checkout").path) / "WORKBOOK.en.md"
SPANISH_DATE = re.compile(r"[\w/:-]*(?:AAAA|aaaa)[\w/:-]*")
# Line 1 carries the source's sha256, whose hex digits may spell «aaaa»: it is not the customer's part.
HEADER = "<!-- generated from WORKBOOK.md sha256:"


def user_part_lines() -> list[tuple[int, str]]:
    lines = WORKBOOK_EN.read_text(encoding="utf-8").splitlines()
    assert lines and lines[0].startswith(HEADER), f"{WORKBOOK_EN.name} does not start with its header"
    return list(enumerate(lines, start=1))[1:]


def test_the_english_workbook_has_no_spanish_date_marker():
    found = [f"l.{number}: {marker}" for number, line in user_part_lines() for marker in SPANISH_DATE.findall(line)]
    assert not found, f"Spanish date marker(s) in {WORKBOOK_EN.name}: {found}"


def test_the_order_number_reads_in_english():  # flow: CART_CHECKOUT-F08
    assert any("`OS-YYYYMMDD-NNNN`" in line for _, line in user_part_lines())
