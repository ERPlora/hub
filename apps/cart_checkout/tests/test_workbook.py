"""The English WORKBOOK of cart_checkout speaks English: no Spanish date marker survives the translation.

CART_CHECKOUT-F08 step 3 names the order's number; in Spanish its date reads ``AAAAMMDD``, in English
``YYYYMMDD``. The criterion is the one translate_workbooks applies when it writes a translation, written
here on purpose: base's own pattern is private.
"""

import re
from pathlib import Path

from django.apps import apps

from base.workbook_sections import MARK

WORKBOOK_EN = Path(apps.get_app_config("cart_checkout").path) / "WORKBOOK.en.md"
SPANISH_DATE = re.compile(r"[\w/:-]*(?:AAAA|aaaa)[\w/:-]*")


def user_part_lines() -> list[tuple[int, str]]:
    """The lines a customer reads: a mark's hash may spell «aaaa»."""
    lines = WORKBOOK_EN.read_text(encoding="utf-8").splitlines()
    return [(number, line) for number, line in enumerate(lines, start=1) if not MARK.fullmatch(line)]


def test_the_english_workbook_has_no_spanish_date_marker():
    found = [f"l.{number}: {marker}" for number, line in user_part_lines() for marker in SPANISH_DATE.findall(line)]
    assert not found, f"Spanish date marker(s) in {WORKBOOK_EN.name}: {found}"


def test_the_order_number_reads_in_english():  # flow: CART_CHECKOUT-F08
    assert any("`OS-YYYYMMDD-NNNN`" in line for _, line in user_part_lines())
