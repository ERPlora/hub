"""
Import seed products and images for configured business types.

Called as a subprocess by ensure_modules to ensure a fresh Django app registry
that includes dynamically loaded modules (inventory, etc.).
"""
import logging

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Import seed products and images for configured business types'

    def handle(self, *args, **options):
        try:
            from apps.configuration.models import HubConfig
            config = HubConfig.get_solo()

            type_codes = config.selected_business_types or []
            if not type_codes:
                self.stdout.write('No business types configured, skipping seed import')
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
            skipped = result.get('skipped', 0) if result else 0
            categories = result.get('categories', 0) if result else 0

            self.stdout.write(
                f'Seed import: {imported} imported, {skipped} skipped, '
                f'{categories} categories'
            )
        except Exception as e:
            self.stdout.write(self.style.WARNING(f'Seed import failed: {e}'))
            logger.exception('Seed import failed: %s', e)
