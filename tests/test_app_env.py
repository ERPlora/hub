"""The hub's settings of each environment (deploy/app-env.json) and how a deploy checks and applies them.

``deploy/app_env.py`` runs on the deploy runner, outside Django and the project's virtualenv: it is loaded
here from its path, and git and the aws CLI are replaced by a double (``FakeCommands``), so no test calls AWS.
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

HUB_DIR = Path(__file__).resolve().parents[1]
SCRIPT = HUB_DIR / "deploy" / "app_env.py"
SETTINGS_FILE = HUB_DIR / "deploy" / "app-env.json"


def _load():
    spec = importlib.util.spec_from_file_location("app_env", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["app_env"] = module
    spec.loader.exec_module(module)
    return module


app_env = _load()

SETTINGS_NAMES = ("VERIFACTU_PRODUCTION_ENABLED", "PLATFORM_HUB_SLUG", "VERIFACTU_ERPLORA_ROUTE_ENABLED")

PROD = {
    "hub": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"},
    "worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"},
}
PRE = {
    "hub": {
        "PLATFORM_HUB_SLUG": "erplora",
        "VERIFACTU_PRODUCTION_ENABLED": "false",
        "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false",
    },
    "worker": {
        "PLATFORM_HUB_SLUG": "erplora",
        "VERIFACTU_PRODUCTION_ENABLED": "false",
        "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false",
    },
}


def settings(**sections):
    data = {"prod": copy.deepcopy(PROD), "pre": copy.deepcopy(PRE)}
    data.update(sections)
    return data


def kinds(problems):
    return {(problem.where, problem.kind) for problem in problems}


def revision(family, environment=None, secrets=()):
    """A revision as ecs-deploy.sh hands it over: what it registers, with Terraform's variables in the app container."""
    environment = {"DEBUG": "False", "ERPLORA_ENVIRONMENT": "prod"} if environment is None else environment
    return {
        "family": f"erplora-prod-{family}",
        "containerDefinitions": [
            {
                "name": family,
                "image": "reg.example/erplora/hub:abc123",
                "environment": [{"name": name, "value": value} for name, value in environment.items()],
                "secrets": [{"name": name, "valueFrom": f"arn:secret:{name}"} for name in secrets],
            },
            {
                "name": "pgbouncer",
                "image": "reg.example/erplora/hub:abc123",
                "environment": [{"name": "PGBOUNCER_PORT", "value": "6432"}],
            },
        ],
        "tags": [{"key": "Environment", "value": "prod"}],
    }


def deployed(current=None):
    """The revisions of a deploy whose latest ACTIVE ones carry Terraform's variables plus the app_env in force."""
    current = PROD if current is None else current
    return {
        family: revision(family, {"DEBUG": "False", **current.get(family, {})}, secrets=("FISCAL_CERTIFICATE_KEY",))
        for family in ("hub", "worker", "hub-migrate")
    }


def app_environment(revision, name):
    container = next(c for c in revision["containerDefinitions"] if c["name"] == name)
    return {entry["name"]: entry["value"] for entry in container.get("environment", [])}


# ── The file in the repository ─────────────────────────────────────────────────────────────────────────────────────


def test_the_repository_file_passes_every_check():
    data = json.loads(SETTINGS_FILE.read_text())

    assert app_env.file_problems(data) == []


def test_the_repository_file_keeps_the_settings_the_tasks_run_with_today():
    data = json.loads(SETTINGS_FILE.read_text())

    assert data == {"prod": PROD, "pre": PRE}


def test_charging_in_prod_finds_the_repository_file_sending_to_the_aeat():
    data = json.loads(SETTINGS_FILE.read_text())

    assert app_env.charging_problems(data["prod"], charging=True) == []


# ── The shape of the file ──────────────────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("data", [[], "prod", None, 1])
def test_a_file_that_is_not_an_object_is_refused(data):
    assert kinds(app_env.file_problems(data)) == {("deploy/app-env.json", "not_an_object")}


