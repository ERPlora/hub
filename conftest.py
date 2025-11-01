"""
Pytest configuration and fixtures for CPOS Hub tests
"""
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.fixture
def user(db):
    """
    Create a standard user for testing
    """
    return User.objects.create_user(
        username='testuser',
        email='testuser@example.com',
        password='testpass123'
    )


@pytest.fixture
def superuser(db):
    """
    Create a superuser for testing
    """
    return User.objects.create_superuser(
        username='admin',
        email='admin@example.com',
        password='adminpass123'
    )


@pytest.fixture
def hub_config(db):
    """
    Create a HubConfig instance for testing
    Will be implemented once HubConfig model is created
    """
    # TODO: Implement when HubConfig model exists
    pass


@pytest.fixture
def api_client():
    """
    Django test client for API requests
    """
    from django.test import Client
    return Client()
