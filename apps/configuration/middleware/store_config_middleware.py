from django.shortcuts import redirect
from django.urls import reverse

from apps.configuration.models import HubConfig


class StoreConfigCheckMiddleware:
    """
    Middleware to check if hub is configured after login.
    If not configured, redirects to the AI assistant for setup.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require store configuration check
        self.exempt_paths = [
            reverse('auth:login'),
            reverse('auth:logout'),
            reverse('auth:cloud_login'),
            reverse('auth:get_employees'),
            reverse('auth:verify_pin'),
            reverse('auth:setup_pin'),
            reverse('auth:trust_device'),
            reverse('auth:verify_device_trust'),
            reverse('auth:revoke_device'),
            '/m/assistant/',  # AI assistant (handles setup)
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
                        return redirect('/m/assistant/?context=setup')

                    # Mark as checked for this session
                    request.session['store_config_checked'] = True

        response = self.get_response(request)
        return response
