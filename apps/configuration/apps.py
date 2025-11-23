from django.apps import AppConfig


class ConfigurationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.configuration'
    verbose_name = 'Hub & Store Configuration'

    def ready(self):
        """
        Initialize configuration app.
        Import signals and perform app-level initialization.
        """
        # Import signals here if needed
        pass
