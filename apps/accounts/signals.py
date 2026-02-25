"""
Accounts signals.

Seeds default roles (admin, manager, employee, viewer) after migrations.
Runs on every `python manage.py migrate` to guarantee roles exist.
"""

import logging

from django.conf import settings
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def seed_default_roles(sender, **kwargs):
    """
    Create default roles after accounts migrations complete.

    Resolves hub_id from:
    1. settings.HUB_ID (set from env var in Docker deployments)
    2. HubConfig singleton (set during Cloud SSO login)
    3. Generates a deterministic UUID for local dev

    Uses update_or_create so it's idempotent — safe to run on every deploy.
    """
    # Only run for the accounts app
    if sender.label != 'accounts':
        return

    try:
        from apps.configuration.models import HubConfig
        from apps.core.services.permission_service import PermissionService
        import uuid

        hub_id = None

        # 1. From settings (Docker env var — always available in deployments)
        settings_hub_id = getattr(settings, 'HUB_ID', None)
        if settings_hub_id:
            hub_id = str(settings_hub_id)

        # 2. From HubConfig (set during Cloud SSO login)
        if not hub_id:
            hub_config = HubConfig.get_config()
            if hub_config.hub_id:
                hub_id = str(hub_config.hub_id)

        # 3. Deterministic fallback for local dev
        if not hub_id:
            hub_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, 'erplora.local'))

        PermissionService.create_default_roles(hub_id)
        logger.info(f"Default roles seeded for hub_id={hub_id}")

    except Exception as e:
        # Don't block migrations if seeding fails (e.g. fresh DB, tables not ready)
        logger.debug(f"Skipped default roles seeding: {e}")


def connect_signals():
    """Connect post_migrate signal. Called from AppConfig.ready()."""
    post_migrate.connect(seed_default_roles)