def test_an_unknown_environment_is_refused():
    problems = app_env.file_problems(settings(staging={"hub": {}}))

    assert ("staging", "unknown_environment") in kinds(problems)


def test_a_missing_environment_is_refused():
    data = settings()
    del data["pre"]

    assert ("pre", "missing_environment") in kinds(app_env.file_problems(data))


def test_an_unknown_family_is_refused():
    data = settings()
    data["prod"]["db-bootstrap"] = {}

    assert ("prod.db-bootstrap", "unknown_family") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("where", ["prod", "prod.hub"])
def test_a_secrets_section_is_refused(where):
    data = settings()
    environment, *family = where.split(".")
    target = data[environment][family[0]] if family else data[environment]
    target["secrets"] = {"FISCAL_CERTIFICATE_KEY": "arn:aws:secretsmanager:x:1:secret:key"}

    assert (f"{where}.secrets", "secrets_section") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("value", [[], "hub", None])
def test_an_environment_or_family_that_is_not_an_object_is_refused(value):
    data = settings()
    data["prod"]["worker"] = value

    assert ("prod.worker", "not_an_object") in kinds(app_env.file_problems(data))


def test_an_unknown_variable_is_refused():
    data = settings()
    data["prod"]["hub"]["VERIFACTU_PRODUCTON_ENABLED"] = "true"

    assert ("prod.hub.VERIFACTU_PRODUCTON_ENABLED", "unknown_variable") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("value", [True, False, 1, 0.5, None, {"on": "true"}, ["true"]])
def test_a_value_that_is_not_text_is_refused(value):
    data = settings()
    data["prod"]["hub"]["VERIFACTU_PRODUCTION_ENABLED"] = value

    assert ("prod.hub.VERIFACTU_PRODUCTION_ENABLED", "not_text") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VERIFACTU_PRODUCTION_ENABLED", "yes"),
        ("VERIFACTU_PRODUCTION_ENABLED", "True"),
        ("VERIFACTU_ERPLORA_ROUTE_ENABLED", ""),
        ("PLATFORM_HUB_SLUG", "Erplora"),
        ("PLATFORM_HUB_SLUG", "erplora.com"),
        ("PLATFORM_HUB_SLUG", "-erplora"),
    ],
)
def test_a_value_the_hub_does_not_read_that_way_is_refused(name, value):
    data = settings()
    data["prod"]["hub"][name] = value

    assert (f"prod.hub.{name}", "invalid_value") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("name", list(SETTINGS_NAMES))
def test_the_migration_takes_none_of_the_hub_settings(name):
    data = settings()
    data["prod"]["hub-migrate"] = {name: "false" if name.startswith("VERIFACTU") else "erplora"}

    assert (f"prod.hub-migrate.{name}", "wrong_family") in kinds(app_env.file_problems(data))


def test_an_empty_migration_family_is_accepted():
    data = settings()
    data["prod"]["hub-migrate"] = {}

    assert app_env.file_problems(data) == []


# ── Nothing that looks like a secret ───────────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "value",
    [
        "-----BEGIN PRIVATE KEY-----",
        "AKIAIOSFODNN7EXAMPLE",
        "sk_live_51HxQabcdefghijkl",
        "rk_test_51HxQabcdefghijkl",
        "ghp_abcdefghijklmnopqrstuvwxyz0123456789",
        "github_pat_11ABCDEFG0123456789",
        "xoxb-123456789012-abcdef",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.sig",
        "postgres://hub:s3cret@db.internal:5432/hub",
        "3f9a1c0e7b2d4a6f8e1c3b5d7f9a0c2e4b6d8f0a",
        "dGhpcyBpcyBhIHNlY3JldCBrZXkgb2YgMzIgYnl0ZXM=",
    ],
)
def test_a_value_shaped_like_a_secret_looks_like_one(value):
    assert app_env.looks_like_secret("PLATFORM_HUB_SLUG", value)


