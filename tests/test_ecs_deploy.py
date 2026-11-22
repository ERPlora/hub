"""Tests of scripts/ecs_deploy.py: the deploy of an image tag of the hub to prod or pre.

The deploy runs as the workflow runs it, with a fake aws CLI and a fake git first on the PATH (ecs_deploy_doubles).
The settings of deploy/app-env.json are tested in test_ecs_deploy_settings.py, the revisions it refuses in
test_ecs_deploy_guards.py and its waits in test_ecs_deploy_waits.py.
"""

import re

from ecs_deploy_doubles import DeployCase

REGION = "--region eu-south-2"
PRIMARY = "--query services[0].deployments[?status=='PRIMARY'] | [0].[taskDefinition, rolloutState] --output text"
NETWORK = '{"awsvpcConfiguration":{"subnets":["s"],"securityGroups":["g"],"assignPublicIp":"ENABLED"}}'
SETTINGS = ('{"hub":{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"},'
            '"worker":{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"}}')


def prod_calls():
    """Every call of a prod deploy, in order: the three revisions, the settings in force and the SaaS's revision are
    read (and checked) before any is registered, and the settings are recorded last, with the tag."""
    cluster = "--cluster erplora-prod"
    task = f"describe-tasks {cluster} --tasks arn:task/erplora-prod/migrate1 {REGION} --query tasks[0]."
    families = ("hub", "worker", "hub-migrate")
    return [
        *(f"ecs describe-task-definition --task-definition erplora-prod-{name} --include TAGS {REGION} --output json"
          for name in families),
        f"ssm get-parameter --name /erplora/prod/hub/app_env --query Parameter.Value --output text {REGION}",
        f"ecs describe-task-definition --task-definition erplora-prod-saas {REGION} --output json",
        *(f"ecs register-task-definition --cli-input-json file://WORKDIR/{name}.json {REGION} --query "
          "taskDefinition.taskDefinitionArn --output text" for name in families),
        f"ecs describe-services {cluster} --services worker {REGION} --query services[0].networkConfiguration "
        "--output json",
        f"ecs run-task {cluster} --launch-type FARGATE --task-definition arn:td/erplora-prod-hub-migrate:2 "
        f"--network-configuration {NETWORK} --started-by deploy-abc123 {REGION} --output json",
        f"ecs {task}lastStatus --output text",
        f"ecs {task}lastStatus --output text",
        f"ecs {task}containers[?name=='hub-migrate'].exitCode | [0] --output text",
        f"ecs update-service {cluster} --service hub --task-definition arn:td/erplora-prod-hub:2 {REGION}",
        f"ecs update-service {cluster} --service worker --task-definition arn:td/erplora-prod-worker:2 {REGION}",
        f"ecs wait services-stable {cluster} {REGION} --services hub worker",
        f"ecs describe-services {cluster} --services hub {REGION} {PRIMARY}",
        f"ecs describe-services {cluster} --services worker {REGION} {PRIMARY}",
        f"ssm put-parameter --name /erplora/prod/hub/app_env --value {SETTINGS} --type String --overwrite {REGION}",
        f"ssm put-parameter --name /erplora/prod/hub/image_tag --value abc123 --type String --overwrite {REGION}",
    ]


