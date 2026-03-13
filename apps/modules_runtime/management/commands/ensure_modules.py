"""
Ensure all modules are installed on startup.

On AWS App Runner, the container filesystem is ephemeral — modules in
MODULES_DIR are lost on every restart. This command restores them by:

1. Checking if MODULES_DIR already has modules (fast exit for local dev)
2. Querying Cloud for the authoritative list of installed modules
3. Falling back to blueprint recomputation if Cloud is unreachable
4. Bulk-downloading all modules in parallel
5. Disabling (prefix with _) any modules marked inactive in Cloud
6. Running migrations for the restored modules

Runs automatically at container startup, before gunicorn.
"""
import logging
from pathlib import Path

import requests as http_requests
from django.conf import settings
from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Ensure all modules are installed (restore from Cloud on container restart)'

    def handle(self, *args, **options):
        modules_dir = Path(getattr(settings, 'MODULES_DIR', ''))
        if not modules_dir.exists():
            self.stdout.write('MODULES_DIR does not exist, skipping')
            return

        # Fast path: if modules already present, just ensure seeds
        existing = [
            d for d in modules_dir.iterdir()
            if d.is_dir() and not d.name.startswith('.')
        ]
        if len(existing) > 1:
            self.stdout.write(f'{len(existing)} modules already present, skipping restore')
            # Still import seeds (images lost on ephemeral filesystem)
            self._import_seeds()
            return

        self.stdout.write('Modules directory is empty, restoring...')

        hub_token = self._get_hub_token()
        cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')

        # Try Cloud first, fallback to blueprints
        # modules_info: list of {'slug': str, 'is_active': bool}
        modules_info = self._fetch_from_cloud(cloud_url, hub_token)
        if modules_info is None:
            self.stdout.write('Cloud unreachable, falling back to blueprint recomputation')
            modules_info = self._fallback_from_blueprints(cloud_url, hub_token)

        if not modules_info:
            # If hub is not configured yet, at minimum install the assistant
            try:
                from apps.configuration.models import HubConfig
                config = HubConfig.get_solo()
                if not config.is_configured:
                    self.stdout.write('Hub not configured, ensuring assistant module')
                    modules_info = [{'slug': 'assistant', 'is_active': True}]
                else:
                    self.stdout.write('No modules to restore')
                    return
            except Exception:
                self.stdout.write('No modules to restore')
                return

        all_slugs = [m['slug'] for m in modules_info]
        inactive_slugs = {m['slug'] for m in modules_info if not m['is_active']}

        self.stdout.write(
            f'Restoring {len(all_slugs)} modules ({len(inactive_slugs)} inactive)...'
        )

        # Build install list (download ALL modules, active and inactive)
        modules_to_install = [
            {
                'slug': slug,
                'name': slug,
                'download_url': f'{cloud_url}/api/marketplace/modules/{slug}/download/',
            }
            for slug in all_slugs
        ]

        # Bulk download
        from apps.core.services.module_install_service import ModuleInstallService

        result = ModuleInstallService.bulk_download_and_install(
            modules_to_install, hub_token, max_workers=4,
        )

        if result.errors:
            for err in result.errors:
                self.stdout.write(self.style.WARNING(f'  Error: {err}'))

        # Disable inactive modules (rename to _slug)
        for slug in inactive_slugs:
            active_dir = modules_dir / slug
            inactive_dir = modules_dir / f'_{slug}'
            if active_dir.exists() and not inactive_dir.exists():
                active_dir.rename(inactive_dir)
                self.stdout.write(f'  Disabled: {slug}')

        # Run migrations for restored modules
        if result.installed > 0:
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True, schedule_restart=False,
            )

        # Import seed products (categories, products, images)
        # On App Runner the flag file is lost on restart, so always try after restore
        if result.installed > 0:
            self._import_seeds()

        self.stdout.write(self.style.SUCCESS(
            f'Module restore complete: {result.installed} installed, {len(result.errors)} errors'
        ))

    def _import_seeds(self):
        """Import seed products and images for configured business types."""
        try:
            from apps.configuration.models import HubConfig
            config = HubConfig.get_solo()

            type_codes = config.selected_business_types or []
            if not type_codes:
                return

            language = config.language or 'en'
            country = (config.country_code or 'es').lower()

            from apps.core.services.blueprint_service import BlueprintService
            result = BlueprintService.import_seeds(
                type_codes=type_codes,
                language=language,
                country=country,
            )
            imported = result.get('imported', 0) if result else 0
            self.stdout.write(f'Seed import: {imported} products imported')
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Seed import failed: {e}'))

    def _get_hub_token(self):
        """Resolve hub JWT token from settings or database."""
        token = getattr(settings, 'HUB_JWT', '') or ''
        if not token:
            try:
                from apps.configuration.models import HubConfig
                token = HubConfig.get_solo().hub_jwt or ''
            except Exception:
                pass
        return token

    def _fetch_from_cloud(self, cloud_url, hub_token):
        """Fetch installed module list from Cloud API.

        Returns list of dicts {'slug': str, 'is_active': bool}, or None on failure.
        """
        if not hub_token:
            return None

        url = f'{cloud_url}/api/marketplace/hub-modules/'
        headers = {
            'X-Hub-Token': hub_token,
            'Accept': 'application/json',
        }

        try:
            resp = http_requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                logger.warning(
                    '[ensure_modules] Cloud hub-modules returned %d', resp.status_code
                )
                return None

            data = resp.json()
            results = data.get('results', data) if isinstance(data, dict) else data
            if not isinstance(results, list):
                return None

            modules = []
            for item in results:
                slug = item.get('module_slug', '')
                if slug:
                    modules.append({
                        'slug': slug,
                        'is_active': item.get('is_active', True),
                    })

            active = sum(1 for m in modules if m['is_active'])
            inactive = len(modules) - active
            self.stdout.write(
                f'Cloud reports {len(modules)} modules ({active} active, {inactive} inactive)'
            )
            return modules

        except Exception as e:
            logger.warning('[ensure_modules] Cloud fetch failed: %s', e)
            return None

    def _fallback_from_blueprints(self, cloud_url, hub_token):
        """Recompute module list from HubConfig business types.

        Returns list of dicts {'slug': str, 'is_active': bool}, or empty list.
        All modules from blueprint fallback are assumed active.
        """
        try:
            from apps.configuration.models import HubConfig
            config = HubConfig.get_solo()
        except Exception:
            return []

        type_codes = config.selected_business_types or []
        country_code = (config.country_code or '').upper()

        if not type_codes:
            # Hub not configured yet — only ensure assistant
            return [{'slug': 'assistant', 'is_active': True}]

        try:
            from apps.core.services.blueprint_service import (
                BlueprintService, COMPLIANCE_MODULES,
            )

            module_slugs, _ = BlueprintService.resolve_modules_for_types(
                type_codes, include_recommended=True,
            )
            if not module_slugs:
                return [{'slug': 'assistant', 'is_active': True}]

            # Add compliance modules
            compliance = COMPLIANCE_MODULES.get(country_code, [])
            all_slugs = set(module_slugs)
            for slug in compliance:
                all_slugs.add(slug)

            # Always include assistant
            all_slugs.add('assistant')

            self.stdout.write(
                f'Blueprint recomputed {len(all_slugs)} modules '
                f'from types={type_codes}, country={country_code}'
            )
            return [{'slug': s, 'is_active': True} for s in sorted(all_slugs)]

        except Exception as e:
            logger.warning('[ensure_modules] Blueprint fallback failed: %s', e)
            return [{'slug': 'assistant', 'is_active': True}]
