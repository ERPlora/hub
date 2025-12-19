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
        # Initialize the background scheduler for automated backups
        # This runs once when Django starts up
        from .scheduler import init_scheduler
        init_scheduler()
