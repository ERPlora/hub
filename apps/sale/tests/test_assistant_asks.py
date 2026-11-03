"""What layer 1 of the assistant's QA does not say of Sales & POS (erplora-next docs plan 2026-10-31, the assistant's
knowledge and QA): how many phrases its tools put to a turn, and what each role is never offered.

Every ask of every tool of sale bringing its tool among the first ten, role by role, in English and in Spanish, out of
the catalogue of a business with every app on and ranked as a turn ranks, is ``base/tests/test_assistant_asks.py``'s
(sale is listed in ``LIVE_ASSISTANT_ASKS_REQUIRED``), as ``live.E020`` over its asks.
"""

import pytest
from live.assistant import asks_of
from live.operations import registry

from apps.sale.tests.conftest import ctx_for
from base import assistant

LANGUAGES = ("en", "es")
#: The phrases of sale's tools put to the turn at least, both languages together: a silent drop of asks fails.
MIN_PHRASES = 200


def test_every_phrase_of_sale_is_one_of_at_least_200():
    """Each tool of sale says at least two phrases in each language (``live.E020``); they are at least ``MIN_PHRASES``
    in all, so what the layer ranks is the whole set and never a silent few."""
    sale = [op for op in registry.values() if op.app_label == "sale" and assistant.is_tool(op)]
    assert sum(len(asks_of(op).get(language, ())) for op in sale for language in LANGUAGES) >= MIN_PHRASES


@pytest.mark.django_db  # the catalogue is of the apps on in the business (base.activation)
def test_what_the_employee_may_not_do_is_not_in_their_catalogue():
    """The till's settings are the manager's (``sale.manage_settings``), and no manager approves them on the spot:
    the employee's turn never offers them, whatever they ask; the figures of the business are not theirs either."""
    employee = assistant.catalog(ctx_for("hub_employee", language="es"))
    manager = assistant.catalog(ctx_for("hub_manager", language="es"))
    for name in ("sale.settings.update", "sale.payment_method.create", "sale.sale.today"):
        assert name in manager  # positive control: the manager holds it
        assert name not in employee
    # A write the employee lacks but a manager approves with their PIN stays theirs, as its button does (BASE-F84).
    assert "sale.sale.void" in employee
