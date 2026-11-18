"""How a rollback of the hub checks the settings it puts back in force and what it records (deploy/app_env_rollback.py).

A rollback registers nothing: the services go back to revisions that already ran, with the settings those were
registered with. The rollback checks what those revisions run with the deploy's rules, whatever deploy/app-env.json
says, and records it; the aws CLI is a double.
"""

import copy
import json

import pytest
from app_env_doubles import (
    PRE,
    PROD,
    FakeCommands,
    assert_reads_the_settings_in_force_then_the_saas,
    kinds,
    load,
    revision,
    settings,
    with_production,
)

app_env_rollback = load("app_env_rollback")
app_env = app_env_rollback.app_env


def target(family, carried, environment="prod"):
    """A revision a service goes back to, as `describe-task-definition --include TAGS` answers it."""
    definition = revision(family, {"DEBUG": "False", **carried})
    definition["taskDefinitionArn"] = f"arn:aws:ecs:eu-west-1:1:task-definition/erplora-{environment}-{family}:10"
    return {"taskDefinition": definition, "tags": definition.pop("tags")}


def write_targets(workdir, section, environment="prod"):
    for family in ("hub", "worker"):
        (workdir / f"{family}.json").write_text(json.dumps(target(family, section.get(family, {}), environment)))


@pytest.fixture
def workdir(tmp_path):
    write_targets(tmp_path, PROD)
    return tmp_path


def roll_back(monkeypatch, workdir, commands, environment="prod", confirm=""):
    monkeypatch.setattr(app_env, "run", commands)
    return app_env_rollback.main([str(workdir), environment, "eu-west-1", "--confirm", confirm])


def recorded(workdir):
    return json.loads((workdir / "app_env.json").read_text())


def kinds_reported(capsys):
    """Where each problem the rollback reported is."""
    return {line.removeprefix("::error::").split(": ", 1)[0] for line in capsys.readouterr().err.splitlines()}


def older_prod():
    """The settings of an older version: the ERPlora route still closed in prod."""
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        section[family]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "false"
    return section


# ── What a rollback records ────────────────────────────────────────────────────────────────────────────────────────


def test_a_rollback_records_the_hub_settings_the_revisions_run(monkeypatch, workdir):
    write_targets(workdir, older_prod())

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 0

    assert (workdir / "app_env.json").read_text() == json.dumps(older_prod(), sort_keys=True, separators=(",", ":"))


def test_a_revision_that_runs_other_settings_than_its_commit_goes_back_with_what_it_runs(monkeypatch, workdir):
    write_targets(workdir, older_prod())
    commands = FakeCommands(file=json.dumps(settings()))

    assert roll_back(monkeypatch, workdir, commands) == 0

    assert recorded(workdir) == older_prod()
    assert not any(command[0] == "git" for command in commands.calls)


def test_a_setting_the_revision_leaves_out_is_left_out_of_the_record(monkeypatch, workdir):
    carried = copy.deepcopy(PROD)
    del carried["worker"]["PLATFORM_HUB_SLUG"]
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 0

    assert recorded(workdir) == carried


def test_the_migration_keeps_its_settings_in_force(monkeypatch, workdir):
    assert roll_back(monkeypatch, workdir, FakeCommands(current={"prod": {**PROD, "hub-migrate": {}}})) == 0

    assert recorded(workdir) == {**PROD, "hub-migrate": {}}


def test_a_rollback_reads_the_settings_in_force_and_the_saas_revision_of_its_environment(monkeypatch, workdir):
    commands = FakeCommands()

    roll_back(monkeypatch, workdir, commands)

    assert_reads_the_settings_in_force_then_the_saas(commands)


def test_pre_neither_reads_the_saas_nor_asks_for_the_confirmation(monkeypatch, workdir):
    older = copy.deepcopy(PRE)
    older["hub"]["PLATFORM_HUB_SLUG"] = older["worker"]["PLATFORM_HUB_SLUG"] = "erplora-pre"
    write_targets(workdir, older, environment="pre")
    commands = FakeCommands(current={"pre": PRE})

    assert roll_back(monkeypatch, workdir, commands, environment="pre", confirm="anything") == 0

    assert not any("describe-task-definition" in command for command in commands.calls)
    assert any("/erplora/pre/hub/app_env" in command for command in commands.calls)
    assert recorded(workdir) == older


# ── The lock on sending to the AEAT for real ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("before", "after"), [("false", "true"), ("true", "false")])
def test_going_back_to_revisions_that_open_or_close_it_in_prod_needs_the_confirmation(
    monkeypatch, workdir, capsys, before, after
):
    write_targets(workdir, with_production(after))
    commands = FakeCommands(current={"prod": with_production(before)}, saas_charging=False)

    assert roll_back(monkeypatch, workdir, commands) == 1

    assert not (workdir / "app_env.json").exists()
    assert f"confirm_protected=VERIFACTU_PRODUCTION_ENABLED={after}" in capsys.readouterr().err

    assert roll_back(monkeypatch, workdir, commands, confirm=f"VERIFACTU_PRODUCTION_ENABLED={after}") == 0
    assert recorded(workdir) == with_production(after)


def test_a_revision_that_leaves_the_lock_out_closes_it(monkeypatch, workdir, capsys):
    carried = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        del carried[family]["VERIFACTU_PRODUCTION_ENABLED"]
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands(saas_charging=False)) == 1

    assert "confirm_protected=VERIFACTU_PRODUCTION_ENABLED=false" in capsys.readouterr().err


