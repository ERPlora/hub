"""
JWT Validator Service.

Validates JWT tokens locally using public key from Cloud.
"""
import logging
import jwt
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)
User = get_user_model()


class TokenExpired(Exception):
    """Raised when JWT token has expired."""
    pass


class InvalidSignature(Exception):
    """Raised when JWT signature is invalid."""
    pass


class JWTValidationError(Exception):
    """Raised when JWT validation fails."""
    pass


class JWTValidator:
    """
    Validates JWT tokens using RSA public key.

    Supports both online and offline validation:
    - Online: Validates with Cloud's public key
    - Offline: Validates with cached public key
    """

    def __init__(self):
        """Initialize validator."""
        pass

    def validate(self, token, public_key):
        """
        Validate JWT token with public key.

        Args:
            token: JWT token string
            public_key: RSA public key in PEM format

        Returns:
            dict: Decoded token payload

        Raises:
            TokenExpired: If token has expired
            InvalidSignature: If signature is invalid
            JWTValidationError: If validation fails
        """
        if not token:
            raise JWTValidationError("Token is required")

        if not public_key:
            raise JWTValidationError("Public key is required")

        try:
            # Decode and validate JWT
            payload = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                options={
                    'verify_signature': True,
                    'verify_exp': True,
                    'verify_iat': True,
                }
            )

            logger.debug(f"Token validated successfully for user {payload.get('user_id')}")
            return payload

        except jwt.ExpiredSignatureError as e:
            logger.warning(f"Token expired: {e}")
            raise TokenExpired("Token has expired")

        except jwt.InvalidSignatureError as e:
            logger.error(f"Invalid signature: {e}")
            raise InvalidSignature("Token signature is invalid")

        except jwt.DecodeError as e:
            logger.error(f"Token decode error: {e}")
            raise JWTValidationError(f"Failed to decode token: {e}")

        except Exception as e:
            logger.error(f"Token validation error: {e}")
            raise JWTValidationError(f"Token validation failed: {e}")

    def validate_and_get_user(self, token, public_key):
        """
        Validate token and return associated user.

        Args:
            token: JWT token string
            public_key: RSA public key in PEM format

        Returns:
            User: Django user object

        Raises:
            TokenExpired: If token has expired
            InvalidSignature: If signature is invalid
            JWTValidationError: If validation fails or user not found
        """
        payload = self.validate(token, public_key)

        user_id = payload.get('user_id')
        if not user_id:
            raise JWTValidationError("Token payload missing user_id")

        try:
            user = User.objects.get(id=user_id)
            return user
        except User.DoesNotExist:
            raise JWTValidationError(f"User {user_id} not found")


# Global singleton
_validator_instance = None


def get_jwt_validator():
    """
    Get or create JWTValidator singleton.

    Returns:
        JWTValidator: Singleton instance
    """
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = JWTValidator()
    return _validator_instance
