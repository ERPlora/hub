"""
Middleware that converts Django messages to HTMX HX-Trigger events.

When an HTMX request is made and the response contains pending Django messages,
this middleware adds them as HX-Trigger headers so the client-side toast system
can display them.
"""
import json
from django.contrib.messages import get_messages


class HtmxMessagesMiddleware:
    """Convert Django messages to HX-Trigger showMessage events for HTMX."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if not getattr(request, 'htmx', False):
            return response

        messages = list(get_messages(request))
        if not messages:
            return response

        # Map Django message level tags to our toast types
        type_map = {
            'debug': 'info',
            'info': 'info',
            'success': 'success',
            'warning': 'warning',
            'error': 'error',
        }

        # Use the first message (most common case)
        msg = messages[0]
        msg_type = type_map.get(msg.tags.split()[-1] if msg.tags else 'info', 'info')

        # Merge with existing HX-Trigger
        existing = response.get('HX-Trigger', '')
        try:
            triggers = json.loads(existing) if existing else {}
        except (json.JSONDecodeError, TypeError):
            triggers = {}

        triggers['showMessage'] = {
            'message': str(msg),
            'type': msg_type,
        }

        response['HX-Trigger'] = json.dumps(triggers)
        return response
