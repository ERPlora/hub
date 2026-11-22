"""Tests of scripts/ecs_common.py, what the hub's deploy (ecs_deploy.py) and rollback (ecs_rollback.py) share.

How each script uses these pieces with a fake aws CLI is tested by test_ecs_deploy*.py and test_ecs_rollback*.py.
"""

import importlib.util
import io
import signal
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "ecs_common.py"
spec = importlib.util.spec_from_file_location("ecs_common", SCRIPT)
ecs_common = importlib.util.module_from_spec(spec)
# A dataclass looks its module up in sys.modules.
sys.modules["ecs_common"] = ecs_common
spec.loader.exec_module(ecs_common)

ROLE = "arn:aws:iam::123456789012:role"


def release(environment="prod", **seconds):
    return ecs_common.Release(region="eu-south-2", environment=environment, cluster=f"erplora-{environment}",
                              seconds=seconds)


def revision(environment="prod", task=None, execution=None, tags=None):
    return {"taskDefinition": {"taskRoleArn": task or f"{ROLE}/erplora-{environment}-hub-task",
                               "executionRoleArn": execution or f"{ROLE}/erplora-{environment}-hub-execution"},
            "tags": [{"key": "Environment", "value": environment}] if tags is None else tags}


class StopTest(unittest.TestCase):
    def stopped(self, work):
        """The Stop <work> raises and what it says on stderr."""
        said = io.StringIO()
        with redirect_stderr(said), self.assertRaises(ecs_common.Stop) as stop:
            work()
        return stop.exception.code, said.getvalue()

    def test_a_refusal_says_its_error_and_stops_with_1(self):
        def refuse():
            raise ecs_common.refusal("no")
        self.assertEqual((1, "::error::no\n"), self.stopped(refuse))

    def test_what_cannot_be_read_is_said_by_the_script_and_stops_with_jq_s_code(self):
        def unreadable():
            raise ecs_common.unreadable("the answer", ValueError("why"))
        with mock.patch.object(sys, "argv", ["scripts/ecs_rollback.py"]):
            self.assertEqual((5, "ecs_rollback.py: the answer cannot be read: why\n"), self.stopped(unreadable))

    def test_a_command_writes_back_without_its_trailing_newlines(self):
        self.assertEqual("a\n b", ecs_common.run([sys.executable, "-c", "print('a\\n b\\n\\n')"]))

    def test_a_command_that_fails_stops_with_its_code(self):
        self.assertEqual(3, self.stopped(lambda: ecs_common.run([sys.executable, "-c", "raise SystemExit(3)"]))[0])

    def test_a_command_killed_by_a_signal_stops_with_128_plus_the_signal(self):
        kill = f"import os; os.kill(os.getpid(), {int(signal.SIGKILL)})"
        self.assertEqual(137, self.stopped(lambda: ecs_common.run([sys.executable, "-c", kill]))[0])

    def test_a_command_that_does_not_exist_stops_with_127_named_by_the_script(self):
        with mock.patch.object(sys, "argv", ["scripts/ecs_deploy.py"]):
            stopped = self.stopped(lambda: ecs_common.run(["/nowhere/aws"]))
        self.assertEqual((127, "ecs_deploy.py: /nowhere/aws: command not found\n"), stopped)

    def test_the_environment_is_prod_or_pre_and_its_refusal_ends_with_the_consequence(self):
        self.assertEqual("pre", ecs_common.environment_given({"ENVIRONMENT": "pre"}, ""))
        stopped = self.stopped(lambda: ecs_common.environment_given({}, "; nothing was changed"))
        self.assertEqual((1, "::error::ENVIRONMENT must be prod or pre, not ''; nothing was changed\n"), stopped)

    def test_the_seconds_are_digits_as_given_or_their_default(self):
        defaults = {"POLL_SECONDS": "15", "ROLLOUT_TIMEOUT_SECONDS": "600"}
        given = ecs_common.seconds_given({"POLL_SECONDS": "007", "ROLLOUT_TIMEOUT_SECONDS": ""}, defaults, "")
        self.assertEqual({"POLL_SECONDS": "007", "ROLLOUT_TIMEOUT_SECONDS": "600"}, given)
        stopped = self.stopped(lambda: ecs_common.seconds_given({"ROLLOUT_TIMEOUT_SECONDS": "1s"}, defaults, "; x"))
        self.assertEqual((1, "::error::ROLLOUT_TIMEOUT_SECONDS must be a number of seconds, not '1s'; x\n"), stopped)

    def test_the_work_ends_with_the_code_it_stops_with_or_0(self):
        def stop():
            raise ecs_common.Stop(254)
        # The streams are reconfigured, as only a text stream over bytes can be.
        with redirect_stdout(io.TextIOWrapper(io.BytesIO())), redirect_stderr(io.TextIOWrapper(io.BytesIO())):
            self.assertEqual((254, 0), (ecs_common.main(stop), ecs_common.main(lambda: None)))


class ReadTest(unittest.TestCase):
    def test_a_release_names_its_environment(self):
        prod, pre = release(POLL_SECONDS="010"), release("pre")
        self.assertEqual(("", "erplora-prod", 10), (prod.suffix, prod.prefix, prod.seconds_of("POLL_SECONDS")))
        self.assertEqual(("-pre", "erplora-pre"), (pre.suffix, pre.prefix))

    def test_a_value_is_read_and_written_as_jq_reads_and_writes_it(self):
        self.assertEqual([], ecs_common.values(" \n"))
        self.assertEqual([None, 1, None], [ecs_common.key(None, "a"), ecs_common.key({"a": 1}, "a"),
                                           ecs_common.key({}, "a")])
        self.assertRaises(TypeError, ecs_common.key, [], "a")
        self.assertEqual([[1], [2]], [ecs_common.each({"a": 1}), ecs_common.each([2])])
        self.assertEqual([], ecs_common.tags({"tags": "s"}))
        self.assertEqual(["d", "d", 0], [ecs_common.otherwise(None, "d"), ecs_common.otherwise(False, "d"),
                                         ecs_common.otherwise(0, "d")])
        self.assertEqual(['{"ñ":[1]}', "s"], [ecs_common.text({"ñ": [1]}), ecs_common.text("s")])
        self.assertEqual(['{\n  "ñ": [\n    1\n  ]\n}', "s"],
                         [ecs_common.written({"ñ": [1]}), ecs_common.written("s\n")])

    def test_a_revision_of_its_environment_has_its_tag_and_both_roles(self):
        self.assertTrue(ecs_common.of_its_environment([revision()], release()))
        for found in ([], [revision(tags=[])], [revision(tags=[{"key": "Environment", "value": "pre"}])],
                      [revision(task=f"{ROLE}/erplora-pre-hub-task")],
                      [revision(execution=f"x{ROLE}/erplora-prod-hub-execution")], [[]]):
            with self.subTest(found):
                self.assertFalse(ecs_common.of_its_environment(found, release()))

    def test_another_environment_s_revision_is_refused_naming_what_it_carries(self):
        found = [revision("pre")]
        said = io.StringIO()
        with redirect_stderr(said), self.assertRaises(ecs_common.Stop):
            ecs_common.refuse_another_environment(found, "erplora-prod-hub", release(), "; nothing was changed")
        self.assertEqual(f"::error::erplora-prod-hub is no revision of prod (Environment=pre, task role "
                         f"{ROLE}/erplora-pre-hub-task, execution role {ROLE}/erplora-pre-hub-execution); nothing was "
                         "changed\n",
                         said.getvalue())
        self.assertIsNone(ecs_common.refuse_another_environment([revision()], "erplora-prod-hub", release(), ""))
