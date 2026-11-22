"""Tests of scripts/ecs_rollback.py: a previous revision that is not of the environment rolled back is refused before
any service moves.

The deploy roles can register any family (ECS takes no resource there), so a revision of the family may have come from
the other environment's role. It is of the environment when it carries the tag Environment=<environment> and the task
and execution roles erplora-<environment>-*, the same guard as the deploy's (test_ecs_deploy_guards.py).
"""

from ecs_rollback_doubles import TD, RollbackCase

ROLE = "arn:aws:iam::123456789012:role"


class RefusedRevisionTest(RollbackCase):
    def assertRefused(self, revision, environment, carries):
        self.assertChangedNothing()
        self.assertIn(f"::error::{TD}/{revision} is no revision of {environment} ({carries}); nothing was changed\n",
                      self.out)

    def test_prod_refuses_a_previous_revision_tagged_pre_naming_what_it_carries(self):
        self.revision("erplora-prod-worker:10", environment="pre")
        self.assertEqual(1, self.rollback())
        self.assertRefused("erplora-prod-worker:10", "prod", f"Environment=pre, task role {ROLE}/erplora-prod-worker-task, "
                                                             f"execution role {ROLE}/erplora-prod-worker-execution")
        self.assertTrue(self.called("describe-task-definition --task-definition .*erplora-prod-hub:10 "))

    def test_prod_refuses_a_previous_revision_without_the_environment_tag(self):
        self.revision("erplora-prod-hub:10", environment="")
        self.rollback()
        self.assertRefused("erplora-prod-hub:10", "prod", f"Environment=none, task role {ROLE}/erplora-prod-hub-task, "
                                                          f"execution role {ROLE}/erplora-prod-hub-execution")
        self.assertFalse(self.called("erplora-prod-worker"))

    def test_pre_refuses_a_previous_revision_with_prod_roles(self):
        role = f"{ROLE}/erplora-prod-worker-task"
        self.revision("erplora-pre-worker:5", task_role=role, execution_role=role)
        self.rollback(ENVIRONMENT="pre")
        self.assertRefused("erplora-pre-worker:5", "pre", f"Environment=pre, task role {role}, execution role {role}")

    def test_pre_refuses_a_previous_revision_with_only_a_prod_execution_role(self):
        self.revision("erplora-pre-hub:5", execution_role=f"{ROLE}/erplora-prod-hub-execution")
        self.rollback(ENVIRONMENT="pre")
        self.assertRefused("erplora-pre-hub:5", "pre", f"Environment=pre, task role {ROLE}/erplora-pre-hub-task, "
                                                       f"execution role {ROLE}/erplora-prod-hub-execution")

    def test_a_revision_without_its_roles_is_refused_and_the_error_says_none(self):
        self.revision("erplora-prod-hub:10")
        self.edit("erplora-prod-hub:10.json", lambda found: [found["taskDefinition"].pop(name) for name in (
            "taskRoleArn", "executionRoleArn")])
        self.rollback()
        self.assertRefused("erplora-prod-hub:10", "prod", "Environment=prod, task role none, execution role none")

    def test_the_environment_is_checked_before_the_image(self):
        self.revision("erplora-prod-hub:10", image="other.example/thing:1", environment="pre")
        self.rollback()
        self.assertNotIn("does not run", self.out)
        self.assertRefused("erplora-prod-hub:10", "prod", f"Environment=pre, task role {ROLE}/erplora-prod-hub-task, "
                                                          f"execution role {ROLE}/erplora-prod-hub-execution")

    def test_an_answer_with_nothing_in_it_is_no_revision_of_the_environment(self):
        for text, carries in (("", ""), (" \n", ""),
                              ("{}", "Environment=none, task role none, execution role none")):
            with self.subTest(text):
                self.answer("erplora-prod-hub:10", text)
                self.assertEqual(1, self.rollback())
                self.assertRefused("erplora-prod-hub:10", "prod", carries)
