"""Tests of scripts/ecs_rollback.py: the hub's services of one environment go back to the ACTIVE revision right before
the one each PRIMARY deployment runs.

The rollback runs as the workflow runs it, with a fake aws CLI first on the PATH (ecs_rollback_doubles). The revisions
it refuses for being of another environment are tested in test_ecs_rollback_guards.py, the settings they run in
test_ecs_rollback_settings.py and its waits in test_ecs_rollback_waits.py.
"""

import json

from ecs_rollback_doubles import TD, RollbackCase, arn

REGION = "--region eu-south-2"
PRIMARY = "--query services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState] --output text"
SETTINGS = ('{"hub":{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"},'
            '"worker":{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"}}')


def prod_calls():
    """Every call of a prod rollback, in order: each service's revision, its family's ACTIVE revisions and the previous
    one, the settings in force and the SaaS's revision are read before any service moves, and the settings and the tag
    are recorded last."""
    cluster = "--cluster erplora-prod"
    reads = []
    for name in ("hub", "worker"):
        reads += [f"ecs describe-services {cluster} --services {name} {REGION} {PRIMARY}",
                  f"ecs list-task-definitions --family-prefix erplora-prod-{name} --status ACTIVE --sort DESC {REGION} "
                  "--query taskDefinitionArns --output text",
                  f"ecs describe-task-definition --task-definition {TD}/erplora-prod-{name}:10 --include TAGS {REGION} "
                  "--output json"]
    return [
        *reads,
        f"ssm get-parameter --name /erplora/prod/hub/app_env --query Parameter.Value --output text {REGION}",
        f"ecs describe-task-definition --task-definition erplora-prod-saas {REGION} --output json",
        f"ecs update-service {cluster} --service hub --task-definition {TD}/erplora-prod-hub:10 {REGION}",
        f"ecs update-service {cluster} --service worker --task-definition {TD}/erplora-prod-worker:10 {REGION}",
        f"ecs wait services-stable {cluster} {REGION} --services hub worker",
        f"ecs describe-services {cluster} --services hub {REGION} {PRIMARY}",
        f"ecs describe-services {cluster} --services worker {REGION} {PRIMARY}",
        f"ssm put-parameter --name /erplora/prod/hub/app_env --value {SETTINGS} --type String --overwrite {REGION}",
        f"ssm put-parameter --name /erplora/prod/hub/image_tag --value tag-10 --type String --overwrite {REGION}",
    ]


