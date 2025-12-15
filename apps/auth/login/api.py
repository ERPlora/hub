"""
Auth Login API

Authentication endpoints: login, logout, PIN verification, Cloud login.
"""
import requests
from django.utils import timezone
from django.conf import settings as django_settings
from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig
from apps.sync.models import TokenCache
from apps.core.api_base import SuccessResponseSerializer, ErrorResponseSerializer


# =============================================================================
# Serializers
# =============================================================================

class PinLoginSerializer(serializers.Serializer):
    """Serializer for PIN-based local login"""
    user_id = serializers.IntegerField(help_text="Local user ID")
    pin = serializers.CharField(max_length=4, min_length=4, help_text="4-digit PIN code")


class CloudLoginSerializer(serializers.Serializer):
    """Serializer for Cloud-based login"""
    email = serializers.EmailField(help_text="User email")
    password = serializers.CharField(write_only=True, help_text="User password")


class SetupPinSerializer(serializers.Serializer):
    """Serializer for setting up PIN after Cloud login"""
    user_id = serializers.IntegerField(help_text="Local user ID")
    pin = serializers.CharField(max_length=4, min_length=4, help_text="4-digit PIN code")

    def validate_pin(self, value):
        if not value.isdigit():
            raise serializers.ValidationError("PIN must contain only digits")
        return value


class UserSerializer(serializers.Serializer):
    """Basic user info serializer"""
    id = serializers.IntegerField()
    name = serializers.CharField()
    email = serializers.EmailField()
    role = serializers.CharField()


class LoginResponseSerializer(serializers.Serializer):
    """Response serializer for login"""
    success = serializers.BooleanField()
    user = UserSerializer()
    sync_reason = serializers.CharField(required=False)


class CloudLoginResponseSerializer(serializers.Serializer):
    """Response serializer for Cloud login"""
    success = serializers.BooleanField()
    first_time = serializers.BooleanField(help_text="True if user needs to set up PIN")
    access = serializers.CharField(required=False)
    refresh = serializers.CharField(required=False)
    user = UserSerializer()


class LocalUserListSerializer(serializers.ModelSerializer):
    """Serializer for listing local users for login"""
    initials = serializers.CharField(source='get_initials', read_only=True)
    role_color = serializers.CharField(source='get_role_color', read_only=True)

    class Meta:
        model = LocalUser
        fields = ['id', 'name', 'email', 'role', 'initials', 'role_color']


# =============================================================================
# Helper Functions
# =============================================================================

