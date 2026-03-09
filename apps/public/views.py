from django.http import Http404
from django.shortcuts import render

from apps.accounts.decorators import public_view
from apps.configuration.models import HubConfig, StoreConfig


@public_view
def public_index(request):
    """Public landing page for the business."""
    store = StoreConfig.get_solo()

    if not store.public_site_enabled:
        raise Http404

    hub_config = HubConfig.get_solo()
    hub_id = hub_config.hub_id

    # Discover active public modules
    public_links = []

    try:
        from catalog.models import CatalogSettings
        catalog = CatalogSettings.get_settings(hub_id)
        if catalog.is_active:
            public_links.append({
                'url': '/public/catalog/',
                'label': catalog.title or 'Catálogo',
                'icon': '📋',
            })
    except (ImportError, Exception):
        pass

    # Social media links
    social_links = []
    if store.instagram:
        social_links.append({'url': store.instagram, 'label': 'Instagram', 'icon': '📷'})
    if store.facebook:
        social_links.append({'url': store.facebook, 'label': 'Facebook', 'icon': '👤'})
    if store.tiktok:
        social_links.append({'url': store.tiktok, 'label': 'TikTok', 'icon': '🎵'})
    if store.google_maps:
        social_links.append({'url': store.google_maps, 'label': 'Google Maps', 'icon': '📍'})

    # Contact info
    whatsapp_url = ''
    if store.phone:
        phone_clean = store.phone.replace(' ', '').replace('-', '').replace('(', '').replace(')', '')
        if not phone_clean.startswith('+'):
            phone_clean = '+34' + phone_clean
        whatsapp_url = f'https://wa.me/{phone_clean.replace("+", "")}'

    return render(request, 'public/index.html', {
        'store': store,
        'public_links': public_links,
        'social_links': social_links,
        'whatsapp_url': whatsapp_url,
    })
