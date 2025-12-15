"""
Main Settings Views
"""
from decimal import Decimal, InvalidOperation
from django.http import JsonResponse
from django.conf import settings as django_settings
from django.utils import translation
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig, StoreConfig


@login_required
@htmx_view('main/settings/pages/index.html', 'main/settings/partials/content.html')
def index(request):
    """Settings page"""
    user = LocalUser.objects.get(id=request.session['local_user_id'])
    hub_config = HubConfig.get_config()
    store_config = StoreConfig.get_config()

    if request.method == 'POST':
        action = request.POST.get('action')

        # Handle dark mode toggle (instant save)
        if action == 'update_theme':
            dark_mode = request.POST.get('dark_mode') == 'true'
            hub_config.dark_mode = dark_mode
            hub_config.save()
            return JsonResponse({'success': True})

        # Handle store settings form
        if action == 'update_store':
            store_config.business_name = request.POST.get('business_name', '').strip()
            store_config.business_address = request.POST.get('business_address', '').strip()
            store_config.vat_number = request.POST.get('vat_number', '').strip()
            store_config.phone = request.POST.get('phone', '').strip()
            store_config.email = request.POST.get('email', '').strip()
            store_config.website = request.POST.get('website', '').strip()

            # Tax configuration
            try:
                tax_rate = request.POST.get('tax_rate', '0')
                store_config.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('0')
            except InvalidOperation:
                store_config.tax_rate = Decimal('0')

            store_config.tax_included = request.POST.get('tax_included') == 'true'

            # Receipt configuration
            store_config.receipt_header = request.POST.get('receipt_header', '').strip()
            store_config.receipt_footer = request.POST.get('receipt_footer', '').strip()

            # Handle logo upload
            if 'logo' in request.FILES:
                store_config.logo = request.FILES['logo']

            # Update is_configured based on required fields
            store_config.is_configured = store_config.is_complete()
            store_config.save()

            return JsonResponse({'success': True, 'message': 'Store settings saved'})

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
        'store_config': store_config,
        'language_choices': django_settings.LANGUAGES,
        'currency_choices': django_settings.POPULAR_CURRENCY_CHOICES,
    }
