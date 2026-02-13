"""
Core Views

Only truly core/utility views that don't belong to any specific app:
- Health check (for Docker/monitoring)
- Language switcher
- Update notifications

All other views have been moved to their respective apps:
- Authentication → apps/auth/login/views.py
- Employees → apps/main/employees/views.py
- Settings → apps/configuration/views.py
- Modules → apps/system/modules/views.py
- PWA → apps/configuration/views.py
"""
from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.conf import settings as django_settings

from apps.accounts.models import LocalUser


# =============================================================================
# Language Management
# =============================================================================

def set_language(request):
    """
    Change user's language preference without URL prefixes.
    Accepts language code via POST or GET parameter 'language'.
    Saves preference in:
    - LocalUser.language (if authenticated)
    - Session and cookie (always)
    """
    from django.http import HttpResponseRedirect
    from django.utils.translation import activate

    language = request.POST.get('language') or request.GET.get('language')
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER', '/')

    if language and language in [lang[0] for lang in django_settings.LANGUAGES]:
        # Activate the language for this request
        activate(language)

        # Save to LocalUser if authenticated
        if 'local_user_id' in request.session:
            try:
                user = LocalUser.objects.get(id=request.session['local_user_id'])
                user.language = language
                user.save(update_fields=['language'])
                request.session['user_language'] = language
            except LocalUser.DoesNotExist:
                pass

        response = HttpResponseRedirect(next_url)

        # Set language cookie (persistent preference - 1 year)
        response.set_cookie(
            django_settings.LANGUAGE_COOKIE_NAME,
            language,
            max_age=django_settings.LANGUAGE_COOKIE_AGE,
            path='/',
            secure=getattr(django_settings, 'LANGUAGE_COOKIE_SECURE', False),
            samesite=getattr(django_settings, 'LANGUAGE_COOKIE_SAMESITE', 'Lax')
        )

        # Also save in session (higher priority than cookie)
        request.session[django_settings.LANGUAGE_COOKIE_NAME] = language

        return response

    return HttpResponseRedirect(next_url)


# =============================================================================
# Health Check
# =============================================================================

@require_http_methods(["GET"])
def health_check(request):
    """
    Health check endpoint for Docker healthcheck and monitoring.

    Verifies:
    - Django is running
    - Database is accessible
    - Returns version and status

    Returns:
        JsonResponse with status 200 if healthy, 500 if unhealthy
    """
    try:
        # Verify database connection
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")

        # Get Hub version
        import config.settings as settings
        version = getattr(settings, 'HUB_VERSION', 'unknown')

        return JsonResponse({
            'status': 'ok',
            'database': 'ok',
            'version': version,
        }, status=200)

    except Exception as e:
        return JsonResponse({
            'status': 'error',
            'error': str(e),
        }, status=500)


# =============================================================================
# Cloud Connection Status (HTMX partial)
# =============================================================================

def connection_status(request):
    """
    HTMX endpoint - Returns cloud icon based on Cloud connection status.

    Green cloud: Connected to Cloud
    Red cloud-offline: No connection to Cloud
    """
    from django.http import HttpResponse
    from apps.core.services.connectivity import ConnectivityChecker

    # Get Cloud URL from settings
    cloud_url = getattr(django_settings, 'CLOUD_API_URL', 'https://erplora.com')
    checker = ConnectivityChecker(cloud_url=cloud_url)

    import djicons

    if checker.is_online():
        # Green - Connected
        icon_html = djicons.get("cloudy-outline", slot="icon-only", css_class="text-green-500", title="Connected to Cloud")
        return HttpResponse(icon_html)
    else:
        # Red - No connection
        icon_html = djicons.get("cloud-offline-outline", slot="icon-only", css_class="text-red-500", title="No Cloud connection")
        return HttpResponse(icon_html)


# =============================================================================
# Update Notifications (HTMX partials)
# =============================================================================

def update_notification(request):
    """Render update notification banner (HTMX partial)."""
    # TODO: Implement actual update check logic
    return render(request, 'ui/update_notification_empty.html')


def update_notification_dismiss(request):
    """Dismiss update notification (HTMX partial)."""
    return render(request, 'ui/update_notification_empty.html')


# =============================================================================
# Sidebar (HTMX partial)
# =============================================================================

def sidebar_partial(request):
    """
    HTMX endpoint - Returns sidebar nav list for module menu updates.

    Called after module activation/deactivation to refresh the menu
    without a full page reload. Only returns the nav list content,
    not the entire sidebar structure.
    """
    from apps.modules_runtime.loader import module_loader

    # Get fresh menu items
    if 'local_user_id' in request.session:
        menu_items = module_loader.get_menu_items()
    else:
        menu_items = []

    return render(request, 'dashboard/partials/sidebar_nav.html', {
        'MODULE_MENU_ITEMS': menu_items,
    })
