#!/usr/bin/env python3
"""Checks the hub's settings the revisions a rollback goes back to run, and writes what it records.

scripts/ecs_rollback.py runs it once it has found the revisions the services go back to, before it moves any,
with what `aws ecs describe-task-definition --include TAGS` answers for each in <workdir>/<family>.json:

    deploy/app_env_rollback.py <workdir> <environment> <region> [--confirm=NAME=value[,NAME=value]]

A rollback registers nothing: the services run the settings those revisions were registered with, whatever
deploy/app-env.json says today. So it reads the hub settings of each revision's app container and puts them through
the deploy's checks (deploy/app_env.py): the rules of each environment and, in prod, the lock against the settings in
force and the SaaS charging. Then it writes app_env.json with what ecs_rollback.py records once the rollback
succeeds; otherwise it reports every problem and changes nothing. Standard library only: it runs on the deploy
runner's python3.
"""

import json
import sys

import app_env

# The families whose services go back; the migration keeps the settings in force.
ROLLED_BACK = app_env.SERVING


def running(definition, family):
    """The hub settings the app container of a revision runs with."""
    container = app_env.app_container(definition.get("taskDefinition", {}), family)
    return {e.get("name"): e.get("value") for e in container.get("environment", []) if e.get("name") in app_env.SETTINGS}


def to_record(section, in_force):
    """The settings of the families that go back, and the migration's in force."""
    result = {family: section[family] for family in ROLLED_BACK if family in section}
    result.update({family: variables for family, variables in in_force.items() if family not in ROLLED_BACK})
    return result


def roll_back(workdir, environment, region, confirm):
    in_force = app_env.read_in_force(environment, region)
    definitions = {family: json.loads((workdir / f"{family}.json").read_text()) for family in ROLLED_BACK}
    section = {family: running(definition, family) for family, definition in definitions.items()}
    problems = app_env.section_problems(environment, section)
    if environment == "prod" and not problems:
        problems = app_env.lock_problems(section, in_force, confirm)
        problems += app_env.charging_problems(section, app_env.saas_charges(region))
    if problems:
        raise app_env.Refused(problems)
    app_env.write_settings(workdir, to_record(section, in_force))


def main(argv=None):
    args = app_env.arguments(argv, __doc__.splitlines()[0], positionals=("region",))
    try:
        roll_back(args.workdir, args.environment, args.region, args.confirm)
    except app_env.Refused as refused:
        for problem in refused.problems:
            print(f"::error::{problem}; nothing was changed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
