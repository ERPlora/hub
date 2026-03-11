"""
Blueprint Service for Hub.

Handles communication with Cloud Blueprint API for business type selection,
module computation, and seed product import during setup.
"""
import logging
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

CACHE_TTL = 300  # 5 min

# Compliance modules required per country (installed automatically during blueprint setup)
COMPLIANCE_MODULES = {
    'ES': ['verifactu', 'tax', 'gdpr'],
    'PT': ['tax', 'gdpr'],
    'FR': ['tax', 'gdpr'],
    'DE': ['tax', 'gdpr'],
    'IT': ['tax', 'gdpr'],
}


def _get_session():
    """Get a requests session with retry."""
    session = requests.Session()
    retry = Retry(total=2, backoff_factor=0.3, status_forcelist=[502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('https://', adapter)
    session.mount('http://', adapter)
    return session


def _cloud_url(path):
    """Build full Cloud API URL."""
    base = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
    return f'{base}/api/blueprints/{path}'


class BlueprintService:
    """Service for interacting with Cloud Blueprint API."""

    @classmethod
    def get_sectors(cls, language='en'):
        """GET /api/blueprints/sectors/ — returns list of business sectors."""
        cache_key = f'bp:sectors:{language}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            resp = _get_session().get(
                _cloud_url('sectors/'),
                params={'language': language},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_sectors failed: {e}')
            return []

    @classmethod
    def get_types(cls, sector=None, language='en'):
        """GET /api/blueprints/types/ — returns list of business types."""
        cache_key = f'bp:types:{sector or "all"}:{language}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            params = {'language': language}
            if sector:
                params['sector'] = sector
            resp = _get_session().get(
                _cloud_url('types/'),
                params=params,
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_types failed: {e}')
            return []

    @classmethod
    def get_type_detail(cls, code, language='en'):
        """GET /api/blueprints/types/<code>/ — returns full business type detail."""
        cache_key = f'bp:type:{code}:{language}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            resp = _get_session().get(
                _cloud_url(f'types/{code}/'),
                params={'language': language},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_type_detail failed: {e}')
            return None

    @classmethod
    def get_transversals(cls, language='en'):
        """GET /api/blueprints/transversals/ — returns transversal business models."""
        cache_key = f'bp:transversals:{language}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            resp = _get_session().get(
                _cloud_url('transversals/'),
                params={'language': language},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_transversals failed: {e}')
            return []

    @classmethod
    def get_functional_units(cls, language='en'):
        """GET /api/blueprints/functional-units/ — returns 12 UFOs."""
        cache_key = f'bp:ufos:{language}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            resp = _get_session().get(
                _cloud_url('functional-units/'),
                params={'language': language},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_functional_units failed: {e}')
            return []

    @classmethod
    def compute_modules(cls, type_codes):
        """
        POST /api/blueprints/types/compute/
        Merge multiple business types to get combined UFO matrix + modules + roles.
        """
        try:
            resp = _get_session().post(
                _cloud_url('types/compute/'),
                json={'types': type_codes},
                timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f'BlueprintService.compute_modules failed: {e}')
            return None

    @classmethod
    def get_products(cls, type_code, country='generic', language='en'):
        """GET /api/blueprints/products/<code>/ — returns seed products for a business type."""
        try:
            resp = _get_session().get(
                _cloud_url(f'products/{type_code}/'),
                params={'country': country, 'language': language},
                timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f'BlueprintService.get_products failed: {e}')
            return None

    @classmethod
    def get_tax_data(cls, country_code):
        """GET /api/blueprints/tax/<country_code>/ — returns tax presets for a country."""
        cache_key = f'bp:tax:{country_code}'
        data = cache.get(cache_key)
        if data is not None:
            return data
        try:
            resp = _get_session().get(
                _cloud_url(f'tax/{country_code}/'),
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            cache.set(cache_key, data, CACHE_TTL)
            return data
        except Exception as e:
            logger.error(f'BlueprintService.get_tax_data failed: {e}')
            return None

    @classmethod
    def resolve_modules_for_types(cls, type_codes, include_recommended=True):
        """
        Resolve which module slugs to install for given business types.
        Uses compute_modules() for UFO matrix + get_functional_units() for UFO→module mapping.
        Returns (module_slugs, compute_result) or (None, None) on failure.
        """
        result = cls.compute_modules(type_codes)
        if not result:
            return None, None

        ufo_matrix = result.get('ufo_matrix', {})
        extra_modules = result.get('extra_modules', [])

        # Build UFO → module slugs mapping from functional units
        ufo_data = cls.get_functional_units()
        ufo_to_modules = {}
        if isinstance(ufo_data, dict):
            for unit in ufo_data.get('units', []):
                ufo_to_modules[unit['code']] = unit.get('modules', [])

        # Collect module slugs from active UFOs
        module_slugs = set()
        accepted_levels = {'essential'}
        if include_recommended:
            accepted_levels.add('recommended')

        for ufo_code, level in ufo_matrix.items():
            if level in accepted_levels:
                for slug in ufo_to_modules.get(ufo_code, []):
                    module_slugs.add(slug)

        # Add extra modules (type-specific like kitchen, tables, etc.)
        module_slugs.update(extra_modules)

        logger.info(
            'Resolved %d modules for types %s (UFOs: %s, extras: %s)',
            len(module_slugs), type_codes,
            {k: v for k, v in ufo_matrix.items() if v in accepted_levels},
            extra_modules,
        )
        return sorted(module_slugs), result

    @classmethod
    def install_selected_modules(cls, hub_config, type_codes, module_slugs):
        """
        Install a specific list of module slugs (from Step 5 selection).
        Also creates roles from compute result and schedules seed import.
        """
        from apps.core.services.module_install_service import ModuleInstallService

        # Get compute result for roles
        result = cls.compute_modules(type_codes)

        cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
        hub_token = ModuleInstallService.get_hub_token()

        modules_to_install = [
            {
                'slug': slug,
                'name': slug,
                'download_url': f'{cloud_url}/api/marketplace/modules/{slug}/download/',
            }
            for slug in module_slugs
        ]

        install_result = ModuleInstallService.bulk_download_and_install(
            modules_to_install, hub_token,
        )

        if install_result.installed > 0:
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True, schedule_restart=True,
            )

        # Create roles from blueprint
        roles = result.get('roles', []) if result else []
        if roles and hub_config.hub_id:
            from apps.core.services.permission_service import PermissionService
            PermissionService.create_blueprint_roles(str(hub_config.hub_id), roles)

        # Schedule seed import for after restart
        if install_result.installed > 0:
            cls._write_pending_seed_flag({
                'type_codes': type_codes,
                'language': getattr(hub_config, 'language', 'en') or 'en',
                'country': getattr(hub_config, 'country_code', 'es') or 'es',
            })
            logger.info('Seed import deferred until after restart')
        else:
            try:
                seed_result = cls.import_seeds(
                    type_codes=type_codes,
                    language=getattr(hub_config, 'language', 'en') or 'en',
                    country=getattr(hub_config, 'country_code', 'es') or 'es',
                )
            except Exception as e:
                logger.warning('Seed import failed: %s', e)

        return {
            'success': True,
            'modules_installed': install_result.installed,
            'module_errors': install_result.errors,
            'roles_created': len(roles),
        }

    @classmethod
    def install_blueprint(cls, hub_config, type_codes, include_recommended=True):
        """
        Compute modules for given types, then install them.
        Returns dict with installed modules and roles.
        """
        from apps.core.services.module_install_service import ModuleInstallService

        module_slugs, result = cls.resolve_modules_for_types(
            type_codes, include_recommended,
        )
        if not result:
            return {'success': False, 'error': 'Failed to compute modules'}

        # Build install list with download URLs
        cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
        hub_token = ModuleInstallService.get_hub_token()

        modules_to_install = []
        for slug in module_slugs:
            modules_to_install.append({
                'slug': slug,
                'name': slug,
                'download_url': f'{cloud_url}/api/marketplace/modules/{slug}/download/',
            })

        # Install modules
        install_result = ModuleInstallService.bulk_download_and_install(
            modules_to_install, hub_token,
        )

        # Install compliance modules for the hub's country
        compliance_installed = 0
        country_code = (getattr(hub_config, 'country_code', '') or '').upper()
        compliance_slugs = COMPLIANCE_MODULES.get(country_code, [])
        if compliance_slugs:
            # Only install compliance modules not already in the blueprint list
            existing_slugs = set(module_slugs)
            extra_compliance = [s for s in compliance_slugs if s not in existing_slugs]
            if extra_compliance:
                compliance_to_install = [
                    {
                        'slug': slug,
                        'name': slug,
                        'download_url': f'{cloud_url}/api/marketplace/modules/{slug}/download/',
                    }
                    for slug in extra_compliance
                ]
                compliance_result = ModuleInstallService.bulk_download_and_install(
                    compliance_to_install, hub_token,
                )
                compliance_installed = compliance_result.installed
                if compliance_installed > 0:
                    logger.info(
                        'Installed %d compliance modules for %s: %s',
                        compliance_installed, country_code, extra_compliance,
                    )

        # Create roles from blueprint
        roles = result.get('roles', [])
        if roles and hub_config.hub_id:
            from apps.core.services.permission_service import PermissionService
            PermissionService.create_blueprint_roles(str(hub_config.hub_id), roles)

        # Schedule seed import for after restart (inventory module not loaded yet)
        seeds_imported = 0
        total_installed = install_result.installed + compliance_installed
        if total_installed > 0:
            # Modules were just installed — inventory won't be available until restart.
            # Write a flag file so the next boot runs import_seeds().
            cls._write_pending_seed_flag({
                'type_codes': type_codes,
                'language': getattr(hub_config, 'language', 'en') or 'en',
                'country': getattr(hub_config, 'country_code', 'es') or 'es',
            })
            logger.info('Seed import deferred until after restart')
            ModuleInstallService.run_post_install(
                load_all=True, run_migrations=True, schedule_restart=True,
            )
        else:
            # No new modules installed — inventory should already be loaded.
            try:
                seed_result = cls.import_seeds(
                    type_codes=type_codes,
                    language=getattr(hub_config, 'language', 'en') or 'en',
                    country=getattr(hub_config, 'country_code', 'es') or 'es',
                )
                seeds_imported = seed_result.get('imported', 0)
            except Exception as e:
                logger.warning('Seed import failed during install_blueprint: %s', e)

        logger.info(
            'install_blueprint for %s: %s',
            ', '.join(type_codes),
            {
                'success': True,
                'modules_installed': install_result.installed,
                'compliance_installed': compliance_installed,
                'module_errors': install_result.errors,
                'roles_created': len(roles),
                'seeds_imported': seeds_imported,
            },
        )

        return {
            'success': True,
            'modules_installed': install_result.installed,
            'compliance_installed': compliance_installed,
            'module_errors': install_result.errors,
            'roles_created': len(roles),
            'seeds_imported': seeds_imported,
        }

    @classmethod
    def import_seeds(cls, type_codes, language='en', country='es'):
        """
        Import seed categories and products for business types.
        Idempotent: skips existing categories (by code) and products (by SKU).
        """
        try:
            from django.apps import apps
            apps.get_model('inventory', 'Product')
        except LookupError:
            logger.warning('Inventory module not installed, skipping seed import')
            return {'imported': 0, 'skipped': 0, 'categories': 0}

        tax_class_mapping = cls._build_tax_class_mapping()

        imported = 0
        skipped = 0
        categories_created = 0

        for type_code in type_codes:
            products_data = cls.get_products(type_code, country=country, language=language)
            if not products_data:
                continue

            categories = products_data.get('categories', [])
            products = products_data.get('products', [])

            # Import categories, build code → instance map
            category_map = {}
            for cat_data in categories:
                cat, created = cls._import_category(cat_data, tax_class_mapping)
                if cat:
                    category_map[cat.code] = cat
                    if created:
                        categories_created += 1

            # Import products
            for prod_data in products:
                was_imported = cls._import_product(
                    prod_data,
                    tax_class_mapping=tax_class_mapping,
                    category_map=category_map,
                )
                if was_imported:
                    imported += 1
                else:
                    skipped += 1

        logger.info(
            'Seed import complete: %d products imported, %d skipped, %d categories',
            imported, skipped, categories_created,
        )
        return {'imported': imported, 'skipped': skipped, 'categories': categories_created}

    @classmethod
    def import_selected_products(cls, type_codes, product_codes, language='en', country='es'):
        """
        Import specific products for business types.
        If product_codes is ['*'], imports all products (same as import_seeds).
        Otherwise, only imports products whose code is in product_codes.
        Images are downloaded with per-image error handling (failures don't block import).
        """
        import_all = product_codes == ['*']

        try:
            from django.apps import apps
            apps.get_model('inventory', 'Product')
        except LookupError:
            logger.warning('Inventory module not installed, skipping selective product import')
            return {'imported': 0, 'skipped': 0, 'categories': 0}

        tax_class_mapping = cls._build_tax_class_mapping()

        imported = 0
        skipped = 0
        categories_created = 0

        for type_code in type_codes:
            products_data = cls.get_products(type_code, country=country, language=language)
            if not products_data:
                continue

            categories = products_data.get('categories', [])
            products = products_data.get('products', [])

            # Filter products by code unless importing all
            if not import_all:
                product_code_set = set(product_codes)
                products = [p for p in products if p.get('code') in product_code_set]

            if not products:
                continue

            # Import categories referenced by the selected products
            needed_category_codes = {p.get('category', '') for p in products} - {''}
            category_map = {}
            for cat_data in categories:
                if import_all or cat_data.get('code', '') in needed_category_codes:
                    cat, created = cls._import_category(cat_data, tax_class_mapping)
                    if cat:
                        category_map[cat.code] = cat
                        if created:
                            categories_created += 1

            # Import products
            for prod_data in products:
                was_imported = cls._import_product(
                    prod_data,
                    tax_class_mapping=tax_class_mapping,
                    category_map=category_map,
                )
                if was_imported:
                    imported += 1
                else:
                    skipped += 1

        logger.info(
            'Selective product import complete: %d products imported, %d skipped, %d categories',
            imported, skipped, categories_created,
        )
        return {'imported': imported, 'skipped': skipped, 'categories': categories_created}

    @classmethod
    def _build_tax_class_mapping(cls):
        """Map blueprint tax_class_hint strings to TaxClass records.
        Priority: 1) code field (deterministic), 2) name heuristic, 3) rate fallback."""
        from apps.configuration.models import TaxClass

        tax_classes = list(TaxClass.objects.filter(is_active=True).order_by('rate'))
        if not tax_classes:
            return {}

        mapping = {}

        # 1. Code-based matching (deterministic, preferred)
        for tc in tax_classes:
            if tc.code:
                mapping.setdefault(tc.code, tc)

        # If code-based mapping found all expected keys, return early
        if all(k in mapping for k in ['general', 'reduced', 'exempt']):
            # Map 'standard' as alias for 'general' for backward compatibility
            mapping.setdefault('standard', mapping.get('general'))
            return mapping

        # 2. Name-based matching fallback
        for tc in tax_classes:
            name_lower = tc.name.lower()
            if any(k in name_lower for k in ['general', 'standard', 'normal']):
                mapping.setdefault('standard', tc)
                mapping.setdefault('general', tc)
            elif any(k in name_lower for k in ['super', 'superreducido', 'super-reducido']):
                mapping.setdefault('super_reduced', tc)
            elif any(k in name_lower for k in ['reducido', 'reduced', 'ermäßigt']):
                mapping.setdefault('reduced', tc)
            elif any(k in name_lower for k in ['exento', 'exempt', 'zero', 'cero']):
                mapping.setdefault('exempt', tc)

        # 3. Rate-based heuristic fallback
        if 'standard' not in mapping and 'general' not in mapping:
            tc = max(tax_classes, key=lambda t: t.rate)
            mapping['standard'] = tc
            mapping['general'] = tc
        if 'exempt' not in mapping:
            zero_rate = [t for t in tax_classes if float(t.rate) == 0]
            if zero_rate:
                mapping['exempt'] = zero_rate[0]
        if 'reduced' not in mapping:
            mid = [t for t in tax_classes if t != mapping.get('standard') and t != mapping.get('exempt')]
            if mid:
                mapping['reduced'] = mid[0]

        return mapping

    @classmethod
    def _import_category(cls, cat_data, tax_class_mapping=None):
        """Import a single category, skip if code already exists. Returns (category, created)."""
        try:
            from django.apps import apps
            Category = apps.get_model('inventory', 'Category')

            code = cat_data.get('code', '')
            if not code:
                return None, False

            # Resolve tax_class from hint
            tax_class = None
            hint = cat_data.get('tax_class_hint', '')
            if hint and tax_class_mapping:
                tax_class = tax_class_mapping.get(hint)

            category, created = Category.objects.get_or_create(
                code=code,
                defaults={
                    'name': cat_data.get('name', code),
                    'description': cat_data.get('description', ''),
                    'icon': cat_data.get('icon', 'cube-outline'),
                    'sort_order': cat_data.get('order', 0),
                    'tax_class': tax_class,
                },
            )
            return category, created
        except Exception as e:
            logger.warning('Failed to import category %s: %s', cat_data.get('code', '?'), e)
            return None, False

    @classmethod
    def _import_product(cls, prod_data, tax_class_mapping=None, category_map=None):
        """Import a single product. Skip if SKU already exists. Returns True if imported."""
        try:
            from django.apps import apps
            Product = apps.get_model('inventory', 'Product')

            code = prod_data.get('code', '')
            if not code:
                return False

            # Idempotency: skip if SKU already exists
            if Product.objects.filter(sku=code).exists():
                return False

            # Resolve tax_class from hint
            tax_class = None
            hint = prod_data.get('tax_class_hint', '')
            if hint and tax_class_mapping:
                tax_class = tax_class_mapping.get(hint)

            product = Product.objects.create(
                sku=code,
                name=prod_data.get('name', code),
                description=prod_data.get('description', ''),
                price=prod_data.get('price', 0),
                tax_class=tax_class,
                source='blueprint',
            )

            # Set category M2M
            category_code = prod_data.get('category', '')
            if category_code and category_map:
                category = category_map.get(category_code)
                if category:
                    product.categories.add(category)

            # Download and save product image
            image_path = prod_data.get('image', '')
            if image_path:
                cls._download_and_save_image(product, image_path)

            return True
        except Exception as e:
            logger.warning('Failed to import product %s: %s', prod_data.get('code', '?'), e)
            return False

    @classmethod
    def _download_and_save_image(cls, product, image_path):
        """Download a product image from Cloud Blueprint API and save to ImageField."""
        from django.core.files.base import ContentFile

        if not image_path:
            return

        try:
            url = _cloud_url(f'assets/{image_path}')
            resp = _get_session().get(url, timeout=15)
            resp.raise_for_status()

            filename = image_path.split('/')[-1]
            product.image.save(filename, ContentFile(resp.content), save=True)
        except Exception as e:
            logger.warning('Failed to download image %s for product %s: %s', image_path, product.sku, e)

    @staticmethod
    def _pending_seed_flag_path():
        """Path to the pending seed import flag file (survives process restart)."""
        from pathlib import Path
        data_dir = getattr(settings, 'DATA_DIR', None)
        if data_dir:
            return Path(data_dir) / '.pending_seed_import.json'
        return Path('/tmp/.pending_seed_import.json')

    @classmethod
    def _write_pending_seed_flag(cls, data):
        """Write pending seed import data to a flag file."""
        import json
        path = cls._pending_seed_flag_path()
        try:
            path.write_text(json.dumps(data))
        except Exception as e:
            logger.warning('Failed to write pending seed flag: %s', e)

    @classmethod
    def read_and_clear_pending_seed_flag(cls):
        """Read and delete the pending seed import flag file. Returns dict or None."""
        import json
        path = cls._pending_seed_flag_path()
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            path.unlink()
            return data
        except Exception as e:
            logger.warning('Failed to read pending seed flag: %s', e)
            try:
                path.unlink()
            except OSError:
                pass
            return None
