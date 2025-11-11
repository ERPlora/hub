"""
FRP Client status and management views for CPOS Hub.

Provides UI/API for viewing and managing FRP tunnel connection.
"""

from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from apps.core.frp_client import get_frp_client, FRPClientError
import logging

logger = logging.getLogger(__name__)


@require_http_methods(["GET"])
def frp_status(request):
    """
    Get current FRP client status.

    Returns:
        JSON with FRP connection status
    """
    try:
        client = get_frp_client()
        status = client.get_status()

        return JsonResponse({
            'success': True,
            **status
        })

    except FRPClientError as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'running': False
        })


@csrf_exempt
@require_http_methods(["POST"])
def frp_restart(request):
    """
    Restart the FRP client.

    Returns:
        JSON with restart result
    """
    try:
        client = get_frp_client()
        client.restart()

        return JsonResponse({
            'success': True,
            'message': 'FRP client restarted successfully'
        })

    except FRPClientError as e:
        logger.exception("Error restarting FRP client")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def frp_stop(request):
    """
    Stop the FRP client.

    Returns:
        JSON with stop result
    """
    try:
        client = get_frp_client()
        client.stop()

        return JsonResponse({
            'success': True,
            'message': 'FRP client stopped'
        })

    except FRPClientError as e:
        logger.exception("Error stopping FRP client")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@csrf_exempt
@require_http_methods(["POST"])
def frp_start(request):
    """
    Start the FRP client.

    Returns:
        JSON with start result
    """
    try:
        client = get_frp_client()

        if client.is_running():
            return JsonResponse({
                'success': False,
                'error': 'FRP client is already running'
            }, status=400)

        client.start()

        return JsonResponse({
            'success': True,
            'message': 'FRP client started successfully'
        })

    except FRPClientError as e:
        logger.exception("Error starting FRP client")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)
