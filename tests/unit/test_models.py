"""
Unit tests for apps/core/models.py - Hub core models

Tests HubConfig, LocalUser, StoreConfig, and Plugin models.
"""
import pytest
from django.db import IntegrityError
from apps.core.models import HubConfig, LocalUser, StoreConfig, Plugin


@pytest.mark.unit
@pytest.mark.core
class TestHubConfigModel:
    """Test HubConfig model"""

    @pytest.mark.django_db
    def test_create_hub_config(self):
        """Should create HubConfig instance"""
        config = HubConfig.objects.create(
            hub_id='550e8400-e29b-41d4-a716-446655440000',
            tunnel_port=7001,
            tunnel_token='test_token_123',
            is_configured=True
        )
        assert config.id is not None
        assert config.hub_id is not None
        assert config.is_configured is True

    @pytest.mark.django_db
    def test_hub_config_defaults(self):
        """Should use default values"""
        config = HubConfig.objects.create()
        assert config.is_configured is False
        assert config.os_language == 'en'
        assert config.hub_id is None
        assert config.tunnel_port is None

    @pytest.mark.django_db
    def test_hub_config_get_config_singleton(self):
        """Should implement singleton pattern"""
        config1 = HubConfig.get_config()
        config2 = HubConfig.get_config()
        assert config1.id == config2.id
        assert config1.id == 1

    @pytest.mark.django_db
    def test_hub_config_str_representation(self):
        """Should return string representation"""
        config = HubConfig.objects.create(is_configured=True)
        assert str(config) == "Hub Config (Configured: True)"

    @pytest.mark.django_db
    def test_hub_config_timestamps(self):
        """Should auto-set timestamps"""
        config = HubConfig.objects.create()
        assert config.created_at is not None
        assert config.updated_at is not None


