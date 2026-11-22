"""Tests of scripts/ecs_rollback.py: once the services are stable, each one's PRIMARY deployment is polled until it is
the previous revision, COMPLETED, and nothing is recorded until then.

services-stable can return while a PRIMARY deployment is still IN_PROGRESS: ECS marks it COMPLETED once the old tasks
have drained from the ALB, seconds to a minute later.
"""

from ecs_rollback_doubles import TD, RollbackCase

CHANGED = "put-parameter"


class RolloutTest(RollbackCase):
    def assertPutBack(self, service, state="COMPLETED"):
        """The error of a service the circuit breaker put back on revision 12."""
        self.assertIn(f"::error::{service} runs {TD}/erplora-prod-{service}:12 ({state}), not {TD}/erplora-prod-{service}"
                      ":10; rolled back by the circuit breaker? See the service events\n", self.out)

    def test_in_progress_then_completed_succeeds_after_one_pause(self):
        self.assertEqual(0, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual((2, 2), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual(["15"], self.pauses())
        self.assertGreater(self.line_of(CHANGED), self.last_line_of("describe-services"))

    def test_poll_seconds_sets_the_pause(self):
        self.assertEqual(0, self.rollback(POLL_SECONDS="5", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(["5"], self.pauses())

    def test_only_the_services_still_in_progress_are_read_again(self):
        self.assertEqual(0, self.rollback(FAKE_ROLLOUT_STATES_OF='{"hub": "IN_PROGRESS IN_PROGRESS COMPLETED"}'))
        self.assertEqual((3, 1), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual(["15", "15"], self.pauses())

    def test_a_failed_rollout_fails_at_once_without_a_pause_and_records_nothing(self):
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="FAILED"))
        self.assertEqual((1, 1), (self.reads_of("hub"), self.reads_of("worker")))
        self.assertEqual([], self.pauses())
        self.assertFalse(self.called(CHANGED))
        self.assertIn(f"::error::hub runs {TD}/erplora-prod-hub:10 (FAILED), not {TD}/erplora-prod-hub:10; rolled back "
                      "by the circuit breaker? See the service events\n", self.out)
        self.assertNotIn("services stable", self.out)

    def test_a_rollout_that_turns_failed_fails_on_that_read(self):
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS FAILED"))
        self.assertEqual(2, self.reads_of("hub"))
        self.assertEqual(["15"], self.pauses())
        self.assertFalse(self.called(CHANGED))

    def test_a_service_the_circuit_breaker_puts_back_fails_at_once(self):
        self.assertEqual(1, self.rollback(FAKE_CIRCUIT_BREAKER="worker"))
        self.assertEqual(1, self.reads_of("worker"))
        self.assertEqual([], self.pauses())
        self.assertPutBack("worker")
        self.assertFalse(self.called(CHANGED))

    def test_a_rollout_in_progress_the_circuit_breaker_puts_back_fails_on_that_read(self):
        self.assertEqual(1, self.rollback(FAKE_PRIMARY_REVISIONS="10 12", FAKE_ROLLOUT_STATES="IN_PROGRESS COMPLETED"))
        self.assertEqual(2, self.reads_of("hub"))
        self.assertPutBack("hub")
        self.assertFalse(self.called(CHANGED))

    def test_a_rollout_that_outlasts_30_seconds_reads_at_0_15_and_30_then_fails_naming_each_service(self):
        self.assertEqual(1, self.rollback(ROLLOUT_TIMEOUT_SECONDS="30", FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(3, self.reads_of("hub"))
        self.assertEqual(["15", "15"], self.pauses())
        for service in ("hub", "worker"):
            self.assertIn(f"::error::rollout of {service} did not complete in 30 s; see the service events\n", self.out)
        self.assertFalse(self.called(CHANGED))

    def test_the_rollout_timeout_is_600_seconds_by_default(self):
        self.assertEqual(1, self.rollback(FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(41, self.reads_of("hub"))
        self.assertEqual(["15"] * 40, self.pauses())
        self.assertIn("::error::rollout of hub did not complete in 600 s;", self.out)

    def test_the_timeout_is_said_as_it_was_given(self):
        self.assertEqual(1, self.rollback(ROLLOUT_TIMEOUT_SECONDS="030", FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertIn("::error::rollout of hub did not complete in 030 s;", self.out)
        self.assertEqual(3, self.reads_of("hub"))

    def test_seconds_with_leading_zeros_are_read_in_decimal(self):
        # Bash's arithmetic read them in octal: with 08 the rollback recorded the tag without waiting for the rollout.
        self.assertEqual(0, self.rollback(POLL_SECONDS="08", FAKE_ROLLOUT_STATES="IN_PROGRESS IN_PROGRESS COMPLETED"))
        self.assertEqual(["8", "8"], self.pauses())
        self.assertEqual(3, self.reads_of("hub"))
        self.assertEqual(1, self.rollback(POLL_SECONDS="010", ROLLOUT_TIMEOUT_SECONDS="20",
                                          FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(["10", "10"], self.pauses())

    def test_empty_seconds_take_their_default(self):
        self.assertEqual(1, self.rollback(POLL_SECONDS="", ROLLOUT_TIMEOUT_SECONDS="", FAKE_ROLLOUT_STATES="IN_PROGRESS"))
        self.assertEqual(["15"] * 40, self.pauses())
        self.assertIn("::error::rollout of hub did not complete in 600 s;", self.out)

    def test_a_number_of_seconds_that_is_none_changes_nothing(self):
        for name in ("POLL_SECONDS", "ROLLOUT_TIMEOUT_SECONDS"):
            for value in ("soon", "1.5", "-1", " 1", "1\n", "١"):
                with self.subTest(name=name, value=value):
                    self.assertEqual(1, self.rollback(**{name: value}))
                    self.assertFailsBeforeAnyCall(f"::error::{name} must be a number of seconds, not '{value}'; nothing "
                                                  "was changed\n")
