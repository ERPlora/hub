"""What the tests of scripts/ecs_deploy.py deploy with: a fake aws CLI and a fake git first on the PATH, fixtures for
what they answer, and the deploy run as the workflow runs it, in a process of its own.

The fake aws records every call and answers from the fixtures; the fake git answers deploy/app-env.json of the commit
abc123 from its fixture. Inside the deploy's process time.sleep only records the pause, so no test waits for real, and
gives up after 500 of them, so a loop that never times out fails its test instead of hanging. AWS's configuration and
credentials point to /dev/null: nothing here can reach AWS.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ecs_deploy.py"
CLUSTER_SCOPED = re.compile(r"^ecs (describe-services|run-task|describe-tasks|update-service|wait) ")
NOT_INHERITED = ("CLUSTER", "PROJECT", "POLL_SECONDS", "MIGRATE_TIMEOUT_SECONDS", "ROLLOUT_TIMEOUT_SECONDS",
                 "CONFIRM_PROTECTED", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN")

BOOT = """\
import os, runpy, sys, time

def sleep(seconds):
    with open(os.environ["SLEEP_LOG"], "a", encoding="utf-8") as log:
        log.write(f"{seconds}\\n")
    with open(os.environ["SLEEP_LOG"], encoding="utf-8") as log:
        if len(log.readlines()) > 500:
            sys.exit("fake sleep: more than 500 pauses")

