"""
Help page — fetches pre-rendered help sections from Cloud Blueprint API.
"""
import logging

import requests
from apps.accounts.decorators import login_required
from apps.core.htmx import htmx_view
from django.conf import settings

logger = logging.getLogger(__name__)


def _load_help_sections():
    """Fetch help sections from Cloud Blueprint API (S3-backed, cached)."""
    base = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
    try:
        resp = requests.get(f'{base}/api/blueprints/docs/', timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.RequestException:
        logger.warning('Failed to fetch help docs from Cloud API')
        return []


@login_required
@htmx_view('main/help/pages/index.html', 'main/help/partials/content.html')
def index(request):
    """Help & Documentation page."""
    return {
        'current_section': 'help',
        'page_title': 'Help',
        'sections': _load_help_sections(),
    }


@login_required
def modal(request):
    """Help modal — returns help content inside a modal overlay."""
    from django.shortcuts import render
    return render(request, 'main/help/partials/modal.html', {
        'sections': _load_help_sections(),
    })
