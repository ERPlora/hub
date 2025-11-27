from django.shortcuts import redirect
from django.urls import reverse
from apps.configuration.models import StoreConfig


class StoreConfigCheckMiddleware:
    """
    Middleware to check if store is configured after login.
    If store is not configured, redirect to settings page.
    """

    def __init__(self, get_response):
        self.get_response = get_response
        # Paths that don't require store configuration
        self.exempt_paths = [
            reverse('accounts:login'),
            reverse('accounts:logout'),
            reverse('configuration:settings'),
            '/api/',  # API endpoints
            '/static/',  # Static files
            '/media/',  # Media files
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

                    # If store is not configured, redirect to settings
                    if not store_config.is_complete():
                        request.session['store_config_checked'] = True
                        request.session['settings_message'] = 'Please complete store configuration to continue'
                        return redirect('configuration:settings')

                    # Mark as checked for this session
                    request.session['store_config_checked'] = True

        response = self.get_response(request)
        return response
