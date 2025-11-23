from django.apps import AppConfig


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'
    verbose_name = 'Accounts & Authentication'

    def ready(self):
        """
        Initialize accounts app.
        Import signals and perform app-level initialization.
        """
        # Import signals here if needed
        pass
