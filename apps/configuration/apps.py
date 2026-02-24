from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ConfigurationConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.configuration'
    verbose_name = _('Hub & Store Configuration')

    def ready(self):
        """
        Initialize configuration app.
        Import signals and perform app-level initialization.
        """
        # Initialize the background scheduler for automated backups
        # This runs once when Django starts up
        from .scheduler import init_scheduler
        init_scheduler()
