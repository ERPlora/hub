"""
Core API

System endpoints: health check, updates, language.
"""
from django.conf import settings as django_settings
from django.utils.translation import activate
from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from drf_spectacular.utils import extend_schema

from apps.accounts.models import LocalUser
from .api_base import IsAuthenticated, SuccessResponseSerializer, ErrorResponseSerializer


# =============================================================================
# Serializers
# =============================================================================

class HealthCheckSerializer(serializers.Serializer):
    """Serializer for health check response"""
    status = serializers.CharField()
    database = serializers.CharField()
    version = serializers.CharField()


class UpdateInfoSerializer(serializers.Serializer):
    """Serializer for update information"""
    current_version = serializers.CharField()
    latest_version = serializers.CharField(required=False)
    update_available = serializers.BooleanField()
    download_url = serializers.URLField(required=False)
    release_notes = serializers.CharField(required=False)
    last_check = serializers.DateTimeField(required=False)


class LanguageSerializer(serializers.Serializer):
    """Serializer for language change"""
    language = serializers.CharField(max_length=10, help_text="Language code (e.g., 'en', 'es')")
    next = serializers.CharField(required=False, help_text="URL to redirect after language change")


# =============================================================================
# API Views
# =============================================================================

@extend_schema(tags=['System'])
class HealthCheckView(APIView):
    """Health check endpoint for monitoring."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Health check",
        description="Check if the Hub is healthy (for Docker, monitoring, etc.)",
        responses={200: HealthCheckSerializer, 500: ErrorResponseSerializer}
    )
    def get(self, request):
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")

            import config.settings as settings_module
            version = getattr(settings_module, 'HUB_VERSION', 'unknown')

            return Response({
                'status': 'ok',
                'database': 'ok',
                'version': version,
            })

        except Exception as e:
            return Response({
                'status': 'error',
                'database': 'error',
                'error': str(e),
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@extend_schema(tags=['System'])
class UpdateCheckView(APIView):
    """Check for available updates."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Check for updates",
        description="Check if there are any available updates for the Hub",
        responses={200: UpdateInfoSerializer}
    )
    def get(self, request):
        try:
            from .views_update import check_updates as check_updates_view
            # Get update info from existing view logic
            import config.settings as settings_module
            current_version = getattr(settings_module, 'HUB_VERSION', '0.1.0')

            return Response({
                'current_version': current_version,
                'update_available': False,  # TODO: Implement actual check
                'latest_version': current_version,
            })
        except Exception as e:
            return Response({
                'current_version': 'unknown',
                'update_available': False,
                'error': str(e)
            })


@extend_schema(tags=['System'])
class UpdateStatusView(APIView):
    """Get update status."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get update status",
        description="Get the current update/installation status",
        responses={200: UpdateInfoSerializer}
    )
    def get(self, request):
        import config.settings as settings_module
        current_version = getattr(settings_module, 'HUB_VERSION', '0.1.0')

        return Response({
            'current_version': current_version,
            'update_available': False,
            'status': 'up_to_date'
        })


@extend_schema(tags=['System'])
class LanguageView(APIView):
    """Change user language preference."""
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Set language",
        description="Change the user's language preference",
        request=LanguageSerializer,
        responses={200: SuccessResponseSerializer, 400: ErrorResponseSerializer}
    )
    def post(self, request):
        serializer = LanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        language = serializer.validated_data['language']
        valid_languages = [lang[0] for lang in django_settings.LANGUAGES]

        if language not in valid_languages:
            return Response(
                {'success': False, 'error': f'Invalid language. Valid options: {valid_languages}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Activate the language
        activate(language)

        # Save to LocalUser if authenticated
        if 'local_user_id' in request.session:
            try:
                user = LocalUser.objects.get(id=request.session['local_user_id'])
                user.language = language
                user.save(update_fields=['language'])
                request.session['user_language'] = language
            except LocalUser.DoesNotExist:
                pass

        # Set in session
        request.session[django_settings.LANGUAGE_COOKIE_NAME] = language

        return Response({
            'success': True,
            'language': language
        })


@extend_schema(tags=['System'])
class CurrentUserView(APIView):
    """Get current logged-in user info."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get current user",
        description="Get information about the currently logged-in user",
        responses={200: serializers.DictField()}
    )
    def get(self, request):
        return Response({
            'id': request.session.get('local_user_id'),
            'name': request.session.get('user_name'),
            'email': request.session.get('user_email'),
            'role': request.session.get('user_role'),
            'language': request.session.get('user_language'),
            'is_authenticated': True,
        })


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path

api_urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='api_health'),
    path('updates/check/', UpdateCheckView.as_view(), name='api_updates_check'),
    path('updates/status/', UpdateStatusView.as_view(), name='api_updates_status'),
    path('language/', LanguageView.as_view(), name='api_language'),
    path('me/', CurrentUserView.as_view(), name='api_current_user'),
]
