"""
Unit tests for LocalUser model.

Tests the LocalUser model used for Hub authentication with PIN.
"""
import pytest
from django.test import TestCase
from django.contrib.auth.hashers import check_password
from apps.accounts.models import LocalUser


class TestLocalUserModel(TestCase):
    """Test LocalUser model fields and methods."""

    def test_create_local_user(self):
        """Create a basic LocalUser."""
        user = LocalUser.objects.create(
            email='test@example.com',
            name='Test User',
            role='employee',
            pin_hash=''
        )

        assert user.email == 'test@example.com'
        assert user.name == 'Test User'
        assert user.role == 'employee'
        assert user.is_active is True

    def test_cloud_user_id_nullable(self):
        """cloud_user_id should be nullable for DEMO_MODE."""
        user = LocalUser.objects.create(
            email='demo@example.com',
            name='Demo User',
            role='admin',
            pin_hash='',
            cloud_user_id=None
        )

        assert user.cloud_user_id is None

    def test_cloud_user_id_can_be_set(self):
        """cloud_user_id can be set to link with Cloud user."""
        user = LocalUser.objects.create(
            email='linked@example.com',
            name='Linked User',
            role='admin',
            pin_hash='',
            cloud_user_id=12345
        )

        assert user.cloud_user_id == 12345

    def test_cloud_user_id_unique_per_hub(self):
        """cloud_user_id should be unique per hub when set."""
        import uuid
        from django.db import IntegrityError

        shared_hub_id = uuid.uuid4()

        LocalUser.objects.create(
            email='first@example.com',
            name='First',
            role='admin',
            pin_hash='',
            cloud_user_id=100,
            hub_id=shared_hub_id
        )

        with pytest.raises(IntegrityError):
            LocalUser.objects.create(
                email='second@example.com',
                name='Second',
                role='admin',
                pin_hash='',
                cloud_user_id=100,  # Same cloud_user_id
                hub_id=shared_hub_id  # Same hub
            )


class TestLocalUserPIN(TestCase):
    """Test PIN hashing and verification."""

    def test_set_pin_hashes_correctly(self):
        """set_pin should hash the PIN."""
        user = LocalUser.objects.create(
            email='pin@example.com',
            name='PIN User',
            role='employee',
            pin_hash=''
        )

        user.set_pin('1234')

        # PIN should be hashed, not stored in plain text
        assert user.pin_hash != '1234'
        assert len(user.pin_hash) > 0

    def test_check_pin_correct(self):
        """check_pin should return True for correct PIN."""
        user = LocalUser.objects.create(
            email='check@example.com',
            name='Check User',
            role='employee',
            pin_hash=''
        )
        user.set_pin('5678')

        assert user.check_pin('5678') is True

    def test_check_pin_incorrect(self):
        """check_pin should return False for incorrect PIN."""
        user = LocalUser.objects.create(
            email='wrong@example.com',
            name='Wrong User',
            role='employee',
            pin_hash=''
        )
        user.set_pin('1111')

        assert user.check_pin('9999') is False
        assert user.check_pin('1112') is False
        assert user.check_pin('') is False

    def test_empty_pin_hash_check_fails(self):
        """User without PIN should fail check_pin."""
        user = LocalUser.objects.create(
            email='nopin@example.com',
            name='No PIN',
            role='employee',
            pin_hash=''
        )

        assert user.check_pin('1234') is False


class TestLocalUserInitials(TestCase):
    """Test initials generation for avatars."""

    def test_get_initials_two_words(self):
        """Two word name should return first letters of each."""
        user = LocalUser.objects.create(
            email='two@example.com',
            name='John Doe',
            role='employee',
            pin_hash=''
        )

        assert user.get_initials() == 'JD'

    def test_get_initials_single_word(self):
        """Single word name should return first letter."""
        user = LocalUser.objects.create(
            email='single@example.com',
            name='Alice',
            role='employee',
            pin_hash=''
        )

        assert user.get_initials() == 'A'

    def test_get_initials_three_words(self):
        """Three word name should return first two initials."""
        user = LocalUser.objects.create(
            email='three@example.com',
            name='John Michael Doe',
            role='employee',
            pin_hash=''
        )

        assert user.get_initials() == 'JM'

    def test_get_initials_empty_name(self):
        """Empty name should return ?."""
        user = LocalUser.objects.create(
            email='empty@example.com',
            name='',
            role='employee',
            pin_hash=''
        )

        assert user.get_initials() == '?'


