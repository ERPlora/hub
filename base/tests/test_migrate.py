"""``manage.py migrate`` migrates control only (PLAN-DB §4 «Comandos», §14.9; plan 2026-10-22-fase-2-tenencia §2.7).

A hub's, a demo's or a template's database changes only through the migrator, which creates just the apps that hub
has: ``migrate`` on its alias would create them all, so it is refused before it opens a connection.
"""

import pytest
from django.core.management import CommandError, call_command


#: A fixed id: the parameters name the tests, and xdist's workers must collect the same ones.
HEX = "0190a1b2c3d47e5f8a9b0c1d2e3f4a5b"


@pytest.mark.parametrize("alias", [f"hub_{HEX}", f"demo_{HEX}", f"pre_hub_{HEX}", f"hub_{HEX}__ddl", "hub_template"])
def test_migrate_refuses_any_alias_but_controls(alias):
    with pytest.raises(CommandError, match="migrator"):
        call_command("migrate", database=alias, verbosity=0)


@pytest.mark.django_db
def test_migrate_still_migrates_control():
    call_command("migrate", database="default", verbosity=0)
