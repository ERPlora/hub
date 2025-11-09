"""
Fixtures para JWT Validation tests.
"""
import pytest
import jwt
from datetime import datetime, timedelta
from django.test import RequestFactory
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend


@pytest.fixture
def rf():
    """Django RequestFactory."""
    return RequestFactory()


@pytest.fixture
def rsa_keys():
    """Generate RSA key pair for testing."""
    # Generate private key
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )

    # Get private key PEM
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')

    # Get public key PEM
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')

    return {
        'private': private_pem,
        'public': public_pem
    }


@pytest.fixture
def valid_jwt_token(rsa_keys):
    """Generate a valid JWT token."""
    payload = {
        'user_id': 1,
        'exp': datetime.utcnow() + timedelta(hours=1),
        'iat': datetime.utcnow(),
        'token_type': 'access'
    }

    token = jwt.encode(payload, rsa_keys['private'], algorithm='RS256')
    return token


@pytest.fixture
def expired_jwt_token(rsa_keys):
    """Generate an expired JWT token."""
    payload = {
        'user_id': 1,
        'exp': datetime.utcnow() - timedelta(hours=1),  # Expired
        'iat': datetime.utcnow() - timedelta(hours=2),
        'token_type': 'access'
    }

    token = jwt.encode(payload, rsa_keys['private'], algorithm='RS256')
    return token
