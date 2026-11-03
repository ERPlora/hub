"""``manage.py shell`` opens a database context (phase 2, S1; plan 2026-10-22).

Without a context a hub's model fails (``HubContextMissing``), so the shell runs on control (the registry, the
platform's outbox) or, with ``--hub <slug>``, in that hub's database (the e2e's ``manage.py shell -c`` helpers relay a
hub's outbox there). Since S5 there is no shared database: a business without its own is refused.
"""

import contextvars

import pytest
from django.core.management import CommandError, call_command

from base.tenancy import context

from base.tenancy.tests import hubs

pytestmark = [pytest.mark.django_db(databases=hubs.HUB_DATABASES), pytest.mark.usefixtures("no_fallback")]

PROBE = "from base.tenancy import context; print(context.current().kind, context.current_hub() and context.current_hub().slug)"


@pytest.fixture
def no_fallback(monkeypatch):
    monkeypatch.setattr(context, "_test_fallback", None)


def shell(*args, **options) -> None:
    contextvars.Context().run(call_command, "shell", *args, command=PROBE, **options)


def test_the_shell_runs_on_control(capsys):
    shell()

    assert capsys.readouterr().out.splitlines()[-1] == "control None"


def test_the_shell_of_a_hub_runs_in_it(capsys, hub_b):
    shell(hub=hub_b.slug)

    assert capsys.readouterr().out.splitlines()[-1] == f"hub {hub_b.slug}"


def test_the_shell_of_a_business_without_its_own_database_is_refused():
    with pytest.raises(CommandError, match="no database of its own"):
        shell(hub="b")


def test_a_hub_that_does_not_exist_is_refused():
    with pytest.raises(CommandError, match="nowhere"):
        shell(hub="nowhere")
