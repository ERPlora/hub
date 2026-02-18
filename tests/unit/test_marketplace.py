"""
Unit tests for the marketplace views.

Tests the multi-store marketplace with modules, hubs, cart, and filters.
URL patterns (app_name='marketplace'):
- marketplace:index -> /marketplace/
- marketplace:module_detail -> /marketplace/<slug>/
- marketplace:products_list -> /marketplace/products/ (HTMX)
- marketplace:cart_page -> /marketplace/cart/
- marketplace:cart_add -> /marketplace/cart/add/
- marketplace:cart_remove -> /marketplace/cart/remove/<item_id>/
- marketplace:cart_clear -> /marketplace/cart/clear/
- marketplace:store_hubs -> /marketplace/hubs/
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse


pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _mock_cloud_modules_response():
    """Return a mock response with module data from Cloud API."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            'id': 'mod-1',
            'name': 'Inventory',
            'slug': 'inventory',
            'description': 'Manage your stock',
            'category': 'operations',
            'industries': ['retail'],
            'module_type': 'free',
            'price': 0,
            'tags': ['stock', 'warehouse'],
            'is_free': True,
        },
        {
            'id': 'mod-2',
            'name': 'Sales',
            'slug': 'sales',
            'description': 'Point of sale module',
            'category': 'pos',
            'industries': ['retail', 'hospitality'],
            'module_type': 'one_time',
            'price': 49.99,
            'tags': ['pos', 'checkout'],
            'is_free': False,
        },
    ]
    return mock_response


def _mock_cloud_module_detail_response(slug='inventory'):
    """Return a mock response with single module details."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        'id': 'mod-1',
        'name': 'Inventory',
        'slug': slug,
        'description': 'Manage your stock and warehouse operations.',
        'category': 'operations',
        'industries': ['retail'],
        'module_type': 'free',
        'price': 0,
        'version': '1.2.0',
        'author': 'ERPlora',
        'is_free': True,
        'is_owned': False,
        'screenshots': [],
        'changelog': 'Initial release',
    }
    return mock_response


def _mock_categories_response():
    """Return mock categories response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {'id': 'operations', 'name': 'Operations'},
        {'id': 'pos', 'name': 'Point of Sale'},
    ]
    return mock_response


def _mock_industries_response():
    """Return mock industries response."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {'id': 'retail', 'name': 'Retail'},
        {'id': 'hospitality', 'name': 'Hospitality'},
    ]
    return mock_response


class TestMarketplaceIndex:
    """Tests for the marketplace index page."""

    @patch('apps.marketplace.views.requests.get')
    def test_marketplace_page_loads(self, mock_get, authenticated_client, hub_config):
        """Marketplace page should load with 200 for authenticated users."""
        mock_get.side_effect = [
            _mock_categories_response(),
            _mock_industries_response(),
        ]

        url = reverse('marketplace:index')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    @patch('apps.marketplace.views.requests.get')
    def test_htmx_request_returns_partial(self, mock_get, authenticated_client, hub_config):
        """HTMX requests should return a partial (no DOCTYPE)."""
        mock_get.side_effect = [
            _mock_categories_response(),
            _mock_industries_response(),
        ]

        url = reverse('marketplace:index')
        response = authenticated_client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert '<!DOCTYPE' not in content


class TestModuleDetail:
    """Tests for the module detail page."""

    @patch('apps.marketplace.views.requests.get')
    def test_module_detail_loads_with_mock_api(self, mock_get, authenticated_client, hub_config):
        """Module detail page should load with mock Cloud API data."""
        # Set up hub_config with a JWT token so the view tries the API
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        # Mock: detail request, ownership request, related modules request
        mock_get.side_effect = [
            _mock_cloud_module_detail_response('inventory'),
            MagicMock(status_code=200, json=MagicMock(return_value={'is_owned': False})),
            _mock_cloud_modules_response(),
        ]

        url = reverse('marketplace:module_detail', kwargs={'slug': 'inventory'})
        response = authenticated_client.get(url)

        assert response.status_code == 200


class TestProductsList:
    """Tests for the products list HTMX endpoint."""

    @patch('apps.marketplace.views.requests.get')
    def test_products_list_htmx_endpoint(self, mock_get, authenticated_client, hub_config):
        """Products list HTMX endpoint should return module cards."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_get.return_value = _mock_cloud_modules_response()

        url = reverse('marketplace:products_list')
        response = authenticated_client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200


