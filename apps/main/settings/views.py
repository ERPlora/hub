"""
Main Settings Views
"""
from django.http import JsonResponse
from django.conf import settings as django_settings
from django.utils import translation
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig


@login_required
@htmx_view('main/settings/pages/index.html', 'main/settings/partials/content.html')
def index(request):
    """Settings page"""
    user = LocalUser.objects.get(id=request.session['local_user_id'])
    hub_config = HubConfig.get_config()

    if request.method == 'POST':
        action = request.POST.get('action')

        # Handle dark mode toggle (instant save)
        if action == 'update_theme':
            dark_mode = request.POST.get('dark_mode') == 'true'
            hub_config.dark_mode = dark_mode
            hub_config.save()
            return JsonResponse({'success': True})

        # Handle user preferences form (language + avatar)
        language = request.POST.get('language')
        avatar = request.FILES.get('avatar')

        if language or avatar:
            # Update language
            if language:
                valid_languages = [code for code, name in django_settings.LANGUAGES]
                if language in valid_languages:
                    user.language = language
                    # Activate language in Django session
                    translation.activate(language)
                    request.session['_language'] = language
                    request.session['user_language'] = language

            # Handle avatar upload
            if avatar:
                user.avatar = avatar

            user.save()
            return JsonResponse({'success': True, 'message': 'User preferences saved'})

        # Handle hub settings form (currency)
        currency = request.POST.get('currency')
        if currency:
            # Validate against POPULAR_CURRENCY_CHOICES (used in UI)
            valid_currencies = [code for code, name in django_settings.POPULAR_CURRENCY_CHOICES]
            if currency in valid_currencies:
                hub_config.currency = currency
                hub_config.save()
                return JsonResponse({'success': True, 'message': 'Hub settings saved'})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid currency'}, status=400)

        return JsonResponse({'success': True})

    # Use POPULAR_CURRENCY_CHOICES for the UI (24 most common currencies)
    return {
        'current_section': 'settings',
        'page_title': 'Settings',
        'user': user,
        'hub_config': hub_config,
        'language_choices': django_settings.LANGUAGES,
        'currency_choices': django_settings.POPULAR_CURRENCY_CHOICES,
    }
