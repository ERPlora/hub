"""Tests of scripts/ecs_deploy.py: the migration it runs and polls before any service changes, and the rollout it
polls after services-stable until every service's PRIMARY deployment is the new revision, COMPLETED.

FAKE_TASK_STATUSES=STOPPED in the rollout tests: the migration needs no pause, so every pause logged is the rollout's.
"""

from ecs_deploy_doubles import DeployCase


class MigrationTest(DeployCase):
    def test_a_slow_migration_is_polled_until_it_is_stopped_every_15_seconds(self):
        self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="PROVISIONING PENDING RUNNING STOPPED"))
        self.assertEqual(4, len(self.lines("describe-tasks .*lastStatus")))
        self.assertEqual(["15", "15", "15"], self.pauses())

    def test_poll_seconds_sets_the_pause(self):
        self.assertEqual(0, self.deploy(POLL_SECONDS="5", FAKE_TASK_STATUSES="RUNNING STOPPED"))
        self.assertEqual(["5"], self.pauses())

    def test_empty_seconds_take_their_default(self):
        self.assertEqual(1, self.deploy(POLL_SECONDS="", MIGRATE_TIMEOUT_SECONDS="", ROLLOUT_TIMEOUT_SECONDS="",
                                        FAKE_TASK_STATUSES="RUNNING STOPPED", FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(["15"] * 41, self.pauses())
        self.assertIn("::error::rollout of hub did not complete in 600 s;", self.out)

    def test_a_timeout_of_0_fails_on_a_migration_that_is_not_stopped_and_leaves_it_running(self):
        self.assertEqual(1, self.deploy(MIGRATE_TIMEOUT_SECONDS="0", apart=True))
        self.assertFalse(self.called("update-service|put-parameter|stop-task"))
        self.assertEqual(b"::error::hub-migrate is still RUNNING after 0s; it was left running (arn:task/erplora-prod/"
                         b"migrate1) and no service changed; logs in /ecs/erplora-prod-hub-migrate\n", self.stderr)

    def test_a_timeout_of_30_seconds_polls_at_0_15_and_30_then_fails(self):
        self.assertEqual(1, self.deploy(MIGRATE_TIMEOUT_SECONDS="30", FAKE_TASK_STATUSES="RUNNING"))
        self.assertEqual(3, len(self.lines("describe-tasks .*lastStatus")))
        self.assertEqual(["15", "15"], self.pauses())
        self.assertFalse(self.called("update-service"))

    def test_the_migration_s_clock_counts_poll_seconds(self):
        self.assertEqual(1, self.deploy(POLL_SECONDS="5", MIGRATE_TIMEOUT_SECONDS="10", FAKE_TASK_STATUSES="RUNNING"))
        self.assertEqual(3, len(self.lines("describe-tasks .*lastStatus")))
        self.assertEqual(["5", "5"], self.pauses())

    def test_the_timeout_is_said_as_it_was_given(self):
        self.assertEqual(1, self.deploy(MIGRATE_TIMEOUT_SECONDS="030", FAKE_TASK_STATUSES="RUNNING"))
        self.assertIn("::error::hub-migrate is still RUNNING after 030s;", self.out)
        self.assertEqual(3, len(self.lines("describe-tasks .*lastStatus")))

    def test_a_failed_migration_changes_no_service_and_names_its_code_and_log_group(self):
        for code in ("1", "00", "137"):
            with self.subTest(code):
                self.assertEqual(1, self.deploy(FAKE_MIGRATE_EXIT=code))
                self.assertFalse(self.called("update-service|put-parameter"))
                self.assertIn(f"::error::hub-migrate exited with code {code}; logs in /ecs/erplora-prod-hub-migrate\n",
                              self.out)

    def test_a_migration_that_never_ran_shows_the_stopped_reason(self):
        reason = "CannotPullContainerError: pull image manifest has been retried 1 time(s)"
        self.assertEqual(1, self.deploy(FAKE_MIGRATE_EXIT="None", FAKE_STOPPED_REASON=reason))
        self.assertFalse(self.called("update-service"))
        self.assertIn(f"::error::hub-migrate stopped without running: {reason}\n", self.out)

    def test_a_migration_task_that_cannot_start_shows_the_failures(self):
        self.assertEqual(1, self.deploy(FAKE_RUN_TASK_FAILURE="RESOURCE:ENI"))
        self.assertFalse(self.called("describe-tasks|update-service|put-parameter"))
        failures = '[{"arn":"arn:capacity","reason":"RESOURCE:ENI"}]'
        self.assertIn(f"::error::hub-migrate did not start: {failures}\n", self.out)


class RunTaskAnswerTest(DeployCase):
    """The answer of run-task is read as jq read it: `.tasks[0].taskArn // empty` and `.failures`."""

    def test_an_answer_without_a_task_did_not_start(self):
        for answer, failures in (('{"tasks": [], "failures": []}', "[]"), ('{"tasks": [{}]}', "null"),
                                 ('{"tasks": [{"taskArn": false}]}', "null"), ('{"tasks": [{"taskArn": ""}]}', "null"),
                                 ('{"tasks": [{"taskArn": null}], "failures": {"a": "ñ"}}', '{"a":"ñ"}'),
                                 ('{"tasks": [], "failures": "ñ"}', '"ñ"'),
                                 ("null", "null"), ("", ""), ("  ", "")):
            with self.subTest(answer):
                self.assertEqual(1, self.deploy(FAKE_RUN_TASK_ANSWER=answer))
                self.assertIn(f"::error::hub-migrate did not start: {failures}\n", self.out)
                self.assertFalse(self.called("describe-tasks"))

    def test_a_task_that_is_no_text_is_written_as_jq_writes_it(self):
        for answer, task in (('{"tasks": [{"taskArn": 5}]}', "5"), ('{"tasks": [{"taskArn": true}]}', "true"),
                             ('{"tasks": [{"taskArn": 0}]}', "0"),
                             ('{"tasks": [{"taskArn": {"a": [1]}}]}', '{\n  "a": [\n    1\n  ]\n}'),
                             ('{"tasks": [{"taskArn": "arn:t\\n\\n"}]}', "arn:t")):
            with self.subTest(answer):
                self.assertEqual(0, self.deploy(FAKE_RUN_TASK_ANSWER=answer))
                self.assertIn(f"running hub-migrate: {task}\nupdated hub\n", self.out)

    def test_an_answer_that_cannot_be_read_ends_the_deploy_with_jq_s_code(self):
        for answer in ("not json", "[]", '{"tasks": "s"}', '{"tasks": ["s"]}', '"s"', '{"tasks": {}}'):
            with self.subTest(answer):
                self.assertEqual(5, self.deploy(FAKE_RUN_TASK_ANSWER=answer))
                self.assertIn("ecs_deploy.py: the answer of run-task cannot be read: ", self.out)
                self.assertNotIn("::error::", self.out)
                self.assertFalse(self.called("describe-tasks"))


class RolloutTest(DeployCase):
    def reads_of(self, service):
        return len(self.lines(f"describe-services .*--services {service} .*deployments"))

    def assertRolledBack(self, service="hub"):
        self.assertIn(f"::error::{service} runs arn:td/erplora-prod-{service}:1 (COMPLETED), not "
                      f"arn:td/erplora-prod-{service}:2; rolled back by the circuit breaker? See the service events\n",
                      self.out)

    def test_in_progress_then_completed_succeeds_after_one_pause(self):
        self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual((2, 2), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual(["15"], self.pauses())
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services .*deployments"))

    def test_only_the_services_still_in_progress_are_read_again(self):
        self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="STOPPED",
                                        FAKE_ROLLOUT_STATES_OF='{"worker": "IN_PROGRESS IN_PROGRESS COMPLETED"}'))
        self.assertEqual((1, 3), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual(["15", "15"], self.pauses())

    def test_a_failed_rollout_fails_at_once_without_a_pause_and_records_nothing(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_ROLLOUT_STATES="FAILED"))
        self.assertEqual((1, 1), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual([], self.pauses())
        self.assertFalse(self.called("put-parameter"))
        self.assertIn("::error::hub runs arn:td/erplora-prod-hub:2 (FAILED), not arn:td/erplora-prod-hub:2;", self.out)
        self.assertIn("::error::worker runs arn:td/erplora-prod-worker:2 (FAILED), not", self.out)

    def test_a_rollout_that_turns_failed_fails_on_that_read(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED"))
        self.assertEqual(2, self.reads_of("hub"))
        self.assertEqual(["15"], self.pauses())
        self.assertFalse(self.called("put-parameter"))

    def test_a_service_rolled_back_to_the_old_revision_fails_at_once(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_PRIMARY_REVISIONS="1"))
        self.assertEqual(1, self.reads_of("hub"))
        self.assertEqual([], self.pauses())
        self.assertRolledBack()
        self.assertFalse(self.called("put-parameter"))

    def test_a_rollout_in_progress_the_circuit_breaker_rolls_back_fails_on_that_read(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_PRIMARY_REVISIONS="2 1",
                                        FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(2, self.reads_of("hub"))
        self.assertRolledBack()
        self.assertFalse(self.called("put-parameter"))

    def test_a_rollout_that_outlasts_30_seconds_reads_at_0_15_and_30_then_fails_naming_each_service(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_ROLLOUT_STATES="IN_PROGRESS",
                                        ROLLOUT_TIMEOUT_SECONDS="30", apart=True))
        self.assertEqual(3, self.reads_of("hub"))
        self.assertEqual(["15", "15"], self.pauses())
        self.assertEqual(b"::error::rollout of hub did not complete in 30 s; see the service events\n"
                         b"::error::rollout of worker did not complete in 30 s; see the service events\n", self.stderr)
        self.assertFalse(self.called("put-parameter"))

    def test_the_rollout_timeout_is_600_seconds_by_default(self):
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(41, self.reads_of("hub"))
        self.assertEqual(40, len(self.pauses()))
        self.assertIn("::error::rollout of hub did not complete in 600 s", self.out)

    def test_the_primary_deployment_is_split_as_bash_s_read_splits_it(self):
        """The answer for hub; worker's rollout completes. The first line only: the task definition is its first word
        and the state the rest, without the blanks around them."""
        self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="STOPPED",
                                        FAKE_PRIMARY_ANSWER=" \tarn:td/erplora-prod-hub:2 \t COMPLETED \t\nx y"))
        for answer, said in (("arn:td/erplora-prod-hub:1  IN  PROGRESS ", "arn:td/erplora-prod-hub:1 (IN  PROGRESS)"),
                             ("None", "None ()"), ("", " ()"), ("\narn:td/erplora-prod-hub:2\tCOMPLETED", " ()")):
            with self.subTest(answer):
                self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_PRIMARY_ANSWER=answer))
                self.assertIn(f"::error::hub runs {said}, not arn:td/erplora-prod-hub:2; rolled back", self.out)
        self.assertEqual(1, self.deploy(FAKE_TASK_STATUSES="STOPPED", FAKE_PRIMARY_ANSWER="arn:td/erplora-prod-hub:2",
                                        ROLLOUT_TIMEOUT_SECONDS="0"))
        self.assertIn("::error::rollout of hub did not complete in 0 s; see the service events\n", self.out)
        self.assertNotIn("rollout of worker", self.out)
