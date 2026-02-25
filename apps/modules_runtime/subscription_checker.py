"""
Module Subscription Status Checker

Verifica el estado de suscripciones de módulos con Cloud API.
Los módulos de suscripción deben tener conexión a internet activa.
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
    Verifica estado de suscripciones de módulos en tiempo real con Cloud.
    Cachea resultados para evitar requests excesivos.
    """

    # Cache de 5 minutos para estado de suscripciones
    CACHE_TIMEOUT = 300  # 5 minutes
    CACHE_KEY_PREFIX = 'module_subscription_status_'

    def __init__(self):
        from apps.configuration.models import HubConfig
        self.hub_config = HubConfig.get_config()

    def check_subscription_status(self, module_id: int) -> Dict:
        """
        Verificar estado de suscripción de un módulo.

        Args:
            module_id: ID del módulo en Cloud

        Returns:
            {
                'has_active_subscription': bool,
                'subscription_status': str,
                'current_period_end': int,  # timestamp
                'error': str (opcional)
            }
        """
        # Verificar cache primero
        cache_key = f"{self.CACHE_KEY_PREFIX}{module_id}"
        cached_status = cache.get(cache_key)

        if cached_status:
            logger.debug(f"[SUBSCRIPTION] Using cached status for module {module_id}")
            return cached_status

        # Si no hay conexión a Cloud configurada
        if not self.hub_config.is_configured or not self.hub_config.cloud_api_token:
            return {
                'has_active_subscription': False,
                'subscription_status': 'not_configured',
                'error': 'Hub not configured with Cloud'
            }

        # Consultar Cloud API
        api_url = f"{settings.CLOUD_API_URL}/api/modules/{module_id}/subscription-status/"
        headers = {'X-Hub-Token': self.hub_config.cloud_api_token}

        try:
            response = requests.get(api_url, headers=headers, timeout=10)
            response.raise_for_status()
            result = response.json()

            # Cachear resultado
            cache.set(cache_key, result, self.CACHE_TIMEOUT)

            logger.info(
                f"[SUBSCRIPTION] Module {module_id} subscription status: "
                f"{result.get('subscription_status')}"
            )

            return result

        except requests.exceptions.ConnectionError:
            logger.warning(f"[SUBSCRIPTION] No internet connection to verify module {module_id}")
            return {
                'has_active_subscription': False,
                'subscription_status': 'offline',
                'error': 'No internet connection'
            }

        except requests.exceptions.Timeout:
            logger.warning(f"[SUBSCRIPTION] Timeout verifying module {module_id}")
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
                logger.warning(f"[SUBSCRIPTION] Module {module_id} not found")
                return {
                    'has_active_subscription': False,
                    'subscription_status': 'not_found',
                    'error': 'Module not found'
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

    def verify_module_access(self, module_slug: str, module_type: str = None) -> bool:
        """
        Verificar si un módulo puede ejecutarse basado en su tipo y estado de suscripción.

        Args:
            module_slug: Slug del módulo (e.g., 'analytics')
            module_type: Tipo de módulo ('free', 'paid', 'subscription')

        Returns:
            True si el módulo puede ejecutarse, False si no
        """
        from pathlib import Path

        try:
            # Verificar módulo desde filesystem
            modules_dir = Path(settings.MODULES_DIR)
            module_dir = modules_dir / module_slug

            # Check if module exists and is active (not prefixed with _)
            if not module_dir.exists():
                # Try with _ prefix (inactive)
                module_dir = modules_dir / f"_{module_slug}"
                if not module_dir.exists():
                    logger.error(f"[SUBSCRIPTION] Module {module_slug} not found in filesystem")
                    return False
                else:
                    logger.warning(f"[SUBSCRIPTION] Module {module_slug} is not active (disabled)")
                    return False

            # Module exists and is active (no _ prefix)
            # Read module.py for metadata
            module_py_path = module_dir / 'module.py'
            if module_py_path.exists():
                try:
                    import importlib.util
                    spec = importlib.util.spec_from_file_location(f"{module_slug}.module", module_py_path)
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if not module_type:
                        module_type = getattr(mod, 'MODULE_TYPE', 'free')
                except Exception as e:
                    logger.warning(f"[SUBSCRIPTION] Error reading module.py for {module_slug}: {e}")
                    module_type = module_type or 'free'

            # Si es gratuito, siempre permitir
            if module_type == 'free' or not module_type:
                return True

            # Si es de pago único, permitir (ya fue verificado en la instalación)
            if module_type == 'paid':
                return True

            # Si es de suscripción, verificar estado online
            if module_type == 'subscription':
                # Get cloud_module_id from metadata
                if module_py_path.exists():
                    try:
                        cloud_module_id = getattr(mod, 'CLOUD_MODULE_ID', None)
                        if not cloud_module_id:
                            logger.error(f"[SUBSCRIPTION] Module {module_slug} has no CLOUD_MODULE_ID")
                            return False
                    except Exception as e:
                        logger.error(f"[SUBSCRIPTION] Error reading CLOUD_MODULE_ID: {e}")
                        return False
                else:
                    logger.error(f"[SUBSCRIPTION] Module {module_slug} has no module.py")
                    return False

                status = self.check_subscription_status(cloud_module_id)

                if not status.get('has_active_subscription'):
                    logger.warning(
                        f"[SUBSCRIPTION] Module {module_slug} subscription not active: "
                        f"{status.get('subscription_status')}"
                    )
                    return False

                return True

            # Por defecto, no permitir si no sabemos el tipo
            return False

        except Exception as e:
            logger.error(f"[SUBSCRIPTION] Error verifying module access: {e}")
            return False

    def clear_cache(self, module_id: Optional[int] = None):
        """
        Limpiar cache de estado de suscripciones.

        Args:
            module_id: Si se especifica, solo limpia ese módulo. Si no, limpia todo.
        """
        if module_id:
            cache_key = f"{self.CACHE_KEY_PREFIX}{module_id}"
            cache.delete(cache_key)
            logger.info(f"[SUBSCRIPTION] Cleared cache for module {module_id}")
        else:
            # Limpiar todos los caches de suscripciones
            # (requeriría iterar sobre todas las claves, por ahora solo loggear)
            logger.info("[SUBSCRIPTION] Cache clear requested (all modules)")


# Singleton instance
_subscription_checker = None


def get_subscription_checker() -> SubscriptionChecker:
    """Get or create singleton SubscriptionChecker instance."""
    global _subscription_checker
    if _subscription_checker is None:
        _subscription_checker = SubscriptionChecker()
    return _subscription_checker
