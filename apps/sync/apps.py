import os
import sys
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class SyncConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.sync'
    verbose_name = _('Cloud Synchronization')

    def ready(self):
        """
        Initialize sync app.

        - Initialize HubConfig from environment variables (HUB_JWT, etc.)
        - Start heartbeat service in web deployment mode
        """
        # Skip during migrations or management commands
        if 'migrate' in sys.argv or 'makemigrations' in sys.argv:
            return

        # Skip if running tests
        if 'test' in sys.argv:
            return

        # Initialize HubConfig from env vars
        self._init_hub_config()

        # Start heartbeat service (only in web mode with autoreload disabled)
        self._start_heartbeat_service()

    def _init_hub_config(self):
        """Initialize HubConfig from environment variables."""
        from django.conf import settings

        # Only run in web deployment mode
        deployment_mode = getattr(settings, 'DEPLOYMENT_MODE', 'local')
        if deployment_mode != 'web':
            return

        try:
            from apps.configuration.models import HubConfig

            config = HubConfig.get_solo()
            updated_fields = []

            # Update hub_id from env
            hub_id_env = os.environ.get('HUB_ID')
            if hub_id_env and str(config.hub_id) != hub_id_env:
                import uuid
                try:
                    config.hub_id = uuid.UUID(hub_id_env)
                    updated_fields.append('hub_id')
                except ValueError:
                    pass

            # Update hub_jwt from env
            hub_jwt_env = getattr(settings, 'HUB_JWT', '')
            if hub_jwt_env and config.hub_jwt != hub_jwt_env:
                config.hub_jwt = hub_jwt_env
                updated_fields.append('hub_jwt')

            # Update cloud_api_token from env (legacy)
            cloud_api_token_env = os.environ.get('CLOUD_API_TOKEN')
            if cloud_api_token_env and config.cloud_api_token != cloud_api_token_env:
                config.cloud_api_token = cloud_api_token_env
                updated_fields.append('cloud_api_token')

            if updated_fields:
                config.save()
                print(f"[SYNC] HubConfig updated from env: {', '.join(updated_fields)}")

        except Exception as e:
            print(f"[SYNC] Error initializing HubConfig: {e}")

    def _start_heartbeat_service(self):
        """Start Cloud sync service (WebSocket or HTTP polling)."""
        from django.conf import settings

        # Check if sync is enabled
        sync_enabled = getattr(settings, 'CLOUD_SYNC_ENABLED', True)
        if not sync_enabled:
            return

        # Don't start in Django's autoreloader child process
        # (RUN_MAIN is set in the forked process)
        if os.environ.get('RUN_MAIN') != 'true':
            # Only start in the main process when using runserver
            # In production (daphne/gunicorn), RUN_MAIN won't be set
            if 'runserver' in sys.argv:
                return

        # Check if Hub is configured (has hub_jwt)
        try:
            from apps.configuration.models import HubConfig
            config = HubConfig.get_solo()
            if not config.hub_jwt:
                print("[SYNC] Hub not configured (no hub_jwt), skipping heartbeat")
                return
        except Exception:
            return

        # Choose sync method: WebSocket (preferred) or HTTP polling (fallback)
        use_websocket = getattr(settings, 'CLOUD_SYNC_WEBSOCKET', True)

        try:
            if use_websocket:
                from .services.websocket_client import start_websocket_client
                start_websocket_client()
                print("[SYNC] WebSocket client started")
            else:
                from .services.heartbeat import start_heartbeat_service
                start_heartbeat_service()
                print("[SYNC] HTTP polling started")
        except Exception as e:
            print(f"[SYNC] Error starting sync service: {e}")
