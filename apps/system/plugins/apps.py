from django.apps import AppConfig


class SystemPluginsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.system.plugins"
    label = "system_plugins"
    verbose_name = "System - Plugins"
