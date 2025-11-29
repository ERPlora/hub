"""
Unit tests for HubConfig and StoreConfig singleton models.

Tests the global configuration system used across the Hub.
"""
import pytest
from django.test import TestCase
from django.core.cache import cache
from apps.configuration.models import HubConfig, StoreConfig


class TestHubConfigSingleton(TestCase):
    """Test HubConfig singleton pattern."""

    def setUp(self):
        cache.clear()

    def test_get_solo_creates_if_not_exists(self):
        """get_solo should create config if it doesn't exist."""
        HubConfig.objects.all().delete()

        config = HubConfig.get_solo()

        assert config is not None
        assert HubConfig.objects.count() == 1

    def test_get_solo_returns_same_instance(self):
        """get_solo should always return the same instance."""
        config1 = HubConfig.get_solo()
        config2 = HubConfig.get_solo()

        assert config1.id == config2.id

    def test_get_config_alias(self):
        """get_config should be alias for get_solo."""
        config1 = HubConfig.get_solo()
        config2 = HubConfig.get_config()

        assert config1.id == config2.id


class TestHubConfigValues(TestCase):
    """Test HubConfig value methods."""

    def setUp(self):
        cache.clear()
        HubConfig.objects.all().delete()

    def test_get_value_returns_default_for_missing(self):
        """get_value should return default if field doesn't have value."""
        value = HubConfig.get_value('nonexistent_field', 'default')

        assert value == 'default'

    def test_get_value_returns_actual_value(self):
        """get_value should return actual field value."""
        config = HubConfig.get_solo()
        config.currency = 'USD'
        config.save()
        cache.clear()

        value = HubConfig.get_value('currency', 'EUR')

        assert value == 'USD'

    def test_set_value_updates_field(self):
        """set_value should update the field."""
        HubConfig.set_value('dark_mode', True)
        cache.clear()

        config = HubConfig.get_solo()
        assert config.dark_mode is True

    def test_update_values_multiple_fields(self):
        """update_values should update multiple fields at once."""
        HubConfig.update_values(
            currency='GBP',
            dark_mode=True,
            os_language='es'
        )
        cache.clear()

        config = HubConfig.get_solo()
        assert config.currency == 'GBP'
        assert config.dark_mode is True
        assert config.os_language == 'es'


class TestHubConfigDefaults(TestCase):
    """Test HubConfig default values."""

    def setUp(self):
        cache.clear()
        HubConfig.objects.all().delete()

    def test_default_currency(self):
        """Default currency should be EUR."""
        config = HubConfig.get_solo()
        assert config.currency == 'EUR'

    def test_default_language(self):
        """Default language should be en."""
        config = HubConfig.get_solo()
        assert config.os_language == 'en'

    def test_default_dark_mode(self):
        """Default dark_mode should be False."""
        config = HubConfig.get_solo()
        assert config.dark_mode is False

    def test_default_is_configured(self):
        """Default is_configured should be False."""
        config = HubConfig.get_solo()
        assert config.is_configured is False


class TestStoreConfigSingleton(TestCase):
    """Test StoreConfig singleton pattern."""

    def setUp(self):
        cache.clear()

    def test_get_solo_creates_if_not_exists(self):
        """get_solo should create config if it doesn't exist."""
        StoreConfig.objects.all().delete()

        config = StoreConfig.get_solo()

        assert config is not None
        assert StoreConfig.objects.count() == 1

    def test_get_solo_returns_same_instance(self):
        """get_solo should always return the same instance."""
        config1 = StoreConfig.get_solo()
        config2 = StoreConfig.get_solo()

        assert config1.id == config2.id


class TestStoreConfigDefaults(TestCase):
    """Test StoreConfig default values."""

    def setUp(self):
        cache.clear()
        StoreConfig.objects.all().delete()

    def test_default_tax_rate(self):
        """Default tax_rate should be 0.00."""
        config = StoreConfig.get_solo()
        assert config.tax_rate == 0

    def test_default_tax_included(self):
        """Default tax_included should be True."""
        config = StoreConfig.get_solo()
        assert config.tax_included is True

    def test_default_is_configured(self):
        """Default is_configured should be False."""
        config = StoreConfig.get_solo()
        assert config.is_configured is False


class TestStoreConfigValues(TestCase):
    """Test StoreConfig value methods."""

    def setUp(self):
        cache.clear()
        StoreConfig.objects.all().delete()

    def test_get_value_business_name(self):
        """get_value should return business_name."""
        config = StoreConfig.get_solo()
        config.business_name = 'Test Store'
        config.save()
        cache.clear()

        value = StoreConfig.get_value('business_name', '')

        assert value == 'Test Store'

    def test_set_value_tax_rate(self):
        """set_value should update tax_rate."""
        from decimal import Decimal

        StoreConfig.set_value('tax_rate', Decimal('21.00'))
        cache.clear()

        config = StoreConfig.get_solo()
        assert config.tax_rate == Decimal('21.00')


class TestConfigCaching(TestCase):
    """Test configuration caching behavior."""

    def setUp(self):
        cache.clear()

    def test_get_solo_uses_cache(self):
        """get_solo should cache the result."""
        # First call
        config1 = HubConfig.get_solo()

        # Modify directly in DB
        HubConfig.objects.filter(id=config1.id).update(currency='JPY')

        # Second call should return cached value
        config2 = HubConfig.get_solo()
        assert config2.currency != 'JPY'  # Still cached

    def test_save_invalidates_cache(self):
        """save should invalidate cache."""
        config = HubConfig.get_solo()
        config.currency = 'CAD'
        config.save()

        # Cache should be invalidated, new value returned
        new_config = HubConfig.get_solo()
        assert new_config.currency == 'CAD'
