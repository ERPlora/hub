"""
Unit tests for configuration models.

Tests HubConfig, StoreConfig, and BackupConfig singleton models.
"""
import pytest
from decimal import Decimal

pytestmark = pytest.mark.unit


class TestHubConfig:
    """Tests for HubConfig singleton model."""

    def test_singleton_get_solo(self, db):
        """Test that get_solo returns singleton instance."""
        from apps.configuration.models import HubConfig

        config1 = HubConfig.get_solo()
        config2 = HubConfig.get_solo()

        assert config1.pk == config2.pk
        assert config1.pk == 1

    def test_singleton_prevents_multiple_instances(self, db):
        """Test that saving always uses pk=1."""
        from apps.configuration.models import HubConfig

        # First instance
        config1 = HubConfig.get_solo()

        # Try to create another
        config2 = HubConfig()
        config2.currency = 'USD'
        config2.save()

        assert config2.pk == 1
        assert HubConfig.objects.count() == 1

    def test_get_value(self, hub_config):
        """Test getting individual field values."""
        from apps.configuration.models import HubConfig

        hub_config.currency = 'GBP'
        hub_config.save()

        result = HubConfig.get_value('currency')
        assert result == 'GBP'

    def test_get_value_with_default(self, db):
        """Test getting value with default."""
        from apps.configuration.models import HubConfig

        result = HubConfig.get_value('nonexistent_field', 'default_value')
        assert result == 'default_value'

    def test_set_value(self, hub_config):
        """Test setting individual field values."""
        from apps.configuration.models import HubConfig

        success = HubConfig.set_value('currency', 'JPY')

        assert success is True
        assert HubConfig.get_value('currency') == 'JPY'

    def test_update_values(self, hub_config):
        """Test updating multiple values at once."""
        from apps.configuration.models import HubConfig

        success = HubConfig.update_values(
            currency='CHF',
            dark_mode=True
        )

        assert success is True
        assert HubConfig.get_value('currency') == 'CHF'
        assert HubConfig.get_value('dark_mode') is True

    def test_get_all_values(self, hub_config):
        """Test getting all config values as dict."""
        from apps.configuration.models import HubConfig

        hub_config.currency = 'EUR'
        hub_config.dark_mode = False
        hub_config.save()

        values = HubConfig.get_all_values()

        assert isinstance(values, dict)
        assert values['currency'] == 'EUR'
        assert values['dark_mode'] is False

    def test_cache_invalidation(self, hub_config):
        """Test that cache is invalidated on save."""
        from apps.configuration.models import HubConfig
        from django.core.cache import cache

        # Get initial value (cached)
        _ = HubConfig.get_solo()
        cache_key = HubConfig._get_cache_key()
        assert cache.get(cache_key) is not None

        # Update and save
        hub_config.currency = 'AUD'
        hub_config.save()

        # Cache should be invalidated
        # (new get_solo will re-cache)
        new_config = HubConfig.get_solo()
        assert new_config.currency == 'AUD'


class TestStoreConfig:
    """Tests for StoreConfig singleton model."""

    def test_singleton_get_solo(self, db):
        """Test that get_solo returns singleton instance."""
        from apps.configuration.models import StoreConfig

        config1 = StoreConfig.get_solo()
        config2 = StoreConfig.get_solo()

        assert config1.pk == config2.pk
        assert config1.pk == 1

    def test_is_complete_true(self, store_config):
        """Test is_complete returns True when required fields are filled."""
        assert store_config.is_complete() is True

    def test_is_complete_false(self, unconfigured_store):
        """Test is_complete returns False when required fields are missing."""
        assert unconfigured_store.is_complete() is False

    def test_is_complete_partial(self, db):
        """Test is_complete with partial data."""
        from apps.configuration.models import StoreConfig

        config = StoreConfig.get_solo()
        config.business_name = 'Test'
        config.business_address = ''  # Missing
        config.vat_number = 'ES123'
        config.save()

        assert config.is_complete() is False

    def test_tax_configuration(self, store_config):
        """Test tax configuration fields."""
        store_config.tax_rate = Decimal('10.00')
        store_config.tax_included = False
        store_config.save()

        from apps.configuration.models import StoreConfig
        config = StoreConfig.get_solo()

        assert config.tax_rate == Decimal('10.00')
        assert config.tax_included is False


class TestBackupConfig:
    """Tests for BackupConfig model."""

    def test_singleton_get_solo(self, db):
        """Test that get_solo returns singleton instance."""
        from apps.configuration.models import BackupConfig

        config1 = BackupConfig.get_solo()
        config2 = BackupConfig.get_solo()

        assert config1.pk == config2.pk

    def test_get_cron_trigger_kwargs_daily(self, db):
        """Test cron trigger for daily frequency."""
        from apps.configuration.models import BackupConfig

        config = BackupConfig.get_solo()
        config.frequency = BackupConfig.Frequency.DAILY
        config.time_hour = 3
        config.time_minute = 30
        config.save()

        kwargs = config.get_cron_trigger_kwargs()

        assert kwargs['hour'] == 3
        assert kwargs['minute'] == 30
        assert 'day_of_week' not in kwargs

    def test_get_cron_trigger_kwargs_weekly(self, db):
        """Test cron trigger for weekly frequency."""
        from apps.configuration.models import BackupConfig

        config = BackupConfig.get_solo()
        config.frequency = BackupConfig.Frequency.WEEKLY
        config.time_hour = 2
        config.save()

        kwargs = config.get_cron_trigger_kwargs()

        assert kwargs['hour'] == 2
        assert kwargs['day_of_week'] == 'sun'

    def test_get_cron_trigger_kwargs_monthly(self, db):
        """Test cron trigger for monthly frequency."""
        from apps.configuration.models import BackupConfig

        config = BackupConfig.get_solo()
        config.frequency = BackupConfig.Frequency.MONTHLY
        config.save()

        kwargs = config.get_cron_trigger_kwargs()

        assert kwargs['day'] == 1

    def test_str_disabled(self, db):
        """Test string representation when disabled."""
        from apps.configuration.models import BackupConfig

        config = BackupConfig.get_solo()
        config.enabled = False
        config.save()

        assert 'Disabled' in str(config)

    def test_str_enabled(self, db):
        """Test string representation when enabled."""
        from apps.configuration.models import BackupConfig

        config = BackupConfig.get_solo()
        config.enabled = True
        config.frequency = BackupConfig.Frequency.DAILY
        config.time_hour = 3
        config.time_minute = 0
        config.save()

        result = str(config)
        assert 'daily' in result
        assert '03:00' in result


class TestSingletonConfigMixin:
    """Tests for the SingletonConfigMixin behavior."""

    def test_delete_protection(self, hub_config):
        """Test that deletion is protected by default."""
        from django.db.models import ProtectedError

        with pytest.raises(ProtectedError):
            hub_config.delete()

    def test_force_delete(self, db):
        """Test that force_delete allows deletion."""
        from apps.configuration.models import HubConfig

        config = HubConfig.get_solo()
        config.delete(force_delete=True)

        # Should be deleted
        assert HubConfig.objects.count() == 0

    def test_cache_key_format(self):
        """Test cache key format."""
        from apps.configuration.models import HubConfig

        cache_key = HubConfig._get_cache_key()
        assert 'hubconfig' in cache_key.lower()
        assert 'instance' in cache_key.lower()