class ProdRollbackTest(RollbackCase):
    def test_the_calls_are_exactly_these(self):
        self.assertEqual(0, self.rollback())
        self.assertEqual(prod_calls(), self.calls())

    def test_what_the_rollback_says_and_where(self):
        self.assertEqual(0, self.rollback(apart=True))
        self.assertEqual(
            b"::warning::rolling back hub worker to their previous revisions; migrations are not undone\n"
            + f"rolling back hub to {TD}/erplora-prod-hub:10\nrolling back worker to {TD}/erplora-prod-worker:10\n"
            .encode() + b"services stable on the previous revisions\n"
            b"recorded its settings and tag-10 in /erplora/prod/hub/app_env and image_tag\n", self.stdout)
        self.assertEqual(b"", self.stderr)

    def test_a_service_goes_back_to_the_highest_active_revision_of_its_own_family_below_the_one_it_runs(self):
        cases = {
            # Not in order; the highest below 12 is 11.
            "erplora-prod-hub:11": ["erplora-prod-hub:9", "erplora-prod-hub:11", "erplora-prod-hub:10"],
            # The same family of another region is another family.
            "erplora-prod-hub:9": [TD.replace("eu-south-2", "eu-west-1") + "/erplora-prod-hub:11",
                                   "erplora-prod-hub:9"],
            # A revision that is no number is none of them.
            "erplora-prod-hub:8": ["erplora-prod-hub:latest", "erplora-prod-hub:8"],
        }
        for previous, listed in cases.items():
            with self.subTest(previous):
                self.revision(previous, image="reg.example/erplora/hub:tag-10")
                self.listed("erplora-prod-hub", "erplora-prod-hub:12", *listed)
                self.assertEqual(0, self.rollback())
                self.assertTrue(self.called(f"update-service .*--service hub --task-definition {arn(previous)} "))

    def test_only_the_first_line_of_the_answer_lists_revisions(self):
        self.revision("erplora-prod-hub:9", image="reg.example/erplora/hub:tag-10")
        listed = f"{arn('erplora-prod-hub:12')}\t{arn('erplora-prod-hub:9')}\n{arn('erplora-prod-hub:11')}"
        (self.fixtures / "list-erplora-prod-hub").write_text(listed)
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called(f"update-service .*--service hub --task-definition {arn('erplora-prod-hub:9')} "))

    def test_revisions_are_compared_as_numbers(self):
        self.primary["hub"] = arn("erplora-prod-hub:100")
        self.listed("erplora-prod-hub", "erplora-prod-hub:100", "erplora-prod-hub:99", "erplora-prod-hub:20")
        self.revision("erplora-prod-hub:99", image="reg.example/erplora/hub:tag-10")
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called(f"update-service .*--service hub --task-definition {arn('erplora-prod-hub:99')} "))

    def test_without_an_earlier_active_revision_nothing_changes(self):
        self.listed("erplora-prod-hub", "erplora-prod-hub-migrate:11", "erplora-prod-hub:13", "erplora-prod-hub:12")
        self.rollback()
        self.assertChangedNothing()
        self.assertIn(f"::error::hub runs {TD}/erplora-prod-hub:12 and erplora-prod-hub has no earlier ACTIVE "
                      "revision; nothing was changed\n", self.out)
        self.assertFalse(self.called("erplora-prod-worker"))

    def test_a_service_that_runs_no_revision_of_its_family_changes_nothing(self):
        running_now = dict(self.primary)
        for service, running in (("worker", "None"), ("hub", arn("erplora-prod-hub-migrate:11")),
                                 ("hub", arn("old-erplora-prod-hub:12")), ("hub", arn("erplora-prod-hub:12x")),
                                 ("hub", arn("erplora-prod-hub:"))):
            with self.subTest(running):
                self.primary = {**running_now, service: running}
                self.rollback()
                self.assertChangedNothing()
                self.assertIn(f"::error::{service} has no PRIMARY deployment of erplora-prod-{service} "
                              f"(got '{running}'); nothing was changed\n", self.out)

    def test_previous_revisions_on_different_tags_change_nothing(self):
        self.revision("erplora-prod-worker:10", image="reg.example/erplora/hub:tag-9")
        self.rollback()
        self.assertChangedNothing()
        self.assertIn("::error::the previous revisions run different tags (tag-10 tag-9); nothing was changed\n",
                      self.out)
        self.assertFalse(self.called("get-parameter|erplora-prod-saas"))

    def test_a_previous_revision_without_the_hub_image_changes_nothing(self):
        for image in ("other.example/thing:1", "reg.example/erplora/hub-pre:tag-10", "reg.example/xerplora/hub:tag-10",
                      "reg.example/erplora/hubx:tag-10", "reg.example/erplora/hub"):
            with self.subTest(image):
                self.revision("erplora-prod-hub:10", image=image)
                self.rollback()
                self.assertChangedNothing()
                self.assertIn(f"::error::{TD}/erplora-prod-hub:10 does not run an erplora/hub image ({image}); nothing "
                              "was changed\n", self.out)

    def test_an_image_that_names_the_hub_repository_after_another_registry_goes_back_with_its_tag(self):
        # Without a registry to compare, the image only has to be of the environment's repository.
        self.revision("erplora-prod-hub:10", image="mirror.example/reg.example/erplora/hub:tag-10")
        self.revision("erplora-prod-worker:10", image="reg.example:5000/erplora/hub:tag-10")
        self.assertEqual(0, self.rollback())
        self.assertTrue(self.called("put-parameter --name /erplora/prod/hub/image_tag --value tag-10 "))

    def test_the_image_is_the_first_of_the_container_named_after_the_family(self):
        def around(found):
            containers = found["taskDefinition"]["containerDefinitions"]
            found["taskDefinition"]["containerDefinitions"] = [
                {"name": "pgbouncer", "image": "other.example/pgbouncer:1"}, *containers,
                {"name": "hub", "image": "other.example/hub:2"}]
        self.edit("erplora-prod-hub:10.json", around)
        self.assertEqual(0, self.rollback())
        # Containers listed as an object are read as their values, as jq reads them.
        self.revision("erplora-prod-hub:10", containers={"app": {"name": "hub", "image": "other.example/hub:3"}})
        self.rollback()
        self.assertChangedNothing(f"{TD}/erplora-prod-hub:10 does not run an erplora/hub image "
                                  r"\(other.example/hub:3\); ")

    def test_an_app_container_without_an_image_is_said_as_none(self):
        for containers in ([{"name": "pgbouncer", "image": "reg.example/erplora/hub:tag-10"}],
                           [{"name": "hub", "image": None}], [{"name": "hub", "image": False}], [{"name": "hub"}],
                           [None, {"name": "hub"}]):
            with self.subTest(containers):
                self.revision("erplora-prod-hub:10", containers=containers)
                self.rollback()
                self.assertChangedNothing(f"{TD}/erplora-prod-hub:10 does not run an erplora/hub image \\(none\\); ")

    def test_an_image_that_is_no_text_is_written_as_jq_writes_it(self):
        self.revision("erplora-prod-hub:10", containers=[{"name": "hub", "image": {"a": [1, "ñ"]}}])
        self.rollback()
        self.assertChangedNothing()
        self.assertIn(f"image ({json.dumps({'a': [1, 'ñ']}, indent=2, ensure_ascii=False)}); nothing", self.out)


