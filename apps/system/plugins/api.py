"""
Plugins API

Plugin management, marketplace, and installation endpoints.
"""
import json
import os
import shutil
import tempfile
import zipfile
import requests
from pathlib import Path

from django.conf import settings as django_settings
from rest_framework import status, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema, OpenApiResponse

from apps.configuration.models import HubConfig
from apps.core.api_base import IsAuthenticated, IsAdmin, SuccessResponseSerializer, ErrorResponseSerializer


# =============================================================================
# Serializers
# =============================================================================

class PluginSerializer(serializers.Serializer):
    """Serializer for plugin information"""
    plugin_id = serializers.CharField(help_text="Plugin identifier")
    folder_name = serializers.CharField(help_text="Folder name on disk")
    name = serializers.CharField(help_text="Display name")
    description = serializers.CharField(allow_blank=True)
    version = serializers.CharField()
    author = serializers.CharField(allow_blank=True)
    icon = serializers.CharField(help_text="Ionicon name")
    is_active = serializers.BooleanField()


class PluginActionSerializer(serializers.Serializer):
    """Response serializer for plugin actions"""
    success = serializers.BooleanField()
    message = serializers.CharField(required=False)
    requires_restart = serializers.BooleanField(required=False)
    error = serializers.CharField(required=False)


class PluginInstallSerializer(serializers.Serializer):
    """Serializer for installing plugin from marketplace"""
    plugin_slug = serializers.CharField(help_text="Plugin slug/identifier")
    download_url = serializers.URLField(help_text="URL to download plugin ZIP")


class PluginPurchaseSerializer(serializers.Serializer):
    """Serializer for purchasing a plugin"""
    plugin_id = serializers.CharField(help_text="Plugin ID from marketplace")


class MarketplacePluginSerializer(serializers.Serializer):
    """Serializer for marketplace plugin listing"""
    id = serializers.IntegerField()
    slug = serializers.CharField()
    name = serializers.CharField()
    description = serializers.CharField()
    version = serializers.CharField()
    author = serializers.CharField(required=False, allow_blank=True)
    price = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    is_free = serializers.BooleanField(required=False)
    download_url = serializers.URLField(required=False, allow_null=True)
    icon_url = serializers.URLField(required=False, allow_null=True)
    category = serializers.CharField(required=False, allow_blank=True)


class MarketplaceResponseSerializer(serializers.Serializer):
    """Response for marketplace fetch"""
    success = serializers.BooleanField()
    plugins = MarketplacePluginSerializer(many=True)
    categories = serializers.ListField(child=serializers.DictField(), required=False)


class OwnershipResponseSerializer(serializers.Serializer):
    """Response for ownership check"""
    success = serializers.BooleanField()
    owned = serializers.BooleanField()
    purchase_type = serializers.CharField(required=False)


class PurchaseResponseSerializer(serializers.Serializer):
    """Response for purchase"""
    success = serializers.BooleanField()
    is_free = serializers.BooleanField(required=False)
    checkout_url = serializers.URLField(required=False)
    session_id = serializers.CharField(required=False)
    mode = serializers.CharField(required=False)
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False)
    currency = serializers.CharField(required=False)


# =============================================================================
# API Views
# =============================================================================

