"""
Pytest fixtures for accounts tests.
"""
import pytest
import uuid
from django.test import RequestFactory, Client
from django.contrib.sessions.backends.db import SessionStore

from apps.accounts.models import LocalUser, Permission, Role, RolePermission
from apps.configuration.models import HubConfig, StoreConfig


@pytest.fixture
def configured_hub(db, hub_id):
    """Configure HubConfig with test hub_id."""
    # Clear any cached config
    HubConfig._clear_cache()

    # Get or create the singleton
    hub_config = HubConfig.get_config()
    hub_config.hub_id = hub_id
    hub_config.is_configured = True
    hub_config.save()

    return hub_config


@pytest.fixture
def configured_store(db):
    """Ensure store is configured to skip setup wizard redirect."""
    # Clear any cached config
    StoreConfig._clear_cache()

    config = StoreConfig.get_config()
    config.is_configured = True
    config.save()

    return config


@pytest.fixture
def rf():
    """Django RequestFactory."""
    return RequestFactory()


@pytest.fixture
def client():
    """Django test client."""
    return Client()


@pytest.fixture
def hub_id():
    """Generate a test hub_id."""
    return uuid.uuid4()


@pytest.fixture
def admin_user(db, hub_id):
    """Create an admin user."""
    user = LocalUser.objects.create(
        hub_id=hub_id,
        name="Admin User",
        email="admin@test.com",
        role="admin",
        is_active=True,
    )
    user.set_pin("1234")
    user.save()
    return user


@pytest.fixture
def manager_user(db, hub_id):
    """Create a manager user."""
    user = LocalUser.objects.create(
        hub_id=hub_id,
        name="Manager User",
        email="manager@test.com",
        role="manager",
        is_active=True,
    )
    user.set_pin("5678")
    user.save()
    return user


@pytest.fixture
def employee_user(db, hub_id):
    """Create an employee user."""
    user = LocalUser.objects.create(
        hub_id=hub_id,
        name="Employee User",
        email="employee@test.com",
        role="employee",
        is_active=True,
    )
    user.set_pin("9012")
    user.save()
    return user


@pytest.fixture
def permission_view_product(db, hub_id):
    """Create a view product permission."""
    return Permission.objects.create(
        hub_id=hub_id,
        codename="inventory.view_product",
        name="Can view product",
        module_id="inventory",
    )


@pytest.fixture
def permission_add_product(db, hub_id):
    """Create an add product permission."""
    return Permission.objects.create(
        hub_id=hub_id,
        codename="inventory.add_product",
        name="Can add product",
        module_id="inventory",
    )


@pytest.fixture
def permission_view_sale(db, hub_id):
    """Create a view sale permission."""
    return Permission.objects.create(
        hub_id=hub_id,
        codename="sales.view_sale",
        name="Can view sale",
        module_id="sales",
    )


@pytest.fixture
def role_custom(db, hub_id):
    """Create a custom role."""
    return Role.objects.create(
        hub_id=hub_id,
        name="supervisor",
        display_name="Supervisor",
        description="Supervisor with limited permissions",
        is_system=False,
        is_active=True,
    )


@pytest.fixture
def role_admin(db, hub_id):
    """Create the admin system role."""
    return Role.objects.create(
        hub_id=hub_id,
        name="admin",
        display_name="Administrator",
        description="Full access to all features",
        is_system=True,
        is_active=True,
    )


@pytest.fixture
def role_manager(db, hub_id):
    """Create the manager system role."""
    return Role.objects.create(
        hub_id=hub_id,
        name="manager",
        display_name="Manager",
        description="Can manage sales and inventory",
        is_system=True,
        is_active=True,
    )


@pytest.fixture
def role_employee(db, hub_id):
    """Create the employee system role."""
    return Role.objects.create(
        hub_id=hub_id,
        name="employee",
        display_name="Employee",
        description="Basic POS operations",
        is_system=True,
        is_active=True,
    )


@pytest.fixture
def authenticated_session(admin_user):
    """Create an authenticated session for admin user."""
    session = SessionStore()
    session['local_user_id'] = str(admin_user.id)
    session['user_role'] = admin_user.role
    session.create()
    return session


@pytest.fixture
def request_with_session(rf, authenticated_session):
    """Create a request with authenticated session."""
    request = rf.get('/')
    request.session = authenticated_session
    return request
