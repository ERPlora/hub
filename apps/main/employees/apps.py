from django.apps import AppConfig


class MainEmployeesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.main.employees"
    label = "main_employees"
    verbose_name = "Main - Employees"
