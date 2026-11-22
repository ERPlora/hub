"""Tests of scripts/ecs_rollback.py: the settings the previous revisions run go through the deploy's checks
(deploy/app_env_rollback.py) before any service moves, and are recorded in /erplora/<environment>/hub/app_env once the
services run those revisions.

A rollback registers nothing, so the services run the settings their previous revisions were registered with,
whatever deploy/app-env.json says today. In prod, changing VERIFACTU_PRODUCTION_ENABLED takes CONFIRM_PROTECTED, and
while the SaaS charges the hub keeps sending to the AEAT.
"""

from ecs_doubles import APP_ENV
from ecs_rollback_doubles import RollbackCase


def changed(environment, name, **settings):
    return {**APP_ENV[environment][name], **settings}


class SettingsTest(RollbackCase):
    def test_the_settings_are_checked_before_any_service_moves(self):
        self.assertEqual(0, self.rollback())
        self.assertLess(self.line_of("ssm get-parameter --name /erplora/prod/hub/app_env "),
                        self.line_of("update-service"))
        self.assertLess(self.line_of("describe-task-definition --task-definition erplora-prod-saas "),
                        self.line_of("update-service"))

    def test_the_rollback_records_what_prod_s_previous_revisions_run_with_the_tag(self):
        self.assertEqual(0, self.rollback())
        self.assertEqual(APP_ENV["prod"], self.recorded_settings())
        put = self.line_of("put-parameter --name /erplora/prod/hub/app_env ")
        self.assertGreater(put, self.last_line_of("describe-services"))
        self.assertLess(put, self.line_of("put-parameter --name /erplora/prod/hub/image_tag "))

    def test_revisions_that_run_other_settings_replace_the_ones_in_force(self):
        for name in ("hub", "worker"):
            settings = changed("prod", name, VERIFACTU_ERPLORA_ROUTE_ENABLED="false")
            self.revision(f"erplora-prod-{name}:10", settings=settings)
        self.assertEqual(0, self.rollback())
        self.assertEqual("false", self.recorded_settings()["worker"]["VERIFACTU_ERPLORA_ROUTE_ENABLED"])

    def test_pre_records_pre_s_settings_and_never_reads_the_saas(self):
        self.assertEqual(0, self.rollback(ENVIRONMENT="pre"))
        self.assertEqual(APP_ENV["pre"], self.recorded_settings())
        self.assertFalse(self.called("saas"))

    def test_revisions_whose_settings_break_a_rule_are_never_gone_back_to(self):
        self.revision("erplora-prod-worker:10", settings=changed("prod", "worker", PLATFORM_HUB_SLUG="Erplora_Old"))
        self.assertEqual(1, self.rollback())
        self.assertChangedNothing("prod.worker.PLATFORM_HUB_SLUG:.*; nothing was changed")
        self.assertNotIn("Erplora_Old", self.out)

    def test_without_the_settings_in_force_nothing_changes(self):
        (self.fixtures / "erplora_prod_hub_app_env.json").unlink()
        self.rollback()
        self.assertChangedNothing("/erplora/prod/hub/app_env:.*; nothing was changed")


class LockTest(RollbackCase):
    """Going back to revisions that open the AEAT's production environment in prod takes the confirmation."""

    def setUp(self):
        super().setUp()
        self.write("erplora_prod_hub_app_env.json", {name: changed("prod", name, VERIFACTU_PRODUCTION_ENABLED="false")
                                                     for name in ("hub", "worker")})
        self.saas_charging("false")

    def test_without_the_confirmation_nothing_changes_and_the_error_says_how(self):
        self.rollback()
        self.assertChangedNothing("prod.VERIFACTU_PRODUCTION_ENABLED:")
        self.assertIn("confirm_protected=VERIFACTU_PRODUCTION_ENABLED=true", self.out)

    def test_a_confirmation_of_something_else_changes_nothing(self):
        self.rollback(CONFIRM_PROTECTED="VERIFACTU_PRODUCTION_ENABLED=false")
        self.assertChangedNothing("prod.VERIFACTU_PRODUCTION_ENABLED:")

    def test_with_the_exact_confirmation_it_goes_back_and_records_the_open_lock(self):
        self.assertEqual(0, self.rollback(CONFIRM_PROTECTED="VERIFACTU_PRODUCTION_ENABLED=true"))
        self.assertEqual("true", self.recorded_settings()["hub"]["VERIFACTU_PRODUCTION_ENABLED"])
        self.assertTrue(self.called("update-service .*--service hub "))

    def test_while_the_saas_charges_it_never_goes_back_to_revisions_that_close_the_aeat(self):
        self.write("erplora_prod_hub_app_env.json", APP_ENV["prod"])
        self.saas_charging("true")
        for name in ("hub", "worker"):
            settings = changed("prod", name, VERIFACTU_PRODUCTION_ENABLED="false")
            self.revision(f"erplora-prod-{name}:10", settings=settings)
        self.rollback(CONFIRM_PROTECTED="VERIFACTU_PRODUCTION_ENABLED=false")
        self.assertChangedNothing("prod.hub.VERIFACTU_PRODUCTION_ENABLED:")
