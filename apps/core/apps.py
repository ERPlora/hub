from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.core'
    verbose_name = _('Core')

    def ready(self):
        """Initialize core app when Django is ready."""
        self._setup_module_icons()
        self._register_choosers()
        self._run_pending_seed_import()
        self._run_deferred_setup()

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

    def _register_choosers(self):
        """Register core model choosers."""
        from apps.core.chooser import chooser_registry
        from apps.accounts.models import LocalUser

        def employee_queryset(request):
            hub_id = request.session.get('hub_id') if request else None
            qs = LocalUser.objects.filter(is_deleted=False, is_active=True)
            if hub_id:
                qs = qs.filter(hub_id=hub_id)
            return qs.order_by('name')

        chooser_registry.register(LocalUser, {
            'search_fields': ['name', 'email'],
            'icon': 'person-outline',
            'label': 'Employees',
            'order_by': ['name'],
            'per_page': 20,
            'subtitle_field': 'email',
            'queryset_fn': employee_queryset,
        })

    def _run_pending_seed_import(self):
        """Run deferred seed import if flagged by install_blueprint()."""
        import logging

        logger = logging.getLogger(__name__)

        try:
            from apps.core.services.blueprint_service import BlueprintService
            pending = BlueprintService.read_and_clear_pending_seed_flag()
        except Exception:
            return

        if not pending:
            return

        type_codes = pending.get('type_codes', [])
        language = pending.get('language', 'en')
        country = pending.get('country', 'es')

        if not type_codes:
            return

        try:
            result = BlueprintService.import_seeds(
                type_codes=type_codes,
                language=language,
                country=country,
            )
            logger.info('Deferred seed import complete: %s', result)
        except Exception as e:
            logger.warning('Deferred seed import failed: %s', e)

    def _run_deferred_setup(self):
        """Run deferred setup tasks (payment methods, invoice series) after restart."""
        import json
        import logging
        from pathlib import Path

        logger = logging.getLogger(__name__)

        try:
            from django.conf import settings
            data_dir = getattr(settings, 'DATA_DIR', None)
            flag_path = Path(data_dir) / '.pending_setup.json' if data_dir else Path('/tmp/.pending_setup.json')

            if not flag_path.exists():
                return

            data = json.loads(flag_path.read_text())
            flag_path.unlink()
        except Exception:
            return

        try:
            from apps.setup.services import SetupService
            pm = SetupService.create_payment_methods()
            inv = SetupService.create_invoice_series()
            logger.info('Deferred setup complete: %d payment methods, %d invoice series', pm, inv)
        except Exception as e:
            logger.warning('Deferred setup failed: %s', e)
