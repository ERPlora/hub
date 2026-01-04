from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = 'Core'

    def ready(self):
        """Initialize core app when Django is ready."""
        self._setup_icons()

    def _setup_icons(self):
        """Setup djicons with Hub's ionicons and module icons."""
        from pathlib import Path
        from django.conf import settings

        try:
            from djicons.contrib.erplora import setup_erplora_icons
        except ImportError:
            return

        # Path to ionicons SVG files in Hub's static directory
        ionicons_dir = Path(settings.BASE_DIR) / 'static' / 'ionicons' / 'dist' / 'svg'

        # Path to modules directory
        modules_dir = getattr(settings, 'MODULES_DIR', None)

        # Setup icons (ionicons + module custom icons)
        if ionicons_dir.exists():
            setup_erplora_icons(
                modules_dir=modules_dir or Path('/nonexistent'),
                ionicons_dir=ionicons_dir,
            )
