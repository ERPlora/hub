"""What the tests of scripts/ecs_deploy.py deploy with: the fake aws CLI of ecs_doubles and a fake git first on the
PATH, and fixtures for what they answer.

The fake aws records every call and answers from the fixtures; the fake git answers deploy/app-env.json of the commit
abc123 from its fixture.
"""

import json

from ecs_doubles import APP_ENV, FAKE_AWS_END, FAKE_AWS_START, SCRIPTS, ScriptCase, one

FAKE_AWS = FAKE_AWS_START + r'''

def register_task_definition():
    import json
    revision = json.loads(read(value("--cli-input-json").removeprefix("file://")))
    with open(env["REGISTERED_LOG"], "a", encoding="utf-8") as registered:
        registered.write(json.dumps(revision, separators=(",", ":")) + "\n")
    print(f"arn:td/{revision['family']}:2")


def describe_services():
    service = value("--services")
    if "deployments" not in value("--query"):
        print('{"awsvpcConfiguration":{"subnets":["s"],"securityGroups":["g"],"assignPublicIp":"ENABLED"}}')
    elif service == "hub" and "FAKE_PRIMARY_ANSWER" in env:
        answer("FAKE_PRIMARY_ANSWER")
    else:
        # The PRIMARY deployment after the wait: successive reads of a service answer the next of
        # FAKE_PRIMARY_REVISIONS and FAKE_ROLLOUT_STATES (or the service's own in FAKE_ROLLOUT_STATES_OF, as JSON);
        # by default the new revision (2), COMPLETED.
        states = env.get("FAKE_ROLLOUT_STATES", "COMPLETED")
        if "FAKE_ROLLOUT_STATES_OF" in env:
            import json
            states = json.loads(env["FAKE_ROLLOUT_STATES_OF"]).get(service, states)
        revision = nth(f"revision.{service}", env.get("FAKE_PRIMARY_REVISIONS", "2"))
        state = nth(f"state.{service}", states)
        name = service.removesuffix("-pre")
        family = f"erplora-pre-{name}" if service.endswith("-pre") else f"erplora-prod-{name}"
        print(f"arn:td/{family}:{revision}\t{state}")


def run_task():
    if "FAKE_RUN_TASK_ANSWER" in env:
        answer("FAKE_RUN_TASK_ANSWER")
    elif env.get("FAKE_RUN_TASK_FAILURE"):
        import json
        print(json.dumps({"tasks": [], "failures": [{"arn": "arn:capacity", "reason": env["FAKE_RUN_TASK_FAILURE"]}]}))
    else:
        # The task ARN names the cluster the task runs in, as ECS does.
        print(f'{{"tasks": [{{"taskArn": "arn:task/{value("--cluster")}/migrate1"}}], "failures": []}}')


def describe_tasks():
    query = value("--query")
    if "lastStatus" in query:
        print(nth("status", env.get("FAKE_TASK_STATUSES", "RUNNING STOPPED")))
    elif "exitCode" in query:
        print(env.get("FAKE_MIGRATE_EXIT", "0"))
    elif "stoppedReason" in query:
        answer("FAKE_STOPPED_REASON") if "FAKE_STOPPED_REASON" in env else print("Essential container in task exited")


def update_service():
    print(f'{{"service": {{"serviceName": "{value("--service")}"}}}}')


COMMANDS = {
    "ecs describe-task-definition": describe_task_definition, "ecs register-task-definition": register_task_definition,
    "ecs describe-services": describe_services, "ecs run-task": run_task, "ecs describe-tasks": describe_tasks,
    "ssm get-parameter": get_parameter, "ssm put-parameter": put_parameter, "ecs update-service": update_service,
}
''' + FAKE_AWS_END

# git answers deploy/app-env.json of abc123 (or FAKE_COMMIT) from its fixture, and fails as git does without it.
FAKE_GIT = r'''
import os
import sys

args = sys.argv[1:]
with open(os.environ["GIT_LOG"], "a", encoding="utf-8") as calls:
    calls.write(" ".join(args) + "\n")
settings = os.path.join(os.environ["FIXTURES"], "app-env.json")
commit = os.environ.get("FAKE_COMMIT", "abc123")
if args[:2] == ["show", f"{commit}:deploy/app-env.json"]:
    if os.path.isfile(settings):
        with open(settings, encoding="utf-8") as found:
            sys.stdout.write(found.read())
        sys.exit(0)
    print(f"fatal: path 'deploy/app-env.json' does not exist in '{commit}'", file=sys.stderr)
elif args[:2] == ["cat-file", "-e"] and args[2:] == [f"{commit}^{{commit}}"]:
    sys.exit(0)
else:
    print(f"fatal: unexpected git {' '.join(args)}", file=sys.stderr)
sys.exit(128)
'''

