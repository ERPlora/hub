"""What the tests of scripts/ecs_deploy.py and scripts/ecs_rollback.py share: each script runs as its workflow runs it,
in a process of its own, with a fake aws CLI first on the PATH that records every call and answers from fixtures.

Inside the script's process time.sleep only records the pause, so no test waits for real, and gives up after 500 of
them, so a loop that never times out fails its test instead of hanging. AWS's configuration and credentials point to
/dev/null: nothing here can reach AWS.
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

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
# The ECS calls that act in a cluster.
CLUSTER_SCOPED = re.compile(r"^ecs (describe-services|run-task|describe-tasks|update-service|wait) ")
NOT_INHERITED = ("CLUSTER", "PROJECT", "POLL_SECONDS", "MIGRATE_TIMEOUT_SECONDS", "ROLLOUT_TIMEOUT_SECONDS",
                 "CONFIRM", "CONFIRM_PROTECTED", "AWS_PROFILE", "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                 "AWS_SESSION_TOKEN")

# Runs a script as `python3 <script>` runs it, with its folder first on sys.path.
BOOT = """\
import os, runpy, sys, time

def sleep(seconds):
    with open(os.environ["SLEEP_LOG"], "a", encoding="utf-8") as log:
        log.write(f"{seconds}\\n")
    with open(os.environ["SLEEP_LOG"], encoding="utf-8") as log:
        if len(log.readlines()) > 500:
            sys.exit("fake sleep: more than 500 pauses")

time.sleep = sleep
sys.path[0] = os.path.dirname(os.path.abspath(sys.argv[1]))
runpy.run_path(sys.argv[1], run_name="__main__")
"""

# What every fake aws starts with: it records the call, and answers the calls both scripts make alike. Imports only what
# each answer needs: the fake answers every aws call of every test, and Python starts slowly.
FAKE_AWS_START = r'''
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
    # A family or the last part of an ARN (erplora-prod-hub:10) names its fixture.
    path = os.path.join(fixtures, f"{value('--task-definition').rsplit('/', 1)[-1]}.json")
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
'''

# What every fake aws ends with: its COMMANDS answer, unless the call is the one FAKE_KILLED_ON or FAKE_FAILS_ON names.
FAKE_AWS_END = r'''
command = " ".join(args[:2])
if env.get("FAKE_KILLED_ON") == command:
    os.kill(os.getpid(), 9)
if env.get("FAKE_FAILS_ON") == command:
    refuse(f"An error occurred (AccessDeniedException) when calling {command}")
COMMANDS.get(command, lambda: None)()
'''

# The settings in force of each environment: those deploy/app-env.json of the commit deployed gives, and those the
# previous revisions a rollback goes back to run.
APP_ENV = {
    "prod": {"hub": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"},
             "worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "true"}},
    "pre": {"hub": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "false",
                    "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"},
            "worker": {"PLATFORM_HUB_SLUG": "erplora", "VERIFACTU_PRODUCTION_ENABLED": "false",
                       "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"}},
}


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


class ScriptCase(unittest.TestCase):
    """A fresh work folder for each test, with a bin/ for the fakes and the fixtures they answer from, each
    environment's settings in force and the SaaS's latest revision charging real money. A subclass names its script and
    installs its fake aws."""

    script: Path

    def setUp(self):
        self.work = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.work)
        self.fixtures = self.work / "fixtures"
        for folder in (self.work / "bin", self.fixtures):
            folder.mkdir()
        for environment in ("prod", "pre"):
            self.write(f"erplora_{environment}_hub_app_env.json", APP_ENV[environment])
        self.saas_charging("true")

    def install(self, name, source):
        """Puts a fake <name> first on the PATH: <source> run by this Python."""
        path = self.work / "bin" / name
        path.write_text(f"#!{sys.executable} -IS\n{source}")
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

    def environ(self, unset, env, **own):
        """The script's environment: this test's own, without the settings it must not inherit, plus the fakes' and
        <own>; <env> overrides it and <unset> takes variables out of it."""
        environ = {key: value for key, value in os.environ.items() if key not in NOT_INHERITED}
        environ.update(PATH=f"{self.work / 'bin'}:{os.environ['PATH']}", AWS_REGION="eu-south-2", ENVIRONMENT="prod",
                       FIXTURES=str(self.fixtures), CALLS_LOG=str(self.work / "calls.log"),
                       SLEEP_LOG=str(self.work / "sleep.log"), APP_ENV_PUT=str(self.work / "app-env-put.json"),
                       AWS_CONFIG_FILE=os.devnull, AWS_SHARED_CREDENTIALS_FILE=os.devnull, **own)
        environ.update(env)
        for name in unset:
            environ.pop(name, None)
        return environ

    def execute(self, environ, apart):
        """Runs the script: stdout and stderr land together in self.out, or apart in self.stdout and self.stderr. The
        calls, the pauses and the fake's counters start empty."""
        for log in ("calls.log", "sleep.log"):
            (self.work / log).write_text("")
        for leftover in (*self.work.glob("polls.*"), self.work / "app-env-put.json"):
            leftover.unlink(missing_ok=True)
        done = subprocess.run([sys.executable, "-c", BOOT, str(self.script)], env=environ, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE if apart else subprocess.STDOUT, timeout=120, check=False)
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

    def assertFailsBeforeAnyCall(self, *names):
        self.assertNotEqual(0, self.status)
        self.assertEqual([], self.calls())
        for name in names:
            self.assertIn(name, self.out)
