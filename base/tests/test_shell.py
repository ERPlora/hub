"""``manage.py shell`` opens a database context (phase 2, S1; plan 2026-10-22).

Without a context a hub's model fails (``HubContextMissing``), so the shell runs in phase 1's shared database, where
every hub with ``db_name=""`` keeps its data, as it always has (the e2e's ``manage.py shell -c`` helpers relay the
outbox there); ``--hub <slug>`` runs it in that hub's database instead.
"""

import contextvars

import pytest
from django.core.management import CommandError, call_command

from base.tenancy import context

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("no_fallback")]

PROBE = "from base.tenancy import context; print(context.current().kind, context.current_hub() and context.current_hub().slug)"


@pytest.fixture
def no_fallback(monkeypatch):
    monkeypatch.setattr(context, "_test_fallback", None)


def shell(*args, **options) -> None:
    contextvars.Context().run(call_command, "shell", *args, command=PROBE, **options)


def test_the_shell_runs_on_the_shared_database(capsys):
    shell()

    assert capsys.readouterr().out.splitlines()[-1] == "shared None"


def test_the_shell_of_a_hub_runs_in_it(capsys):
    shell(hub="b")

    assert capsys.readouterr().out.splitlines()[-1] == "hub b"


def test_a_hub_that_does_not_exist_is_refused():
    with pytest.raises(CommandError, match="nowhere"):
        shell(hub="nowhere")
