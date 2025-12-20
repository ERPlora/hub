from django.apps import AppConfig


class MainSettingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.main.settings"
    label = "main_settings"
    verbose_name = "Main - Settings"