class TestLocalUserRoleColors(TestCase):
    """Test role color assignment for UI."""

    def test_admin_role_color(self):
        """Admin should have primary color."""
        user = LocalUser.objects.create(
            email='admin@example.com',
            name='Admin',
            role='admin',
            pin_hash=''
        )

        assert user.get_role_color() == 'primary'

    def test_manager_role_color(self):
        """Manager should have tertiary color."""
        user = LocalUser.objects.create(
            email='manager@example.com',
            name='Manager',
            role='manager',
            pin_hash=''
        )

        assert user.get_role_color() == 'tertiary'

    def test_employee_role_color(self):
        """Employee should have success color."""
        user = LocalUser.objects.create(
            email='employee@example.com',
            name='Employee',
            role='employee',
            pin_hash=''
        )

        assert user.get_role_color() == 'success'

    def test_unknown_role_color(self):
        """Unknown role should have medium color."""
        user = LocalUser.objects.create(
            email='unknown@example.com',
            name='Unknown',
            role='unknown_role',
            pin_hash=''
        )

        assert user.get_role_color() == 'medium'


class TestLocalUserDjangoCompatibility(TestCase):
    """Test Django auth compatibility properties."""

    def test_is_authenticated_always_true(self):
        """LocalUser instances are always authenticated."""
        user = LocalUser.objects.create(
            email='auth@example.com',
            name='Auth User',
            role='employee',
            pin_hash=''
        )

        assert user.is_authenticated is True

    def test_is_anonymous_always_false(self):
        """LocalUser instances are never anonymous."""
        user = LocalUser.objects.create(
            email='anon@example.com',
            name='Anon User',
            role='employee',
            pin_hash=''
        )

        assert user.is_anonymous is False

    def test_first_name_property(self):
        """first_name should return first word of name."""
        user = LocalUser.objects.create(
            email='fname@example.com',
            name='John Doe',
            role='employee',
            pin_hash=''
        )

        assert user.first_name == 'John'

    def test_last_name_property(self):
        """last_name should return remaining words of name."""
        user = LocalUser.objects.create(
            email='lname@example.com',
            name='John Michael Doe',
            role='employee',
            pin_hash=''
        )

        assert user.last_name == 'Michael Doe'

    def test_username_returns_email(self):
        """username property should return email."""
        user = LocalUser.objects.create(
            email='username@example.com',
            name='Username User',
            role='employee',
            pin_hash=''
        )

        assert user.username == 'username@example.com'
        assert user.get_username() == 'username@example.com'

    def test_get_full_name(self):
        """get_full_name should return name."""
        user = LocalUser.objects.create(
            email='fullname@example.com',
            name='Full Name User',
            role='employee',
            pin_hash=''
        )

        assert user.get_full_name() == 'Full Name User'


class TestLocalUserStr(TestCase):
    """Test string representation."""

    def test_str_representation(self):
        """__str__ should return name and email."""
        user = LocalUser.objects.create(
            email='str@example.com',
            name='String Test',
            role='employee',
            pin_hash=''
        )

        assert str(user) == 'String Test (str@example.com)'


class TestLocalUserDefaults(TestCase):
    """Test default values."""

    def test_default_role_is_employee(self):
        """Default role should be employee."""
        user = LocalUser.objects.create(
            email='default@example.com',
            name='Default',
            pin_hash=''
        )

        assert user.role == 'employee'

    def test_default_is_active_true(self):
        """Default is_active should be True."""
        user = LocalUser.objects.create(
            email='active@example.com',
            name='Active',
            pin_hash=''
        )

        assert user.is_active is True

    def test_default_language_is_en(self):
        """Default language should be en."""
        user = LocalUser.objects.create(
            email='lang@example.com',
            name='Language',
            pin_hash=''
        )

        assert user.language == 'en'
