from django.apps import AppConfig


class ExampleConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'example'
    verbose_name = 'Example Plugin'

    def ready(self):
        """Código que se ejecuta cuando el plugin se carga"""
        pass