@pytest.mark.parametrize(
    "name", ["FISCAL_CERTIFICATE_KEY", "DB_PASSWORD", "STRIPE_SECRET", "GITHUB_TOKEN", "AWS_CREDENTIALS", "SENTRY_DSN"]
)
def test_a_name_of_a_secret_looks_like_one(name):
    assert app_env.looks_like_secret(name, "false")


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("VERIFACTU_PRODUCTION_ENABLED", "true"),
        ("PLATFORM_HUB_SLUG", "erplora"),
        ("PLATFORM_HUB_SLUG", "restaurante-casa-pepe-de-la-esquina-del-barrio-viejo"),
        ("CACHE_PREFIX", "hub"),
    ],
)
def test_an_ordinary_setting_does_not_look_like_a_secret(name, value):
    assert not app_env.looks_like_secret(name, value)


def test_a_known_variable_holding_something_shaped_like_a_secret_is_refused():
    data = settings()
    data["pre"]["worker"]["PLATFORM_HUB_SLUG"] = "3f9a1c0e7b2d4a6f8e1c3b5d7f9a0c2e4b6d8f0a"

    assert ("pre.worker.PLATFORM_HUB_SLUG", "looks_like_secret") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("name", ["STRIPE_SECRET_KEY", "DB_PASSWORD", "GITHUB_TOKEN"])
def test_a_variable_named_like_a_secret_is_refused_as_one(name):
    data = settings()
    data["prod"]["hub"][name] = "x"

    assert (f"prod.hub.{name}", "looks_like_secret") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("PLATFORM_HUB_SLUG", "Hunter2-Passw0rd!"),
        ("VERIFACTU_PRODUCTION_ENABLED", {"token": "Hunter2-Passw0rd!"}),
        ("VERIFACTU_ERPLORA_ROUTE_ENABLED", ["Hunter2-Passw0rd!"]),
    ],
)
def test_no_problem_repeats_the_value_it_refuses(name, value):
    data = settings()
    data["prod"]["hub"][name] = value
    data["prod"]["worker"][name] = value

    problems = app_env.file_problems(data)

    assert problems
    assert not [problem for problem in problems if "Hunter2" in str(problem)]


def test_the_file_sets_only_the_hub_settings_terraform_left_to_it():
    assert set(app_env.SETTINGS) == set(SETTINGS_NAMES)


def test_no_known_variable_is_named_like_a_secret():
    assert [name for name in app_env.SETTINGS if app_env.looks_like_secret(name, "")] == []


# ── The safety rules of each environment ───────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("family", ["hub", "worker"])
def test_pre_never_opens_the_aeat_production_environment(family):
    data = settings()
    data["pre"][family]["VERIFACTU_PRODUCTION_ENABLED"] = "true"
    data["pre"]["hub" if family == "worker" else "worker"]["VERIFACTU_PRODUCTION_ENABLED"] = "true"

    assert (f"pre.{family}.VERIFACTU_PRODUCTION_ENABLED", "pre_must_be_false") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("family", ["hub", "worker"])
def test_pre_says_it_explicitly(family):
    data = settings()
    del data["pre"][family]["VERIFACTU_PRODUCTION_ENABLED"]

    assert (f"pre.{family}.VERIFACTU_PRODUCTION_ENABLED", "pre_must_be_false") in kinds(app_env.file_problems(data))


def test_the_hub_and_its_worker_send_to_the_same_aeat_environment():
    data = settings()
    data["prod"]["worker"]["VERIFACTU_PRODUCTION_ENABLED"] = "false"

    assert ("prod.VERIFACTU_PRODUCTION_ENABLED", "families_disagree") in kinds(app_env.file_problems(data))


@pytest.mark.parametrize("value", ["false", None])
def test_charging_requires_the_hub_sending_to_the_aeat(value):
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        if value is None:
            del section[family]["VERIFACTU_PRODUCTION_ENABLED"]
        else:
            section[family]["VERIFACTU_PRODUCTION_ENABLED"] = value

    problems = app_env.charging_problems(section, charging=True)

    assert kinds(problems) == {
        ("prod.hub.VERIFACTU_PRODUCTION_ENABLED", "charging_needs_production"),
        ("prod.worker.VERIFACTU_PRODUCTION_ENABLED", "charging_needs_production"),
    }


