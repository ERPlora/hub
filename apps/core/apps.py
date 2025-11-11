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
        import os

        # Only run startup tasks if not in a management command (except runserver)
        # Skip for migrate, makemigrations, shell, etc.
        import sys
        skip_commands = ['migrate', 'makemigrations', 'shell', 'createsuperuser', 'test']
        should_skip = any(cmd in sys.argv for cmd in skip_commands)

        # With runserver, Django spawns two processes:
        # 1. Parent process (RUN_MAIN not set) - for autoreload watching
        # 2. Child process (RUN_MAIN='true') - the actual server
        # We only want to run startup tasks in the child process
        is_child_process = os.environ.get('RUN_MAIN') == 'true'
        is_runserver = 'runserver' in sys.argv

        # Run startup tasks if:
        # - Not a skipped command AND
        # - Either it's the runserver child process OR it's not runserver at all
        if not should_skip and (is_child_process or not is_runserver):
            run_startup_tasks()
