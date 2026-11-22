#!/usr/bin/env python3
"""Checks the hub's settings of each environment (deploy/app-env.json) and applies one environment's to a deploy.

scripts/ecs_deploy.py runs it once it has prepared every revision it will register, one <family>.json per family in
its work directory, and before it registers any:

    deploy/app_env.py <workdir> <environment> <commit> <region> [--confirm=NAME=value[,NAME=value]]

It reads deploy/app-env.json of the commit being deployed, the settings in force in /erplora/<environment>/hub/app_env
(ERPlora/aws README, "Ajustes de la app") and, in prod, the latest ACTIVE revision of the SaaS. When every check passes
it writes its family's settings into each <family>.json, and app_env.json with what ecs_deploy.py records once the
deploy succeeds; otherwise it reports every problem and changes nothing. Standard library only: it runs on the deploy
runner's python3.
"""

import argparse
import copy
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

PROJECT = "hub"
FILE = "deploy/app-env.json"
ENVIRONMENTS = ("prod", "pre")
FAMILIES = ("hub", "worker", "hub-migrate")
SERVING = ("hub", "worker")
SAAS_FAMILY = "erplora-prod-saas"
# Opening or closing the AEAT's production environment in prod takes an explicit confirmation at deploy time.
LOCK = "VERIFACTU_PRODUCTION_ENABLED"
# What python-decouple, which reads the SaaS's settings, takes for true.
TRUTHY = frozenset({"y", "yes", "t", "true", "on", "1"})


class Setting(NamedTuple):
    pattern: re.Pattern
    families: tuple
    # What the hub takes when the variable is absent (config/settings/).
    default: str


BOOLEAN = re.compile("true|false")
SLUG = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
SETTINGS = {
    "PLATFORM_HUB_SLUG": Setting(SLUG, SERVING, "erplora"),
    LOCK: Setting(BOOLEAN, SERVING, "false"),
    "VERIFACTU_ERPLORA_ROUTE_ENABLED": Setting(BOOLEAN, SERVING, "true"),
}

SECRET_NAME = re.compile(r"SECRET|PASSWORD|PASSWD|TOKEN|CREDENTIAL|PRIVATE|DSN|(?:^|_)KEY(?:$|_)", re.IGNORECASE)
SECRET_VALUE = re.compile(
    r"-----BEGIN|AKIA[0-9A-Z]{16}|\b[sr]k_(?:live|test)_|\bgh[pousr]_[A-Za-z0-9]{20,}|github_pat_|xox[abprs]-"
    r"|eyJ[\w-]{8,}\.[\w-]+\.|://[^/\s:@]+:[^/\s@]+@"
)
RANDOM_RUN = re.compile(r"[A-Za-z0-9+/=]{32,}")


class Problem(NamedTuple):
    where: str
    kind: str
    message: str

    def __str__(self):
        return f"{self.where}: {self.message}"


class Refused(Exception):
    def __init__(self, problems):
        self.problems = list(problems)
        super().__init__("; ".join(map(str, self.problems)))


class CommandFailed(Exception):
    """A command that exited with an error, with what it printed."""


def looks_like_secret(name, value):
    if SECRET_NAME.search(name) or SECRET_VALUE.search(value):
        return True
    return any(re.search(r"\d", run) and re.search(r"[A-Za-z]", run) for run in RANDOM_RUN.findall(value))


def _is_secrets(key):
    return key.lower() in {"secret", "secrets"}


def _secrets_problem(where):
    message = f"secrets never go in {FILE}: the repository is public, they stay in Terraform"
    return Problem(where, "secrets_section", message)


def file_problems(data):
    if not isinstance(data, dict):
        return [Problem(FILE, "not_an_object", "must be a JSON object of environments")]
    problems = [
        Problem(name, "unknown_environment", f"is no environment of the hub ({', '.join(ENVIRONMENTS)})")
        for name in data
        if name not in ENVIRONMENTS
    ]
    for environment in ENVIRONMENTS:
        if environment in data:
            problems += section_problems(environment, data[environment])
        else:
            problems.append(Problem(environment, "missing_environment", f"{FILE} gives no settings for it"))
    return problems


def section_problems(environment, section):
    """What is wrong with one environment's settings: their shape first, then the safety rules."""
    if not isinstance(section, dict):
        return [Problem(environment, "not_an_object", "must be an object of task families")]
    problems = []
    for family, variables in section.items():
        problems += _family_problems(f"{environment}.{family}", family, variables)
    return problems or _rule_problems(environment, section)