@extend_schema(tags=['Plugins'])
class PluginListView(APIView):
    """List all installed plugins."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List installed plugins",
        description="Get list of all installed plugins with their status",
        responses={200: PluginSerializer(many=True)}
    )
    def get(self, request):
        plugins_dir = Path(django_settings.PLUGINS_DIR)
        all_plugins = []

        if plugins_dir.exists():
            for plugin_dir in plugins_dir.iterdir():
                if not plugin_dir.is_dir() or plugin_dir.name.startswith('.'):
                    continue

                plugin_id = plugin_dir.name
                is_active = not plugin_id.startswith('_')
                display_id = plugin_id.lstrip('_')

                plugin_data = {
                    'plugin_id': display_id,
                    'folder_name': plugin_id,
                    'name': display_id.replace('_', ' ').title(),
                    'description': '',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'cube-outline',
                    'is_active': is_active,
                }

                # Read plugin.json if exists
                plugin_json_path = plugin_dir / 'plugin.json'
                if plugin_json_path.exists():
                    try:
                        with open(plugin_json_path, 'r', encoding='utf-8') as f:
                            json_data = json.load(f)
                            plugin_data['name'] = json_data.get('name', plugin_data['name'])
                            plugin_data['description'] = json_data.get('description', '')
                            plugin_data['version'] = json_data.get('version', '1.0.0')
                            plugin_data['author'] = json_data.get('author', '')
                            menu_config = json_data.get('menu', {})
                            plugin_data['icon'] = menu_config.get('icon', 'cube-outline')
                    except Exception:
                        pass

                all_plugins.append(plugin_data)

        # Sort: active first, then by name
        all_plugins.sort(key=lambda x: (not x['is_active'], x['name']))

        return Response(all_plugins)


@extend_schema(tags=['Plugins'])
class PluginActivateView(APIView):
    """Activate a plugin."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Activate plugin",
        description="Activate a deactivated plugin by removing underscore prefix from folder",
        responses={
            200: PluginActionSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request, plugin_id):
        plugins_dir = Path(django_settings.PLUGINS_DIR)
        disabled_folder = plugins_dir / f"_{plugin_id}"
        active_folder = plugins_dir / plugin_id

        if not disabled_folder.exists():
            return Response(
                {'success': False, 'error': 'Plugin not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if active_folder.exists():
            return Response(
                {'success': False, 'error': 'Plugin already active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            disabled_folder.rename(active_folder)

            # Try to load the plugin
            from apps.plugins_runtime.loader import plugin_loader
            plugin_loaded = plugin_loader.load_plugin(plugin_id)

            if not plugin_loaded:
                active_folder.rename(disabled_folder)
                return Response(
                    {'success': False, 'error': f'Failed to load plugin {plugin_id}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Mark for restart
            if 'plugins_pending_restart' not in request.session:
                request.session['plugins_pending_restart'] = []

            if plugin_id not in request.session['plugins_pending_restart']:
                request.session['plugins_pending_restart'].append(plugin_id)
                request.session.modified = True

            return Response({
                'success': True,
                'message': 'Plugin activated. Restart required for URLs.',
                'requires_restart': True
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Plugins'])
class PluginDeactivateView(APIView):
    """Deactivate a plugin."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate plugin",
        description="Deactivate a plugin by adding underscore prefix to folder",
        responses={
            200: PluginActionSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request, plugin_id):
        plugins_dir = Path(django_settings.PLUGINS_DIR)
        active_folder = plugins_dir / plugin_id
        disabled_folder = plugins_dir / f"_{plugin_id}"

        if not active_folder.exists():
            return Response(
                {'success': False, 'error': 'Plugin not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if disabled_folder.exists():
            return Response(
                {'success': False, 'error': 'Plugin already disabled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            active_folder.rename(disabled_folder)
            return Response({
                'success': True,
                'message': 'Plugin deactivated. Restart required.',
                'requires_restart': True
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Plugins'])
class PluginDeleteView(APIView):
    """Delete a plugin."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete plugin",
        description="Permanently delete a plugin from the filesystem",
        responses={200: SuccessResponseSerializer, 404: ErrorResponseSerializer}
    )
    def delete(self, request, plugin_id):
        plugins_dir = Path(django_settings.PLUGINS_DIR)
        active_folder = plugins_dir / plugin_id
        disabled_folder = plugins_dir / f"_{plugin_id}"

        folder_to_delete = None
        if active_folder.exists():
            folder_to_delete = active_folder
        elif disabled_folder.exists():
            folder_to_delete = disabled_folder

        if not folder_to_delete:
            return Response(
                {'success': False, 'error': 'Plugin not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            shutil.rmtree(folder_to_delete)
            return Response({'success': True, 'message': 'Plugin deleted successfully.'})
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Plugins'])
class PluginRestartView(APIView):
    """Restart server after plugin changes."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Restart server",
        description="Restart the server and run migrations after plugin changes",
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        try:
            from django.core.management import call_command
            call_command('migrate', '--run-syncdb')

            if 'plugins_pending_restart' in request.session:
                del request.session['plugins_pending_restart']
                request.session.modified = True

            wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
            if wsgi_file.exists():
                wsgi_file.touch()

            return Response({
                'success': True,
                'message': 'Server restarting... Migrations applied.'
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Marketplace'])
class MarketplaceView(APIView):
    """Fetch plugins from Cloud marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get marketplace plugins",
        description="Fetch available plugins from ERPlora Cloud marketplace",
        responses={
            200: MarketplaceResponseSerializer,
            401: ErrorResponseSerializer,
            500: ErrorResponseSerializer,
        }
    )
    def get(self, request):
        try:
            hub_config = HubConfig.get_solo()
            cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')

            auth_token = hub_config.hub_jwt or hub_config.cloud_api_token
            if not auth_token:
                return Response(
                    {'success': False, 'error': 'Hub not connected to Cloud'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

            headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

            response = requests.get(
                f"{cloud_api_url}/api/marketplace/plugins/",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                plugins = data.get('results', data) if isinstance(data, dict) else data

                categories = []
                try:
                    cat_response = requests.get(
                        f"{cloud_api_url}/api/marketplace/categories/",
                        headers=headers,
                        timeout=10
                    )
                    if cat_response.status_code == 200:
                        categories = cat_response.json()
                except Exception:
                    pass

                return Response({
                    'success': True,
                    'plugins': plugins if isinstance(plugins, list) else [],
                    'categories': categories
                })
            else:
                return Response(
                    {'success': False, 'error': f'Cloud API returned {response.status_code}'},
                    status=response.status_code
                )

        except requests.exceptions.RequestException as e:
            return Response(
                {'success': False, 'error': f'Failed to connect to Cloud: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Marketplace'])
class PluginPurchaseView(APIView):
    """Purchase a plugin from marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Purchase plugin",
        description="Initiate purchase of a plugin from the marketplace",
        request=PluginPurchaseSerializer,
        responses={
            200: PurchaseResponseSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        }
    )
    def post(self, request):
        serializer = PluginPurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plugin_id = serializer.validated_data['plugin_id']

        try:
            hub_config = HubConfig.get_solo()
            auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

            if not auth_token:
                return Response(
                    {'success': False, 'error': 'Hub not connected to Cloud'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
            headers = {'Content-Type': 'application/json', 'X-Hub-Token': auth_token}

            response = requests.post(
                f"{cloud_api_url}/api/marketplace/plugins/{plugin_id}/purchase/",
                json={
                    'success_url': f"{cloud_api_url}/dashboard/plugins/marketplace/payment-success/?plugin_id={plugin_id}&source=hub",
                    'cancel_url': f"{cloud_api_url}/dashboard/plugins/marketplace/"
                },
                headers=headers,
                timeout=30
            )

            result = response.json()

            if response.status_code == 201 and result.get('is_free'):
                return Response({'success': True, 'is_free': True, 'message': 'Free plugin acquired'})

            if response.status_code == 200 and result.get('checkout_url'):
                return Response({
                    'success': True,
                    'checkout_url': result['checkout_url'],
                    'session_id': result.get('session_id'),
                    'mode': result.get('mode'),
                    'amount': result.get('amount'),
                    'currency': result.get('currency', 'EUR')
                })

            if response.status_code == 409:
                return Response(
                    {'success': False, 'error': 'You already own this plugin', 'already_owned': True},
                    status=status.HTTP_409_CONFLICT
                )

            return Response(
                {'success': False, 'error': result.get('error', 'Unknown error')},
                status=response.status_code
            )

        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Marketplace'])
class PluginOwnershipView(APIView):
    """Check plugin ownership."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Check ownership",
        description="Check if the Hub owner owns a specific plugin",
        responses={200: OwnershipResponseSerializer, 400: ErrorResponseSerializer}
    )
    def get(self, request, plugin_id):
        try:
            hub_config = HubConfig.get_solo()
            auth_token = hub_config.hub_jwt or hub_config.cloud_api_token

            if not auth_token:
                return Response(
                    {'success': False, 'owned': False, 'error': 'Hub not connected'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            cloud_api_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
            headers = {'Accept': 'application/json', 'X-Hub-Token': auth_token}

            response = requests.get(
                f"{cloud_api_url}/api/marketplace/plugins/{plugin_id}/check_ownership/",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return Response({
                    'success': True,
                    'owned': data.get('owned', False),
                    'purchase_type': data.get('purchase_type'),
                })
            else:
                return Response(
                    {'success': False, 'owned': False, 'error': f'Cloud API returned {response.status_code}'},
                    status=response.status_code
                )

        except Exception as e:
            return Response(
                {'success': False, 'owned': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Marketplace'])
class PluginInstallView(APIView):
    """Install plugin from marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Install plugin",
        description="Download and install a plugin from the marketplace",
        request=PluginInstallSerializer,
        responses={200: PluginActionSerializer, 400: ErrorResponseSerializer}
    )
    def post(self, request):
        serializer = PluginInstallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        plugin_slug = serializer.validated_data['plugin_slug']
        download_url = serializer.validated_data['download_url']

        try:
            plugins_dir = Path(django_settings.PLUGINS_DIR)
            plugin_target_dir = plugins_dir / plugin_slug

            if plugin_target_dir.exists() or (plugins_dir / f"_{plugin_slug}").exists():
                return Response(
                    {'success': False, 'error': 'Plugin already installed'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            response = requests.get(download_url, timeout=60, stream=True)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            try:
                with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                    namelist = zip_ref.namelist()
                    root_folders = set(name.split('/')[0] for name in namelist if name.split('/')[0])

                    if len(root_folders) == 1:
                        root_folder = list(root_folders)[0]
                        zip_ref.extractall(plugins_dir)
                        extracted_dir = plugins_dir / root_folder
                        if extracted_dir != plugin_target_dir:
                            extracted_dir.rename(plugin_target_dir)
                    else:
                        plugin_target_dir.mkdir(parents=True, exist_ok=True)
                        zip_ref.extractall(plugin_target_dir)

                from apps.plugins_runtime.loader import plugin_loader
                plugin_loader.load_plugin(plugin_slug)

                if 'plugins_pending_restart' not in request.session:
                    request.session['plugins_pending_restart'] = []

                if plugin_slug not in request.session['plugins_pending_restart']:
                    request.session['plugins_pending_restart'].append(plugin_slug)
                    request.session.modified = True

                return Response({
                    'success': True,
                    'message': f'Plugin {plugin_slug} installed successfully',
                    'requires_restart': True
                })

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except requests.exceptions.RequestException as e:
            return Response(
                {'success': False, 'error': f'Failed to download plugin: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except zipfile.BadZipFile:
            return Response(
                {'success': False, 'error': 'Invalid plugin package'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path

api_urlpatterns = [
    # Plugin management
    path('', PluginListView.as_view(), name='api_plugins_list'),
    path('<str:plugin_id>/activate/', PluginActivateView.as_view(), name='api_plugin_activate'),
    path('<str:plugin_id>/deactivate/', PluginDeactivateView.as_view(), name='api_plugin_deactivate'),
    path('<str:plugin_id>/delete/', PluginDeleteView.as_view(), name='api_plugin_delete'),
    path('restart/', PluginRestartView.as_view(), name='api_plugins_restart'),

    # Marketplace
    path('marketplace/', MarketplaceView.as_view(), name='api_marketplace'),
    path('marketplace/purchase/', PluginPurchaseView.as_view(), name='api_plugin_purchase'),
    path('marketplace/install/', PluginInstallView.as_view(), name='api_plugin_install'),
    path('marketplace/<str:plugin_id>/ownership/', PluginOwnershipView.as_view(), name='api_plugin_ownership'),
]
