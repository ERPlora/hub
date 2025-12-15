from django.apps import AppConfig


class DashboardCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.dashboard.core"
    label = "dashboard_core"
    verbose_name = "Dashboard Core"
