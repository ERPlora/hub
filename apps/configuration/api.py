"""
Configuration API

Hub and Store configuration endpoints.
"""
from django.conf import settings as django_settings
from django.utils.translation import activate, gettext as _
from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from drf_spectacular.utils import extend_schema

from .models import HubConfig, StoreConfig
from apps.core.api_base import IsAuthenticated, IsAdmin, SuccessResponseSerializer, ErrorResponseSerializer


# =============================================================================
# Serializers
# =============================================================================

class HubConfigSerializer(serializers.ModelSerializer):
    """Serializer for Hub configuration"""
    currency_choices = serializers.SerializerMethodField()
    language_choices = serializers.SerializerMethodField()
    theme_choices = serializers.SerializerMethodField()

    class Meta:
        model = HubConfig
        fields = [
            'hub_id', 'is_configured', 'os_language', 'currency',
            'color_theme', 'dark_mode', 'auto_print',
            'currency_choices', 'language_choices', 'theme_choices',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'hub_id', 'is_configured', 'created_at', 'updated_at',
            'currency_choices', 'language_choices', 'theme_choices'
        ]

    def get_currency_choices(self, obj):
        return [{'code': c[0], 'name': c[1]} for c in django_settings.CURRENCY_CHOICES]

    def get_language_choices(self, obj):
        return [{'code': c[0], 'name': c[1]} for c in django_settings.LANGUAGES]

    def get_theme_choices(self, obj):
        return [{'code': c[0], 'name': c[1]} for c in HubConfig._meta.get_field('color_theme').choices]


class HubConfigUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating Hub configuration"""

    class Meta:
        model = HubConfig
        fields = ['os_language', 'currency', 'color_theme', 'dark_mode', 'auto_print']

    def validate_currency(self, value):
        valid_currencies = [c[0] for c in django_settings.CURRENCY_CHOICES]
        if value not in valid_currencies:
            raise serializers.ValidationError(_("Invalid currency"))
        return value

    def validate_os_language(self, value):
        valid_languages = [lang[0] for lang in django_settings.LANGUAGES]
        if value not in valid_languages:
            raise serializers.ValidationError(_("Invalid language"))
        return value


class StoreConfigSerializer(serializers.ModelSerializer):
    """Serializer for Store configuration"""
    is_complete = serializers.SerializerMethodField()

    class Meta:
        model = StoreConfig
        fields = [
            'business_name', 'business_address', 'vat_number',
            'phone', 'email', 'website', 'logo',
            'tax_rate', 'tax_included',
            'receipt_header', 'receipt_footer',
            'is_configured', 'is_complete',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['is_configured', 'is_complete', 'created_at', 'updated_at']

    def get_is_complete(self, obj):
        return obj.is_complete()


class StoreConfigUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating Store configuration"""

    class Meta:
        model = StoreConfig
        fields = [
            'business_name', 'business_address', 'vat_number',
            'phone', 'email', 'website', 'logo',
            'tax_rate', 'tax_included',
            'receipt_header', 'receipt_footer'
        ]


class ThemeToggleSerializer(serializers.Serializer):
    """Serializer for theme toggle response"""
    success = serializers.BooleanField()
    dark_mode = serializers.BooleanField()


class LanguageChangeSerializer(serializers.Serializer):
    """Serializer for language change request"""
    language = serializers.CharField(max_length=10, help_text="Language code (e.g., 'en', 'es')")


# =============================================================================
# API Views
# =============================================================================