def verify_user_access_with_cloud(user):
    """Verify if user has active access to Hub by querying Cloud."""
    hub_config = HubConfig.get_config()

    if not hub_config.is_configured:
        return True, "hub_not_configured"

    try:
        response = requests.get(
            f"{django_settings.CLOUD_API_URL}/api/hubs/{hub_config.hub_id}/users/check/{user.email}/",
            headers={'X-Hub-Token': hub_config.cloud_api_token},
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            has_access = data.get('has_access', False)

            if not has_access and user.is_active:
                user.is_active = False
                user.save(update_fields=['is_active'])
                return False, "removed_from_cloud"
            elif has_access and not user.is_active:
                user.is_active = True
                user.save(update_fields=['is_active'])
                return True, "reactivated_from_cloud"

            return has_access, "synced_with_cloud"
        else:
            return user.is_active, "cloud_error_use_local"

    except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
        return user.is_active, "offline_use_local"
    except Exception as e:
        print(f"Error verifying access in Cloud: {str(e)}")
        return user.is_active, "error_use_local"


# =============================================================================
# API Views
# =============================================================================

@extend_schema(tags=['Authentication'])
class UsersListView(APIView):
    """List available local users for login selection."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="List local users",
        description="Get list of active local users for PIN login selection",
        responses={200: LocalUserListSerializer(many=True)}
    )
    def get(self, request):
        users = LocalUser.objects.filter(is_active=True).order_by('name')
        serializer = LocalUserListSerializer(users, many=True)
        return Response(serializer.data)


@extend_schema(tags=['Authentication'])
class PinLoginView(APIView):
    """Authenticate user with PIN code."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login with PIN",
        description="Authenticate a local user using their 4-digit PIN",
        request=PinLoginSerializer,
        responses={
            200: LoginResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request):
        serializer = PinLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        pin = serializer.validated_data['pin']

        try:
            user = LocalUser.objects.get(id=user_id, is_active=True)
        except LocalUser.DoesNotExist:
            return Response(
                {'success': False, 'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if user.check_pin(pin):
            has_access, reason = verify_user_access_with_cloud(user)

            if not has_access:
                return Response({
                    'success': False,
                    'error': 'Access denied. You have been removed from this Hub.',
                    'reason': reason
                }, status=status.HTTP_401_UNAUTHORIZED)

            user.last_login = timezone.now()
            user.save()

            # Store session
            request.session['local_user_id'] = user.id
            request.session['user_name'] = user.name
            request.session['user_email'] = user.email
            request.session['user_role'] = user.role
            request.session['user_language'] = user.language

            return Response({
                'success': True,
                'user': {
                    'id': user.id,
                    'name': user.name,
                    'email': user.email,
                    'role': user.role,
                },
                'sync_reason': reason
            })
        else:
            return Response(
                {'success': False, 'error': 'Incorrect PIN'},
                status=status.HTTP_401_UNAUTHORIZED
            )


@extend_schema(tags=['Authentication'])
class CloudLoginView(APIView):
    """Authenticate user via ERPlora Cloud."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Login with Cloud credentials",
        description="Authenticate using ERPlora Cloud email and password",
        request=CloudLoginSerializer,
        responses={
            200: CloudLoginResponseSerializer,
            400: ErrorResponseSerializer,
            401: ErrorResponseSerializer,
            503: ErrorResponseSerializer,
        }
    )
    def post(self, request):
        serializer = CloudLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = serializer.validated_data['email']
        password = serializer.validated_data['password']

        cloud_api_url = django_settings.CLOUD_API_URL

        try:
            response = requests.post(
                f"{cloud_api_url}/api/auth/login/",
                json={'email': email, 'password': password},
                timeout=10
            )

            if response.status_code == 200:
                auth_data = response.json()
                access_token = auth_data.get('access')
                refresh_token = auth_data.get('refresh')

                # Cache tokens
                token_cache = TokenCache.get_cache()
                token_cache.cache_jwt_tokens(access_token, refresh_token)

                # Get user info
                user_response = requests.get(
                    f"{cloud_api_url}/api/auth/me/",
                    headers={'Authorization': f'Bearer {access_token}'},
                    timeout=10
                )

                if user_response.status_code == 200:
                    user_info = user_response.json()
                    hub_config = HubConfig.get_config()

                    # Register Hub if first time
                    if not hub_config.is_configured:
                        hub_response = requests.post(
                            f"{cloud_api_url}/api/hubs/register/",
                            json={'name': f"Hub - {email}", 'address': 'Local'},
                            headers={'Authorization': f'Bearer {access_token}'},
                            timeout=10
                        )

                        if hub_response.status_code == 201:
                            hub_data = hub_response.json()
                            hub_config.hub_id = hub_data.get('hub_id')
                            hub_config.cloud_api_token = hub_data.get('cloud_api_token')
                            hub_config.is_configured = True
                            hub_config.save()

                    hub_config = HubConfig.get_config()
                    is_first_user = LocalUser.objects.count() == 0
                    cloud_user_id = user_info.get('id')

                    # Get or create local user
                    local_user = None

                    try:
                        local_user = LocalUser.objects.get(cloud_user_id=cloud_user_id)
                    except LocalUser.DoesNotExist:
                        try:
                            local_user = LocalUser.objects.get(email=email)
                            local_user.cloud_user_id = cloud_user_id
                            local_user.save(update_fields=['cloud_user_id'])
                        except LocalUser.DoesNotExist:
                            local_user = LocalUser.objects.create(
                                cloud_user_id=cloud_user_id,
                                email=email,
                                name=user_info.get('name', email.split('@')[0]),
                                role='admin' if is_first_user else 'cashier',
                                pin_hash='',
                                language=user_info.get('language', hub_config.os_language),
                            )

                    if not local_user.is_active:
                        local_user.is_active = True
                        local_user.pin_hash = ''
                        local_user.save(update_fields=['is_active', 'pin_hash'])

                    first_time = not local_user.pin_hash

                    # Store session
                    request.session['jwt_token'] = access_token
                    request.session['jwt_refresh'] = refresh_token
                    request.session['local_user_id'] = local_user.id
                    request.session['user_name'] = local_user.name
                    request.session['user_email'] = local_user.email
                    request.session['user_role'] = local_user.role
                    request.session['user_language'] = local_user.language

                    return Response({
                        'success': True,
                        'first_time': first_time,
                        'access': access_token,
                        'refresh': refresh_token,
                        'user': {
                            'id': local_user.id,
                            'name': local_user.name,
                            'email': local_user.email,
                            'role': local_user.role,
                        }
                    })
                else:
                    return Response(
                        {'success': False, 'error': 'Failed to get user info'},
                        status=status.HTTP_400_BAD_REQUEST
                    )
            else:
                return Response(
                    {'success': False, 'error': 'Invalid credentials'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        except requests.exceptions.ConnectionError:
            return Response(
                {'success': False, 'error': 'Cannot connect to Cloud. Check internet connection.'},
                status=status.HTTP_503_SERVICE_UNAVAILABLE
            )
        except requests.exceptions.Timeout:
            return Response(
                {'success': False, 'error': 'Connection timeout'},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )


@extend_schema(tags=['Authentication'])
class SetupPinView(APIView):
    """Setup PIN for first-time Cloud login user."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Setup PIN",
        description="Set up a 4-digit PIN for a user after Cloud login",
        request=SetupPinSerializer,
        responses={
            200: SuccessResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request):
        serializer = SetupPinSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user_id = serializer.validated_data['user_id']
        pin = serializer.validated_data['pin']

        try:
            user = LocalUser.objects.get(id=user_id)
        except LocalUser.DoesNotExist:
            return Response(
                {'success': False, 'error': 'User not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        user.set_pin(pin)
        user.last_login = timezone.now()
        user.save()

        # Update session
        request.session['local_user_id'] = user.id
        request.session['user_name'] = user.name
        request.session['user_email'] = user.email
        request.session['user_role'] = user.role
        request.session['user_language'] = user.language

        return Response({'success': True})


@extend_schema(tags=['Authentication'])
class LogoutView(APIView):
    """Logout and clear session."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Logout",
        description="Clear user session and logout",
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        request.session.flush()
        return Response({'success': True, 'message': 'Logged out successfully'})


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path

api_urlpatterns = [
    path('users/', UsersListView.as_view(), name='api_users_list'),
    path('pin-login/', PinLoginView.as_view(), name='api_pin_login'),
    path('cloud-login/', CloudLoginView.as_view(), name='api_cloud_login'),
    path('setup-pin/', SetupPinView.as_view(), name='api_setup_pin'),
    path('logout/', LogoutView.as_view(), name='api_logout'),
]
