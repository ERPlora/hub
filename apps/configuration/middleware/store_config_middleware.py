from django.shortcuts import redirect
from django.urls import reverse
from apps.configuration.models import StoreConfig


class StoreConfigCheckMiddleware:
    """
    Middleware to check if store is configured after login.
    If store is not configured, redirect to setup wizard.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require store configuration
        self.exempt_paths = [
            reverse('auth:login'),
            reverse('auth:logout'),
            reverse('auth:cloud_login'),
            reverse('auth:verify_pin'),
            reverse('auth:setup_pin'),
            reverse('setup:wizard'),
            reverse('main:settings'),
            '/api/',  # API endpoints
            '/static/',  # Static files
            '/media/',  # Media files
            '/__debug__/',  # Debug toolbar
        ]

    def __call__(self, request):
        # Check if user is logged in
        if 'local_user_id' in request.session:
            # Check if current path is exempt
            path = request.path
            is_exempt = any(path.startswith(exempt) for exempt in self.exempt_paths)

            if not is_exempt:
                # Check if store configuration check has been done in this session
                if not request.session.get('store_config_checked', False):
                    store_config = StoreConfig.get_config()

                    # If store is not configured (wizard not completed), redirect to setup wizard
                    if not store_config.is_configured:
                        return redirect('setup:wizard')

                    # Mark as checked for this session
                    request.session['store_config_checked'] = True

        response = self.get_response(request)
        return response
