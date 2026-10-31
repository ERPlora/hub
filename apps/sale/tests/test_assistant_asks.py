"""Layer 1 of the assistant's QA for Sales & POS (erplora-next docs plan 2026-10-31, the assistant's knowledge and QA).

Every tool of sale says what a waiter, a cashier or the owner would type to ask for it (``AI.asks``, in English and in
Spanish). Each of those phrases, put to the same selection a turn makes (``live.assistant.relevant``), has to bring its
own tool among the first ten offered — with no model and no network — as each role that holds it.

The catalogue is the Hub's own (``base.assistant.catalog``: the role's permissions, the writes a manager may approve,
what is never done from the chat) in a business with Sales & POS, the apps it requires and the platform on; the turn
ranks as the Hub's does (``base.assistant.ALWAYS`` first, ``live.assistant.app_words``).
"""

import pytest
from live.assistant import app_words, tool_name
from live.assistant_qa import misses, uncovered
from live.checks import check_assistant_asks
from live.meta import all_live_app_configs

from apps.sale.tests.conftest import ctx_for
from base import assistant

#: The roles of a business, as the SaaS sends them: the owner holds everything, the employee the till.
ROLES = ("hub_owner", "hub_manager", "hub_employee")
LANGUAGES = ("en", "es")
#: Where an ask's tool has to come at worst among the tools a turn offers (``ALWAYS`` included).
TOP = 10
SALE = tool_name("sale.")


def with_what_it_requires(label: str) -> set[str]:
    """``label`` and every app it requires, however deep, with the platform (on in every business)."""
    configs = {config.label: config for config in all_live_app_configs()}
    on = {name for name, config in configs.items() if config.kind != "app"}
    pending = [label]
    while pending:
        name = pending.pop()
        if name not in on:
            on.add(name)
            pending += list(configs[name].requires)
    return on


@pytest.fixture
def sale_on(monkeypatch):
    """A business with Sales & POS on and nothing else but what it needs: the catalogue its people get."""
    configs = {config.label: config for config in all_live_app_configs()}
    on = with_what_it_requires("sale")
    monkeypatch.setattr(assistant, "active_apps", lambda scope: {name: configs[name] for name in on})
    return on


def tools_of(role: str, language: str) -> dict:
    return assistant.catalog(ctx_for(role, language=language))


def test_the_business_has_sale_and_what_it_requires_on(sale_on):
    assert {"base", "sale", "tax", "customer"} <= sale_on
    assert "inventory" not in sale_on  # optional for sale (PLAN §20.5): not required, so not on


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("role", ROLES)
def test_every_tool_of_sale_says_how_people_ask_for_it(sale_on, role, language):
    tools = tools_of(role, language)
    sale = {name: op for name, op in tools.items() if op.app_label == "sale"}
    assert sale  # positive control: the role holds tools of sale
    assert uncovered(sale, language) == []


@pytest.mark.parametrize("language", LANGUAGES)
@pytest.mark.parametrize("role", ROLES)
def test_each_ask_of_sale_is_offered_its_tool_among_the_first_ten(sale_on, role, language):
    tools = tools_of(role, language)
    found = misses(tools, language=language, top=TOP, app_words=app_words, always=assistant.ALWAYS)
    assert [miss for miss in found if miss.tool_name.startswith(SALE)] == []


def test_what_the_employee_may_not_do_is_not_in_their_catalogue(sale_on):
    """The till's settings are the manager's (``sale.manage_settings``), and no manager approves them on the spot:
    the employee's turn never offers them, whatever they ask; the figures of the business are not theirs either."""
    employee = tools_of("hub_employee", "es")
    manager = tools_of("hub_manager", "es")
    for name in ("sale.settings.update", "sale.payment_method.create", "sale.sale.today"):
        assert name in manager  # positive control: the manager holds it
        assert name not in employee
    # A write the employee lacks but a manager approves with their PIN stays theirs, as its button does (BASE-F84).
    assert "sale.sale.void" in employee


def test_live_asks_nothing_more_of_sale_once_it_is_listed(settings):
    """``live.E020`` with Sales & POS in ``LIVE_ASSISTANT_ASKS_REQUIRED``: every tool says at least two phrases of its
    own in each language, none empty, its own name nor longer than a chat line."""
    settings.LIVE_ASSISTANT_ASKS_REQUIRED = ("sale",)
    assert check_assistant_asks() == []
