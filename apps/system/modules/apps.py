from django.apps import AppConfig


class SystemModulesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.system.modules"
    label = "system_modules"
    verbose_name = "System - Modules"
