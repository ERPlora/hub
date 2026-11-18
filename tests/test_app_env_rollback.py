"""How a rollback of the hub checks the settings it puts back in force and what it records (deploy/app_env_rollback.py).

A rollback registers nothing: the services go back to revisions that already ran, with the settings those carry. The
rollback goes through only if those are the settings of deploy/app-env.json in the commit they run (the settings in
force for a commit from before the file) and they pass the deploy's checks; git and the aws CLI are a double.
"""

import copy
import json

import pytest
from app_env_doubles import (
    COMMIT,
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
    return app_env_rollback.main([str(workdir), environment, COMMIT, "eu-west-1", "--confirm", confirm])


def recorded(workdir):
    return json.loads((workdir / "app_env.json").read_text())


def older_prod():
    """The settings of an older commit: the ERPlora route still closed in prod."""
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        section[family]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "false"
    return section


# ── What a rollback records ────────────────────────────────────────────────────────────────────────────────────────


def test_a_rollback_records_the_settings_of_the_commit_it_goes_back_to(monkeypatch, workdir):
    write_targets(workdir, older_prod())
    commands = FakeCommands(file=json.dumps(settings(prod=older_prod())))

    assert roll_back(monkeypatch, workdir, commands) == 0

    assert (workdir / "app_env.json").read_text() == json.dumps(older_prod(), sort_keys=True, separators=(",", ":"))
    assert ["git", "show", f"{COMMIT}:deploy/app-env.json"] in commands.calls


def test_the_migration_keeps_its_settings_in_force(monkeypatch, workdir):
    file = settings(prod={**PROD, "hub-migrate": {}})
    commands = FakeCommands(file=json.dumps(file), current={"prod": PROD})

    assert roll_back(monkeypatch, workdir, commands) == 0
    assert recorded(workdir) == PROD

    commands = FakeCommands(current={"prod": {**PROD, "hub-migrate": {}}})

    assert roll_back(monkeypatch, workdir, commands) == 0
    assert recorded(workdir) == {**PROD, "hub-migrate": {}}


def test_a_rollback_reads_the_settings_in_force_and_the_saas_revision_of_its_environment(monkeypatch, workdir):
    commands = FakeCommands()

    roll_back(monkeypatch, workdir, commands)

    assert_reads_the_settings_in_force_then_the_saas(commands)


def test_pre_neither_reads_the_saas_nor_asks_for_the_confirmation(monkeypatch, workdir):
    older = copy.deepcopy(PRE)
    older["hub"]["PLATFORM_HUB_SLUG"] = older["worker"]["PLATFORM_HUB_SLUG"] = "erplora-pre"
    write_targets(workdir, older, environment="pre")
    commands = FakeCommands(file=json.dumps(settings(pre=older)), current={"pre": PRE})

    assert roll_back(monkeypatch, workdir, commands, environment="pre", confirm="anything") == 0

    assert not any("describe-task-definition" in command for command in commands.calls)
    assert any("/erplora/pre/hub/app_env" in command for command in commands.calls)
    assert recorded(workdir) == older


# ── The lock on sending to the AEAT for real ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(("before", "after"), [("false", "true"), ("true", "false")])
def test_going_back_to_a_version_that_opens_or_closes_it_in_prod_needs_the_confirmation(
    monkeypatch, workdir, capsys, before, after
):
    write_targets(workdir, with_production(after))
    file = json.dumps(settings(prod=with_production(after)))
    commands = FakeCommands(file=file, current={"prod": with_production(before)}, saas_charging=False)

    assert roll_back(monkeypatch, workdir, commands) == 1

    assert not (workdir / "app_env.json").exists()
    assert f"confirm_protected=VERIFACTU_PRODUCTION_ENABLED={after}" in capsys.readouterr().err

    assert roll_back(monkeypatch, workdir, commands, confirm=f"VERIFACTU_PRODUCTION_ENABLED={after}") == 0
    assert recorded(workdir) == with_production(after)


def test_a_confirmation_of_something_else_is_refused(monkeypatch, workdir):
    write_targets(workdir, with_production("false"))
    file = json.dumps(settings(prod=with_production("false")))
    commands = FakeCommands(file=file, current={"prod": PROD}, saas_charging=False)

    assert roll_back(monkeypatch, workdir, commands, confirm="VERIFACTU_PRODUCTION_ENABLED=true") == 1

    assert not (workdir / "app_env.json").exists()


def test_while_the_saas_charges_it_never_goes_back_to_a_version_that_closes_it(monkeypatch, workdir, capsys):
    write_targets(workdir, with_production("false"))
    commands = FakeCommands(file=json.dumps(settings(prod=with_production("false"))))

    assert roll_back(monkeypatch, workdir, commands, confirm="VERIFACTU_PRODUCTION_ENABLED=false") == 1

    assert not (workdir / "app_env.json").exists()
    assert "prod.hub.VERIFACTU_PRODUCTION_ENABLED" in capsys.readouterr().err


def test_an_unreadable_saas_revision_refuses_the_prod_rollback(monkeypatch, workdir, capsys):
    assert roll_back(monkeypatch, workdir, FakeCommands(saas_charging=None)) == 1

    assert "erplora-prod-saas" in capsys.readouterr().err


# ── The revisions the services go back to ─────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("family", ["hub", "worker"])
def test_a_revision_that_runs_other_settings_than_its_commit_is_refused(workdir, family):
    carried = copy.deepcopy(PROD)
    carried[family]["VERIFACTU_PRODUCTION_ENABLED"] = "false"
    write_targets(workdir, carried)
    definitions = {name: json.loads((workdir / f"{name}.json").read_text()) for name in ("hub", "worker")}

    problems = app_env_rollback.revision_problems(PROD, definitions)

    where = f"arn:aws:ecs:eu-west-1:1:task-definition/erplora-prod-{family}:10.VERIFACTU_PRODUCTION_ENABLED"
    assert kinds(problems) == {(where, "revision_differs")}


def test_a_revision_that_leaves_out_what_its_commit_sets_is_refused(monkeypatch, workdir):
    carried = copy.deepcopy(PROD)
    del carried["worker"]["VERIFACTU_PRODUCTION_ENABLED"]
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    assert not (workdir / "app_env.json").exists()


def test_a_setting_left_out_on_one_side_with_the_hub_default_on_the_other_is_no_difference(monkeypatch, workdir):
    carried = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        carried[family]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "true"
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 0

    assert recorded(workdir) == PROD


def test_the_difference_never_repeats_the_value_the_revision_runs(monkeypatch, workdir, capsys):
    carried = copy.deepcopy(PROD)
    carried["hub"]["PLATFORM_HUB_SLUG"] = "erplora-old-slug"
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    err = capsys.readouterr().err
    assert "PLATFORM_HUB_SLUG" in err
    assert "erplora-old-slug" not in err


def test_a_revision_without_the_app_container_is_refused(monkeypatch, workdir, capsys):
    definition = target("worker", PROD["worker"])
    definition["taskDefinition"]["containerDefinitions"][0]["name"] = "web"
    (workdir / "worker.json").write_text(json.dumps(definition))

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    assert "erplora-prod-worker" in capsys.readouterr().err


# ── A commit from before deploy/app-env.json, and what refuses the rollback ────────────────────────────────────────


def test_a_commit_from_before_the_file_keeps_the_settings_in_force(monkeypatch, workdir, capsys):
    assert roll_back(monkeypatch, workdir, FakeCommands(file=False)) == 0

    assert recorded(workdir) == PROD
    assert capsys.readouterr().err.startswith("::warning::")


def test_a_commit_from_before_the_file_whose_revisions_run_other_settings_is_refused(monkeypatch, workdir):
    write_targets(workdir, with_production("false"))
    commands = FakeCommands(file=False, saas_charging=False)

    assert roll_back(monkeypatch, workdir, commands) == 1

    assert not (workdir / "app_env.json").exists()


def test_a_commit_from_before_the_file_never_keeps_pre_on_the_aeat_production_environment(
    monkeypatch, workdir, capsys
):
    in_force = copy.deepcopy(PRE)
    in_force["hub"]["VERIFACTU_PRODUCTION_ENABLED"] = in_force["worker"]["VERIFACTU_PRODUCTION_ENABLED"] = "true"
    write_targets(workdir, in_force, environment="pre")
    commands = FakeCommands(file=False, current={"pre": in_force})

    assert roll_back(monkeypatch, workdir, commands, environment="pre") == 1

    assert not (workdir / "app_env.json").exists()
    assert "pre.hub.VERIFACTU_PRODUCTION_ENABLED" in capsys.readouterr().err


def test_an_unknown_commit_refuses_the_rollback(monkeypatch, workdir, capsys):
    commands = FakeCommands(file=False)
    commands.commits = set()

    assert roll_back(monkeypatch, workdir, commands) == 1

    assert COMMIT in capsys.readouterr().err


def test_a_commit_whose_file_breaks_a_rule_refuses_the_rollback(monkeypatch, workdir, capsys):
    data = settings()
    data["prod"]["hub"]["DEBUG"] = "True"

    assert roll_back(monkeypatch, workdir, FakeCommands(file=json.dumps(data))) == 1

    assert "::error::prod.hub.DEBUG: " in capsys.readouterr().err


def test_a_missing_settings_parameter_refuses_the_rollback(monkeypatch, workdir, capsys):
    assert roll_back(monkeypatch, workdir, FakeCommands(current={})) == 1

    assert "/erplora/prod/hub/app_env" in capsys.readouterr().err


def test_every_refusal_is_reported_and_says_nothing_was_changed(monkeypatch, workdir, capsys):
    carried = copy.deepcopy(PROD)
    carried["hub"]["PLATFORM_HUB_SLUG"] = carried["worker"]["PLATFORM_HUB_SLUG"] = "other"
    write_targets(workdir, carried)

    assert roll_back(monkeypatch, workdir, FakeCommands()) == 1

    errors = capsys.readouterr().err.splitlines()
    assert len(errors) == 2
    assert all(line.startswith("::error::") and line.endswith("; nothing was changed") for line in errors)