# Terraform's variables and the settings in force of prod's apps.
PROD_APP = [{"name": "DEBUG", "value": "False"}, {"name": "PLATFORM_HUB_SLUG", "value": "erplora"},
            {"name": "VERIFACTU_PRODUCTION_ENABLED", "value": "true"}]


class DeployCase(ScriptCase):
    """A fresh fake AWS for each test: prod's and pre's families on their own image, and deploy/app-env.json of the
    commit deployed equal to the settings in force."""

    script = SCRIPTS / "ecs_deploy.py"

    def setUp(self):
        super().setUp()
        # The hub and the worker run the app plus its pgbouncer sidecar, both on the hub image; the hub fixture also
        # carries containers of other images, which must stay as they are.
        self.fixture("erplora-prod-hub", [
            *one("hub", "hub:bootstrap", environment=PROD_APP), *one("pgbouncer", "hub:bootstrap"),
            {"name": "log-router", "image": "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable"},
            {"name": "look-alike", "image": "reg.example/erplora/hubx:bootstrap"}])
        self.fixture("erplora-prod-worker",
                     one("worker", "hub:bootstrap", environment=PROD_APP) + one("pgbouncer", "hub:bootstrap"))
        self.fixture("erplora-prod-hub-migrate", one("hub-migrate", "hub:bootstrap"))
        self.fixture("erplora-prod-db-bootstrap", one("db-bootstrap", "hub:bootstrap"))
        # pre: the same families in its own cluster, on its own ECR repository; its containers keep the short names.
        self.fixture("erplora-pre-hub", one("hub", "hub-pre:bootstrap") + one("pgbouncer", "hub-pre:bootstrap"))
        self.fixture("erplora-pre-worker", one("worker", "hub-pre:bootstrap") + one("pgbouncer", "hub-pre:bootstrap"))
        self.fixture("erplora-pre-hub-migrate", one("hub-migrate", "hub-pre:bootstrap"))
        self.fixture("erplora-pre-db-bootstrap", one("db-bootstrap", "hub:bootstrap"))
        self.write("app-env.json", APP_ENV)
        self.install("aws", FAKE_AWS)
        self.install("git", FAKE_GIT)

    def deploy(self, *unset, apart=False, **env):
        """Deploys abc123 to prod with the fakes; <env> overrides the environment and <unset> takes variables out of
        it. stdout and stderr land together in self.out, or apart in self.stdout and self.stderr. The logs and the
        fake's counters start empty."""
        for log in ("registered.log", "git.log"):
            (self.work / log).write_text("")
        environ = self.environ(unset, env, REGISTRY="reg.example", IMAGE_TAG="abc123",
                               REGISTERED_LOG=str(self.work / "registered.log"), GIT_LOG=str(self.work / "git.log"))
        return self.execute(environ, apart)

    def git_calls(self):
        return (self.work / "git.log").read_text().splitlines()

    def registered(self):
        lines = (self.work / "registered.log").read_text().splitlines()
        return {revision["family"]: revision for revision in map(json.loads, lines)}

    def images(self, family, name=None):
        containers = self.registered()[family]["containerDefinitions"]
        return [c["image"] for c in containers if name is None or c["name"] == name]

    def environment_of(self, family, name):
        """The variables of the container <name> in the revision registered for <family>."""
        container = next(c for c in self.registered()[family]["containerDefinitions"] if c["name"] == name)
        return {variable["name"]: variable["value"] for variable in container.get("environment", [])}

    def assertNothingRegistered(self, error=None):
        """The deploy failed, registered and ran nothing and recorded no settings; <error>, when given, is a pattern its
        ::error:: line matches."""
        self.assertNotEqual(0, self.status)
        self.assertEqual({}, self.registered())
        self.assertFalse(self.called("register-task-definition|run-task|update-service|put-parameter"))
        self.assertFalse((self.work / "app-env-put.json").exists())
        if error is not None:
            self.assertRegex(self.out, f"::error::{error}")
