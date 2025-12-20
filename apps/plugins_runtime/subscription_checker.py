"""
Plugin Subscription Status Checker

Verifica el estado de suscripciones de plugins con Cloud API.
Los plugins de suscripción deben tener conexión a internet activa.
"""
import requests
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class SubscriptionChecker:
    """
    Verifica estado de suscripciones de plugins en tiempo real con Cloud.
    Cachea resultados para evitar requests excesivos.
    """

    # Cache de 5 minutos para estado de suscripciones
    CACHE_TIMEOUT = 300  # 5 minutes
    CACHE_KEY_PREFIX = 'plugin_subscription_status_'

    def __init__(self):
        from apps.configuration.models import HubConfig
        self.hub_config = HubConfig.get_config()

    def check_subscription_status(self, plugin_id: int) -> Dict:
        """
        Verificar estado de suscripción de un plugin.

        Args:
            plugin_id: ID del plugin en Cloud

        Returns:
            {
                'has_active_subscription': bool,
                'subscription_status': str,
                'current_period_end': int,  # timestamp
                'error': str (opcional)
            }
        """
        # Verificar cache primero
        cache_key = f"{self.CACHE_KEY_PREFIX}{plugin_id}"
        cached_status = cache.get(cache_key)

        if cached_status:
            logger.debug(f"[SUBSCRIPTION] Using cached status for plugin {plugin_id}")
            return cached_status

        # Si no hay conexión a Cloud configurada
        if not self.hub_config.is_configured or not self.hub_config.cloud_api_token:
            return {
                'has_active_subscription': False,
                'subscription_status': 'not_configured',
                'error': 'Hub not configured with Cloud'
            }

        # Consultar Cloud API
        api_url = f"{settings.CLOUD_API_URL}/api/plugins/{plugin_id}/subscription-status/"
        headers = {'X-Hub-Token': self.hub_config.cloud_api_token}

        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()

            # Cachear resultado
            cache.set(cache_key, result, self.CACHE_TIMEOUT)

            logger.info(
                f"[SUBSCRIPTION] Plugin {plugin_id} subscription status: "
                f"{result.get('subscription_status')}"
            )

            return result

        except requests.exceptions.ConnectionError:
            logger.warning(f"[SUBSCRIPTION] No internet connection to verify plugin {plugin_id}")
            return {
                'has_active_subscription': False,
                'subscription_status': 'offline',
                'error': 'No internet connection'
            }

        except requests.exceptions.Timeout:
            logger.warning(f"[SUBSCRIPTION] Timeout verifying plugin {plugin_id}")
            return {
                'has_active_subscription': False,
                'subscription_status': 'timeout',
                'error': 'Request timeout'
            }

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                logger.error(f"[SUBSCRIPTION] Invalid Hub token")
                return {
                    'has_active_subscription': False,
                    'subscription_status': 'unauthorized',
                    'error': 'Invalid Hub token'
                }
            elif e.response.status_code == 404:
                logger.warning(f"[SUBSCRIPTION] Plugin {plugin_id} not found")
                return {
                    'has_active_subscription': False,
                    'subscription_status': 'not_found',
                    'error': 'Plugin not found'
                }
            else:
                logger.error(f"[SUBSCRIPTION] HTTP error: {e}")
                return {
                    'has_active_subscription': False,
                    'subscription_status': 'error',
                    'error': str(e)
                }

        except Exception as e:
            logger.error(f"[SUBSCRIPTION] Unexpected error: {e}")
            return {
                'has_active_subscription': False,
                'subscription_status': 'error',
                'error': str(e)
            }

    def verify_plugin_access(self, plugin_slug: str, plugin_type: str = None) -> bool:
        """
        Verificar si un plugin puede ejecutarse basado en su tipo y estado de suscripción.

        Args:
            plugin_slug: Slug del plugin (e.g., 'analytics')
            plugin_type: Tipo de plugin ('free', 'paid', 'subscription')

        Returns:
            True si el plugin puede ejecutarse, False si no
        """
        from pathlib import Path
        import json

        try:
            # Verificar plugin desde filesystem
            plugins_dir = Path(settings.PLUGINS_DIR)
            plugin_dir = plugins_dir / plugin_slug

            # Check if plugin exists and is active (not prefixed with _)
            if not plugin_dir.exists():
                # Try with _ prefix (inactive)
                plugin_dir = plugins_dir / f"_{plugin_slug}"
                if not plugin_dir.exists():
                    logger.error(f"[SUBSCRIPTION] Plugin {plugin_slug} not found in filesystem")
                    return False
                else:
                    logger.warning(f"[SUBSCRIPTION] Plugin {plugin_slug} is not active (disabled)")
                    return False

            # Plugin exists and is active (no _ prefix)
            # Read plugin.json for metadata
            plugin_json_path = plugin_dir / 'plugin.json'
            if plugin_json_path.exists():
                try:
                    with open(plugin_json_path, 'r', encoding='utf-8') as f:
                        metadata = json.load(f)
                        # Get plugin type from metadata if not provided
                        if not plugin_type:
                            plugin_type = metadata.get('type', 'free')
                except Exception as e:
                    logger.warning(f"[SUBSCRIPTION] Error reading plugin.json for {plugin_slug}: {e}")
                    plugin_type = plugin_type or 'free'

            # Si es gratuito, siempre permitir
            if plugin_type == 'free' or not plugin_type:
                return True

            # Si es de pago único, permitir (ya fue verificado en la instalación)
            if plugin_type == 'paid':
                return True

            # Si es de suscripción, verificar estado online
            if plugin_type == 'subscription':
                # Get cloud_plugin_id from metadata
                if plugin_json_path.exists():
                    try:
                        with open(plugin_json_path, 'r', encoding='utf-8') as f:
                            metadata = json.load(f)
                            cloud_plugin_id = metadata.get('cloud_plugin_id')

                            if not cloud_plugin_id:
                                logger.error(f"[SUBSCRIPTION] Plugin {plugin_slug} has no cloud_plugin_id")
                                return False
                    except Exception as e:
                        logger.error(f"[SUBSCRIPTION] Error reading cloud_plugin_id: {e}")
                        return False
                else:
                    logger.error(f"[SUBSCRIPTION] Plugin {plugin_slug} has no plugin.json")
                    return False

                status = self.check_subscription_status(cloud_plugin_id)

                if not status.get('has_active_subscription'):
                    logger.warning(
                        f"[SUBSCRIPTION] Plugin {plugin_slug} subscription not active: "
                        f"{status.get('subscription_status')}"
                    )
                    return False

                return True

            # Por defecto, no permitir si no sabemos el tipo
            return False

        except Exception as e:
            logger.error(f"[SUBSCRIPTION] Error verifying plugin access: {e}")
            return False

    def clear_cache(self, plugin_id: Optional[int] = None):
        """
        Limpiar cache de estado de suscripciones.

        Args:
            plugin_id: Si se especifica, solo limpia ese plugin. Si no, limpia todo.
        """
        if plugin_id:
            cache_key = f"{self.CACHE_KEY_PREFIX}{plugin_id}"
            cache.delete(cache_key)
            logger.info(f"[SUBSCRIPTION] Cleared cache for plugin {plugin_id}")
        else:
            # Limpiar todos los caches de suscripciones
            # (requeriría iterar sobre todas las claves, por ahora solo loggear)
            logger.info("[SUBSCRIPTION] Cache clear requested (all plugins)")


# Singleton instance
_subscription_checker = None


def get_subscription_checker() -> SubscriptionChecker:
    """Get or create singleton SubscriptionChecker instance."""
    global _subscription_checker
    if _subscription_checker is None:
        _subscription_checker = SubscriptionChecker()
    return _subscription_checker
