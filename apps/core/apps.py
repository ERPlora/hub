from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = _('Core')

    def ready(self):
        """Initialize core app when Django is ready."""
        self._setup_module_icons()
        self._run_pending_seed_import()

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

    def _run_pending_seed_import(self):
        """Run deferred seed import if flagged by install_blueprint()."""
        import logging
        from django.core.cache import cache

        logger = logging.getLogger(__name__)

        pending = cache.get('bp:pending_seed_import')
        if not pending:
            return

        # Clear flag immediately to avoid re-running on next restart
        cache.delete('bp:pending_seed_import')

        type_codes = pending.get('type_codes', [])
        language = pending.get('language', 'en')
        country = pending.get('country', 'es')

        if not type_codes:
            return

        try:
            from apps.core.services.blueprint_service import BlueprintService
            result = BlueprintService.import_seeds(
                type_codes=type_codes,
                language=language,
                country=country,
            )
            logger.info(
                'Deferred seed import complete: %s',
                result,
            )
        except Exception as e:
            logger.warning('Deferred seed import failed: %s', e)
