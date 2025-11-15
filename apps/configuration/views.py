from django.shortcuts import render, redirect
from django.http import JsonResponse
from .models import HubConfig, StoreConfig


def index(request):
    """
    Root URL - redirect to dashboard if logged in, otherwise to login
    """
    if 'local_user_id' in request.session:
        return redirect('configuration:dashboard')
    else:
        return redirect('accounts:login')


def dashboard(request):
    """
    Dashboard view - placeholder for now
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    context = {
        'current_view': 'dashboard'
    }
    return render(request, 'core/dashboard.html', context)


def pos(request):
    """
    Point of Sale view - placeholder for now
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    context = {
        'current_view': 'pos'
    }
    return render(request, 'core/pos.html', context)


def settings(request):
    """
    Settings view
    """
    # Check if user is logged in
    if 'local_user_id' not in request.session:
        return redirect('accounts:login')

    hub_config = HubConfig.get_config()
    store_config = StoreConfig.get_config()

    # Handle POST request for store configuration update
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_currency':
            # Update currency
            currency = request.POST.get('currency', 'USD')

            # Validate currency
            valid_currencies = [choice[0] for choice in HubConfig.CURRENCY_CHOICES]
            if currency in valid_currencies:
                hub_config.currency = currency
                hub_config.save()
                return JsonResponse({'success': True})
            else:
                return JsonResponse({'success': False, 'error': 'Invalid currency'}, status=400)

        elif action == 'update_theme':
            # Update theme preferences
            color_theme = request.POST.get('color_theme', 'default')
            auto_print = request.POST.get('auto_print') == 'true'
            dark_mode_param = request.POST.get('dark_mode')

            # Log for debugging
            print(f"[UPDATE THEME] color_theme={color_theme}, auto_print={auto_print}, dark_mode={dark_mode_param}")

            hub_config.color_theme = color_theme
            hub_config.auto_print = auto_print

            # Update dark_mode if provided (from header toggle)
            if dark_mode_param is not None:
                hub_config.dark_mode = dark_mode_param == 'true'
                print(f"[UPDATE THEME] Updated dark_mode to {hub_config.dark_mode}")

            hub_config.save()
            print(f"[UPDATE THEME] Saved: color_theme={hub_config.color_theme}, dark_mode={hub_config.dark_mode}")

            return JsonResponse({'success': True})

        elif action == 'update_store':
            # Update store configuration
            store_config.business_name = request.POST.get('business_name', '').strip()
            store_config.business_address = request.POST.get('business_address', '').strip()
            store_config.vat_number = request.POST.get('vat_number', '').strip()
            store_config.phone = request.POST.get('phone', '').strip()
            store_config.email = request.POST.get('email', '').strip()
            store_config.website = request.POST.get('website', '').strip()

            # Tax configuration
            tax_rate = request.POST.get('tax_rate', '0.00')
            try:
                store_config.tax_rate = float(tax_rate) if tax_rate else 0.00
            except ValueError:
                store_config.tax_rate = 0.00

            store_config.tax_included = request.POST.get('tax_included') == 'on'

            # Handle logo upload
            if 'logo' in request.FILES:
                store_config.logo = request.FILES['logo']

            # Receipt configuration
            store_config.receipt_header = request.POST.get('receipt_header', '').strip()
            store_config.receipt_footer = request.POST.get('receipt_footer', '').strip()

            # Check if store is now complete
            store_config.is_configured = store_config.is_complete()

            store_config.save()

            # Store success message in session
            request.session['settings_message'] = 'Store configuration saved successfully'

            return redirect('configuration:settings')

    # Get success message if any
    settings_message = request.session.pop('settings_message', None)

    context = {
        'hub_config': hub_config,
        'store_config': store_config,
        'settings_message': settings_message,
        'current_view': 'settings'
    }
    return render(request, 'core/settings.html', context)
