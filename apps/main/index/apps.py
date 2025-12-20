from django.apps import AppConfig


class MainIndexConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.main.index"
    label = "main_index"
    verbose_name = "Main - Dashboard"
