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
        if roles:
            from apps.core.services.permission_service import PermissionService
            PermissionService.create_blueprint_roles(roles)

        return {
            'success': True,
            'modules_installed': install_result,
            'roles_created': len(roles),
        }

    @classmethod
    def import_seeds(cls, type_codes, language, country, tax_class_mapping=None):
        """
        Import seed products for business types.
        Skips existing products by code (never overwrites).
        """
        imported = 0
        skipped = 0

        for type_code in type_codes:
            products_data = cls.get_products(type_code, country=country, language=language)
            if not products_data:
                continue

            categories = products_data.get('categories', [])
            products = products_data.get('products', [])

            # Import categories
            for cat_data in categories:
                cls._import_category(cat_data)

            # Import products
            for prod_data in products:
                was_imported = cls._import_product(prod_data, tax_class_mapping)
                if was_imported:
                    imported += 1
                else:
                    skipped += 1

        return {'imported': imported, 'skipped': skipped}

    @classmethod
    def _import_category(cls, cat_data):
        """Import a single category, skip if code already exists."""
        try:
            from apps.modules_runtime.loader import get_model
            Category = get_model('inventory', 'Category')
            if Category is None:
                return
            code = cat_data.get('code', '')
            if not code:
                return
            Category.objects.get_or_create(
                code=code,
                defaults={
                    'name': cat_data.get('name', code),
                    'description': cat_data.get('description', ''),
                }
            )
        except Exception as e:
            logger.warning(f'Failed to import category {cat_data}: {e}')

    @classmethod
    def _import_product(cls, prod_data, tax_class_mapping=None):
        """Import a single product, skip if code already exists. Returns True if imported."""
        try:
            from apps.modules_runtime.loader import get_model
            Product = get_model('inventory', 'Product')
            if Product is None:
                return False
            code = prod_data.get('code', '')
            if not code:
                return False
            if Product.objects.filter(code=code).exists():
                return False
            # Map blueprint unit/is_weighable to model fields
            unit = prod_data.get('unit', 'unit')
            is_weighable = prod_data.get('is_weighable', False)

            Product.objects.create(
                code=code,
                name=prod_data.get('name', code),
                description=prod_data.get('description', ''),
                price=prod_data.get('price', 0),
                unit_of_measure=unit if unit else 'unit',
                sold_by_weight=bool(is_weighable),
                source='blueprint',
            )
            return True
        except Exception as e:
            logger.warning(f'Failed to import product {prod_data}: {e}')
            return False