class ProdDeployTest(DeployCase):
    def test_the_calls_are_exactly_these(self):
        self.assertEqual(0, self.deploy())
        self.assertEqual(prod_calls(), [re.sub(r"file://\S*/", "file://WORKDIR/", call) for call in self.calls()])

    def test_registers_hub_worker_and_hub_migrate_and_never_db_bootstrap(self):
        self.deploy()
        self.assertEqual(["erplora-prod-hub", "erplora-prod-hub-migrate", "erplora-prod-worker"],
                         sorted(self.registered()))
        self.assertFalse(self.called("db-bootstrap"))

    def test_every_container_of_the_hub_image_gets_the_new_image_and_the_others_keep_theirs(self):
        self.deploy()
        new = "reg.example/erplora/hub:abc123"
        self.assertEqual([new, new, "public.ecr.aws/aws-observability/aws-for-fluent-bit:stable",
                          "reg.example/erplora/hubx:bootstrap"], self.images("erplora-prod-hub"))
        self.assertEqual([new, new], self.images("erplora-prod-worker"))
        self.assertEqual([new], self.images("erplora-prod-hub-migrate"))

    def test_the_rest_of_the_definition_and_its_tags_are_kept_and_the_read_only_fields_go(self):
        self.deploy()
        hub = self.registered()["erplora-prod-hub"]
        self.assertEqual("arn:aws:iam::123456789012:role/erplora-prod-hub-task", hub["taskRoleArn"])
        self.assertEqual("arn:aws:iam::123456789012:role/erplora-prod-hub-execution", hub["executionRoleArn"])
        read_only = {"taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
                     "registeredAt", "registeredBy", "deregisteredAt"}
        self.assertFalse(any(read_only & set(revision) for revision in self.registered().values()))
        self.assertEqual([{"key": "Project", "value": "erplora"}, {"key": "ManagedBy", "value": "terraform"},
                          {"key": "Environment", "value": "prod"}], self.registered()["erplora-prod-worker"]["tags"])

    def test_a_deregistered_at_of_the_base_revision_is_not_registered(self):
        self.edit("erplora-prod-hub.json", lambda found: found["taskDefinition"].update(deregisteredAt="t"))
        self.deploy()
        self.assertNotIn("deregisteredAt", self.registered()["erplora-prod-hub"])

    def test_the_migration_runs_before_any_service_changes_and_the_tag_is_recorded_after_the_check(self):
        self.deploy()
        self.assertLess(self.last_line_of("describe-tasks"), self.line_of("update-service"))
        for service in ("hub", "worker"):
            self.assertGreater(self.last_line_of(f"describe-services .*--services {service} .*deployments"),
                               self.line_of("wait services-stable"))
        self.assertGreater(self.line_of("ssm put-parameter"), self.last_line_of("describe-services .*deployments"))
        self.assertFalse(self.called("wait tasks-stopped|desired-count|containers\\[0\\]"))
        self.assertEqual({"erplora-prod"}, self.clusters_named())

    def test_what_the_deploy_says_and_where(self):
        self.assertEqual(0, self.deploy(apart=True))
        self.assertEqual(
            b"registered arn:td/erplora-prod-hub:2\nregistered arn:td/erplora-prod-worker:2\n"
            b"registered arn:td/erplora-prod-hub-migrate:2\nrunning hub-migrate: arn:task/erplora-prod/migrate1\n"
            b"updated hub\nupdated worker\nservices stable on the new revisions\n"
            b"recorded its settings and abc123 in /erplora/prod/hub/app_env and image_tag\n", self.stdout)
        self.assertEqual(b"", self.stderr)


