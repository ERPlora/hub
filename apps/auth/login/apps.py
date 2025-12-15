from django.apps import AppConfig


class AuthLoginConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auth.login"
    label = "auth_login"
    verbose_name = "Authentication - Login"
