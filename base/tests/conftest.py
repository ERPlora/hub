"""Fixtures of the base tests: users with a role on a host, and a stand-in for the SaaS."""

import json

import pytest
from django.contrib.auth import get_user_model

from base import auth
from base.models import Membership

SECRET = "test-internal-secret"
ANA = {"user_id": "42", "email": "ana@example.com", "name": "Ana", "locale": "es", "role": "hub_manager"}


@pytest.fixture
def make_user(db):
    def make(username: str = "ana", *, host: str | None = None, role: str | None = None, **fields):
        user = get_user_model().objects.create_user(username=username, password="pw", **fields)
        if host is not None:
            Membership.objects.create(user=user, host=host, role=role or Membership.Role.EMPLOYEE)
        return user

    return make


@pytest.fixture
def superuser(db):
    return get_user_model().objects.create_superuser(username="root", password="pw", email="root@example.com")


@pytest.fixture
def saas(settings):
    """The local SaaS's URL and the shared secret, whatever the environment says."""
    settings.SAAS_URL = "http://localhost:8001"
    settings.INTERNAL_SHARED_SECRET = SECRET


class FakeSaas:
    """Stands in for ``base.auth.post``: records the call and answers ``(status, body)`` or raises."""

    def __init__(self, status: int = 200, body: object = ANA, raises: Exception | None = None):
        self.status, self.raises = status, raises
        self.body = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.calls: list[dict] = []

    def __call__(self, url, body, headers, timeout):
        self.calls.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        if self.raises is not None:
            raise self.raises
        return self.status, self.body


@pytest.fixture
def fake_saas(monkeypatch, saas):
    def install(**kwargs) -> FakeSaas:
        fake = FakeSaas(**kwargs)
        monkeypatch.setattr(auth, "post", fake)
        return fake

    return install
