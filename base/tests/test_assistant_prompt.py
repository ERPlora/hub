"""The instructions of a turn of the Hub's assistant (``base/assistant/prompt.py``): what it answers and how, in
which language and money, and what it is told of the person who asks."""

import pytest

from base import assistant
from base.models import Membership


# ── The instructions of a turn ───────────────────────────────────────────────────────────────────────────────────


def test_the_instructions_answer_how_to_questions_only_from_the_documentation():
    """How ERPlora works comes from its documentation, cited; what it does not cover is said, never
    made up. Its records still come only from its tools. Cited by the ``cite`` line each excerpt brings (hub#1079: «citing
    the section» alone let the answer give the steps and name no excerpt)."""
    text = " ".join(assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={}).split())
    assert (
        "For questions about how ERPlora works (how to do something, what an option means, plans), search the "
        "documentation with `base__docs__search` and answer only from what it returns; end that answer with the `cite` "
        "of each excerpt you used, at least one, as it comes and in a line of its own; if it returns nothing, say the "
        "documentation does not cover it."
    ) in text
    assert "Never invent a record" in text



def test_the_instructions_keep_ids_out_of_the_answer():
    """hub#538: after creating a member, the answer listed it in a table with «ID 01a192cb-…». The model reads ids to
    call its tools, but names a record to the person by its name, as the card and the screens do, never by its id."""
    text = " ".join(assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={}).split())
    assert (
        "Name a record to the person by its name, as the screens do: never write an id (a code such as "
        "0190a3b4-…) in the answer, not in a table either."
    ) in text


def test_the_instructions_ask_for_a_missing_datum_and_leave_the_yes_to_the_card():
    """An owner does not know which data a change needs (the tax category or the SKU of a product): told only never to
    invent, the assistant is left to make one up, give up, or ask in the chat whether to go ahead instead of showing the
    card.
    It looks the datum up with its tools first and asks for it only when none gives it, one short question at a time,
    as the panel's assistant of erplora.com does; a request that fits several records is asked about too."""
    text = " ".join(assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={}).split())
    assert "That card is the only confirmation: never ask in your text whether to go ahead." in text
    assert (
        "Look up with your tools what a change needs; ask only for a datum its tool requires, that no tool gives and "
        "the person has not said, one short question at a time, and never invent it."
    ) in text
    assert "If the request fits several records, ask which one." in text


def test_the_instructions_set_the_language_the_money_and_the_screens():
    text = assistant.prompt.instructions(language="es", currency="EUR", decimals=2, business="Bar Pepe", screens={"/settings": "Ajustes"})
    # Off-topic questions (films, cinemas) would spend the business's allowance.
    assert "Only help with this business and with using ERPlora" in text
    assert "Spanish" in text
    # An amount by its mark, not by the words «in cents».
    assert "EUR" in text and '"money": true' in text and "minor unit" in text
    assert "[Ajustes](/settings)" in text
    assert "Bar Pepe" in text


@pytest.mark.parametrize(
    ("currency", "decimals", "example"),
    [("EUR", 2, "17.00 EUR → 1700"), ("JPY", 0, "17 JPY → 17"), ("KWD", 3, "17.000 KWD → 17000")],
)
def test_the_instructions_say_an_amount_in_the_currency_its_result_gives(currency, decimals, example):
    """A tool's result gives its amounts with their
    currency (``currency`` and ``currency_decimals``: an invoice keeps the one it was issued in) and the card paints them
    in it, but the model was told to say every amount in the business's, with two decimals: its text and the card
    disagreed. An amount goes in the minor unit of its currency (no cents in yen), said in the currency its result
    gives, else in the business's."""
    text = assistant.prompt.instructions(language="en", currency=currency, decimals=decimals, business="Bar Pepe", screens={})
    assert example in text
    assert "`currency`" in text and "`currency_decimals`" in text
    assert "two decimals" not in text


# ── Who asks: their role and what it may do (hub#585, BASE-F100) ─────────────────────────────────────────────────


def _said(language="en", **who):
    text = assistant.prompt.instructions(language=language, currency="EUR", decimals=2, business="Bar Pepe", screens={}, **who)
    return " ".join(text.split())