@pytest.mark.unit
@pytest.mark.core
class TestLocalUserModel:
    """Test LocalUser model"""

    @pytest.mark.django_db
    def test_create_local_user(self):
        """Should create LocalUser instance"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='hashed_pin'
        )
        assert user.id is not None
        assert user.cloud_user_id == 1
        assert user.email == 'test@example.com'

    @pytest.mark.django_db
    def test_local_user_defaults(self):
        """Should use default values"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='hash'
        )
        assert user.role == 'cashier'
        assert user.is_active is True
        assert user.language == 'en'

    @pytest.mark.django_db
    def test_local_user_unique_email(self):
        """Should enforce unique email constraint"""
        LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='User 1',
            pin_hash='hash'
        )
        with pytest.raises(IntegrityError):
            LocalUser.objects.create(
                cloud_user_id=2,
                email='test@example.com',  # Duplicate
                name='User 2',
                pin_hash='hash'
            )

    @pytest.mark.django_db
    def test_local_user_unique_cloud_id(self):
        """Should enforce unique cloud_user_id constraint"""
        LocalUser.objects.create(
            cloud_user_id=1,
            email='user1@example.com',
            name='User 1',
            pin_hash='hash'
        )
        with pytest.raises(IntegrityError):
            LocalUser.objects.create(
                cloud_user_id=1,  # Duplicate
                email='user2@example.com',
                name='User 2',
                pin_hash='hash'
            )

    @pytest.mark.django_db
    def test_set_pin(self):
        """Should hash and save PIN"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='temp'
        )
        user.set_pin('1234')
        assert user.pin_hash != '1234'  # Should be hashed
        assert user.pin_hash.startswith('pbkdf2_')  # Django password format

    @pytest.mark.django_db
    def test_check_pin_correct(self):
        """Should verify correct PIN"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='temp'
        )
        user.set_pin('1234')
        assert user.check_pin('1234') is True

    @pytest.mark.django_db
    def test_check_pin_incorrect(self):
        """Should reject incorrect PIN"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='temp'
        )
        user.set_pin('1234')
        assert user.check_pin('9999') is False

    @pytest.mark.django_db
    def test_get_initials_two_words(self):
        """Should return first letter of first and last name"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='John Doe',
            pin_hash='hash'
        )
        assert user.get_initials() == 'JD'

    @pytest.mark.django_db
    def test_get_initials_one_word(self):
        """Should return first letter if single name"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='John',
            pin_hash='hash'
        )
        assert user.get_initials() == 'J'

    @pytest.mark.django_db
    def test_get_initials_empty_name(self):
        """Should return ? if no name"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='',
            pin_hash='hash'
        )
        assert user.get_initials() == '?'

    @pytest.mark.django_db
    def test_get_role_color_admin(self):
        """Should return primary color for admin"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Admin',
            role='admin',
            pin_hash='hash'
        )
        assert user.get_role_color() == 'primary'

    @pytest.mark.django_db
    def test_get_role_color_cashier(self):
        """Should return success color for cashier"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Cashier',
            role='cashier',
            pin_hash='hash'
        )
        assert user.get_role_color() == 'success'

    @pytest.mark.django_db
    def test_get_role_color_unknown(self):
        """Should return medium color for unknown role"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='User',
            role='unknown',
            pin_hash='hash'
        )
        assert user.get_role_color() == 'medium'

    @pytest.mark.django_db
    def test_local_user_str_representation(self):
        """Should return string representation"""
        user = LocalUser.objects.create(
            cloud_user_id=1,
            email='test@example.com',
            name='Test User',
            pin_hash='hash'
        )
        assert str(user) == 'Test User (test@example.com)'

    @pytest.mark.django_db
    def test_local_user_ordering(self):
        """Should order by name"""
        LocalUser.objects.create(
            cloud_user_id=1, email='z@example.com', name='Zebra', pin_hash='h'
        )
        LocalUser.objects.create(
            cloud_user_id=2, email='a@example.com', name='Alpha', pin_hash='h'
        )
        users = LocalUser.objects.all()
        assert users[0].name == 'Alpha'
        assert users[1].name == 'Zebra'


@pytest.mark.unit
@pytest.mark.core
class TestStoreConfigModel:
    """Test StoreConfig model"""

    @pytest.mark.django_db
    def test_create_store_config(self):
        """Should create StoreConfig instance"""
        config = StoreConfig.objects.create(
            business_name='Test Store',
            business_address='123 Test St',
            vat_number='VAT123'
        )
        assert config.id is not None
        assert config.business_name == 'Test Store'

    @pytest.mark.django_db
    def test_store_config_defaults(self):
        """Should use default values"""
        config = StoreConfig.objects.create()
        assert config.is_configured is False
        assert config.tax_rate == 0.00
        assert config.tax_included is True

    @pytest.mark.django_db
    def test_store_config_get_config_singleton(self):
        """Should implement singleton pattern"""
        config1 = StoreConfig.get_config()
        config2 = StoreConfig.get_config()
        assert config1.id == config2.id
        assert config1.id == 1

    @pytest.mark.django_db
    def test_store_config_is_complete_true(self):
        """Should return True if required fields filled"""
        config = StoreConfig.objects.create(
            business_name='Test Store',
            business_address='123 Test St',
            vat_number='VAT123'
        )
        assert config.is_complete() is True

    @pytest.mark.django_db
    def test_store_config_is_complete_false_missing_name(self):
        """Should return False if missing business name"""
        config = StoreConfig.objects.create(
            business_address='123 Test St',
            vat_number='VAT123'
        )
        assert config.is_complete() is False

    @pytest.mark.django_db
    def test_store_config_is_complete_false_missing_address(self):
        """Should return False if missing address"""
        config = StoreConfig.objects.create(
            business_name='Test Store',
            vat_number='VAT123'
        )
        assert config.is_complete() is False

    @pytest.mark.django_db
    def test_store_config_is_complete_false_missing_vat(self):
        """Should return False if missing VAT number"""
        config = StoreConfig.objects.create(
            business_name='Test Store',
            business_address='123 Test St'
        )
        assert config.is_complete() is False

    @pytest.mark.django_db
    def test_store_config_str_representation_with_name(self):
        """Should return string representation with business name"""
        config = StoreConfig.objects.create(
            business_name='Test Store',
            is_configured=True
        )
        assert str(config) == 'Test Store (Configured: True)'

    @pytest.mark.django_db
    def test_store_config_str_representation_without_name(self):
        """Should return 'Store' if no business name"""
        config = StoreConfig.objects.create()
        assert str(config) == 'Store (Configured: False)'


@pytest.mark.unit
@pytest.mark.core
class TestPluginModel:
    """Test Plugin model"""

    @pytest.mark.django_db
    def test_create_plugin(self):
        """Should create Plugin instance"""
        plugin = Plugin.objects.create(
            plugin_id='test-plugin',
            name='Test Plugin',
            version='1.0.0'
        )
        assert plugin.id is not None
        assert plugin.plugin_id == 'test-plugin'

    @pytest.mark.django_db
    def test_plugin_defaults(self):
        """Should use default values"""
        plugin = Plugin.objects.create(
            plugin_id='test-plugin',
            name='Test Plugin',
            version='1.0.0'
        )
        assert plugin.is_installed is False
        assert plugin.is_active is True
        assert plugin.icon == 'extension-puzzle-outline'
        assert plugin.category == 'general'
        assert plugin.menu_order == 100
        assert plugin.show_in_menu is True

    @pytest.mark.django_db
    def test_plugin_unique_plugin_id(self):
        """Should enforce unique plugin_id constraint"""
        Plugin.objects.create(
            plugin_id='test-plugin',
            name='Plugin 1',
            version='1.0.0'
        )
        with pytest.raises(IntegrityError):
            Plugin.objects.create(
                plugin_id='test-plugin',  # Duplicate
                name='Plugin 2',
                version='2.0.0'
            )

    @pytest.mark.django_db
    def test_plugin_str_representation(self):
        """Should return string representation"""
        plugin = Plugin.objects.create(
            plugin_id='test-plugin',
            name='Test Plugin',
            version='1.0.0'
        )
        assert str(plugin) == 'Test Plugin v1.0.0'

    @pytest.mark.django_db
    def test_plugin_ordering(self):
        """Should order by menu_order then name"""
        Plugin.objects.create(
            plugin_id='plugin-z',
            name='Z Plugin',
            version='1.0.0',
            menu_order=200
        )
        Plugin.objects.create(
            plugin_id='plugin-a',
            name='A Plugin',
            version='1.0.0',
            menu_order=100
        )
        plugins = Plugin.objects.all()
        assert plugins[0].name == 'A Plugin'  # Lower menu_order first
        assert plugins[1].name == 'Z Plugin'
