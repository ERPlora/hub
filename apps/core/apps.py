from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """
        Run initialization tasks when Django is ready.

        This is called once the app registry is fully populated and
        all models have been imported.
        """
        # Import here to avoid AppRegistryNotReady error
        from .startup import run_startup_tasks

        # Only run startup tasks if not in a management command
        # (to avoid running twice with runserver auto-reload)
        import sys
        if 'runserver' not in sys.argv and 'migrate' not in sys.argv:
            run_startup_tasks()