def test_a_confirmation_of_something_else_is_refused(monkeypatch, workdir):
    write_targets(workdir, with_production("false"))
    commands = FakeCommands(current={"prod": PROD}, saas_charging=False)

    assert roll_back(monkeypatch, workdir, commands, confirm="VERIFACTU_PRODUCTION_ENABLED=true") == 1

    assert not (workdir / "app_env.json").exists()


def test_while_the_saas_charges_it_never_goes_back_to_revisions_that_close_it(monkeypatch, workdir, capsys):
    write_targets(workdir, with_production("false"))

    assert roll_back(monkeypatch, workdir, FakeCommands(), confirm="VERIFACTU_PRODUCTION_ENABLED=false") == 1

    assert not (workdir / "app_env.json").exists()
    assert "prod.hub.VERIFACTU_PRODUCTION_ENABLED" in capsys.readouterr().err


def test_while_the_saas_charges_it_never_goes_back_to_closed_revisions_even_if_it_was_already_closed(
    monkeypatch, workdir, capsys
):
    write_targets(workdir, with_production("false"))
    commands = FakeCommands(current={"prod": with_production("false")})

    assert roll_back(monkeypatch, workdir, commands) == 1

    assert not (workdir / "app_env.json").exists()
    assert kinds_reported(capsys) == {"prod.hub.VERIFACTU_PRODUCTION_ENABLED", "prod.worker.VERIFACTU_PRODUCTION_ENABLED"}


def test_an_unreadable_saas_revision_refuses_the_prod_rollback(monkeypatch, workdir, capsys):
    assert roll_back(monkeypatch, workdir, FakeCommands(saas_charging=None)) == 1

    assert "erplora-prod-saas" in capsys.readouterr().err


# ── The rules of each environment, on what the revisions run ──────────────────────────────────────────────────────


def test_pre_never_goes_back_to_revisions_on_the_aeat_production_environment(monkeypatch, workdir, capsys):
    carried = copy.deepcopy(PRE)
    carried["hub"]["VERIFACTU_PRODUCTION_ENABLED"] = carried["worker"]["VERIFACTU_PRODUCTION_ENABLED"] = "true"
    write_targets(workdir, carried, environment="pre")
    commands = FakeCommands(current={"pre": carried})

    assert roll_back(monkeypatch, workdir, commands, environment="pre") == 1

    assert not (workdir / "app_env.json").exists()
    assert "pre.hub.VERIFACTU_PRODUCTION_ENABLED" in capsys.readouterr().err


def test_revisions_whose_hub_and_worker_send_to_different_aeat_environments_are_refused(monkeypatch, workdir):
    carried = with_production("true")
    carried["worker"]["VERIFACTU_PRODUCTION_ENABLED"] = "false"
    definitions = {"hub": target("hub", carried["hub"]), "worker": target("worker", carried["worker"])}
    section = {family: app_env_rollback.running(definition, family) for family, definition in definitions.items()}

    assert kinds(app_env.section_problems("prod", section)) == {("prod.VERIFACTU_PRODUCTION_ENABLED", "families_disagree")}

    write_targets(workdir, carried)
    assert roll_back(monkeypatch, workdir, FakeCommands(), confirm="VERIFACTU_PRODUCTION_ENABLED=false") == 1


def test_only_the_hub_settings_of_the_app_container_are_read():
    definition = target("hub", {"ALLOWED_HOSTS": "hubs.erplora.com", **PROD["hub"]})

    assert app_env_rollback.running(definition, "hub") == PROD["hub"]


@pytest.mark.parametrize("value", ["Erplora_Old", "ghp_" + "a1B2c3D4e5F6g7H8i9J0" * 2])
def test_a_refusal_never_repeats_the_value_the_revision_runs(monkeypatch, workdir, capsys, value):
    carried = copy.deepcopy(PROD)
    carried["hub"]["PLATFORM_HUB_SLUG"] = value
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    err = capsys.readouterr().err
    assert "prod.hub.PLATFORM_HUB_SLUG" in err
    assert value not in err


def test_a_revision_without_the_app_container_is_refused(monkeypatch, workdir, capsys):
    definition = target("worker", PROD["worker"])
    definition["taskDefinition"]["containerDefinitions"][0]["name"] = "web"
    (workdir / "worker.json").write_text(json.dumps(definition))

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    assert "erplora-prod-worker" in capsys.readouterr().err


# ── What else refuses the rollback ─────────────────────────────────────────────────────────────────────────────────


def test_a_missing_settings_parameter_refuses_the_rollback(monkeypatch, workdir, capsys):
    assert roll_back(monkeypatch, workdir, FakeCommands(current={})) == 1

    assert "/erplora/prod/hub/app_env" in capsys.readouterr().err


def test_every_refusal_is_reported_and_says_nothing_was_changed(monkeypatch, workdir, capsys):
    carried = copy.deepcopy(PROD)
    carried["hub"]["PLATFORM_HUB_SLUG"] = carried["worker"]["PLATFORM_HUB_SLUG"] = "Other"
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    errors = capsys.readouterr().err.splitlines()
    assert len(errors) == 2
    assert all(line.startswith("::error::") and line.endswith("; nothing was changed") for line in errors)