class TestCartPage:
    """Tests for the cart page."""

    def test_cart_page_loads(self, authenticated_client, hub_config):
        """Cart page should load for authenticated users."""
        url = reverse('marketplace:cart_page')
        response = authenticated_client.get(url)

        assert response.status_code == 200


class TestCartOperations:
    """Tests for cart add, remove, and clear operations."""

    def test_cart_add(self, authenticated_client, hub_config):
        """Adding an item to the cart should succeed."""
        url = reverse('marketplace:cart_add')
        response = authenticated_client.post(
            url,
            data=json.dumps({
                'item_id': 'mod-1',
                'item_name': 'Inventory Module',
                'item_price': 49.99,
                'item_icon': 'cube-outline',
                'quantity': 1,
            }),
            content_type='application/json',
        )

        assert response.status_code == 200

    def test_cart_remove(self, authenticated_client, hub_config):
        """Removing an item from the cart should succeed."""
        # First add an item
        add_url = reverse('marketplace:cart_add')
        authenticated_client.post(
            add_url,
            data=json.dumps({
                'item_id': 'mod-1',
                'item_name': 'Inventory Module',
                'item_price': 49.99,
                'quantity': 1,
            }),
            content_type='application/json',
        )

        # Then remove it
        remove_url = reverse('marketplace:cart_remove', kwargs={'item_id': 'mod-1'})
        response = authenticated_client.delete(remove_url)

        assert response.status_code == 200

    def test_cart_clear(self, authenticated_client, hub_config):
        """Clearing the cart should succeed."""
        # First add an item
        add_url = reverse('marketplace:cart_add')
        authenticated_client.post(
            add_url,
            data=json.dumps({
                'item_id': 'mod-1',
                'item_name': 'Inventory Module',
                'item_price': 49.99,
                'quantity': 1,
            }),
            content_type='application/json',
        )

        # Clear the cart (store_type is passed via URL kwargs, not reverse args)
        clear_url = reverse('marketplace:cart_clear')
        response = authenticated_client.delete(clear_url)

        assert response.status_code == 200


class TestMarketplaceAuth:
    """Tests for marketplace authentication requirements."""

    def test_unauthenticated_redirects_to_login(self, client, db, store_config):
        """Unauthenticated users should be redirected to the login page."""
        url = reverse('marketplace:index')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_cart_page_requires_auth(self, client, db, store_config):
        """Cart page should require authentication."""
        url = reverse('marketplace:cart_page')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_cart_add_requires_auth(self, client, db, store_config):
        """Cart add should require authentication."""
        url = reverse('marketplace:cart_add')
        response = client.post(
            url,
            data=json.dumps({'item_id': 'mod-1', 'item_name': 'Test', 'item_price': 10}),
            content_type='application/json',
        )

        assert response.status_code == 302
        assert '/login/' in response.url


class TestHubsStore:
    """Tests for the hubs store page."""

    @patch('apps.marketplace.views.requests.get')
    def test_hubs_store_page_loads(self, mock_get, authenticated_client, hub_config):
        """Hubs store page should load with 200."""
        # Mock Cloud API calls for filters (categories/industries may still be fetched)
        mock_get.side_effect = [
            _mock_categories_response(),
            _mock_industries_response(),
        ]

        url = reverse('marketplace:store_hubs')
        response = authenticated_client.get(url)

        assert response.status_code == 200
