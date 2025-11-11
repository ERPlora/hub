from django.apps import AppConfig


class PluginsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.plugins'
    verbose_name = 'Plugin System'

    def ready(self):
        """
        Initialize plugins app.
        Load installed plugins and register them with Django.
        """
        # Import signals here if needed
        pass
