"""Tests of scripts/ecs_deploy.py: the settings of deploy/app-env.json that deploy/app_env.py checks and applies to the
revisions before any is registered, and that the deploy records in /erplora/<environment>/hub/app_env once it succeeds.

The rules themselves are tested in test_app_env.py; these check that the deploy hands app_env.py what it prepared, stops
before registering when app_env.py refuses, and records what it wrote.
"""

import copy

from ecs_deploy_doubles import APP_ENV, DeployCase

SECRET = {"name": "PLATFORM_HUB_SLUG", "valueFrom": "arn:secret:x"}


def with_route(settings):
    for family in ("hub", "worker"):
        settings["prod"][family]["VERIFACTU_ERPLORA_ROUTE_ENABLED"] = "false"


class AppliedSettingsTest(DeployCase):
    def test_the_deploy_reads_the_file_of_the_commit_it_deploys_and_applies_it(self):
        self.edit("app-env.json", lambda settings: (
            settings["prod"]["hub"].update(PLATFORM_HUB_SLUG="erplora-cloud", VERIFACTU_ERPLORA_ROUTE_ENABLED="false"),
            settings["prod"]["worker"].update(PLATFORM_HUB_SLUG="erplora-cloud")))
        self.assertEqual(0, self.deploy())
        self.assertIn("show abc123:deploy/app-env.json", self.git_calls())
        worker = {"DEBUG": "False", "PLATFORM_HUB_SLUG": "erplora-cloud", "VERIFACTU_PRODUCTION_ENABLED": "true"}
        self.assertEqual({**worker, "VERIFACTU_ERPLORA_ROUTE_ENABLED": "false"},
                         self.environment_of("erplora-prod-hub", "hub"))
        self.assertEqual(worker, self.environment_of("erplora-prod-worker", "worker"))
        for family, name in (("hub", "pgbouncer"), ("worker", "pgbouncer"), ("hub-migrate", "hub-migrate")):
            self.assertEqual({}, self.environment_of(f"erplora-prod-{family}", name))

    def test_the_deploy_records_the_settings_once_the_services_are_checked_before_the_tag(self):
        self.edit("app-env.json", lambda settings: settings["prod"]["hub"].update(PLATFORM_HUB_SLUG="erplora-cloud"))
        self.deploy()
        settings = self.recorded_settings()
        self.assertEqual("erplora-cloud", settings["hub"]["PLATFORM_HUB_SLUG"])
        self.assertEqual(sorted(settings), list(settings))
        recorded = self.line_of("put-parameter --name /erplora/prod/hub/app_env ")
        self.assertGreater(recorded, self.last_line_of("describe-services .*deployments"))
        self.assertLess(recorded, self.line_of("/erplora/prod/hub/image_tag"))

    def test_a_variable_the_file_no_longer_gives_leaves_the_revision(self):
        self.edit("app-env.json", lambda settings: settings["prod"]["worker"].pop("PLATFORM_HUB_SLUG"))
        self.assertEqual(0, self.deploy())
        self.assertEqual({"DEBUG": "False", "VERIFACTU_PRODUCTION_ENABLED": "true"},
                         self.environment_of("erplora-prod-worker", "worker"))

    def test_pre_gets_and_records_pre_s_settings_and_never_reads_the_saas(self):
        self.assertEqual(0, self.deploy(ENVIRONMENT="pre"))
        for family in ("hub", "worker"):
            self.assertEqual(APP_ENV["pre"][family], self.environment_of(f"erplora-pre-{family}", family))
        self.assertTrue(self.called("^ssm put-parameter --name /erplora/pre/hub/app_env "))
        self.assertEqual(APP_ENV["pre"], self.recorded_settings())
        self.assertFalse(self.called("saas"))

    def test_a_commit_without_the_file_keeps_the_settings_in_force_with_a_warning(self):
        (self.fixtures / "app-env.json").unlink()
        self.assertEqual(0, self.deploy())
        self.assertIn("::warning::abc123 has no deploy/app-env.json", self.out)
        self.assertEqual(APP_ENV["prod"], self.recorded_settings())

    def test_the_settings_are_recorded_exactly_as_app_env_wrote_them(self):
        self.deploy()
        self.assertEqual('{"hub":{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"},"worker":'
                         '{"PLATFORM_HUB_SLUG":"erplora","VERIFACTU_PRODUCTION_ENABLED":"true"}}\n',
                         (self.work / "app-env-put.json").read_text())


