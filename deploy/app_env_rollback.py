#!/usr/bin/env python3
"""Checks the hub's settings a rollback puts back in force and writes what it records.

.github/scripts/ecs-rollback.sh runs it once it has found the revisions the services go back to, before it moves any,
with what `aws ecs describe-task-definition --include TAGS` answers for each in <workdir>/<family>.json:

    deploy/app_env_rollback.py <workdir> <environment> <commit> <region> [--confirm=NAME=value[,NAME=value]]

A rollback registers nothing, so the services run the settings those revisions carry. It goes through only if they are
the settings of deploy/app-env.json in the commit they run (the settings in force for a commit from before the file)
and those pass the deploy's checks (deploy/app_env.py): the rules of each environment and, in prod, the lock and the
SaaS charging. Then it writes app_env.json with what ecs-rollback.sh records once the rollback succeeds; otherwise it
reports every problem and changes nothing. Standard library only: it runs on the deploy runner's python3.
"""

import argparse
import json
import sys
from pathlib import Path

import app_env

# The families whose services go back; the migration keeps the settings in force.
ROLLED_BACK = app_env.SERVING


def as_read(variables, family):
    """The value of each hub setting of a family as the hub reads it: an absent one takes its default."""
    return {
        name: variables.get(name, setting.default)
        for name, setting in app_env.SETTINGS.items()
        if family in setting.families
    }


def revision_problems(section, definitions):
    """Each revision has to run the settings the rollback records; no message repeats a value."""
    problems = []
    for family in ROLLED_BACK:
        revision = definitions[family].get("taskDefinition", {})
        container = app_env.app_container(revision, family)
        carried = as_read({e.get("name"): e.get("value") for e in container.get("environment", [])}, family)
        wanted = as_read(section.get(family, {}), family)
        where = revision.get("taskDefinitionArn", revision.get("family", family))
        message = "runs another value than the settings this rollback records"
        problems += [
            app_env.Problem(f"{where}.{name}", "revision_differs", message)
            for name in wanted
            if carried[name] != wanted[name]
        ]
    return problems


def to_record(section, in_force):
    """The settings of the families that go back, and the migration's in force."""
    result = {family: section[family] for family in ROLLED_BACK if family in section}
    result.update({family: variables for family, variables in in_force.items() if family not in ROLLED_BACK})
    return result


def roll_back(workdir, environment, commit, region, confirm):
    in_force = app_env.read_in_force(environment, region)
    section = app_env.read_section(commit, environment, in_force)
    definitions = {family: json.loads((workdir / f"{family}.json").read_text()) for family in ROLLED_BACK}
    problems = revision_problems(section, definitions)
    if environment == "prod":
        problems += app_env.lock_problems(section, in_force, confirm)
        problems += app_env.charging_problems(section, app_env.saas_charges(region))
    if problems:
        raise app_env.Refused(problems)
    record = to_record(section, in_force)
    (workdir / "app_env.json").write_text(json.dumps(record, sort_keys=True, separators=(",", ":")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("workdir", type=Path)
    parser.add_argument("environment", choices=app_env.ENVIRONMENTS)
    parser.add_argument("commit")
    parser.add_argument("region")
    parser.add_argument("--confirm", default="", help="the protected changes confirmed, NAME=value[,NAME=value]")
    args = parser.parse_args(argv)
    try:
        roll_back(args.workdir, args.environment, args.commit, args.region, args.confirm)
    except app_env.Refused as refused:
        for problem in refused.problems:
            print(f"::error::{problem}; nothing was changed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
