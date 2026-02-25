"""
Modules API

Module management, marketplace, and installation endpoints.
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

class ModuleSerializer(serializers.Serializer):
    """Serializer for module information"""
    module_id = serializers.CharField(help_text="Module identifier")
    folder_name = serializers.CharField(help_text="Folder name on disk")
    name = serializers.CharField(help_text="Display name")
    description = serializers.CharField(allow_blank=True)
    version = serializers.CharField()
    author = serializers.CharField(allow_blank=True)
    icon = serializers.CharField(help_text="Icon name (djicons)")
    is_active = serializers.BooleanField()


class ModuleActionSerializer(serializers.Serializer):
    """Response serializer for module actions"""
    success = serializers.BooleanField()
    message = serializers.CharField(required=False)
    requires_restart = serializers.BooleanField(required=False)
    error = serializers.CharField(required=False)


class ModuleInstallSerializer(serializers.Serializer):
    """Serializer for installing module from marketplace"""
    module_slug = serializers.CharField(help_text="Module slug/identifier")
    download_url = serializers.URLField(help_text="URL to download module ZIP")


class ModulePurchaseSerializer(serializers.Serializer):
    """Serializer for purchasing a module"""
    module_id = serializers.CharField(help_text="Module ID from marketplace")


class MarketplaceModuleSerializer(serializers.Serializer):
    """Serializer for marketplace module listing"""
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
    modules = MarketplaceModuleSerializer(many=True)
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

@extend_schema(tags=['Modules'])
class ModuleListView(APIView):
    """List all installed modules."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="List installed modules",
        description="Get list of all installed modules with their status",
        responses={200: ModuleSerializer(many=True)}
    )
    def get(self, request):
        modules_dir = Path(django_settings.MODULES_DIR)
        all_modules = []

        if modules_dir.exists():
            for module_dir in modules_dir.iterdir():
                if not module_dir.is_dir() or module_dir.name.startswith('.'):
                    continue

                module_id = module_dir.name
                is_active = not module_id.startswith('_')
                display_id = module_id.lstrip('_')

                module_data = {
                    'module_id': display_id,
                    'folder_name': module_id,
                    'name': display_id.replace('_', ' ').title(),
                    'description': '',
                    'version': '1.0.0',
                    'author': '',
                    'icon': 'cube-outline',
                    'is_active': is_active,
                }

                # Read module.py if exists
                module_py_path = module_dir / 'module.py'
                if module_py_path.exists():
                    try:
                        import importlib.util
                        spec = importlib.util.spec_from_file_location(f"{display_id}.module", module_py_path)
                        mod = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(mod)
                        module_data['name'] = str(getattr(mod, 'MODULE_NAME', module_data['name']))
                        module_data['description'] = str(getattr(mod, 'MODULE_DESCRIPTION', ''))
                        module_data['version'] = getattr(mod, 'MODULE_VERSION', '1.0.0')
                        module_data['author'] = getattr(mod, 'MODULE_AUTHOR', '')
                        module_data['icon'] = getattr(mod, 'MODULE_ICON', 'cube-outline')
                    except Exception:
                        pass

                all_modules.append(module_data)

        # Sort: active first, then by name
        all_modules.sort(key=lambda x: (not x['is_active'], x['name']))

        return Response(all_modules)


