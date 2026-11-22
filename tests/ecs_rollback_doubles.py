"""What the tests of scripts/ecs_rollback.py roll back with: the fake aws CLI of ecs_doubles, which keeps each service's
PRIMARY revision as state (update-service moves it), and fixtures for the revisions each family lists and for what each
previous revision runs.

prod's services run revision 12 of their families and pre's revision 7; the previous revision of each family is 10 in
prod and 5 in pre, on its environment's image with the tag tag-<revision>, and runs the settings in force.
"""

from ecs_doubles import APP_ENV, FAKE_AWS_END, FAKE_AWS_START, SCRIPTS, ScriptCase, task_definition

TD = "arn:aws:ecs:eu-south-2:123456789012:task-definition"

FAKE_AWS = FAKE_AWS_START + r'''

def state(name):
    return os.path.join(os.path.dirname(fixtures), "state", name)


def describe_services():
    # A service's PRIMARY deployment: the revision of its state, COMPLETED. After update-service, successive reads
    # answer the next of FAKE_ROLLOUT_STATES (or the service's own in FAKE_ROLLOUT_STATES_OF, as JSON) and, if set, of
    # FAKE_PRIMARY_REVISIONS (revision numbers of the family it runs).
    service = value("--services")
    primary = read(state(f"primary-{service}")).decode()
    status = "COMPLETED"
    if os.path.exists(state(f"moved-{service}")):
        states = env.get("FAKE_ROLLOUT_STATES") or "COMPLETED"
        if "FAKE_ROLLOUT_STATES_OF" in env:
            import json
            states = json.loads(env["FAKE_ROLLOUT_STATES_OF"]).get(service, states)
        status = nth(f"state.{service}", states)
        if env.get("FAKE_PRIMARY_REVISIONS"):
            primary = f"{primary.rsplit(':', 1)[0]}:{nth(f'revision.{service}', env['FAKE_PRIMARY_REVISIONS'])}"
    print(f"{primary}\t{status}")


def list_task_definitions():
    sys.stdout.buffer.write(read(os.path.join(fixtures, f"list-{value('--family-prefix')}")) + b"\n")


def update_service():
    # The circuit breaker of FAKE_CIRCUIT_BREAKER's service puts its old revision back.
    service = value("--service")
    open(state(f"moved-{service}"), "w").close()
    if env.get("FAKE_CIRCUIT_BREAKER") != service:
        with open(state(f"primary-{service}"), "w", encoding="utf-8") as primary:
            primary.write(value("--task-definition"))
    print(f'{{"service": {{"serviceName": "{service}"}}}}')


COMMANDS = {
    "ecs describe-services": describe_services, "ecs list-task-definitions": list_task_definitions,
    "ecs describe-task-definition": describe_task_definition, "ecs update-service": update_service,
    "ssm get-parameter": get_parameter, "ssm put-parameter": put_parameter,
}
''' + FAKE_AWS_END


def arn(revision):
    """The ARN of <revision> (erplora-prod-hub:10), or <revision> itself when it is one already."""
    return revision if revision.startswith("arn:") else f"{TD}/{revision}"


class RollbackCase(ScriptCase):
    """A fresh fake AWS for each test. The family prefix of prod's hub also lists hub-migrate, and hub has a newer
    revision (13) than the one it runs: its previous one is hub:10, not hub-migrate:11."""

    script = SCRIPTS / "ecs_rollback.py"

    def setUp(self):
        super().setUp()
        (self.work / "state").mkdir()
        self.primary = {"hub": arn("erplora-prod-hub:12"), "worker": arn("erplora-prod-worker:12"),
                        "hub-pre": arn("erplora-pre-hub:7"), "worker-pre": arn("erplora-pre-worker:7")}
        self.listed("erplora-prod-hub", "erplora-prod-hub-migrate:14", "erplora-prod-hub-migrate:11",
                    "erplora-prod-hub:13", "erplora-prod-hub:12", "erplora-prod-hub:10", "erplora-prod-hub:9")
        self.listed("erplora-prod-worker", "erplora-prod-worker:12", "erplora-prod-worker:10")
        self.listed("erplora-pre-hub", "erplora-pre-hub-migrate:8", "erplora-pre-hub:7", "erplora-pre-hub:5")
        self.listed("erplora-pre-worker", "erplora-pre-worker:7", "erplora-pre-worker:5")
        for previous in ("erplora-prod-hub:10", "erplora-prod-worker:10", "erplora-pre-hub:5", "erplora-pre-worker:5"):
            self.revision(previous)
        self.install("aws", FAKE_AWS)

    def listed(self, family, *revisions):
        """What list-task-definitions answers for the family prefix <family>: <revisions>, newest first."""
        (self.fixtures / f"list-{family}").write_text("".join(f"{arn(revision)}\t" for revision in revisions))

    def revision(self, revision, image=None, settings=None, containers=None, **rest):
        """What describe-task-definition answers for <revision> (erplora-prod-hub:10): its app container, named after
        its family's short name, runs <image> (by default its environment's, with the tag tag-<number>) and <settings>
        (by default the ones in force), beside a pgbouncer of the same image; <containers> replaces both. <rest> goes
        to task_definition: environment, task_role and execution_role."""
        family, number = revision.rsplit(":", 1)
        environment, name = family.split("-", 2)[1:]
        image = image or f"reg.example/erplora/hub{'' if environment == 'prod' else '-pre'}:tag-{number}"
        settings = APP_ENV[environment][name] if settings is None else settings
        variables = [{"name": "DEBUG", "value": "False"}, *({"name": k, "value": v} for k, v in settings.items())]
        if containers is None:
            containers = [{"name": name, "image": image, "environment": variables},
                          {"name": "pgbouncer", "image": image}]
        self.write(f"{revision}.json", task_definition(family, containers, **rest))

    def answer(self, revision, text):
        """describe-task-definition answers <text> as it is for <revision>."""
        (self.fixtures / f"{revision}.json").write_text(text)

    def rollback(self, *unset, apart=False, **env):
        """Rolls prod back with the fakes and CONFIRM=ROLLBACK; <env> overrides the environment and <unset> takes
        variables out of it. Each service starts on its revision of self.primary."""
        for leftover in (self.work / "state").iterdir():
            leftover.unlink()
        for service, revision in self.primary.items():
            (self.work / "state" / f"primary-{service}").write_text(revision)
        return self.execute(self.environ(unset, env, CONFIRM="ROLLBACK"), apart)

    def reads_of(self, service):
        """How many times the service's PRIMARY deployment was read after the wait."""
        waited = self.lines("^ecs wait services-stable ")
        reads = self.lines(f"^ecs describe-services .*--services {service} ")
        return len([n for n in reads if waited and n > waited[0]])

    def assertChangedNothing(self, error=None):
        """The rollback failed, moved no service and recorded nothing; <error>, when given, is a pattern its ::error::
        line matches."""
        self.assertNotEqual(0, self.status)
        self.assertFalse(self.called("update-service|put-parameter"))
        self.assertFalse((self.work / "app-env-put.json").exists())
        if error is not None:
            self.assertRegex(self.out, f"::error::{error}")