class PreRollbackTest(RollbackCase):
    def test_pre_rolls_back_hub_pre_and_worker_pre_to_its_own_previous_revisions(self):
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertEqual({"erplora-pre"}, self.clusters_named())
        self.assertEqual(["erplora-pre-hub", "erplora-pre-worker"],
                         [call.split()[3] for call in self.calls() if call.startswith("ecs list-task-definitions ")])
        self.assertEqual([f"ecs update-service --cluster erplora-pre --service {name}-pre --task-definition "
                          f"{TD}/erplora-pre-{name}:5 {REGION}" for name in ("hub", "worker")],
                         [call for call in self.calls() if "update-service" in call])
        self.assertTrue(self.called(f"^ecs wait services-stable --cluster erplora-pre {REGION} --services hub-pre "
                                    "worker-pre$"))
        self.assertTrue(self.called("^ssm put-parameter --name /erplora/pre/hub/image_tag --value tag-5 "))
        self.assertTrue(self.called("^ssm put-parameter --name /erplora/pre/hub/app_env "))
        self.assertIn("::warning::rolling back hub-pre worker-pre to their previous revisions;", self.out)
        self.assertIn("recorded its settings and tag-5 in /erplora/pre/hub/app_env and image_tag\n", self.out)

    def test_pre_never_names_a_prod_cluster_family_service_or_parameter(self):
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertFalse(self.called(r"erplora-prod|/erplora/prod/|--services? (hub|worker)( |$)|desired-count"))

    def test_prod_touches_nothing_of_pre(self):
        self.assertEqual(0, self.rollback())
        self.assertFalse(self.called(r"erplora-pre|-pre |/erplora/pre/"))

    def test_pre_refuses_a_previous_revision_on_prod_s_repository(self):
        self.revision("erplora-pre-hub:5", image="reg.example/erplora/hub:tag-5")
        self.rollback(ENVIRONMENT="pre")
        self.assertChangedNothing(f"{TD}/erplora-pre-hub:5 does not run an erplora/hub-pre image "
                                  r"\(reg.example/erplora/hub:tag-5\); nothing was changed")

    def test_a_pre_service_on_a_prod_revision_changes_nothing(self):
        self.primary["hub-pre"] = arn("erplora-prod-hub:12")
        self.rollback(ENVIRONMENT="pre")
        self.assertChangedNothing("hub-pre has no PRIMARY deployment of erplora-pre-hub "
                                  f"\\(got '{TD}/erplora-prod-hub:12'\\)")