@pytest.mark.parametrize(
    ("role", "language", "name"),
    [
        (Membership.Role.OWNER, "en", "Owner"),
        (Membership.Role.OWNER, "es", "Propietario"),
        (Membership.Role.ADMIN, "en", "Admin"),
        (Membership.Role.ADMIN, "es", "Administrador"),
        (Membership.Role.MANAGER, "en", "Manager"),
        (Membership.Role.MANAGER, "es", "Encargado"),
        (Membership.Role.EMPLOYEE, "en", "Employee"),
        (Membership.Role.EMPLOYEE, "es", "Empleado"),
    ],
)
def test_the_instructions_name_the_persons_role_in_the_chat_language(role, language, name):
    """hub#585: the model never knew whom it served, so an employee who asked to switch an app off got «too many
    steps» or a made-up «it is already off». It is told their role as the screens name it, and that its tools are
    that role's."""
    assert f"You talk to the «{name}» of this business: your tools are the ones this role may use, no more." in _said(
        language, role=role
    )


@pytest.mark.parametrize(
    ("role", "who"),
    [(Membership.Role.EMPLOYEE, "a manager or the owner"), (Membership.Role.MANAGER, "the owner or an administrator")],
)
def test_a_role_that_cannot_do_something_is_told_who_can_and_no_other_tool_is_tried(role, who):
    """A tool may be missing for their role or because its app is off or out of the plan (``active_apps``): the model
    says it is not available to them here, with both reasons, never that the role alone is to blame."""
    text = _said(role=role)
    assert (
        "When they ask for something none of your tools does, do not try other tools for it and never tell the state "
        "of something else instead: say plainly that it is not available to them here, because their role cannot do "
        f"it or because its app is not on, and that {who} can, or on which screen it is done."
    ) in text


@pytest.mark.parametrize("role", [Membership.Role.OWNER, Membership.Role.ADMIN])
def test_the_owner_and_an_administrator_are_never_told_their_role_cannot(role):
    """They hold every permission of every app: what no tool does is done on its screen, not someone else's."""
    text = _said(role=role)
    assert "their role cannot" not in text
    assert "If something cannot be done from here (you have no tool for it), say on which screen it is done." in text


@pytest.mark.parametrize("role", ["", "staff", None])
def test_without_a_role_of_the_business_no_role_is_named(role):
    """An automation's step (``apps.flow``) or a session with no role here: nobody to name."""
    assert "You talk to the" not in _said(role=role)


def test_a_write_a_manager_approves_is_said_to_ask_for_that_approval():
    """BASE-F100 step 1: an employee is offered the write their app lets a manager approve; the model says it will ask
    a manager to approve it, instead of running it as if it were theirs or saying they cannot."""
    text = _said(role=Membership.Role.EMPLOYEE, approvable=["demo.item.add_line", "demo.item.create"])
    assert (
        "This person needs a manager's approval to run `demo__item__add_line`, `demo__item__create`: before you call "
        "one, say that its card will ask a manager to approve it (their PIN or badge) and that it runs only once "
        "approved."
    ) in text
    assert "approv" not in _said(role=Membership.Role.EMPLOYEE)


def test_the_setup_block_carries_what_is_pending_and_who_does_it():
    status = {
        "total": 3,
        "pending": 2,
        "unavailable": 0,
        "blocking_pending": 1,
        "items": [
            {"key": "base.business", "title": "Los datos de tu negocio", "state": "pending", "level": "legal",
             "actionable": True, "route": "/settings#business", "description": "Razón social y NIF."},
            {"key": "invoice.series", "title": "Tu numeración", "state": "pending", "level": "functional",
             "actionable": False, "route": "/m/invoice", "description": ""},
            {"key": "base.apps", "title": "Tus apps", "state": "done", "level": "recommended",
             "actionable": True, "route": "/apps", "description": ""},
        ],
    }
    block = assistant.prompt.setup_block(status)
    assert "Los datos de tu negocio" in block and "/settings#business" in block
    assert "Tu numeración" in block and "administrator" in block
    assert "Tus apps" in block
    assert "could not be read" in assistant.prompt.setup_block(None)
