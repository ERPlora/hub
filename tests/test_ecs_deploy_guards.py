"""Tests of scripts/ecs_deploy.py: the latest revision of each family is read, and refused before anything is
registered, when it is not of the environment deployed or has no container of the hub image.

The deploy roles can register any family (ECS takes no resource there), so the guard keeps pre's role from turning a
prod revision into its own and back. The revisions are read with jq's rules: a value that cannot be read through stops
the deploy with jq's exit code for it, 5.
"""

import json
import re

from ecs_deploy_doubles import DeployCase, one, task_definition

ROLE = "arn:aws:iam::123456789012:role/erplora-prod-hub"
PROD_TAG = {"key": "Environment", "value": "prod"}


class RefusedRevisionTest(DeployCase):
    def test_prod_refuses_a_revision_tagged_pre_naming_what_it_carries(self):
        self.fixture("erplora-prod-worker", one("worker", "hub:bootstrap"), "pre")
        self.assertEqual(1, self.deploy())
        self.assertNothingRegistered()
        self.assertEqual(
            "::error::erplora-prod-worker is no revision of prod (Environment=pre, task role "
            "arn:aws:iam::123456789012:role/erplora-prod-worker-task, execution role "
            "arn:aws:iam::123456789012:role/erplora-prod-worker-execution); nothing was registered\n", self.out)
        self.assertFalse(self.called("erplora-prod-hub-migrate"))

    def test_prod_refuses_a_revision_without_the_environment_tag(self):
        self.fixture("erplora-prod-hub-migrate", one("hub-migrate", "hub:bootstrap"), "")
        self.deploy()
        self.assertNothingRegistered("erplora-prod-hub-migrate is no revision of prod \\(Environment=none, ")

    def test_pre_refuses_a_revision_with_a_prod_task_role(self):
        self.fixture("erplora-pre-hub", one("hub", "hub-pre:bootstrap"), "pre",
                     "arn:aws:iam::123456789012:role/erplora-prod-hub-task")
        self.deploy(ENVIRONMENT="pre")
        self.assertNothingRegistered("erplora-pre-hub is no revision of pre .*nothing was registered")

    def test_pre_refuses_a_revision_with_a_prod_execution_role(self):
        self.fixture("erplora-pre-worker", one("worker", "hub-pre:bootstrap"), "pre", None,
                     "arn:aws:iam::123456789012:role/erplora-prod-worker-execution")
        self.deploy(ENVIRONMENT="pre")
        self.assertNothingRegistered("erplora-pre-worker is no revision of pre .*nothing was registered")

    def test_a_revision_without_a_task_role_is_refused_and_the_error_says_so(self):
        self.edit("erplora-prod-hub.json", lambda found: found["taskDefinition"].pop("taskRoleArn"))
        self.deploy()
        self.assertNothingRegistered("erplora-prod-hub is no revision of prod \\(Environment=prod, task role none, ")

    def test_a_role_must_be_of_the_environment_s_prefix_and_start_the_arn(self):
        for role in ("arn:aws:iam::123456789012:role/erplora-prod", f"x\n{ROLE}", ROLE.upper(),
                     "arn:aws:iam::12345678901x:role/erplora-prod-hub", "arn:aws:iam:::role/erplora-prod-hub",
                     "arn:aws:sts::123456789012:role/erplora-prod-hub", "", False):
            with self.subTest(role):
                self.edit("erplora-prod-hub.json", lambda found, role=role: found["taskDefinition"].update(
                    executionRoleArn=role))
                self.assertEqual(1, self.deploy())
                self.assertNothingRegistered("erplora-prod-hub is no revision of prod")

    def test_a_role_of_another_partition_or_account_length_is_of_the_environment(self):
        for role in ("arn:aws-us-gov:iam::123456789012:role/erplora-prod-x", "arn:aws:iam::1:role/erplora-prod-",
                     f"{ROLE}\n"):
            with self.subTest(role):
                self.edit("erplora-prod-hub.json", lambda found, role=role: found["taskDefinition"].update(
                    taskRoleArn=role))
                self.assertEqual(0, self.deploy(FAKE_TASK_STATUSES="STOPPED"))

    def test_what_a_refused_revision_carries_is_written_as_jq_writes_it(self):
        self.edit("erplora-prod-hub.json", lambda found: (found["tags"].append({"key": "Environment", "value": 5}),
                                                          found["tags"].remove(PROD_TAG),
                                                          found["taskDefinition"].update(taskRoleArn={"a": [1, "ñ"]},
                                                                                         executionRoleArn="x\n\n")))
        self.assertEqual(1, self.deploy())
        self.assertEqual('::error::erplora-prod-hub is no revision of prod (Environment=5, task role {"a":[1,"ñ"]}, '
                         "execution role x); nothing was registered\n", self.out)

    def test_only_the_first_environment_tag_is_said_and_a_role_that_is_no_text_is_refused(self):
        self.edit("erplora-prod-hub.json", lambda found: found.update(tags=[{"key": "Environment", "value": None},
                                                                            {"key": "Environment", "value": "pre"}]))
        self.deploy()
        self.assertNothingRegistered("erplora-prod-hub is no revision of prod \\(Environment=none, ")
        self.fixture("erplora-prod-hub", one("hub", "hub:bootstrap"))
        self.edit("erplora-prod-hub.json", lambda found: found["taskDefinition"].update(taskRoleArn=5))
        self.assertEqual(1, self.deploy())
        self.assertNothingRegistered("erplora-prod-hub is no revision of prod \\(Environment=prod, task role 5, ")


    def test_a_role_that_is_no_text_is_said_as_jq_says_it(self):
        for role, said in ((0, "0"), (False, "none"), (None, "none"), ("", ""), (["a"], '["a"]')):
            with self.subTest(role):
                self.edit("erplora-prod-hub.json", lambda found, role=role: found["taskDefinition"].update(
                    taskRoleArn=role))
                self.assertEqual(1, self.deploy())
                self.assertNothingRegistered(f"erplora-prod-hub is no revision of prod \\(Environment=prod, task role "
                                             f"{re.escape(said)}, execution role arn:")


