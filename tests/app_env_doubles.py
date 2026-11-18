"""What the tests of deploy/app_env.py and deploy/app_env_rollback.py share: the scripts, the settings and the doubles.

The scripts run on the deploy runner, outside Django and the project's virtualenv: they are loaded here from their
path, and git and the aws CLI are replaced by a double (``FakeCommands``), so no test calls AWS.
"""

import copy
import importlib.util
import json
import sys
from pathlib import Path

HUB_DIR = Path(__file__).resolve().parents[1]
DEPLOY_DIR = HUB_DIR / "deploy"


def load(name):
    """The script deploy/<name>.py as a module, registered under its name so the other script imports this one."""
    spec = importlib.util.spec_from_file_location(name, DEPLOY_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


app_env = load("app_env")

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
COMMIT = "abc123"


def settings(**sections):
    data = {"prod": copy.deepcopy(PROD), "pre": copy.deepcopy(PRE)}
    data.update(sections)
    return data


def with_production(value):
    section = copy.deepcopy(PROD)
    for family in ("hub", "worker"):
        section[family]["VERIFACTU_PRODUCTION_ENABLED"] = value
    return section


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


def app_environment(revision, name):
    container = next(c for c in revision["containerDefinitions"] if c["name"] == name)
    return {entry["name"]: entry["value"] for entry in container.get("environment", [])}


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
