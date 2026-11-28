"""A drawer: its name, and a change that names the drawer and changes something."""

from apps.cash_register.schemas.registers import RegisterIn, RegisterUpdateIn
from apps.cash_register.tests.schema_checks import refused


def test_a_drawer_has_a_name():
    assert RegisterIn.model_validate({"name": "  Bar  "}).name == "Bar"
    assert refused(RegisterIn, name="   ") == ["name"]
    assert refused(RegisterIn, name="x" * 101) == ["name"]


def test_a_drawer_change_names_the_drawer_and_changes_something():
    assert refused(RegisterUpdateIn, name="Terrace") == [""]
    assert refused(RegisterUpdateIn, register_name="Bar") == [""]
    RegisterUpdateIn.model_validate({"register_name": "Bar", "is_active": False})
