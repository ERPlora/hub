"""
Unit tests for the marketplace views.

Tests the multi-store marketplace with modules, hubs, and filters.
URL patterns (app_name='marketplace'):
- marketplace:index -> /marketplace/
- marketplace:module_detail -> /marketplace/<slug>/
- marketplace:products_list -> /marketplace/products/ (HTMX)
- marketplace:module_purchase -> /marketplace/purchase/ (POST)
- marketplace:store_hubs -> /marketplace/hubs/
- marketplace:my_purchases -> /marketplace/purchases/
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


class TestModulePurchase:
    """Tests for the module purchase endpoint."""

    @patch('apps.marketplace.views.requests.post')
    def test_purchase_requires_post(self, mock_post, authenticated_client, hub_config):
        """Purchase endpoint should reject GET requests."""
        url = reverse('marketplace:module_purchase')
        response = authenticated_client.get(url)

        assert response.status_code == 405

    @patch('apps.marketplace.views.requests.post')
    def test_purchase_requires_module_id(self, mock_post, authenticated_client, hub_config):
        """Purchase endpoint should require module_id."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        url = reverse('marketplace:module_purchase')
        response = authenticated_client.post(
            url,
            data=json.dumps({'module_slug': 'sales'}),
            content_type='application/json',
        )

        assert response.status_code == 400

    @patch('apps.marketplace.views.requests.post')
    def test_purchase_calls_cloud_api(self, mock_post, authenticated_client, hub_config):
        """Purchase endpoint should call Cloud API and return checkout data."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_post.return_value = MagicMock(
            status_code=200,
            json=MagicMock(return_value={
                'client_secret': 'cs_test_secret',
                'session_id': 'cs_test_123',
                'stripe_publishable_key': 'pk_test_123',
            })
        )

        url = reverse('marketplace:module_purchase')
        response = authenticated_client.post(
            url,
            data=json.dumps({
                'module_id': 'mod-2',
                'module_slug': 'sales',
                'module_name': 'Sales',
            }),
            content_type='application/json',
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['client_secret'] == 'cs_test_secret'

    @patch('apps.marketplace.views.requests.post')
    def test_purchase_handles_already_owned(self, mock_post, authenticated_client, hub_config):
        """Purchase endpoint should handle 409 (already owned)."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_post.return_value = MagicMock(
            status_code=409,
            json=MagicMock(return_value={
                'error': 'You already own Sales',
            })
        )

        url = reverse('marketplace:module_purchase')
        response = authenticated_client.post(
            url,
            data=json.dumps({
                'module_id': 'mod-2',
                'module_slug': 'sales',
            }),
            content_type='application/json',
        )

        assert response.status_code == 409


class TestMarketplaceAuth:
    """Tests for marketplace authentication requirements."""

    def test_unauthenticated_redirects_to_login(self, client, db, store_config):
        """Unauthenticated users should be redirected to the login page."""
        url = reverse('marketplace:index')
        response = client.get(url)

        assert response.status_code == 302
        assert '/login/' in response.url

    def test_purchase_requires_auth(self, client, db, store_config):
        """Module purchase should require authentication."""
        url = reverse('marketplace:module_purchase')
        response = client.post(
            url,
            data=json.dumps({'module_id': 'mod-1', 'module_slug': 'test'}),
            content_type='application/json',
        )

        assert response.status_code == 302
        assert '/login/' in response.url


class TestMyPurchases:
    """Tests for the My Purchases page."""

    @patch('apps.marketplace.views.requests.get')
    def test_my_purchases_page_loads(self, mock_get, authenticated_client, hub_config):
        """My Purchases page should load with 200."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_get.return_value = _mock_cloud_modules_response()

        url = reverse('marketplace:my_purchases')
        response = authenticated_client.get(url)

        assert response.status_code == 200

    @patch('apps.marketplace.views.requests.get')
    def test_my_purchases_htmx_returns_partial(self, mock_get, authenticated_client, hub_config):
        """HTMX requests should return a partial."""
        hub_config.hub_jwt = 'test.jwt.token'
        hub_config.save()

        mock_get.return_value = _mock_cloud_modules_response()

        url = reverse('marketplace:my_purchases')
        response = authenticated_client.get(url, HTTP_HX_REQUEST='true')

        assert response.status_code == 200
        content = response.content.decode()
        assert '<!DOCTYPE' not in content

    def test_my_purchases_requires_auth(self, client, db, store_config):
        """My Purchases should require authentication."""
        url = reverse('marketplace:my_purchases')
        response = client.get(url)

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
