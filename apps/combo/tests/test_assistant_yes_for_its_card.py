"""hub#1208 in Menus: the yes to the card of a menu said by its name touches only what that card showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). No card of Menus
reads a menu said by its name yet — it says the name as said and no check finds it —, so nothing holds the yes to it
(hub#1217). The control passes; the case of the issue waits on that issue, strict: once Menus names what it finds, it
passes and its mark goes.
"""

import pytest

from apps.combo.models import Combo
from apps.combo.tests.conftest import ctx_for, make_combo
from base.tests.test_assistant_yes_for_its_card import yes_to_its_card

pytestmark = pytest.mark.django_db

BY_ITS_NAME = ("combo.combo.delete", {"combo": "menú"})


def test_the_yes_to_the_card_of_a_menu_said_by_its_name_runs_on_it():
    """Control: nothing changed between the card and the yes."""
    shown = make_combo("Menú vegano")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert not Combo.objects.filter(pk=shown.pk).exists()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="hub#1217: its card reads no record said by its name")
def test_the_yes_touches_only_the_menu_its_card_showed_although_another_fits_the_name_better_meanwhile():
    make_combo("Menú vegano")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME, meanwhile=lambda: make_combo("Menú"))
    assert done["executed"] == []
    assert Combo.objects.count() == 2
