from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """
        Initialize core app when Django is ready.

        Note: WebSocket and FRP startup tasks have been moved to the
        multi_device plugin (plugins/multi_device/). The plugin handles
        all initialization automatically when it's installed and active.
        """
        pass