@extend_schema(tags=['Modules'])
class ModuleActivateView(APIView):
    """Activate a module."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Activate module",
        description="Activate a deactivated module by removing underscore prefix from folder",
        responses={
            200: ModuleActionSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request, module_id):
        modules_dir = Path(django_settings.MODULES_DIR)
        disabled_folder = modules_dir / f"_{module_id}"
        active_folder = modules_dir / module_id

        if not disabled_folder.exists():
            return Response(
                {'success': False, 'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if active_folder.exists():
            return Response(
                {'success': False, 'error': 'Module already active'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            disabled_folder.rename(active_folder)

            # Try to load the module
            from apps.modules_runtime.loader import module_loader
            module_loaded = module_loader.load_module(module_id)

            if not module_loaded:
                active_folder.rename(disabled_folder)
                return Response(
                    {'success': False, 'error': f'Failed to load module {module_id}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Mark for restart
            if 'modules_pending_restart' not in request.session:
                request.session['modules_pending_restart'] = []

            if module_id not in request.session['modules_pending_restart']:
                request.session['modules_pending_restart'].append(module_id)
                request.session.modified = True

            return Response({
                'success': True,
                'message': 'Module activated. Restart required for URLs.',
                'requires_restart': True
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Modules'])
class ModuleDeactivateView(APIView):
    """Deactivate a module."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Deactivate module",
        description="Deactivate a module by adding underscore prefix to folder",
        responses={
            200: ModuleActionSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        }
    )
    def post(self, request, module_id):
        modules_dir = Path(django_settings.MODULES_DIR)
        active_folder = modules_dir / module_id
        disabled_folder = modules_dir / f"_{module_id}"

        if not active_folder.exists():
            return Response(
                {'success': False, 'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        if disabled_folder.exists():
            return Response(
                {'success': False, 'error': 'Module already disabled'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            active_folder.rename(disabled_folder)
            return Response({
                'success': True,
                'message': 'Module deactivated. Restart required.',
                'requires_restart': True
            })
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Modules'])
class ModuleDeleteView(APIView):
    """Delete a module."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Delete module",
        description="Permanently delete a module from the filesystem",
        responses={200: SuccessResponseSerializer, 404: ErrorResponseSerializer}
    )
    def delete(self, request, module_id):
        modules_dir = Path(django_settings.MODULES_DIR)
        active_folder = modules_dir / module_id
        disabled_folder = modules_dir / f"_{module_id}"

        folder_to_delete = None
        if active_folder.exists():
            folder_to_delete = active_folder
        elif disabled_folder.exists():
            folder_to_delete = disabled_folder

        if not folder_to_delete:
            return Response(
                {'success': False, 'error': 'Module not found'},
                status=status.HTTP_404_NOT_FOUND
            )

        try:
            shutil.rmtree(folder_to_delete)
            return Response({'success': True, 'message': 'Module deleted successfully.'})
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


@extend_schema(tags=['Modules'])
class ModuleRestartView(APIView):
    """Restart server after module changes."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Restart server",
        description="Restart the server and run migrations after module changes",
        responses={200: SuccessResponseSerializer}
    )
    def post(self, request):
        try:
            from django.core.management import call_command
            call_command('migrate', '--run-syncdb')

            if 'modules_pending_restart' in request.session:
                del request.session['modules_pending_restart']
                request.session.modified = True

            # Trigger full server restart after response is sent:
            # - Gunicorn/Docker: kill master → Docker restarts container
            # - Dev (runserver): touch wsgi.py → auto-reload
            import signal
            import threading

            def _delayed_restart():
                """Kill Gunicorn master after response is sent. Docker restarts the container."""
                import time
                time.sleep(1.5)
                try:
                    # SIGINT to PID 1 (Gunicorn master in Docker) = fast shutdown
                    # Docker restart policy will relaunch the container
                    os.kill(1, signal.SIGINT)
                except Exception:
                    try:
                        # Non-Docker: kill parent process
                        os.kill(os.getppid(), signal.SIGTERM)
                    except Exception:
                        # Fallback for dev server
                        wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
                        if wsgi_file.exists():
                            wsgi_file.touch()

            threading.Thread(target=_delayed_restart, daemon=True).start()

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
    """Fetch modules from Cloud marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Get marketplace modules",
        description="Fetch available modules from ERPlora Cloud marketplace",
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
                f"{cloud_api_url}/api/marketplace/modules/",
                headers=headers,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                modules = data.get('results', data) if isinstance(data, dict) else data

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
                    'modules': modules if isinstance(modules, list) else [],
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
class ModulePurchaseView(APIView):
    """Purchase a module from marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Purchase module",
        description="Initiate purchase of a module from the marketplace",
        request=ModulePurchaseSerializer,
        responses={
            200: PurchaseResponseSerializer,
            400: ErrorResponseSerializer,
            409: ErrorResponseSerializer,
        }
    )
    def post(self, request):
        serializer = ModulePurchaseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        module_id = serializer.validated_data['module_id']

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
                f"{cloud_api_url}/api/marketplace/modules/{module_id}/purchase/",
                json={
                    'success_url': f"{cloud_api_url}/dashboard/modules/marketplace/payment-success/?module_id={module_id}&source=hub",
                    'cancel_url': f"{cloud_api_url}/dashboard/modules/marketplace/"
                },
                headers=headers,
                timeout=30
            )

            result = response.json()

            if response.status_code == 201 and result.get('is_free'):
                return Response({'success': True, 'is_free': True, 'message': 'Free module acquired'})

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
                    {'success': False, 'error': 'You already own this module', 'already_owned': True},
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
class ModuleOwnershipView(APIView):
    """Check module ownership."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Check ownership",
        description="Check if the Hub owner owns a specific module",
        responses={200: OwnershipResponseSerializer, 400: ErrorResponseSerializer}
    )
    def get(self, request, module_id):
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
                f"{cloud_api_url}/api/marketplace/modules/{module_id}/check_ownership/",
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
class ModuleInstallView(APIView):
    """Install module from marketplace."""
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Install module",
        description="Download and install a module from the marketplace",
        request=ModuleInstallSerializer,
        responses={200: ModuleActionSerializer, 400: ErrorResponseSerializer}
    )
    def post(self, request):
        serializer = ModuleInstallSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        module_slug = serializer.validated_data['module_slug']
        download_url = serializer.validated_data['download_url']

        try:
            modules_dir = Path(django_settings.MODULES_DIR)

            response = requests.get(download_url, timeout=60, stream=True)
            response.raise_for_status()

            with tempfile.NamedTemporaryFile(delete=False, suffix='.zip') as tmp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    tmp_file.write(chunk)
                tmp_path = tmp_file.name

            try:
                # Extract to temp directory first to discover MODULE_ID
                with tempfile.TemporaryDirectory() as tmp_extract:
                    tmp_extract_path = Path(tmp_extract)

                    with zipfile.ZipFile(tmp_path, 'r') as zip_ref:
                        zip_ref.extractall(tmp_extract_path)

                    # Find the extracted module root (may be nested in a folder)
                    extracted_items = list(tmp_extract_path.iterdir())
                    if len(extracted_items) == 1 and extracted_items[0].is_dir():
                        extracted_root = extracted_items[0]
                    else:
                        extracted_root = tmp_extract_path

                    # Read MODULE_ID from module.py
                    module_id = self._get_module_id(extracted_root, module_slug)

                    # Check if already installed
                    module_target_dir = modules_dir / module_id
                    if module_target_dir.exists() or (modules_dir / f"_{module_id}").exists():
                        return Response(
                            {'success': False, 'error': f'Module {module_id} already installed'},
                            status=status.HTTP_400_BAD_REQUEST
                        )

                    # Move to final location
                    shutil.copytree(extracted_root, module_target_dir)

                from apps.modules_runtime.loader import module_loader
                module_loader.load_module(module_id)

                # Run migrations for the new module
                try:
                    from django.core.management import call_command
                    call_command('migrate', '--run-syncdb')
                except Exception:
                    pass  # Non-fatal: migrations will run on next restart

                # Send success response, then restart server so URLs are registered
                import signal
                import threading

                def _delayed_restart():
                    """Kill Gunicorn master after response is sent. Docker restarts the container."""
                    import time
                    time.sleep(2)
                    try:
                        os.kill(1, signal.SIGINT)
                    except Exception:
                        try:
                            os.kill(os.getppid(), signal.SIGTERM)
                        except Exception:
                            wsgi_file = Path(django_settings.BASE_DIR) / 'config' / 'wsgi.py'
                            if wsgi_file.exists():
                                wsgi_file.touch()

                threading.Thread(target=_delayed_restart, daemon=True).start()

                return Response({
                    'success': True,
                    'message': f'Module {module_id} installed successfully. Server restarting...',
                })

            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

        except requests.exceptions.RequestException as e:
            return Response(
                {'success': False, 'error': f'Failed to download module: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        except zipfile.BadZipFile:
            return Response(
                {'success': False, 'error': 'Invalid module package'},
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {'success': False, 'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    @staticmethod
    def _get_module_id(extracted_root: Path, fallback: str) -> str:
        """Read MODULE_ID from module.py, falling back to slug."""
        # Try module.py first
        module_py_path = extracted_root / 'module.py'
        if module_py_path.exists():
            try:
                content = module_py_path.read_text(encoding='utf-8')
                for line in content.splitlines():
                    line = line.strip()
                    if line.startswith('MODULE_ID'):
                        # Parse: MODULE_ID = 'inventory' or MODULE_ID = "inventory"
                        value = line.split('=', 1)[1].strip().strip("'\"")
                        if value:
                            return value
            except Exception:
                pass

        return fallback


# =============================================================================
# URL Patterns
# =============================================================================

from django.urls import path

api_urlpatterns = [
    # Module management
    path('', ModuleListView.as_view(), name='api_modules_list'),
    path('<str:module_id>/activate/', ModuleActivateView.as_view(), name='api_module_activate'),
    path('<str:module_id>/deactivate/', ModuleDeactivateView.as_view(), name='api_module_deactivate'),
    path('<str:module_id>/delete/', ModuleDeleteView.as_view(), name='api_module_delete'),
    path('restart/', ModuleRestartView.as_view(), name='api_modules_restart'),

    # Marketplace
    path('marketplace/', MarketplaceView.as_view(), name='api_marketplace'),
    path('marketplace/purchase/', ModulePurchaseView.as_view(), name='api_module_purchase'),
    path('marketplace/install/', ModuleInstallView.as_view(), name='api_module_install'),
    path('marketplace/<str:module_id>/ownership/', ModuleOwnershipView.as_view(), name='api_module_ownership'),
]
