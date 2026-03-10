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
    def install_blueprint(cls, hub_config, type_codes, include_recommended=True):
        """
        Compute modules for given types, then install them.
        Returns dict with installed modules and roles.
        """
        from apps.core.services.module_install_service import ModuleInstallService

        result = cls.compute_modules(type_codes)
        if not result:
            return {'success': False, 'error': 'Failed to compute modules'}

        # Collect module IDs to install
        module_ids = []
        ufo_matrix = result.get('ufo_matrix', {})
        for ufo_code, level in ufo_matrix.items():
            if level in ('essential', 'recommended' if include_recommended else 'essential'):
                pass  # UFO matrix doesn't directly map to module_ids

        # Use extra_modules from the result
        extra_modules = result.get('extra_modules', [])
        module_ids.extend(extra_modules)

        # Install modules
        install_result = ModuleInstallService.bulk_download_and_install(module_ids)

        # Create roles from blueprint
        roles = result.get('roles', [])
        if roles and hub_config.hub_id:
            from apps.core.services.permission_service import PermissionService
            PermissionService.create_blueprint_roles(str(hub_config.hub_id), roles)

        # Import seed products
        seed_result = {'imported': 0, 'skipped': 0, 'categories': 0}
        try:
            seed_result = cls.import_seeds(
                type_codes=type_codes,
                language=getattr(hub_config, 'language', 'en') or 'en',
                country=getattr(hub_config, 'country_code', 'es') or 'es',
            )
        except Exception as e:
            logger.warning('Seed import failed during install_blueprint: %s', e)

        return {
            'success': True,
            'modules_installed': install_result,
            'roles_created': len(roles),
            'seeds_imported': seed_result.get('imported', 0),
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
    def _build_tax_class_mapping(cls):
        """Map blueprint tax_class_hint strings to TaxClass records."""
        from apps.configuration.models import TaxClass

        tax_classes = list(TaxClass.objects.filter(is_active=True).order_by('rate'))
        if not tax_classes:
            return {}

        mapping = {}

        # Name-based matching (works for Spanish: "General 21%", "Reducido 10%")
        for tc in tax_classes:
            name_lower = tc.name.lower()
            if any(k in name_lower for k in ['general', 'standard', 'normal']):
                mapping.setdefault('standard', tc)
            elif any(k in name_lower for k in ['super', 'superreducido', 'super-reducido']):
                mapping.setdefault('super_reduced', tc)
            elif any(k in name_lower for k in ['reducido', 'reduced', 'ermäßigt']):
                mapping.setdefault('reduced', tc)
            elif any(k in name_lower for k in ['exento', 'exempt', 'zero', 'cero']):
                mapping.setdefault('exempt', tc)

        # Fallback: rate-based heuristic
        if 'standard' not in mapping:
            mapping['standard'] = max(tax_classes, key=lambda t: t.rate)
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
            url = _cloud_url(f'assets/products/{image_path}')
            resp = _get_session().get(url, timeout=15)
            resp.raise_for_status()

            filename = image_path.split('/')[-1]
            product.image.save(filename, ContentFile(resp.content), save=True)
        except Exception as e:
            logger.warning('Failed to download image %s for product %s: %s', image_path, product.sku, e)
