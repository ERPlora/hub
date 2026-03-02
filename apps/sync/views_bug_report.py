"""
Bug Report View — forwards user problem reports to Cloud.
"""
import logging
import requests as http_requests

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from apps.accounts.decorators import login_required
from apps.configuration.models import HubConfig

logger = logging.getLogger(__name__)


@login_required
@require_POST
def submit_bug_report(request):
    """
    Receive a bug report from the Hub frontend and forward to Cloud.

    POST /api/v1/sync/bug-report/
    Content-Type: multipart/form-data
    """
    screenshot = request.FILES.get('screenshot')
    url = request.POST.get('url', '')

    if not screenshot or not url:
        return JsonResponse({'error': 'screenshot and url are required'}, status=400)

    config = HubConfig.get_solo()
    if not config.hub_jwt or not config.hub_id:
        return JsonResponse({'error': 'Hub not connected to Cloud'}, status=503)

    cloud_url = getattr(settings, 'CLOUD_API_URL', 'https://erplora.com')
    endpoint = f"{cloud_url}/api/hubs/me/bug-report/"

    try:
        response = http_requests.post(
            endpoint,
            files={'screenshot': ('screenshot.png', screenshot.read(), 'image/png')},
            data={
                'url': url[:500],
                'description': request.POST.get('description', ''),
                'user_agent': request.POST.get('user_agent', '')[:500],
                'user_email': request.user.email if hasattr(request.user, 'email') else '',
            },
            headers={'Authorization': f'Bearer {config.hub_jwt}'},
            timeout=30,
        )

        if response.status_code == 201:
            logger.info(f"[BUG REPORT] Sent to Cloud: {url[:80]}")
            return JsonResponse({'success': True})
        else:
            logger.warning(f"[BUG REPORT] Cloud returned {response.status_code}")
            return JsonResponse({'error': 'Failed to send report'}, status=502)

    except http_requests.RequestException as e:
        logger.error(f"[BUG REPORT] Error sending to Cloud: {e}")
        return JsonResponse({'error': 'Could not reach Cloud'}, status=503)