def _family_problems(where, family, variables):
    if _is_secrets(family):
        return [_secrets_problem(where)]
    if family not in FAMILIES:
        return [Problem(where, "unknown_family", f"is no task family of the hub ({', '.join(FAMILIES)})")]
    if not isinstance(variables, dict):
        return [Problem(where, "not_an_object", "must be an object of variables")]
    return [problem for name, value in variables.items() for problem in _variable_problems(where, family, name, value)]


def _variable_problems(where, family, name, value):
    where = f"{where}.{name}"
    if _is_secrets(name):
        return [_secrets_problem(where)]
    if SECRET_NAME.search(name):
        return [Problem(where, "looks_like_secret", "is named like a secret; secrets stay in Terraform")]
    if name not in SETTINGS:
        return [Problem(where, "unknown_variable", f"is no setting of {FILE}; Terraform sets the rest")]
    if family not in SETTINGS[name].families:
        return [Problem(where, "wrong_family", f"only goes in {', '.join(SETTINGS[name].families)}")]
    return _value_problems(where, name, value)


def _value_problems(where, name, value):
    if not isinstance(value, str):
        return [Problem(where, "not_text", "must be a JSON string, as ECS hands it over")]
    if looks_like_secret(name, value):
        return [Problem(where, "looks_like_secret", "looks like a secret; secrets stay in Terraform")]
    if not SETTINGS[name].pattern.fullmatch(value):
        return [Problem(where, "invalid_value", f"must match {SETTINGS[name].pattern.pattern}")]
    return []


def _rule_problems(environment, section):
    values = {family: section.get(family, {}).get(LOCK) for family in SERVING}
    if environment == "pre":
        return [
            Problem(f"pre.{family}.{LOCK}", "pre_must_be_false", "must say \"false\": pre never sends to the AEAT")
            for family, value in values.items()
            if value != "false"
        ]
    if len(set(values.values())) > 1:
        return [Problem(f"{environment}.{LOCK}", "families_disagree", "must be the same in hub and worker")]
    return []


def charging_problems(section, charging):
    """Prod's rule: while the SaaS charges real money, every invoice it issues has to reach the AEAT."""
    if not charging:
        return []
    return [
        Problem(f"prod.{family}.{LOCK}", "charging_needs_production", "must be \"true\" while the SaaS charges")
        for family in SERVING
        if section.get(family, {}).get(LOCK) != "true"
    ]


def charges(saas):
    definition = saas.get("taskDefinition") if isinstance(saas, dict) else None
    containers = definition.get("containerDefinitions", []) if isinstance(definition, dict) else []
    return any(
        entry.get("name") == "PLATFORM_INVOICING_ENABLED" and str(entry.get("value", "")).strip().lower() in TRUTHY
        for container in containers
        for entry in container.get("environment", [])
    )


def _names(entries):
    return {entry.get("name") for entry in entries}


def app_container(revision, family):
    """The container the settings go into, named after its family (ERPlora/aws modules/ecs-service)."""
    for container in revision.get("containerDefinitions", []):
        if container.get("name") == family:
            return container
    where = revision.get("family", family)
    raise Refused([Problem(where, "no_app_container", f"has no container named {family} for the settings")])


def owner_problems(environment, section, revisions):
    """One owner per variable: Terraform never sets a setting of the file as a variable, it only passes app_env on
    (ERPlora/aws README, "Ajustes de la app"), so one the latest revision runs and app_env lacks is still the file's,
    left by a rollback or by a deploy that failed after registering. Only a secret of the family is Terraform's."""
    problems = []
    for family, variables in section.items():
        secrets = _names(app_container(revisions[family], family).get("secrets", []))
        problems += [
            Problem(f"{environment}.{family}.{name}", "terraform_secret", f"is a secret Terraform sets in {family}")
            for name in variables
            if name in secrets
        ]
    return problems


def lock_problems(section, in_force, confirm):
    """Prod's lock: a change of what is in force goes through only with confirm set to exactly <name>=<new value>.

    Its messages name the new value, which a setting's pattern has already held to true or false; no other message
    repeats a value of the file, since the deploy logs of a public repository are public."""
    default = SETTINGS[LOCK].default
    changes = sorted({
        f"{LOCK}={section.get(family, {}).get(LOCK, default)}"
        for family in SERVING
        if section.get(family, {}).get(LOCK, default) != in_force.get(family, {}).get(LOCK, default)
    })
    given = sorted({item for item in re.split(r"[,\s]+", confirm) if item})
    if given == changes:
        return []
    where = f"prod.{LOCK}"
    if not given:
        message = f"changes what is in force: run it again by hand with confirm_protected={','.join(changes)}"
        return [Problem(where, "needs_confirmation", message)]
    changed = ",".join(changes) or "nothing protected"
    message = f"confirm_protected says {','.join(given)}, but the settings change {changed}"
    return [Problem(where, "confirmation_mismatch", message)]


