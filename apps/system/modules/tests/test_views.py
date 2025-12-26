"""
Tests for System Modules Views

Unit tests for marketplace views, module management, and API endpoints.
"""
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse


class MarketplaceViewsTest(TestCase):
    """Tests for marketplace page views."""

    def setUp(self):
        self.factory = RequestFactory()
        # Mock session for login_required decorator
        self.session = {'local_user_id': 'test-user-id'}

    def _get_request(self, path, **kwargs):
        """Helper to create a request with session."""
        request = self.factory.get(path, **kwargs)
        request.session = self.session
        return request

    def _post_request(self, path, data=None, **kwargs):
        """Helper to create a POST request with session."""
        request = self.factory.post(path, data=data or {}, **kwargs)
        request.session = self.session
        return request

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_marketplace_modules_list_success(self, mock_hub_config, mock_requests_get):
        """Test marketplace modules list returns modules from Cloud API."""
        from apps.system.modules.views import marketplace_modules_list

        # Mock HubConfig
        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_config.cloud_api_token = None
        mock_hub_config.return_value = mock_config

        # Mock Cloud API response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {
                    'id': '1',
                    'name': 'Test Module',
                    'slug': 'test-module',
                    'description': 'A test module',
                    'version': '1.0.0',
                    'module_type': 'free',
                    'is_owned': True,
                    'is_free': True,
                },
            ]
        }
        mock_requests_get.return_value = mock_response

        request = self._get_request('/modules/htmx/modules-list/')
        response = marketplace_modules_list(request)

        assert response.status_code == 200
        assert b'Test Module' in response.content

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_marketplace_modules_list_with_type_filter(self, mock_hub_config, mock_requests_get):
        """Test marketplace filters by module type."""
        from apps.system.modules.views import marketplace_modules_list

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'results': [
                {'id': '1', 'name': 'Free Module', 'slug': 'free-mod', 'module_type': 'free'},
                {'id': '2', 'name': 'Paid Module', 'slug': 'paid-mod', 'module_type': 'one_time'},
            ]
        }
        mock_requests_get.return_value = mock_response

        # Request with type filter
        request = self._get_request('/modules/htmx/modules-list/', {'type': 'free'})
        response = marketplace_modules_list(request)

        assert response.status_code == 200
        assert b'Free Module' in response.content
        assert b'Paid Module' not in response.content

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_marketplace_modules_list_no_auth_token(self, mock_hub_config, mock_requests_get):
        """Test marketplace returns error when no auth token."""
        from apps.system.modules.views import marketplace_modules_list

        mock_config = MagicMock()
        mock_config.hub_jwt = ''
        mock_config.cloud_api_token = ''
        mock_hub_config.return_value = mock_config

        request = self._get_request('/modules/htmx/modules-list/')
        response = marketplace_modules_list(request)

        assert response.status_code == 200  # Returns HTML error, not HTTP error
        assert b'not connected to Cloud' in response.content

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_marketplace_modules_list_pagination(self, mock_hub_config, mock_requests_get):
        """Test marketplace pagination works correctly."""
        from apps.system.modules.views import marketplace_modules_list

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        # Create 15 modules (more than page size of 12)
        modules = [
            {'id': str(i), 'name': f'Module {i}', 'slug': f'module-{i}', 'module_type': 'free'}
            for i in range(15)
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'results': modules}
        mock_requests_get.return_value = mock_response

        # Page 1 should have 12 modules
        request = self._get_request('/modules/htmx/modules-list/', {'page': '1'})
        response = marketplace_modules_list(request)
        assert response.status_code == 200
        assert b'Module 0' in response.content
        assert b'Module 11' in response.content

        # Page 2 should have 3 modules
        request = self._get_request('/modules/htmx/modules-list/', {'page': '2'})
        response = marketplace_modules_list(request)
        assert response.status_code == 200
        assert b'Module 12' in response.content
        assert b'Module 14' in response.content