class ReadLikeJqTest(DeployCase):
    def test_tags_may_be_an_object_and_a_null_tag_is_skipped(self):
        self.edit("erplora-prod-hub.json", lambda found: found.update(tags={"env": PROD_TAG}))
        self.edit("erplora-prod-worker.json", lambda found: found.update(tags=[None, PROD_TAG]))
        self.assertEqual(0, self.deploy())
        self.assertEqual({"env": PROD_TAG}, self.registered()["erplora-prod-hub"]["tags"])
        self.assertEqual([None, PROD_TAG], self.registered()["erplora-prod-worker"]["tags"])

    def test_an_environment_tag_without_a_value_is_of_no_environment(self):
        self.edit("erplora-prod-hub.json", lambda found: found.update(tags=[{"key": "Environment"}]))
        self.assertEqual(1, self.deploy())
        self.assertNothingRegistered("erplora-prod-hub is no revision of prod \\(Environment=none, task role arn:")

    def test_tags_that_cannot_be_iterated_are_none(self):
        for tags in ("prod", 5, None, []):
            with self.subTest(tags):
                self.edit("erplora-prod-hub.json", lambda found, tags=tags: found.update(tags=tags))
                self.assertEqual(1, self.deploy())
                self.assertNothingRegistered("erplora-prod-hub is no revision of prod \\(Environment=none, ")

    def test_a_tag_that_is_no_object_after_the_environment_one_is_never_read(self):
        self.edit("erplora-prod-hub.json", lambda found: found.update(tags=[PROD_TAG, "x"]))
        self.assertEqual(0, self.deploy())

    def test_a_tag_that_is_no_object_before_the_environment_one_cannot_be_read(self):
        for tag in ("x", 1, [], True):
            with self.subTest(tag):
                self.edit("erplora-prod-hub.json", lambda found, tag=tag: found.update(tags=[tag, PROD_TAG]))
                self.assertEqual(5, self.deploy())
                self.assertNothingRegistered()
                self.assertIn("ecs_deploy.py: erplora-prod-hub cannot be read: ", self.out)

    def test_an_answer_that_is_no_json_object_cannot_be_read(self):
        for answer in ("garbage", "[]", "[1]", '"s"', "5"):
            with self.subTest(answer):
                (self.fixtures / "erplora-prod-hub.json").write_text(answer)
                self.assertEqual(5, self.deploy())
                self.assertNothingRegistered()
                self.assertIn("ecs_deploy.py: erplora-prod-hub cannot be read: ", self.out)
                self.assertNotIn("::error::", self.out)

    def test_a_blank_or_null_answer_carries_nothing(self):
        nothing = "Environment=none, task role none, execution role none"
        for answer, carries in (("", ""), (" \n", ""), ("null", nothing), ("{}", nothing)):
            with self.subTest(answer):
                (self.fixtures / "erplora-prod-hub.json").write_text(answer)
                self.assertEqual(1, self.deploy())
                self.assertEqual(f"::error::erplora-prod-hub is no revision of prod ({carries}); nothing was "
                                 "registered\n", self.out)

    def test_a_definition_that_is_no_object_cannot_be_read(self):
        self.edit("erplora-prod-hub.json", lambda found: found.update(taskDefinition="s"))
        self.assertEqual(5, self.deploy())
        self.assertNothingRegistered()


