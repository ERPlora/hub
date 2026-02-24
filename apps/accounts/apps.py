from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = _('Accounts & Authentication')

    def ready(self):
        """
        Initialize accounts app.
        Import signals and perform app-level initialization.
        """
        # Import signals here if needed
        pass