class ModuleDetailViewTest(TestCase):
    """Tests for module detail view."""

    def setUp(self):
        self.factory = RequestFactory()
        self.session = {'local_user_id': 'test-user-id'}

    def _get_request(self, path, **kwargs):
        request = self.factory.get(path, **kwargs)
        request.session = self.session
        # Mock htmx attribute
        request.htmx = MagicMock()
        request.htmx.__bool__ = MagicMock(return_value=True)
        return request

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_module_detail_success(self, mock_hub_config, mock_requests_get):
        """Test module detail returns module info."""
        from apps.system.modules.views import module_detail

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        # Mock module detail response
        mock_detail_response = MagicMock()
        mock_detail_response.status_code = 200
        mock_detail_response.json.return_value = {
            'id': '1',
            'name': 'Test Module',
            'slug': 'test-module',
            'description': 'Full description here',
            'version': '1.0.0',
            'author': 'ERPlora',
            'is_owned': False,
            'is_free': True,
        }

        # Mock related modules response
        mock_list_response = MagicMock()
        mock_list_response.status_code = 200
        mock_list_response.json.return_value = {'results': []}

        mock_requests_get.side_effect = [mock_detail_response, mock_list_response]

        request = self._get_request('/modules/marketplace/test-module/')
        result = module_detail(request, slug='test-module')

        assert result['module']['name'] == 'Test Module'
        assert result['is_free'] == True

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_module_detail_not_found(self, mock_hub_config, mock_requests_get):
        """Test module detail returns error for non-existent module."""
        from apps.system.modules.views import module_detail

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        mock_response = MagicMock()
        mock_response.status_code = 404
        mock_requests_get.return_value = mock_response

        request = self._get_request('/modules/marketplace/nonexistent/')
        result = module_detail(request, slug='nonexistent')

        assert result['error'] is not None
        assert 'not found' in result['error'].lower()


class MarketplaceAPITest(TestCase):
    """Tests for marketplace API endpoints."""

    def setUp(self):
        self.factory = RequestFactory()
        self.session = {'local_user_id': 'test-user-id'}

    def _post_request(self, path, data=None, content_type='application/json'):
        import json
        request = self.factory.post(
            path,
            data=json.dumps(data or {}),
            content_type=content_type
        )
        request.session = self.session
        return request

    @patch('apps.system.modules.views.requests.post')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_purchase_module_free(self, mock_hub_config, mock_requests_post):
        """Test acquiring a free module."""
        from apps.system.modules.views import purchase_module

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'success': True,
            'is_free': True,
        }
        mock_requests_post.return_value = mock_response

        request = self._post_request(
            '/modules/api/marketplace/purchase/',
            data={'module_id': 'free-module-id'}
        )
        response = purchase_module(request)

        assert response.status_code == 200

    @patch('apps.system.modules.views.requests.get')
    @patch('apps.configuration.models.HubConfig.get_solo')
    def test_check_ownership_owned(self, mock_hub_config, mock_requests_get):
        """Test checking ownership of an owned module."""
        from apps.system.modules.views import check_ownership

        mock_config = MagicMock()
        mock_config.hub_jwt = 'test-jwt-token'
        mock_hub_config.return_value = mock_config

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'owned': True,
            'download_url': 'https://example.com/download/module.zip'
        }
        mock_requests_get.return_value = mock_response

        request = self.factory.get('/modules/api/marketplace/ownership/test-module/')
        request.session = self.session
        response = check_ownership(request, module_id='test-module')

        import json
        data = json.loads(response.content)
        assert data.get('owned') == True


class ModuleManagementTest(TestCase):
    """Tests for module activation/deactivation."""

    def setUp(self):
        self.factory = RequestFactory()
        self.session = {'local_user_id': 'test-user-id'}

    @patch('apps.system.modules.views.Path')
    def test_module_activate(self, mock_path):
        """Test activating an inactive module."""
        from apps.system.modules.views import module_activate

        # Mock module directory
        mock_inactive_dir = MagicMock()
        mock_inactive_dir.exists.return_value = True
        mock_inactive_dir.is_dir.return_value = True

        mock_active_dir = MagicMock()
        mock_active_dir.exists.return_value = False

        mock_path.return_value.__truediv__ = MagicMock(side_effect=[
            mock_inactive_dir,  # _test_module
            mock_active_dir,    # test_module
        ])

        request = self.factory.post('/modules/api/activate/test_module/')
        request.session = self.session

        # The actual test would need more mocking of the filesystem
        # This is a simplified version

    @patch('apps.system.modules.views.Path')
    def test_module_deactivate(self, mock_path):
        """Test deactivating an active module."""
        from apps.system.modules.views import module_deactivate

        # Mock module directory
        mock_active_dir = MagicMock()
        mock_active_dir.exists.return_value = True
        mock_active_dir.is_dir.return_value = True

        mock_inactive_dir = MagicMock()
        mock_inactive_dir.exists.return_value = False

        mock_path.return_value.__truediv__ = MagicMock(side_effect=[
            mock_active_dir,    # test_module
            mock_inactive_dir,  # _test_module
        ])

        request = self.factory.post('/modules/api/deactivate/test_module/')
        request.session = self.session

        # Simplified test - full test would need more filesystem mocking
