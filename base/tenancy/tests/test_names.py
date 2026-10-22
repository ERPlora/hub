"""Names of the hubs' databases (PLAN-DB §3 and §14.12; plan 2026-10-22-fase-2-tenencia §4, step 1).

A hub's database is the control database's name, ``_`` and the hub's whole UUID in hex (``hub_<hex>``; pre's
``pre_hub_<hex>``); a demo's is ``demo_<hex>``. Nothing is ever truncated (the first half of a UUIDv7 is its date),
every name is validated against the control database it belongs to and reaches SQL only as ``sql.Identifier``.
"""

import uuid

import pytest
from psycopg import sql

from base.tenancy import names
from base.tenancy.bootstrap import Names

HUB_ID = uuid.UUID("0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")
HEX = HUB_ID.hex


def test_a_hubs_database_is_the_control_database_and_the_whole_hex_of_its_id():
    assert names.hub_db_name("hub", HUB_ID) == f"hub_{HEX}"
    assert len(HEX) == 32


def test_pre_prefixes_its_hubs_through_its_control_database():
    control = Names.with_prefix("pre_").control

    assert names.hub_db_name(control, HUB_ID) == f"pre_hub_{HEX}"


def test_a_demos_database_is_demo_and_the_hex_of_its_id():
    assert names.demo_db_name(HUB_ID) == f"demo_{HEX}"


def test_templates_derive_from_the_control_database():
    assert names.template_db_name("hub") == "hub_template"
    assert names.template_db_name("hub", "hair_salon") == "hub_template_hair_salon"
    assert names.template_db_name("pre_hub", "restaurant") == "pre_hub_template_restaurant"


@pytest.mark.parametrize(
    "name",
    [
        f"hub_{HEX}",
        f"demo_{HEX}",
        "hub_template",
        "hub_template_restaurant",
        "hub_template_hair_salon",
    ],
)
def test_the_names_of_a_control_database_are_valid(name):
    assert names.validate(name, control="hub") == name


@pytest.mark.parametrize(
    "name",
    [
        f"hub_{HEX[:-1]}",  # truncated
        f"hub_{HEX}0",  # one digit too many
        f"hub_{HEX.upper()}",  # not lowercase hex
        f"hub_{HEX[:-1]}g",  # not hex
        f"pre_hub_{HEX}",  # another control database's
        f"hub_{HEX}; DROP DATABASE hub",
        "hub",  # the control database itself
        "hub_template_",
        "hub_template_Restaurant",
        "hub_template_1restaurant",
        "postgres",
        "",
    ],
)
def test_anything_else_is_refused(name):
    with pytest.raises(names.InvalidDatabaseName):
        names.validate(name, control="hub")


def test_pre_refuses_the_names_of_prod_and_prod_those_of_pre():
    assert names.validate(f"pre_hub_{HEX}", control="pre_hub") == f"pre_hub_{HEX}"
    with pytest.raises(names.InvalidDatabaseName):
        names.validate(f"hub_{HEX}", control="pre_hub")
    with pytest.raises(names.InvalidDatabaseName):
        names.validate("hub_template", control="pre_hub")


def test_a_name_past_postgres_63_characters_is_refused_instead_of_truncated():
    control = "c" * 31  # 31 + 1 + 32 = 64
    with pytest.raises(names.InvalidDatabaseName, match="63"):
        names.hub_db_name(control, HUB_ID)
    with pytest.raises(names.InvalidDatabaseName, match="63"):
        names.template_db_name("hub", "v" * 60)


def test_an_invalid_vertical_never_makes_a_template_name():
    with pytest.raises(names.InvalidDatabaseName):
        names.template_db_name("hub", "Hair Salon")


def test_a_name_reaches_sql_only_quoted_as_an_identifier():
    identifier = names.identifier(f"hub_{HEX}", control="hub")

    assert isinstance(identifier, sql.Identifier)
    assert identifier.as_string() == f'"hub_{HEX}"'
    with pytest.raises(names.InvalidDatabaseName):
        names.identifier('hub_x"; DROP DATABASE hub; --', control="hub")


def test_only_the_hubs_of_a_control_database_and_their_ddl_aliases_count_as_hub_aliases():
    assert names.is_hub_alias(f"hub_{HEX}", control="hub")
    assert names.is_hub_alias(f"hub_{HEX}__ddl", control="hub")
    assert names.is_hub_alias(f"demo_{HEX}", control="hub")
    assert names.is_hub_alias("hub_template", control="hub")
    assert not names.is_hub_alias("default", control="hub")
    assert not names.is_hub_alias("shared", control="hub")
    assert not names.is_hub_alias(f"pre_hub_{HEX}", control="hub")