@extend_schema(tags=['Configuration'])
class HubConfigView(APIView):
    """Hub configuration management."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get Hub configuration",
        description="Get current Hub configuration including theme, language, and currency settings",
        responses={200: HubConfigSerializer}
    )
    def get(self, request):
        hub_config = HubConfig.get_config()
        serializer = HubConfigSerializer(hub_config)
        return Response(serializer.data)

    @extend_schema(
        summary="Update Hub configuration",
        description="Update Hub configuration settings",
        request=HubConfigUpdateSerializer,
        responses={200: HubConfigSerializer, 400: ErrorResponseSerializer}
    )
    def patch(self, request):
        hub_config = HubConfig.get_config()
        serializer = HubConfigUpdateSerializer(hub_config, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()

            # Update session language if changed
            if 'os_language' in request.data:
                request.session['user_language'] = request.data['os_language']

            return Response(HubConfigSerializer(hub_config).data)

        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        summary="Replace Hub configuration",
        description="Replace Hub configuration settings (all fields)",
        request=HubConfigUpdateSerializer,
        responses={200: HubConfigSerializer, 400: ErrorResponseSerializer}
    )
    def put(self, request):
        hub_config = HubConfig.get_config()
        serializer = HubConfigUpdateSerializer(hub_config, data=request.data)

        if serializer.is_valid():
            serializer.save()
            return Response(HubConfigSerializer(hub_config).data)

        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(tags=['Configuration'])
class StoreConfigView(APIView):
    """Store/Business configuration management."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser, JSONParser]

    @extend_schema(
        summary="Get Store configuration",
        description="Get current store/business configuration",
        responses={200: StoreConfigSerializer}
    )
    def get(self, request):
        store_config = StoreConfig.get_config()
        serializer = StoreConfigSerializer(store_config)
        return Response(serializer.data)

    @extend_schema(
        summary="Update Store configuration",
        description="Update store/business configuration (supports multipart for logo upload)",
        request=StoreConfigUpdateSerializer,
        responses={200: StoreConfigSerializer, 400: ErrorResponseSerializer}
    )
    def patch(self, request):
        store_config = StoreConfig.get_config()
        serializer = StoreConfigUpdateSerializer(store_config, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            store_config.is_configured = store_config.is_complete()
            store_config.save()
            return Response(StoreConfigSerializer(store_config).data)

        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

    @extend_schema(
        summary="Replace Store configuration",
        description="Replace store/business configuration (all fields)",
        request=StoreConfigUpdateSerializer,
        responses={200: StoreConfigSerializer, 400: ErrorResponseSerializer}
    )
    def put(self, request):
        store_config = StoreConfig.get_config()
        serializer = StoreConfigUpdateSerializer(store_config, data=request.data)

        if serializer.is_valid():
            serializer.save()
            store_config.is_configured = store_config.is_complete()
            store_config.save()
            return Response(StoreConfigSerializer(store_config).data)

        return Response(
            {'success': False, 'errors': serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )


@extend_schema(tags=['Configuration'])
class ThemeToggleView(APIView):
    """Quick theme toggle endpoint."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Toggle dark mode",
        description="Toggle dark mode on/off",
        responses={200: ThemeToggleSerializer}
    )
    def post(self, request):
        hub_config = HubConfig.get_config()
        hub_config.dark_mode = not hub_config.dark_mode
        hub_config.save()

        return Response({
            'success': True,
            'dark_mode': hub_config.dark_mode
        })


@extend_schema(tags=['Configuration'])
class LanguageChangeView(APIView):
    """Language change endpoint."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Change language",
        description="Change the system language",
        request=LanguageChangeSerializer,
        responses={200: SuccessResponseSerializer, 400: ErrorResponseSerializer}
    )
    def post(self, request):
        serializer = LanguageChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        language = serializer.validated_data['language']
        valid_languages = [lang[0] for lang in django_settings.LANGUAGES]

        if language not in valid_languages:
            return Response(
                {'success': False, 'error': f'Invalid language. Valid options: {valid_languages}'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Update Hub config
        hub_config = HubConfig.get_config()
        hub_config.os_language = language
        hub_config.save()

        # Update session
        activate(language)
        request.session['user_language'] = language

        return Response({
            'success': True,
            'language': language
        })


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path

api_urlpatterns = [
    path('hub/', HubConfigView.as_view(), name='api_hub_config'),
    path('store/', StoreConfigView.as_view(), name='api_store_config'),
    path('theme/toggle/', ThemeToggleView.as_view(), name='api_theme_toggle'),
    path('language/', LanguageChangeView.as_view(), name='api_language_change'),
]