class RefusedSettingsTest(DeployCase):
    def refused(self, where, **env):
        """A deploy whose settings break a rule at <where> fails with app_env.py's code before registering anything,
        and records nothing."""
        self.assertEqual(1, self.deploy(**env))
        self.assertNothingRegistered(f"{where}.*nothing was registered")

    def test_a_variable_that_is_not_a_setting_is_refused(self):
        self.edit("app-env.json", lambda settings: settings["prod"]["hub"].update(DEBUG="True"))
        self.refused("prod.hub.DEBUG:")

    def test_a_value_that_is_not_text_is_refused(self):
        self.edit("app-env.json", lambda settings: settings["prod"]["worker"].update(VERIFACTU_PRODUCTION_ENABLED=True))
        self.refused("prod.worker.VERIFACTU_PRODUCTION_ENABLED:")

    def test_a_secrets_section_is_refused(self):
        self.edit("app-env.json", lambda settings: settings["prod"].update(
            secrets={"FISCAL_CERTIFICATE_KEY": "arn:aws:secretsmanager:eu-west-1:1:secret:fiscal"}))
        self.refused("prod.secrets:")

    def test_a_prod_deploy_also_refuses_something_like_a_secret_in_pre_s_settings(self):
        self.edit("app-env.json", lambda settings: settings["pre"]["hub"].update(
            PLATFORM_HUB_SLUG="3f9a1c0e7b2d4a6f8e1c3b5d7f9a0c2e4b6d8f0a"))
        self.refused("pre.hub.PLATFORM_HUB_SLUG:")

    def test_pre_never_opens_the_aeat_s_production_environment(self):
        def opened(settings):
            for family in ("hub", "worker"):
                settings["pre"][family]["VERIFACTU_PRODUCTION_ENABLED"] = "true"

        self.edit("app-env.json", opened)
        self.refused("pre.hub.VERIFACTU_PRODUCTION_ENABLED:", ENVIRONMENT="pre")

    def test_without_the_settings_in_force_nothing_is_registered(self):
        (self.fixtures / "erplora_prod_hub_app_env.json").unlink()
        self.refused("/erplora/prod/hub/app_env:")

    def test_while_the_saas_charges_the_hub_keeps_sending_to_the_aeat(self):
        def closed(settings):
            for family in ("hub", "worker"):
                settings[family]["VERIFACTU_PRODUCTION_ENABLED"] = "false"

        self.edit("app-env.json", lambda settings: closed(settings["prod"]))
        self.edit("erplora_prod_hub_app_env.json", closed)
        self.refused("prod.hub.VERIFACTU_PRODUCTION_ENABLED:")

    def test_a_setting_terraform_gives_as_a_secret_stays_terraform_s(self):
        for name, value in (("PLATFORM_HUB_SLUG", "erplora"), ("VERIFACTU_ERPLORA_ROUTE_ENABLED", "false")):
            with self.subTest(name):
                self.edit("erplora-prod-worker.json", lambda found, name=name: found["taskDefinition"][
                    "containerDefinitions"][0].update(secrets=[{**SECRET, "name": name}]))
                self.edit("app-env.json", lambda settings, name=name, value=value: settings["prod"]["worker"].update(
                    {name: value}))
                self.refused(f"prod.worker.{name}:")


class OneOwnerTest(DeployCase):
    """ERPlora/aws passes the settings on from app_env and never sets them itself, so one the latest revisions run and
    the app_env in force lacks was left by a rollback, or by a deploy that failed after registering."""

    def left_behind(self):
        for family in ("hub", "worker"):
            self.edit(f"erplora-prod-{family}.json", lambda found: found["taskDefinition"]["containerDefinitions"][0][
                "environment"].append({"name": "VERIFACTU_ERPLORA_ROUTE_ENABLED", "value": "false"}))

    def test_the_same_file_deploys_and_records_the_setting(self):
        self.left_behind()
        self.edit("app-env.json", with_route)
        self.assertEqual(0, self.deploy())
        expected = copy.deepcopy(APP_ENV)
        with_route(expected)
        self.assertEqual(expected["prod"], self.recorded_settings())
        for family in ("hub", "worker"):
            self.assertEqual("false", self.environment_of(f"erplora-prod-{family}", family)[
                "VERIFACTU_ERPLORA_ROUTE_ENABLED"])

    def test_a_file_without_the_setting_takes_it_out_of_the_revisions(self):
        self.left_behind()
        self.assertEqual(0, self.deploy())
        self.assertEqual(APP_ENV["prod"], self.recorded_settings())
        for family in ("hub", "worker"):
            self.assertNotIn("VERIFACTU_ERPLORA_ROUTE_ENABLED", self.environment_of(f"erplora-prod-{family}", family))


class LockTest(DeployCase):
    """Opening the AEAT's production environment in prod takes the confirmation."""

    def setUp(self):
        super().setUp()

        def closed(settings):
            for family in ("hub", "worker"):
                settings[family]["VERIFACTU_PRODUCTION_ENABLED"] = "false"

        self.edit("erplora_prod_hub_app_env.json", closed)
        self.saas_charging("false")

    def test_without_the_confirmation_nothing_is_registered_and_the_error_says_how(self):
        self.assertEqual(1, self.deploy())
        self.assertNothingRegistered("prod.VERIFACTU_PRODUCTION_ENABLED:.*nothing was registered")
        self.assertIn("confirm_protected=VERIFACTU_PRODUCTION_ENABLED=true", self.out)

    def test_a_confirmation_of_something_else_registers_nothing(self):
        self.assertEqual(1, self.deploy(CONFIRM_PROTECTED="VERIFACTU_PRODUCTION_ENABLED=false"))
        self.assertNothingRegistered("prod.VERIFACTU_PRODUCTION_ENABLED:")

    def test_with_the_exact_confirmation_it_deploys_and_records_the_open_lock(self):
        self.assertEqual(0, self.deploy(CONFIRM_PROTECTED="VERIFACTU_PRODUCTION_ENABLED=true"))
        self.assertEqual("true", self.recorded_settings()["hub"]["VERIFACTU_PRODUCTION_ENABLED"])
        self.assertEqual("true", self.environment_of("erplora-prod-worker", "worker")["VERIFACTU_PRODUCTION_ENABLED"])