class PreDeployTest(DeployCase):
    def test_pre_deploys_its_own_families_services_repository_and_tag(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        self.assertEqual(["erplora-pre-hub", "erplora-pre-hub-migrate", "erplora-pre-worker"],
                         sorted(self.registered()))
        new = "reg.example/erplora/hub-pre:abc123"
        self.assertEqual([new, new], self.images("erplora-pre-hub"))
        self.assertEqual([new, new], self.images("erplora-pre-worker"))
        self.assertEqual([new], self.images("erplora-pre-hub-migrate"))
        for revision in self.registered().values():
            self.assertIn({"key": "Environment", "value": "pre"}, revision["tags"])
        self.assertEqual({"erplora-pre"}, self.clusters_named())
        self.assertTrue(self.called("^ecs describe-services --cluster erplora-pre --services worker-pre .*networkConf"))
        self.assertTrue(self.called("run-task --cluster erplora-pre .*--task-definition arn:td/erplora-pre-hub-migr"))
        self.assertTrue(self.called(r"describe-tasks .*containers\[\?name=='hub-migrate'\]\.exitCode"))
        self.assertTrue(self.called(r"wait services-stable .*--services hub-pre worker-pre$"))
        for service in ("hub-pre", "worker-pre"):
            self.assertTrue(self.called(f"describe-services .*--services {service} .*deployments"))
        self.assertTrue(self.called(
            "^ssm put-parameter --name /erplora/pre/hub/image_tag --value abc123 --type String --overwrite"))
        self.assertFalse(self.called("db-bootstrap"))

    def test_a_push_wakes_pre_up_with_one_task_per_service(self):
        self.deploy(ENVIRONMENT="pre")
        self.assertEqual(self.lines("update-service"), self.lines("update-service .*--desired-count 1 "))
        self.assertEqual(2, len(self.lines("update-service")))
        for name in ("hub", "worker"):
            self.assertTrue(self.called(f"update-service --cluster erplora-pre --service {name}-pre "
                                        f"--task-definition arn:td/erplora-pre-{name}:2 "))

    def test_pre_never_names_a_prod_cluster_family_service_parameter_or_repository(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        touched = "\n".join(self.calls()) + (self.work / "registered.log").read_text()
        self.assertIsNone(re.search(r"erplora-prod|/erplora/prod/|erplora/hub:|--services? (hub|worker)( |$)", touched,
                                    re.M))

    def test_prod_touches_nothing_of_pre(self):
        self.assertEqual(0, self.deploy())
        touched = "\n".join(self.calls()) + (self.work / "registered.log").read_text()
        self.assertIsNone(re.search("erplora-pre|-pre |/erplora/pre/", touched))

    def test_a_failed_migration_of_pre_names_pre_s_log_group(self):
        self.assertNotEqual(0, self.deploy(ENVIRONMENT="pre", FAKE_MIGRATE_EXIT="1"))
        self.assertRegex(self.out, "::error::hub-migrate .*code 1.*/ecs/erplora-pre-hub-migrate")


class SettingsOfTheRunTest(DeployCase):
    def test_an_explicit_cluster_is_used_in_every_cluster_scoped_call(self):
        for environment in ("prod", "pre"):
            with self.subTest(environment):
                self.assertEqual(0, self.deploy(ENVIRONMENT=environment, CLUSTER="custom-cluster"))
                self.assertEqual({"custom-cluster"}, self.clusters_named())

    def test_an_empty_cluster_is_the_environment_s_own(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre", CLUSTER=""))
        self.assertEqual({"erplora-pre"}, self.clusters_named())

    def test_an_environment_other_than_prod_or_pre_fails_before_any_aws_call(self):
        for environment in ("dev", "PROD", "staging", " pre", "prod "):
            with self.subTest(environment):
                self.deploy(ENVIRONMENT=environment)
                self.assertFailsBeforeAnyCall(f"::error::ENVIRONMENT must be prod or pre, not '{environment}'\n")

    def test_without_a_required_setting_it_fails_before_any_aws_call_naming_it(self):
        for name in ("AWS_REGION", "REGISTRY", "IMAGE_TAG", "ENVIRONMENT"):
            with self.subTest(name):
                self.deploy(name)
                self.assertFailsBeforeAnyCall(f"::error::{name} is required\n")
                self.assertEqual(1, self.status)
                self.deploy(**{name: ""})
                self.assertFailsBeforeAnyCall(f"::error::{name} is required\n")

    def test_the_first_missing_setting_is_the_one_named(self):
        self.deploy(AWS_REGION="", REGISTRY="", IMAGE_TAG="", ENVIRONMENT="x")
        self.assertEqual("::error::AWS_REGION is required\n", self.out)
        self.deploy(REGISTRY="", IMAGE_TAG="", ENVIRONMENT="")
        self.assertEqual("::error::REGISTRY is required\n", self.out)

    def test_a_number_of_seconds_that_is_none_fails_before_any_aws_call(self):
        for name in ("POLL_SECONDS", "MIGRATE_TIMEOUT_SECONDS", "ROLLOUT_TIMEOUT_SECONDS"):
            for value in ("soon", "1.5", "-1", " 1", "1\n", "١"):
                with self.subTest(name=name, value=value):
                    self.deploy(**{name: value})
                    self.assertFailsBeforeAnyCall(f"::error::{name} must be a number of seconds, not '{value}'\n")
                    self.assertEqual(1, self.status)

    def test_the_migration_is_started_by_the_first_twelve_characters_of_the_tag(self):
        self.assertEqual(0, self.deploy(IMAGE_TAG="0123456789abcdef", FAKE_COMMIT="0123456789abcdef"))
        self.assertTrue(self.called("run-task .*--started-by deploy-0123456789ab "))
        self.assertTrue(self.called("--value 0123456789abcdef "))

    def test_every_aws_call_names_the_region(self):
        self.deploy()
        self.assertTrue(self.calls())
        self.assertTrue(all(REGION in call for call in self.calls()))

    def test_of_the_saas_only_its_latest_revision_is_read_and_only_in_prod(self):
        self.deploy()
        self.assertEqual([f"ecs describe-task-definition --task-definition erplora-prod-saas {REGION} --output json"],
                         [call for call in self.calls() if "saas" in call])
        self.deploy(ENVIRONMENT="pre")
        self.assertFalse(self.called("saas"))


class OutputTest(DeployCase):
    def test_its_lines_come_in_order_with_what_aws_says(self):
        self.assertEqual(254, self.deploy(FAKE_FAILS_ON="ecs update-service"))
        self.assertEqual(
            "registered arn:td/erplora-prod-hub:2\nregistered arn:td/erplora-prod-worker:2\n"
            "registered arn:td/erplora-prod-hub-migrate:2\nrunning hub-migrate: arn:task/erplora-prod/migrate1\n"
            "An error occurred (AccessDeniedException) when calling ecs update-service\n", self.out)

    def test_what_it_is_given_is_said_as_the_bytes_it_was_given(self):
        self.assertEqual(1, self.deploy(ENVIRONMENT="pr\udcffd"))
        self.assertEqual(b"::error::ENVIRONMENT must be prod or pre, not 'pr\xffd'\n", self.stdout)
        self.assertEqual(1, self.deploy(FAKE_MIGRATE_EXIT="None", FAKE_STOPPED_REASON="\u00f1 \udcff exited"))
        self.assertIn(b"::error::hub-migrate stopped without running: \xc3\xb1 \xff exited\n", self.stdout)


class FailingCallTest(DeployCase):
    def test_an_aws_call_that_fails_ends_the_deploy_with_its_exit_code(self):
        self.assertEqual(254, self.deploy(FAKE_FAILS_ON="ecs update-service"))
        self.assertEqual(1, len(self.lines("update-service")))
        self.assertFalse(self.called("wait|put-parameter"))
        self.assertIn("An error occurred (AccessDeniedException) when calling ecs update-service\n", self.out)

    def test_an_aws_call_killed_by_a_signal_ends_the_deploy_with_128_plus_the_signal(self):
        self.assertEqual(137, self.deploy(FAKE_KILLED_ON="ecs wait"))
        self.assertFalse(self.called("deployments|put-parameter"))

    def test_without_aws_on_the_path_it_fails_with_127_and_says_so(self):
        self.assertEqual(127, self.deploy(PATH="/nowhere"))
        self.assertEqual("ecs_deploy.py: aws: command not found\n", self.out)

    def test_a_family_aws_cannot_describe_ends_the_deploy_before_registering(self):
        (self.fixtures / "erplora-prod-worker.json").unlink()
        self.assertEqual(254, self.deploy())
        self.assertNothingRegistered()
        self.assertFalse(self.called("hub-migrate"))
        self.assertIn("Unable to describe task definition", self.out)
