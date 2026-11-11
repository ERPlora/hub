"""hub#1208 in Modifiers: the yes to the card of a group said by its name touches only what that card showed.

The platform holds a yes to what its card read (``base/tests/test_assistant_yes_for_its_card.py``). No card of Modifiers
reads a group said by its name yet — it says the name as said and no check finds it —, so nothing holds the yes to it
(hub#1218). The control passes; the case of the issue waits on that issue, strict: once Modifiers names what it finds, it
passes and its mark goes.
"""

import pytest

from apps.modifier.models import ModifierGroup
from apps.modifier.tests.conftest import ctx_for
from base.tests.test_assistant_yes_for_its_card import yes_to_its_card

pytestmark = pytest.mark.django_db

BY_ITS_NAME = ("modifier.group.delete", {"group": "salsa"})


def test_the_yes_to_the_card_of_a_group_said_by_its_name_runs_on_it():
    """Control: nothing changed between the card and the yes."""
    shown = ModifierGroup.objects.create(name="Salsas picantes")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME)
    assert [row["outcome"] for row in done["executed"]] == ["ok"]
    assert not ModifierGroup.objects.filter(pk=shown.pk).exists()


@pytest.mark.xfail(strict=True, raises=AssertionError, reason="hub#1218: its card reads no record said by its name")
def test_the_yes_touches_only_the_group_its_card_showed_although_another_fits_the_name_better_meanwhile():
    ModifierGroup.objects.create(name="Salsas picantes")
    done = yes_to_its_card(ctx_for("hub_admin"), *BY_ITS_NAME, meanwhile=lambda: ModifierGroup.objects.create(name="Salsa"))
    assert done["executed"] == []
    assert ModifierGroup.objects.count() == 2