time.sleep = sleep
runpy.run_path(sys.argv[1], run_name="__main__")
"""

# Imports only what each answer needs: the fake answers every aws call of every test, and Python starts slowly.
FAKE_AWS = r'''
import os
import sys

args = sys.argv[1:]
env = os.environ
fixtures = env["FIXTURES"]
with open(env["CALLS_LOG"], "a", encoding="utf-8", errors="surrogateescape") as calls:
    calls.write(" ".join(args) + "\n")


def value(flag):
    return next((args[i + 1] for i in range(len(args) - 1) if args[i] == flag), "")


def read(path):
    with open(path, "rb") as found:
        return found.read()


def refuse(message):
    print(message, file=sys.stderr)
    sys.exit(254)


def answer(name):
    sys.stdout.buffer.write(os.environb[name.encode()] + b"\n")


def nth(counter, answers):
    # The next of a list of answers, counted per counter; the last one repeats.
    path = os.path.join(os.path.dirname(fixtures), f"polls.{counter}")
    n = int(read(path)) if os.path.exists(path) else 0
    with open(path, "w", encoding="utf-8") as polls:
        polls.write(str(n + 1))
    answers = answers.split()
    return answers[min(n, len(answers) - 1)]


def describe_task_definition():
    path = os.path.join(fixtures, f"{value('--task-definition')}.json")
    if not os.path.isfile(path):
        refuse("An error occurred (ClientException): Unable to describe task definition.")
    if value("--include") == "TAGS":
        sys.stdout.buffer.write(read(path))
        return
    # Tags only come back when asked for.
    import json
    definition = json.loads(read(path))
    definition.pop("tags", None)
    print(json.dumps(definition, indent=4))


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


def get_parameter():
    # /erplora/prod/hub/app_env answers the fixture erplora_prod_hub_app_env.json.
    path = os.path.join(fixtures, value("--name").strip("/").replace("/", "_") + ".json")
    if not os.path.isfile(path):
        refuse("An error occurred (ParameterNotFound) when calling the GetParameter operation: ")
    sys.stdout.buffer.write(read(path))


def put_parameter():
    if value("--name").endswith("/app_env"):
        with open(env["APP_ENV_PUT"], "w", encoding="utf-8", errors="surrogateescape") as put:
            put.write(value("--value") + "\n")
    print('{"Version": 2, "Tier": "Standard"}')


def update_service():
    print(f'{{"service": {{"serviceName": "{value("--service")}"}}}}')


COMMANDS = {
    "ecs describe-task-definition": describe_task_definition, "ecs register-task-definition": register_task_definition,
    "ecs describe-services": describe_services, "ecs run-task": run_task, "ecs describe-tasks": describe_tasks,
    "ssm get-parameter": get_parameter, "ssm put-parameter": put_parameter, "ecs update-service": update_service,
}
command = " ".join(args[:2])
if env.get("FAKE_KILLED_ON") == command:
    os.kill(os.getpid(), 9)
if env.get("FAKE_FAILS_ON") == command:
    refuse(f"An error occurred (AccessDeniedException) when calling {command}")
COMMANDS.get(command, lambda: None)()
'''

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

# deploy/app-env.json of the commit deployed (abc123): the settings in force of each environment are the same.
APP_ENV = {
    "prod": {"hub": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"},
             "worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"}},
    "pre": {"hub": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "false",
                    "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"},
            "worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "false",
                       "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"}},
}
# Terraform's variables and the settings in force of prod's apps.
PROD_APP = [{"name": "DEBUG", "value": "False"}, {"name": "PLATFORM_HUB_SLUG", "value": "erplora"},
            {"name": "VERIFACTU_PRODUCTION_ENABLED", "value": "true"}]


def task_definition(family, containers, environment=None, task_role=None, execution_role=None):
    """A task definition as `describe-task-definition --include TAGS` returns it, with the roles and the Environment tag
    Terraform gives it (ERPlora/aws modules/ecs-service: erplora-<env>-<name>-task and -execution); the tag ("" = none)
    and the roles may be overridden."""
    environment = family.split("-")[1] if environment is None else environment
    tags = [{"key": "Project", "value": "erplora"}, {"key": "ManagedBy", "value": "terraform"}]
    return {
        "taskDefinition": {
            "family": family, "taskDefinitionArn": f"arn:td/{family}:1", "revision": 1, "status": "ACTIVE",
            "requiresAttributes": [], "compatibilities": ["FARGATE"], "registeredAt": "t", "registeredBy": "u",
            "taskRoleArn": task_role or f"arn:aws:iam::123456789012:role/{family}-task",
            "executionRoleArn": execution_role or f"arn:aws:iam::123456789012:role/{family}-execution",
            "containerDefinitions": containers,
        },
        "tags": tags + ([{"key": "Environment", "value": environment}] if environment else []),
    }


def one(name, image, **more):
    return [{"name": name, "image": f"reg.example/erplora/{image}", **more}]


class DeployCase(unittest.TestCase):
    """A fresh fake AWS for each test: prod's and pre's families on their own image, the settings in force equal to
    deploy/app-env.json and the SaaS's latest revision charging real money."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.fixtures = self.work / "fixtures"
        for folder in (self.work / "bin", self.fixtures):
            folder.mkdir()
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
        for environment in ("prod", "pre"):
            self.write(f"erplora_{environment}_hub_app_env.json", APP_ENV[environment])
        self.saas_charging("true")
        for name, fake in (("aws", FAKE_AWS), ("git", FAKE_GIT)):
            path = self.work / "bin" / name
            path.write_text(f"#!{sys.executable} -IS\n{fake}")
            path.chmod(0o755)

    def write(self, name, data):
        (self.fixtures / name).write_text(json.dumps(data))

    def fixture(self, family, containers, *rest):
        self.write(f"{family}.json", task_definition(family, containers, *rest))

    def edit(self, name, change):
        """Changes the fixture <name> with <change>, a function that edits its data in place."""
        data = json.loads((self.fixtures / name).read_text())
        change(data)
        self.write(name, data)

    def saas_charging(self, charging):
        """The SaaS's latest revision, with PLATFORM_INVOICING_ENABLED=<charging>."""
        self.fixture("erplora-prod-saas", one("saas", "saas:live", environment=[
            {"name": "PLATFORM_INVOICING_ENABLED", "value": charging}]))

    def environ(self, unset, env):
        environ = {key: value for key, value in os.environ.items() if key not in NOT_INHERITED}
        environ.update(PATH=f"{self.work / 'bin'}:{os.environ['PATH']}", AWS_REGION="eu-south-2",
                       REGISTRY="reg.example", IMAGE_TAG="abc123", ENVIRONMENT="prod", FIXTURES=str(self.fixtures),
                       CALLS_LOG=str(self.work / "calls.log"), REGISTERED_LOG=str(self.work / "registered.log"),
                       SLEEP_LOG=str(self.work / "sleep.log"), GIT_LOG=str(self.work / "git.log"),
                       APP_ENV_PUT=str(self.work / "app-env-put.json"), AWS_CONFIG_FILE=os.devnull,
                       AWS_SHARED_CREDENTIALS_FILE=os.devnull)
        environ.update(env)
        for name in unset:
            environ.pop(name, None)
        return environ

    def deploy(self, *unset, apart=False, **env):
        """Deploys abc123 to prod with the fakes; <env> overrides the environment and <unset> takes variables out of
        it. stdout and stderr land together in self.out, or apart in self.stdout and self.stderr. The logs and the
        fake's counters start empty."""
        for log in ("calls.log", "registered.log", "sleep.log", "git.log"):
            (self.work / log).write_text("")
        for leftover in (*self.work.glob("polls.*"), self.work / "app-env-put.json"):
            leftover.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, "-c", BOOT, str(SCRIPT)], env=self.environ(unset, env),
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE if apart else subprocess.STDOUT,
                              timeout=120, check=False)
        self.stdout, self.stderr = done.stdout, done.stderr
        self.out = done.stdout.decode("utf-8", "replace")
        self.status = done.returncode
        return done.returncode

    def calls(self):
        return (self.work / "calls.log").read_text(errors="replace").splitlines()

    def lines(self, pattern):
        return [n for n, call in enumerate(self.calls(), 1) if re.search(pattern, call)]

    def line_of(self, pattern):
        return self.lines(pattern)[0]

    def last_line_of(self, pattern):
        return self.lines(pattern)[-1]

    def called(self, pattern):
        return bool(self.lines(pattern))

    def pauses(self):
        return (self.work / "sleep.log").read_text().split()

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

    def recorded_settings(self):
        return json.loads((self.work / "app-env-put.json").read_text())

    def clusters_named(self):
        """The clusters the cluster-scoped ECS calls named, without repeats ("-" for one without --cluster)."""
        named = set()
        for call in self.calls():
            if CLUSTER_SCOPED.search(call):
                words = call.split()
                named.add(words[words.index("--cluster") + 1] if "--cluster" in words[:-1] else "-")
        return named

    def assertNothingRegistered(self, error=None):
        """The deploy failed, registered and ran nothing and recorded no settings; <error>, when given, is a pattern its
        ::error:: line matches."""
        self.assertNotEqual(0, self.status)
        self.assertEqual({}, self.registered())
        self.assertFalse(self.called("register-task-definition|run-task|update-service|put-parameter"))
        self.assertFalse((self.work / "app-env-put.json").exists())
        if error is not None:
            self.assertRegex(self.out, f"::error::{error}")

    def assertFailsBeforeAnyCall(self, *names):
        self.assertNotEqual(0, self.status)
        self.assertEqual([], self.calls())
        for name in names:
            self.assertIn(name, self.out)