def test_without_charging_the_hub_may_stay_on_the_aeat_test_environment():
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        section[family]["VERIFACTU_PRODUCTION_ENABLED"] = "false"

    assert app_env.charging_problems(section, charging=False) == []


@pytest.mark.parametrize(
    ("value", "charging"), [("true", True), ("True", True), ("1", True), ("false", False), ("0", False), (None, False)]
)
def test_the_saas_charges_when_its_revision_enables_platform_invoicing(value, charging):
    variables = {"STRIPE_EXPECTED_MODE": "live"} | ({} if value is None else {"PLATFORM_INVOICING_ENABLED": value})
    saas = {"taskDefinition": revision("saas", variables)}

    assert app_env.charges(saas) is charging


# ── One owner per variable ─────────────────────────────────────────────────────────────────────────────────────────


def test_a_variable_terraform_sets_is_refused():
    current = {"worker": PROD["worker"]}
    revisions = deployed(current)
    revisions["hub"]["containerDefinitions"][0]["environment"].append({"name": "PLATFORM_HUB_SLUG", "value": "erplora"})

    problems = app_env.owner_problems("prod", PROD, current, revisions)

    assert kinds(problems) == {("prod.hub.PLATFORM_HUB_SLUG", "terraform_owns")}


def test_a_secret_terraform_sets_is_refused():
    revisions = deployed()
    revisions["worker"]["containerDefinitions"][0]["secrets"].append(
        {"name": "PLATFORM_HUB_SLUG", "valueFrom": "arn:aws:secretsmanager:x:1:secret:slug"}
    )

    problems = app_env.owner_problems("prod", PROD, PROD, revisions)

    assert kinds(problems) == {("prod.worker.PLATFORM_HUB_SLUG", "terraform_secret")}


def test_variables_of_the_settings_in_force_and_new_ones_belong_to_the_file():
    section = copy.deepcopy(PROD)
    section["hub"]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "false"

    assert app_env.owner_problems("prod", section, PROD, deployed()) == []


# ── The lock on sending to the AEAT for real ──────────────────────────────────────────────────────────────────────


def with_production(value):
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        section[family]["VERIFACTU_PRODUCTION_ENABLED"] = value
    return section


@pytest.mark.parametrize(("before", "after"), [("false", "true"), ("true", "false")])
def test_opening_or_closing_it_in_prod_needs_the_confirmation(before, after):
    problems = app_env.lock_problems(with_production(after), with_production(before), confirm="")

    assert kinds(problems) == {("prod.VERIFACTU_PRODUCTION_ENABLED", "needs_confirmation")}
    assert f"VERIFACTU_PRODUCTION_ENABLED={after}" in problems[0].message


@pytest.mark.parametrize(("before", "after"), [("false", "true"), ("true", "false")])
def test_the_exact_confirmation_lets_it_through(before, after):
    confirm = f"VERIFACTU_PRODUCTION_ENABLED={after}"

    assert app_env.lock_problems(with_production(after), with_production(before), confirm=confirm) == []


@pytest.mark.parametrize(
    "confirm",
    ["VERIFACTU_PRODUCTION_ENABLED=false", "VERIFACTU_PRODUCTION_ENABLED", "yes", "verifactu_production_enabled=true"],
)
def test_a_confirmation_of_something_else_is_refused(confirm):
    problems = app_env.lock_problems(with_production("true"), with_production("false"), confirm=confirm)

    assert kinds(problems) == {("prod.VERIFACTU_PRODUCTION_ENABLED", "confirmation_mismatch")}


@pytest.mark.parametrize(
    "confirm",
    [
        " VERIFACTU_PRODUCTION_ENABLED=true ",
        "VERIFACTU_PRODUCTION_ENABLED=true,",
        "VERIFACTU_PRODUCTION_ENABLED=true VERIFACTU_PRODUCTION_ENABLED=true",
    ],
)
def test_the_confirmation_may_be_set_apart_by_commas_or_spaces(confirm):
    assert app_env.lock_problems(with_production("true"), with_production("false"), confirm=confirm) == []