class HubImageTest(DeployCase):
    def test_a_family_with_no_container_of_the_hub_image_is_refused_before_registering(self):
        self.fixture("erplora-prod-worker", [{"name": "worker", "image": "other.example/erplora/hub:bootstrap"}])
        self.assertEqual(1, self.deploy())
        self.assertNothingRegistered()
        self.assertEqual("::error::erplora-prod-worker has no container of the image reg.example/erplora/hub:<tag>; "
                         "nothing was registered\n", self.out)
        self.assertFalse(self.called("erplora-prod-hub-migrate"))

    def test_a_family_without_containers_is_refused(self):
        self.fixture("erplora-prod-hub-migrate", [])
        self.deploy()
        self.assertNothingRegistered("erplora-prod-hub-migrate has no container of the image")

    def test_containers_may_be_an_object_and_one_may_be_null_or_lack_an_image(self):
        self.edit("erplora-prod-hub.json", lambda found: found["taskDefinition"].update(containerDefinitions={
            "app": found["taskDefinition"]["containerDefinitions"][0], "gone": None,
            "bare": {"name": "bare"}, "off": {"name": "off", "image": False}}))
        self.assertEqual(0, self.deploy())
        containers = self.registered()["erplora-prod-hub"]["containerDefinitions"]
        self.assertEqual("reg.example/erplora/hub:abc123", containers[0]["image"])
        self.assertEqual([None, {"name": "bare"}, {"name": "off", "image": False}], containers[1:])

    def test_containers_or_an_image_that_cannot_be_read_stop_the_deploy(self):
        for change in ({"containerDefinitions": None}, {"containerDefinitions": "s"},
                       {"containerDefinitions": ["s"]}, {"containerDefinitions": [{"image": 5}]},
                       {"containerDefinitions": [{"image": 0}]}):
            with self.subTest(change):
                self.edit("erplora-prod-hub.json", lambda found, change=change: found["taskDefinition"].update(change))
                self.assertEqual(5, self.deploy())
                self.assertNothingRegistered()
                self.assertIn("ecs_deploy.py: erplora-prod-hub cannot be read: ", self.out)

    def test_the_revision_prepared_for_app_env_is_the_one_registered_before_its_settings(self):
        found = task_definition("erplora-prod-hub-migrate", one("hub-migrate", "hub:bootstrap", cpu=256))
        found["taskDefinition"]["extra"] = {"keep": ["ñ", 1.5, None]}
        (self.fixtures / "erplora-prod-hub-migrate.json").write_text(json.dumps(found))
        self.assertEqual(0, self.deploy())
        definition = found["taskDefinition"]
        for name in ("taskDefinitionArn", "revision", "status", "requiresAttributes", "compatibilities",
                     "registeredAt", "registeredBy"):
            definition.pop(name)
        # app_env.py gives the app's container the family's settings: none for hub-migrate.
        definition["containerDefinitions"][0].update(image="reg.example/erplora/hub:abc123", environment=[])
        self.assertEqual({**definition, "tags": found["tags"]}, self.registered()["erplora-prod-hub-migrate"])
