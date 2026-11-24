"""What else flipping an app's switch changes (``base.app_switch``), by the rules that change it, without the
database: what the Apps screen's question and the assistant's card say before the yes."""

from base import activation, app_switch
from base.activation import FAILED, OFF, ON, Activation

GRAPH = {"reservation": ["table", "schedule"], "table": ["sale"], "schedule": [], "sale": [], "staff": ["schedule"]}


def states(**given: Activation) -> dict[str, Activation]:
    return {label: given.get(label, activation.OFF_ROW) for label in GRAPH}


def test_turning_an_app_on_brings_what_it_needs_that_is_off_or_failed():
    current = states(sale=Activation(ON, True), table=Activation(FAILED, False))
    assert app_switch.along("reservation", current, GRAPH, on=True) == ["schedule", "table"]


def test_turning_an_app_off_takes_what_came_along_only_with_it_but_what_the_country_keeps():
    current = states(
        reservation=Activation(ON, True), table=Activation(ON, False), schedule=Activation(ON, False), sale=Activation(ON, False)
    )
    assert app_switch.along("reservation", current, GRAPH, on=False) == ["sale", "schedule", "table"]
    assert app_switch.along("reservation", current, GRAPH, kept={"sale"}, on=False) == ["schedule", "table"]


def test_what_another_app_on_still_needs_stays_and_is_not_named():
    current = states(
        reservation=Activation(ON, True), table=Activation(ON, False), schedule=Activation(ON, False), staff=Activation(ON, True)
    )
    assert app_switch.along("reservation", current, GRAPH, on=False) == ["table"]


def test_an_app_another_one_on_needs_takes_nothing_with_it_its_yes_is_refused():
    current = states(reservation=Activation(ON, True), table=Activation(ON, False))
    assert app_switch.along("table", current, GRAPH, on=False) == []


def test_an_app_that_changes_only_itself_says_nothing_more():
    current = states(schedule=Activation(OFF, False))
    assert app_switch.said("schedule", app_switch.along("schedule", current, GRAPH, on=True), on=True, language="es") == ""
    assert app_switch.card_datum("") == []


def test_the_switch_of_an_app_the_business_wants_says_what_goes_with_it_and_of_one_off_what_comes_along():
    wanted = states(reservation=Activation(FAILED, True), table=Activation(ON, False), schedule=Activation(ON, False))
    off = states(sale=Activation(ON, True))
    assert app_switch.switch_said("reservation", wanted, GRAPH, language="es") == (
        "Horarios y Mesas se desactivan con ella: solo las necesitaba Reservas."
    )
    assert app_switch.switch_said("reservation", off, GRAPH, language="es") == (
        "Reservas necesita Horarios y Mesas: se activan con ella."
    )