def test_a_confirmation_when_nothing_protected_changes_is_refused():
    problems = app_env.lock_problems(PROD, PROD, confirm="VERIFACTU_PRODUCTION_ENABLED=true")

    assert kinds(problems) == {("prod.VERIFACTU_PRODUCTION_ENABLED", "confirmation_mismatch")}


def test_an_unchanged_lock_needs_no_confirmation():
    assert app_env.lock_problems(PROD, PROD, confirm="") == []


def test_writing_down_the_hub_default_is_no_change():
    current = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        del current[family]["VERIFACTU_PRODUCTION_ENABLED"]

    assert app_env.lock_problems(with_production("false"), current, confirm="") == []


# ── The revision registered ────────────────────────────────────────────────────────────────────────────────────────


def test_the_settings_go_into_the_app_container_only():
    base = revision("hub", {"DEBUG": "False", "VERIFACTU_PRODUCTION_ENABLED": "false"})
    section = {"hub": {"VERIFACTU_PRODUCTION_ENABLED": "true", "PLATFORM_HUB_SLUG": "erplora"}}

    result = app_env.merged(base, "hub", section, {"hub": {"VERIFACTU_PRODUCTION_ENABLED": "false"}})

    assert app_environment(result, "hub") == {
        "DEBUG": "False",
        "VERIFACTU_PRODUCTION_ENABLED": "true",
        "PLATFORM_HUB_SLUG": "erplora",
    }
    assert app_environment(result, "pgbouncer") == {"PGBOUNCER_PORT": "6432"}
    assert result["containerDefinitions"][0]["secrets"] == base["containerDefinitions"][0]["secrets"]
    assert result["tags"] == base["tags"]


def test_a_setting_the_file_drops_leaves_the_revision():
    variables = {"DEBUG": "False", "PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"}
    base = revision("worker", variables)
    current = {"worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"}}

    result = app_env.merged(base, "worker", {"worker": {"PLATFORM_HUB_SLUG": "erplora"}}, current)

    assert app_environment(result, "worker") == {"DEBUG": "False", "PLATFORM_HUB_SLUG": "erplora"}


def test_a_family_without_settings_keeps_terraform_variables():
    base = revision("hub-migrate", {"DEBUG": "False"})

    assert app_env.merged(base, "hub-migrate", PROD, PROD) == base


def test_a_revision_without_the_app_container_is_refused():
    base = revision("hub")
    base["containerDefinitions"][0]["name"] = "web"

    with pytest.raises(app_env.Refused) as refused:
        app_env.merged(base, "hub", PROD, PROD)

    assert kinds(refused.value.problems) == {("erplora-prod-hub", "no_app_container")}


# ── A deploy, with git and the aws CLI replaced ───────────────────────────────────────────────────────────────────


COMMIT = "abc123"


class FakeCommands:
    """Answers git and the aws CLI as a deploy runner would, and records every command."""

    def __init__(self, file=None, current=None, saas_charging=True):
        self.file = json.dumps(settings()) if file is None else file
        self.current = {"prod": PROD, "pre": PRE} if current is None else current
        self.saas_charging = saas_charging
        self.commits = {COMMIT}
        self.calls = []

    def __call__(self, command):
        self.calls.append(command)
        if command[:2] == ["git", "show"]:
            return self._git_show(command[2])
        if command[:3] == ["git", "cat-file", "-e"]:
            return self._git_commit(command[3])
        if command[:3] == ["aws", "ssm", "get-parameter"]:
            return self._parameter(command)
        if command[:3] == ["aws", "ecs", "describe-task-definition"]:
            return self._saas(command)
        raise AssertionError(f"unexpected command {command}")

    def _git_show(self, spec):
        commit, path = spec.split(":", 1)
        if commit not in self.commits or path != "deploy/app-env.json" or self.file is False:
            raise app_env.CommandFailed(f"fatal: path '{path}' does not exist in '{commit}'")
        return self.file

    def _git_commit(self, spec):
        if spec.removesuffix("^{commit}") not in self.commits:
            raise app_env.CommandFailed(f"fatal: Not a valid object name {spec}")
        return ""

    def _parameter(self, command):
        name = command[command.index("--name") + 1]
        environment = name.split("/")[2]
        if name != f"/erplora/{environment}/hub/app_env" or environment not in self.current:
            raise app_env.CommandFailed("An error occurred (ParameterNotFound) when calling the GetParameter operation")
        value = self.current[environment]
        return value if isinstance(value, str) else json.dumps(value)

    def _saas(self, command):
        if command[command.index("--task-definition") + 1] != "erplora-prod-saas" or self.saas_charging is None:
            raise app_env.CommandFailed("An error occurred (ClientException): Unable to describe task definition.")
        invoicing = "true" if self.saas_charging else "false"
        return json.dumps({"taskDefinition": revision("saas", {"PLATFORM_INVOICING_ENABLED": invoicing})})


