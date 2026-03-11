from pathlib import Path

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse

from apps.configuration.models import HubConfig


class StoreConfigCheckMiddleware:
    """
    Middleware to check if hub is configured after login.
    If not configured, redirects to the AI assistant for conversational setup.
    Falls back to the manual setup wizard if the assistant module is not available.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require store configuration check
        self.exempt_paths = [
            reverse('auth:login'),
            reverse('auth:logout'),
            reverse('auth:cloud_login'),
            reverse('auth:verify_pin'),
            reverse('auth:setup_pin'),
            '/setup/',  # Setup wizard (fallback)
            '/m/assistant/',  # AI assistant (for setup mode)
            '/api/',  # API endpoints
            '/static/',  # Static files
            '/media/',  # Media files
            '/__debug__/',  # Debug toolbar
        ]

    def __call__(self, request):
        # Check if user is logged in
        if 'local_user_id' in request.session:
            path = request.path
            is_exempt = any(path.startswith(exempt) for exempt in self.exempt_paths)

            if not is_exempt:
                # Check if setup is needed (once per session)
                if not request.session.get('store_config_checked', False):
                    hub_config = HubConfig.get_config()

                    if not hub_config.is_configured:
                        # Prefer AI assistant, fall back to manual wizard
                        modules_dir = getattr(settings, 'MODULES_DIR', None)
                        if modules_dir and Path(modules_dir).joinpath('assistant').exists():
                            return redirect('/m/assistant/?context=setup')
                        return redirect('setup:index')

                    # Mark as checked for this session
                    request.session['store_config_checked'] = True

        response = self.get_response(request)
        return response
