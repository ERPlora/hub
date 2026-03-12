"""
Configuration signals.

When StoreConfig.logo changes:
- Web (Cloud Hub): calls Cloud API → Cloud dispatches SQS → Lambda generates icons in S3
- Local dev: generates icons directly with Pillow
"""
import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

CACHE_KEY = '_pwa_logo_hash'


@receiver(post_save, sender='configuration.StoreConfig')
def regenerate_pwa_icons_on_logo_change(sender, instance, **kwargs):
    """
    After StoreConfig is saved, check if logo changed and trigger icon generation.
    """
    from .services.pwa_icons import pwa_icons_exist, delete_pwa_icons

    if not instance.logo:
        # Logo removed — delete custom icons so manifest falls back to defaults
        if pwa_icons_exist():
            delete_pwa_icons()
            cache.delete(CACHE_KEY)
            logger.info('StoreConfig logo removed, PWA icons deleted')
        return

    # Compare hash to detect actual logo changes
    current_hash = _get_logo_hash(instance.logo)
    stored_hash = cache.get(CACHE_KEY)

    needs_generation = (
        (current_hash and current_hash != stored_hash)
        or not pwa_icons_exist()
    )

    if not needs_generation:
        return

    if _is_web_deployment():
        _dispatch_via_cloud_api(instance)
    else:
        _generate_locally(instance)

    # Store hash so we don't regenerate on next save
    if current_hash:
        cache.set(CACHE_KEY, current_hash, timeout=None)


def _is_web_deployment():
    """Check if we're running in web mode (has Cloud API connection)."""
    return getattr(settings, 'DEPLOYMENT_MODE', 'local') == 'web'


def _dispatch_via_cloud_api(instance):
    """Send PWA icon generation request to Cloud API → SQS → Lambda."""
    try:
        from apps.sync.services.cloud_api import get_cloud_api, CloudAPIError

        # The logo is already in S3 via django-storages.
        # Build full S3 keys for Lambda to use.
        logo_key = instance.logo.name  # Relative to AWS_LOCATION
        aws_location = getattr(settings, 'AWS_LOCATION', '')

        full_logo_key = f'{aws_location}/{logo_key}' if aws_location else logo_key
        icons_prefix = f'{aws_location}/pwa_icons/' if aws_location else 'pwa_icons/'

        cloud_api = get_cloud_api()
        cloud_api._request('POST', '/api/hubs/me/tasks/', data={
            'task': 'hubs.generate_pwa_icons',
            'payload': {
                'logo_key': full_logo_key,
                'icons_prefix': icons_prefix,
            },
        })

        logger.info('PWA icon generation dispatched via Cloud API (logo: %s)', full_logo_key)

    except Exception:
        logger.exception('Failed to dispatch PWA icons via Cloud API, falling back to local')
        _generate_locally(instance)


def _generate_locally(instance):
    """Generate PWA icons locally with Pillow (development mode)."""
    from .services.pwa_icons import generate_pwa_icons

    success = generate_pwa_icons(instance.logo)
    if success:
        logger.info('PWA icons generated locally')
    else:
        logger.error('Failed to generate PWA icons locally')


def _get_logo_hash(logo_field):
    """Compute MD5 hash of the logo file for change detection."""
    try:
        logo_field.seek(0)
        h = hashlib.md5(logo_field.read()).hexdigest()
        logo_field.seek(0)
        return h
    except Exception:
        return None
