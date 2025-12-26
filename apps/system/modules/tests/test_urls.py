"""
Tests for System Modules URL Configuration

Verifies all routes are correctly configured.
"""
import pytest
from django.test import TestCase
from django.urls import reverse, resolve


class MarketplaceURLsTest(TestCase):
    """Tests for marketplace URL routing."""

    def test_modules_index_url(self):
        """Test modules index URL resolves correctly."""
        url = reverse('system:modules')
        assert url == '/modules/'

        resolver = resolve('/modules/')
        assert resolver.view_name == 'system:modules'

    def test_marketplace_url(self):
        """Test marketplace URL resolves correctly."""
        url = reverse('system:marketplace')
        assert url == '/modules/marketplace/'

        resolver = resolve('/modules/marketplace/')
        assert resolver.view_name == 'system:marketplace'

    def test_module_detail_url(self):
        """Test module detail URL with slug parameter."""
        url = reverse('system:module_detail', kwargs={'slug': 'test-module'})
        assert url == '/modules/marketplace/test-module/'

        resolver = resolve('/modules/marketplace/test-module/')
        assert resolver.view_name == 'system:module_detail'
        assert resolver.kwargs == {'slug': 'test-module'}

    def test_marketplace_modules_list_url(self):
        """Test HTMX modules list endpoint."""
        url = reverse('system:marketplace_modules_list')
        assert url == '/modules/htmx/modules-list/'


class ModuleAPIURLsTest(TestCase):
    """Tests for module API URL routing."""

    def test_module_activate_url(self):
        """Test module activation API URL."""
        url = reverse('system:module_activate', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/activate/test_module/'

    def test_module_deactivate_url(self):
        """Test module deactivation API URL."""
        url = reverse('system:module_deactivate', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/deactivate/test_module/'

    def test_module_delete_url(self):
        """Test module deletion API URL."""
        url = reverse('system:module_delete', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/delete/test_module/'

    def test_module_restart_url(self):
        """Test server restart API URL."""
        url = reverse('system:module_restart')
        assert url == '/modules/api/restart/'


class MarketplaceAPIURLsTest(TestCase):
    """Tests for marketplace API URL routing."""

    def test_fetch_marketplace_url(self):
        """Test fetch marketplace API URL."""
        url = reverse('system:fetch_marketplace')
        assert url == '/modules/api/marketplace/'

    def test_purchase_module_url(self):
        """Test purchase module API URL."""
        url = reverse('system:purchase_module')
        assert url == '/modules/api/marketplace/purchase/'

    def test_install_from_marketplace_url(self):
        """Test install from marketplace API URL."""
        url = reverse('system:install_from_marketplace')
        assert url == '/modules/api/marketplace/install/'

    def test_check_ownership_url(self):
        """Test check ownership API URL."""
        url = reverse('system:check_ownership', kwargs={'module_id': 'test-module'})
        assert url == '/modules/api/marketplace/ownership/test-module/'