class ConfiguredTest(RollbackCase):
    def test_without_the_exact_confirmation_nothing_is_called(self):
        for confirm in ("", "rollback", "ROLLBACK ", " ROLLBACK"):
            with self.subTest(confirm):
                self.assertEqual(1, self.rollback(CONFIRM=confirm))
                self.assertFailsBeforeAnyCall(f"::error::CONFIRM must be exactly ROLLBACK, not '{confirm}'; nothing "
                                              "was changed\n")
        self.assertEqual(1, self.rollback("CONFIRM"))
        self.assertFailsBeforeAnyCall("::error::CONFIRM must be exactly ROLLBACK, not ''; nothing was changed\n")

    def test_without_aws_region_nothing_is_called(self):
        self.assertEqual(1, self.rollback("AWS_REGION"))
        self.assertEqual("::error::AWS_REGION is required\n", self.out)
        self.assertEqual(1, self.rollback(AWS_REGION=""))
        self.assertFailsBeforeAnyCall("::error::AWS_REGION is required\n")

    def test_an_environment_other_than_prod_or_pre_changes_nothing(self):
        for environment in ("", "dev", "PROD", " pre", "prod "):
            with self.subTest(environment):
                self.assertEqual(1, self.rollback(ENVIRONMENT=environment))
                self.assertFailsBeforeAnyCall(f"::error::ENVIRONMENT must be prod or pre, not '{environment}'; nothing "
                                              "was changed\n")
        self.assertEqual(1, self.rollback("ENVIRONMENT"))
        self.assertFailsBeforeAnyCall("::error::ENVIRONMENT must be prod or pre, not ''; nothing was changed\n")

    def test_the_first_check_that_fails_is_the_one_said(self):
        self.rollback("CONFIRM", "AWS_REGION")
        self.assertEqual("::error::CONFIRM must be exactly ROLLBACK, not ''; nothing was changed\n", self.out)
        self.rollback(AWS_REGION="", ENVIRONMENT="dev")
        self.assertEqual("::error::AWS_REGION is required\n", self.out)
        self.rollback(ENVIRONMENT="dev", POLL_SECONDS="soon")
        self.assertEqual("::error::ENVIRONMENT must be prod or pre, not 'dev'; nothing was changed\n", self.out)

    def test_an_explicit_cluster_is_used_in_every_cluster_scoped_call(self):
        for environment in ("prod", "pre"):
            with self.subTest(environment):
                self.assertEqual(0, self.rollback(ENVIRONMENT=environment, CLUSTER="custom-cluster"))
                self.assertEqual({"custom-cluster"}, self.clusters_named())

    def test_an_empty_cluster_is_the_environment_s_own(self):
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre", CLUSTER=""))
        self.assertEqual({"erplora-pre"}, self.clusters_named())

    def test_what_it_is_given_is_said_as_the_bytes_it_was_given(self):
        self.assertEqual(1, self.rollback(CONFIRM="ROLL\udcffBACK"))
        self.assertEqual(b"::error::CONFIRM must be exactly ROLLBACK, not 'ROLL\xffBACK'; nothing was changed\n",
                         self.stdout)


class FailingCallTest(RollbackCase):
    def test_an_aws_call_that_fails_ends_the_rollback_with_its_exit_code(self):
        for command, after in (("ecs describe-services", "list-task-definitions"), ("ecs list-task-definitions",
                               "describe-task-definition"), ("ecs describe-task-definition", "get-parameter"),
                               ("ecs update-service", "wait|put-parameter")):
            with self.subTest(command):
                self.assertEqual(254, self.rollback(FAKE_FAILS_ON=command))
                self.assertEqual(1, len(self.lines(f"^{command} ")))
                self.assertFalse(self.called(after))
                self.assertIn(f"An error occurred (AccessDeniedException) when calling {command}\n", self.out)
                self.assertNotIn("::error::", self.out)
        for command in ("ecs wait", "ssm put-parameter"):
            with self.subTest(command):
                self.assertEqual(254, self.rollback(FAKE_FAILS_ON=command))
                self.assertEqual(len(self.calls()), self.line_of(f"^{command} "))

    def test_an_aws_call_killed_by_a_signal_ends_the_rollback_with_128_plus_the_signal(self):
        self.assertEqual(137, self.rollback(FAKE_KILLED_ON="ecs wait"))
        self.assertEqual(len(self.calls()), self.line_of("^ecs wait "))

    def test_without_aws_on_the_path_it_fails_with_127_and_says_so(self):
        self.assertEqual(127, self.rollback(PATH="/nowhere"))
        self.assertEqual("::warning::rolling back hub worker to their previous revisions; migrations are not undone\n"
                         "ecs_rollback.py: aws: command not found\n", self.out)

    def test_a_previous_revision_aws_cannot_describe_ends_the_rollback_before_changing_anything(self):
        (self.fixtures / "erplora-prod-worker:10.json").unlink()
        self.assertEqual(254, self.rollback())
        self.assertChangedNothing()
        self.assertIn("Unable to describe task definition", self.out)

    def test_a_previous_revision_that_cannot_be_read_ends_the_rollback_with_jq_s_code(self):
        for text in ("not json", "[]", '"s"', '{"tags": {}, "taskDefinition": []}'):
            with self.subTest(text):
                self.answer("erplora-prod-hub:10", text)
                self.assertEqual(5, self.rollback())
                self.assertChangedNothing()
                self.assertIn(f"ecs_rollback.py: {TD}/erplora-prod-hub:10 cannot be read: ", self.out)
                self.assertNotIn("::error::", self.out)
        for containers in (None, "s", ["s"], [{"name": "hub"}, 7]):
            with self.subTest(containers):
                self.revision("erplora-prod-hub:10")
                self.edit("erplora-prod-hub:10.json",
                          lambda found, given=containers: found["taskDefinition"].update(containerDefinitions=given))
                self.assertEqual(5, self.rollback())
                self.assertIn(f"ecs_rollback.py: {TD}/erplora-prod-hub:10 cannot be read: ", self.out)
                self.assertNotIn("::error::", self.out)