@pytest.fixture
def workdir(tmp_path):
    for family, base in deployed().items():
        (tmp_path / f"{family}.json").write_text(json.dumps(base))
    return tmp_path


def deploy(monkeypatch, workdir, commands, environment="prod", confirm=""):
    monkeypatch.setattr(app_env, "run", commands)
    return app_env.main([str(workdir), environment, COMMIT, "eu-west-1", "--confirm", confirm])


def read(workdir, name):
    return json.loads((workdir / f"{name}.json").read_text())


def test_a_deploy_gives_each_revision_the_settings_of_its_commit(monkeypatch, workdir):
    data = settings()
    data["prod"]["hub"]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "false"
    commands = FakeCommands(file=json.dumps(data))

    assert deploy(monkeypatch, workdir, commands) == 0

    assert app_environment(read(workdir, "hub"), "hub")["VERIFACTU_ERPLORA_ROUTE_ENABLED"] == "false"
    assert "VERIFACTU_ERPLORA_ROUTE_ENABLED" not in app_environment(read(workdir, "worker"), "worker")
    assert read(workdir, "app_env") == data["prod"]
    assert ["git", "show", f"{COMMIT}:deploy/app-env.json"] in commands.calls


def test_the_settings_to_record_are_compact_json_with_sorted_keys(monkeypatch, workdir):
    section = {"worker": dict(reversed(PROD["worker"].items())), "hub": dict(reversed(PROD["hub"].items()))}
    commands = FakeCommands(file=json.dumps(settings(prod=section)))

    assert deploy(monkeypatch, workdir, commands) == 0

    assert (workdir / "app_env.json").read_text() == json.dumps(PROD, sort_keys=True, separators=(",", ":"))


def test_a_deploy_reads_the_settings_in_force_and_the_saas_revision_of_its_environment(monkeypatch, workdir):
    commands = FakeCommands()

    deploy(monkeypatch, workdir, commands)

    reads = [command for command in commands.calls if command[0] == "aws"]
    assert [command[:3] for command in reads] == [
        ["aws", "ssm", "get-parameter"],
        ["aws", "ecs", "describe-task-definition"],
    ]
    assert all(command[command.index("--region") + 1] == "eu-west-1" for command in reads)
    assert "/erplora/prod/hub/app_env" in reads[0]
    assert "erplora-prod-saas" in reads[1]


def test_pre_neither_reads_the_saas_nor_asks_for_the_confirmation(monkeypatch, workdir):
    data = settings()
    data["pre"]["hub"]["PLATFORM_HUB_SLUG"] = data["pre"]["worker"]["PLATFORM_HUB_SLUG"] = "erplora-pre"
    commands = FakeCommands(file=json.dumps(data), current={"pre": PRE})

    assert deploy(monkeypatch, workdir, commands, environment="pre", confirm="anything") == 0

    assert not any("describe-task-definition" in command for command in commands.calls)
    assert any("/erplora/pre/hub/app_env" in command for command in commands.calls)
    assert read(workdir, "app_env") == data["pre"]


