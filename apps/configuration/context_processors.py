"""
Context processors para hacer la configuración disponible globalmente en templates.

Usage en templates:
    {{ HUB_CONFIG.currency }}
    {{ HUB_CONFIG.dark_mode }}
    {{ STORE_CONFIG.business_name }}
    {{ STORE_CONFIG.tax_rate }}
"""

from apps.configuration.models import HubConfig, StoreConfig


def global_config(request):
    """
    Añade las configuraciones de Hub y Store a todas las plantillas.

    Returns:
        dict: Contexto con HUB_CONFIG y STORE_CONFIG
    """
    return {
        'HUB_CONFIG': HubConfig.get_solo(),
        'STORE_CONFIG': StoreConfig.get_solo(),
    }
