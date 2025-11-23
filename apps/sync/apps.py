from django.apps import AppConfig


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sync'
    verbose_name = 'Cloud Synchronization'

    def ready(self):
        """
        Initialize sync app.
        Start background sync processes and WebSocket connections.
        """
        # Import signals here if needed
        pass
