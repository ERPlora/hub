"""
Tests for My Modules URL Configuration

Verifies all routes are correctly configured.
URLs are mounted under /modules/

URL Namespace Structure:
- mymodules:index                   -> /modules/
- mymodules:marketplace             -> /modules/marketplace/ (REDIRECTS to /marketplace/modules/)
- mymodules:detail                  -> /modules/marketplace/<slug>/ (REDIRECTS to /marketplace/modules/<slug>/)
- mymodules:htmx_list               -> /modules/htmx/list/
- mymodules:api_activate            -> /modules/api/activate/<id>/
- mymodules:api_deactivate          -> /modules/api/deactivate/<id>/
- mymodules:api_delete              -> /modules/api/delete/<id>/
- mymodules:api_restart             -> /modules/api/restart/
- mymodules:api_fetch               -> /modules/api/marketplace/
- mymodules:api_purchase            -> /modules/api/marketplace/purchase/
- mymodules:api_install             -> /modules/api/marketplace/install/
- mymodules:api_ownership           -> /modules/api/marketplace/ownership/<id>/

NOTE: The marketplace has been moved to /marketplace/ (see apps.marketplace)
"""
import pytest
from django.test import TestCase
from django.urls import reverse, resolve


class MyModulesURLsTest(TestCase):
    """Tests for my modules URL routing."""

    def test_modules_index_url(self):
        """Test modules index URL resolves correctly."""
        url = reverse('mymodules:index')
        assert url == '/modules/'

        resolver = resolve('/modules/')
        assert resolver.view_name == 'mymodules:index'

    def test_marketplace_url_redirects(self):
        """Test marketplace URL redirects to new marketplace."""
        url = reverse('mymodules:marketplace')
        assert url == '/modules/marketplace/'

        # Should be a RedirectView
        resolver = resolve('/modules/marketplace/')
        assert resolver.view_name == 'mymodules:marketplace'

    def test_module_detail_url_redirects(self):
        """Test module detail URL redirects to new marketplace detail."""
        url = reverse('mymodules:detail', kwargs={'slug': 'test-module'})
        assert url == '/modules/marketplace/test-module/'

        # Should be a RedirectView
        resolver = resolve('/modules/marketplace/test-module/')
        assert resolver.view_name == 'mymodules:detail'
        assert resolver.kwargs == {'slug': 'test-module'}

    def test_htmx_list_url(self):
        """Test HTMX modules list endpoint."""
        url = reverse('mymodules:htmx_list')
        assert url == '/modules/htmx/list/'


class ModuleAPIURLsTest(TestCase):
    """Tests for module API URL routing."""

    def test_module_activate_url(self):
        """Test module activation API URL."""
        url = reverse('mymodules:api_activate', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/activate/test_module/'

    def test_module_deactivate_url(self):
        """Test module deactivation API URL."""
        url = reverse('mymodules:api_deactivate', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/deactivate/test_module/'

    def test_module_delete_url(self):
        """Test module deletion API URL."""
        url = reverse('mymodules:api_delete', kwargs={'module_id': 'test_module'})
        assert url == '/modules/api/delete/test_module/'

    def test_module_restart_url(self):
        """Test server restart API URL."""
        url = reverse('mymodules:api_restart')
        assert url == '/modules/api/restart/'


class MarketplaceAPIURLsTest(TestCase):
    """Tests for marketplace API URL routing."""

    def test_fetch_marketplace_url(self):
        """Test fetch marketplace API URL."""
        url = reverse('mymodules:api_fetch')
        assert url == '/modules/api/marketplace/'

    def test_purchase_module_url(self):
        """Test purchase module API URL."""
        url = reverse('mymodules:api_purchase')
        assert url == '/modules/api/marketplace/purchase/'

    def test_install_from_marketplace_url(self):
        """Test install from marketplace API URL."""
        url = reverse('mymodules:api_install')
        assert url == '/modules/api/marketplace/install/'

    def test_check_ownership_url(self):
        """Test check ownership API URL."""
        url = reverse('mymodules:api_ownership', kwargs={'module_id': 'test-module'})
        assert url == '/modules/api/marketplace/ownership/test-module/'