def test_a_refused_deploy_leaves_the_revisions_as_they_were_and_writes_no_settings(monkeypatch, workdir, capsys):
    data = settings()
    data["prod"]["hub"]["DEBUG"] = "True"
    before = {family: read(workdir, family) for family in ("hub", "worker", "hub-migrate")}

    assert deploy(monkeypatch, workdir, FakeCommands(file=json.dumps(data))) == 1

    assert {family: read(workdir, family) for family in before} == before
    assert not (workdir / "app_env.json").exists()
    assert "::error::prod.hub.DEBUG: " in capsys.readouterr().err


def test_every_refusal_is_reported_and_says_nothing_was_registered(monkeypatch, workdir, capsys):
    data = settings()
    data["prod"]["worker"]["PLATFORM_HUB_SLUG"] = "Erplora"
    data["pre"]["hub"]["FOO"] = "bar"

    assert deploy(monkeypatch, workdir, FakeCommands(file=json.dumps(data))) == 1

    errors = capsys.readouterr().err.splitlines()
    assert len(errors) >= 2
    assert all(line.startswith("::error::") and line.endswith("; nothing was registered") for line in errors)


def test_the_saas_charging_refuses_closing_the_aeat_in_the_file(monkeypatch, workdir, capsys):
    data = settings()
    data["prod"] = with_production("false")
    commands = FakeCommands(file=json.dumps(data), current={"prod": with_production("false")})

    assert deploy(monkeypatch, workdir, commands) == 1

    assert "prod.hub.VERIFACTU_PRODUCTION_ENABLED" in capsys.readouterr().err


def test_an_unreadable_saas_revision_refuses_the_prod_deploy(monkeypatch, workdir, capsys):
    assert deploy(monkeypatch, workdir, FakeCommands(saas_charging=None)) == 1

    assert "erplora-prod-saas" in capsys.readouterr().err


def test_opening_the_aeat_in_prod_takes_the_confirmation(monkeypatch, workdir):
    commands = FakeCommands(current={"prod": with_production("false")}, saas_charging=False)

    assert deploy(monkeypatch, workdir, commands) == 1
    assert not (workdir / "app_env.json").exists()

    assert deploy(monkeypatch, workdir, commands, confirm="VERIFACTU_PRODUCTION_ENABLED=true") == 0
    assert read(workdir, "app_env") == PROD


def test_a_missing_settings_parameter_refuses_the_deploy(monkeypatch, workdir, capsys):
    assert deploy(monkeypatch, workdir, FakeCommands(current={})) == 1

    assert "/erplora/prod/hub/app_env" in capsys.readouterr().err


@pytest.mark.parametrize("value", ["not json", "[]", '{"hub": "true"}'])
def test_settings_in_force_that_are_not_families_of_variables_refuse_the_deploy(monkeypatch, workdir, capsys, value):
    assert deploy(monkeypatch, workdir, FakeCommands(current={"prod": value})) == 1

    assert "/erplora/prod/hub/app_env" in capsys.readouterr().err


def test_a_file_that_is_not_json_refuses_the_deploy(monkeypatch, workdir, capsys):
    assert deploy(monkeypatch, workdir, FakeCommands(file="{prod: }")) == 1

    assert "deploy/app-env.json" in capsys.readouterr().err


def test_a_commit_from_before_the_file_keeps_the_settings_in_force(monkeypatch, workdir, capsys):
    commands = FakeCommands(file=False)

    assert deploy(monkeypatch, workdir, commands) == 0

    assert read(workdir, "app_env") == PROD
    assert app_environment(read(workdir, "hub"), "hub") == app_environment(deployed()["hub"], "hub")
    assert capsys.readouterr().err.startswith("::warning::")


def test_an_unknown_commit_refuses_the_deploy(monkeypatch, workdir, capsys):
    commands = FakeCommands(file=False)
    commands.commits = set()

    assert deploy(monkeypatch, workdir, commands) == 1

    assert COMMIT in capsys.readouterr().err
