from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """Initialize core app when Django is ready."""
        self._setup_module_icons()

    def _setup_module_icons(self):
        """Register custom icons from installed modules."""
        from django.conf import settings

        try:
            from djicons.contrib.erplora import discover_module_icons
        except ImportError:
            return

        # Discover and register icons from modules
        modules_dir = getattr(settings, 'MODULES_DIR', None)
        if modules_dir and modules_dir.exists():
            discover_module_icons(modules_dir)