def merged(revision, family, section, in_force):
    """The revision with exactly its family's settings of the file: any other setting leaves, also one the app_env in
    force does not name. Terraform's variables stay."""
    wanted = section.get(family, {})
    dropped = (set(SETTINGS) | set(in_force.get(family, {}))) - set(wanted)
    result = copy.deepcopy(revision)
    container = app_container(result, family)
    variables = {e["name"]: e["value"] for e in container.get("environment", []) if e["name"] not in dropped}
    variables.update(wanted)
    container["environment"] = [{"name": name, "value": value} for name, value in variables.items()]
    return result


def run(command):
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise CommandFailed((result.stderr or result.stdout).strip() or f"exit code {result.returncode}")
    return result.stdout


def _is_families(value):
    return isinstance(value, dict) and all(
        isinstance(variables, dict) and all(isinstance(text, str) for text in variables.values())
        for variables in value.values()
    )


def read_in_force(environment, region):
    name = f"/erplora/{environment}/{PROJECT}/app_env"
    command = ["aws", "ssm", "get-parameter", "--name", name, "--query", "Parameter.Value", "--output", "text"]
    try:
        value = json.loads(run([*command, "--region", region]))
    except (CommandFailed, ValueError) as error:
        raise Refused([Problem(name, "unreadable", f"cannot be read ({error})")]) from error
    if not _is_families(value):
        raise Refused([Problem(name, "not_an_object", "must be a JSON object of families of text variables")])
    return value


def read_section(commit, environment, in_force):
    """The environment's settings in the commit; a commit from before the file keeps the settings in force."""
    try:
        text = run(["git", "show", f"{commit}:{FILE}"])
    except CommandFailed:
        return _settings_in_force(commit, environment, in_force)
    try:
        data = json.loads(text)
    except ValueError as error:
        raise Refused([Problem(FILE, "not_json", f"of {commit} is not JSON ({error})")]) from error
    problems = file_problems(data)
    if problems:
        raise Refused(problems)
    return data[environment]


def _settings_in_force(commit, environment, in_force):
    try:
        run(["git", "cat-file", "-e", f"{commit}^{{commit}}"])
    except CommandFailed as error:
        raise Refused([Problem(commit, "unknown_commit", f"is no commit of this checkout ({error})")]) from error
    print(f"::warning::{commit} has no {FILE}: the deploy keeps the settings in force", file=sys.stderr)
    problems = section_problems(environment, in_force)
    if problems:
        raise Refused(problems)
    return in_force


def saas_charges(region):
    command = ["aws", "ecs", "describe-task-definition", "--task-definition", SAAS_FAMILY, "--region", region]
    try:
        return charges(json.loads(run([*command, "--output", "json"])))
    except (CommandFailed, ValueError) as error:
        message = f"cannot be read to know whether it charges ({error})"
        raise Refused([Problem(SAAS_FAMILY, "unreadable", message)]) from error


def apply(workdir, environment, commit, region, confirm):
    in_force = read_in_force(environment, region)
    section = read_section(commit, environment, in_force)
    revisions = {family: json.loads((workdir / f"{family}.json").read_text()) for family in FAMILIES}
    problems = owner_problems(environment, section, revisions)
    if environment == "prod":
        problems += lock_problems(section, in_force, confirm)
        problems += charging_problems(section, saas_charges(region))
    if problems:
        raise Refused(problems)
    results = {family: merged(revision, family, section, in_force) for family, revision in revisions.items()}
    for family, result in results.items():
        (workdir / f"{family}.json").write_text(json.dumps(result))
    write_settings(workdir, section)


def write_settings(workdir, settings):
    """What ecs_deploy.py and ecs-rollback.sh record in app_env once they succeed: compact JSON, keys sorted."""
    (workdir / "app_env.json").write_text(json.dumps(settings, sort_keys=True, separators=(",", ":")))


def arguments(argv, description, positionals=("commit", "region")):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("workdir", type=Path)
    parser.add_argument("environment", choices=ENVIRONMENTS)
    for name in positionals:
        parser.add_argument(name)
    parser.add_argument("--confirm", default="", help="the protected changes confirmed, NAME=value[,NAME=value]")
    return parser.parse_args(argv)


def main(argv=None):
    args = arguments(argv, __doc__.splitlines()[0])
    try:
        apply(args.workdir, args.environment, args.commit, args.region, args.confirm)
    except Refused as refused:
        for problem in refused.problems:
            print(f"::error::{problem}; nothing was registered", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
