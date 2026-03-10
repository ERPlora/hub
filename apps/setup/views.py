"""
Setup Wizard Views — 4-step setup for new Hub instances.

Step 1: Region (country, language, timezone, currency)
Step 2: Business (sector + business types)
Step 3: Info (business name, NIF, address, logo)
Step 4: Tax (tax classes from preset, editable)
"""
import json
import logging
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import login_required
from apps.configuration.models import HubConfig, StoreConfig
from apps.core.services.blueprint_service import BlueprintService

from .services import SetupService

logger = logging.getLogger(__name__)


def _write_deferred_setup_flag():
    """Write a flag file so deferred setup tasks run after restart."""
    from pathlib import Path
    from django.conf import settings

    data_dir = getattr(settings, 'DATA_DIR', None)
    flag_path = Path(data_dir) / '.pending_setup.json' if data_dir else Path('/tmp/.pending_setup.json')
    try:
        flag_path.write_text(json.dumps({'deferred': True}))
    except Exception as e:
        logger.warning('Failed to write deferred setup flag: %s', e)


# Country → defaults mapping
COUNTRY_DEFAULTS = {
    'ES': {'language': 'es', 'timezone': 'Europe/Madrid', 'currency': 'EUR'},
    'FR': {'language': 'fr', 'timezone': 'Europe/Paris', 'currency': 'EUR'},
    'DE': {'language': 'de', 'timezone': 'Europe/Berlin', 'currency': 'EUR'},
    'IT': {'language': 'it', 'timezone': 'Europe/Rome', 'currency': 'EUR'},
    'PT': {'language': 'pt', 'timezone': 'Europe/Lisbon', 'currency': 'EUR'},
    'GB': {'language': 'en', 'timezone': 'Europe/London', 'currency': 'GBP'},
    'US': {'language': 'en', 'timezone': 'America/New_York', 'currency': 'USD'},
    'MX': {'language': 'es', 'timezone': 'America/Mexico_City', 'currency': 'MXN'},
}


def _get_setup_data(request):
    """Get setup wizard data from session."""
    return request.session.get('setup_data', {})


def _set_setup_data(request, data):
    """Save setup wizard data to session."""
    request.session['setup_data'] = data
    request.session.modified = True


@login_required
def index(request):
    """Welcome page: choose AI assistant or manual setup."""
    hub_config = HubConfig.get_config()
    if hub_config.is_configured:
        return redirect('main:index')

    # Check if assistant module is available
    modules_dir = getattr(settings, 'MODULES_DIR', None)
    has_assistant = bool(
        modules_dir and Path(modules_dir).joinpath('assistant').exists()
    )

    return render(request, 'setup/pages/welcome.html', {
        'has_assistant': has_assistant,
    })


@login_required
def step_region(request):
    """Step 1: Region — country, language, timezone, currency."""
    data = _get_setup_data(request)

    if request.method == 'POST':
        country_code = request.POST.get('country_code', '').upper()
        tax_preset = request.POST.get('tax_preset', '')

        # Get defaults for country
        defaults = COUNTRY_DEFAULTS.get(country_code, {})

        data['country_code'] = country_code
        data['tax_preset'] = tax_preset or f'{country_code.lower()}_standard'
        data['language'] = request.POST.get('language') or defaults.get('language', 'en')
        data['timezone'] = request.POST.get('timezone') or defaults.get('timezone', 'UTC')
        data['currency'] = request.POST.get('currency') or defaults.get('currency', 'EUR')

        _set_setup_data(request, data)
        return redirect('setup:step_business')

    # Load tax data to check available presets
    tax_data = None
    if data.get('country_code'):
        tax_data = BlueprintService.get_tax_data(data['country_code'].lower())

    context = {
        'current_step': 1,
        'setup_data': data,
        'country_defaults': json.dumps(COUNTRY_DEFAULTS),
        'tax_data': tax_data,
    }
    return render(request, 'setup/pages/step1_region.html', context)


@login_required
def step_business(request):
    """Step 2: Business — sector + business types."""
    data = _get_setup_data(request)
    if not data.get('country_code'):
        return redirect('setup:step_region')

    if request.method == 'POST':
        sector = request.POST.get('sector', '')
        business_types = request.POST.getlist('business_types')

        data['sector'] = sector
        data['business_types'] = business_types

        _set_setup_data(request, data)
        return redirect('setup:step_info')

    language = data.get('language', 'en')
    sectors = BlueprintService.get_sectors(language=language)
    sector_list = sectors.get('sectors', []) if isinstance(sectors, dict) else sectors

    context = {
        'current_step': 2,
        'setup_data': data,
        'sectors': sector_list,
        'selected_types_json': json.dumps(data.get('business_types', [])),
    }
    return render(request, 'setup/pages/step2_business.html', context)


@login_required
def load_business_types(request):
    """HTMX endpoint: load business types for a selected sector."""
    sector = request.GET.get('sector', '')
    data = _get_setup_data(request)
    language = data.get('language', 'en')

    types = BlueprintService.get_types(sector=sector, language=language)
    type_list = types if isinstance(types, list) else []

    return render(request, 'setup/partials/business_types.html', {
        'types': type_list,
        'selected_types': data.get('business_types', []),
    })


@login_required
def step_info(request):
    """Step 3: Info — business name, NIF, address, logo."""
    data = _get_setup_data(request)
    if not data.get('business_types'):
        return redirect('setup:step_business')

    if request.method == 'POST':
        data['business_name'] = request.POST.get('business_name', '')
        data['vat_number'] = request.POST.get('vat_number', '')
        data['business_address'] = request.POST.get('business_address', '')
        data['phone'] = request.POST.get('phone', '')
        data['email'] = request.POST.get('email', '')

        _set_setup_data(request, data)
        return redirect('setup:step_tax')

    store_config = StoreConfig.get_config()

    context = {
        'current_step': 3,
        'setup_data': data,
        'store_config': store_config,
    }
    return render(request, 'setup/pages/step3_info.html', context)


@login_required
def step_tax(request):
    """Step 4: Tax — pre-populated from preset, editable."""
    data = _get_setup_data(request)
    if not data.get('business_name'):
        return redirect('setup:step_info')

    if request.method == 'POST':
        tax_classes_json = request.POST.get('tax_classes', '[]')
        data['tax_classes_data'] = json.loads(tax_classes_json)
        data['tax_classes_saved'] = True
        _set_setup_data(request, data)
        # Tax is the last step — finalize is triggered via JS fetch
        return redirect('setup:step_tax')

    # Load tax preset
    country_code = data.get('country_code', 'ES').lower()
    preset_key = data.get('tax_preset', f'{country_code}_standard')
    tax_data = BlueprintService.get_tax_data(country_code)

    tax_classes = []
    preset_name = ''
    has_tax_data = False

    if tax_data and 'presets' in tax_data:
        has_tax_data = True
        preset = tax_data['presets'].get(preset_key, {})
        preset_name = preset.get('name', '')
        tax_classes = preset.get('classes', [])

        # Apply sector override notes
        sector = data.get('sector', '')
        sector_override = preset.get('sector_overrides', {}).get(sector, {})
        if sector_override:
            data['sector_tax_notes'] = sector_override.get('notes', '')

    # If previously saved, use saved data
    if data.get('tax_classes_data'):
        tax_classes = data['tax_classes_data']

    context = {
        'current_step': 4,
        'setup_data': data,
        'tax_classes': json.dumps(tax_classes),
        'preset_name': preset_name,
        'has_tax_data': has_tax_data,
        'sector_notes': data.get('sector_tax_notes', ''),
    }
    return render(request, 'setup/pages/step4_tax.html', context)


@login_required
def load_tax_preset(request):
    """HTMX endpoint: load tax classes for a specific preset."""
    country_code = request.GET.get('country', 'es').lower()
    preset_key = request.GET.get('preset', f'{country_code}_standard')

    tax_data = BlueprintService.get_tax_data(country_code)
    tax_classes = []
    if tax_data and 'presets' in tax_data:
        preset = tax_data['presets'].get(preset_key, {})
        tax_classes = preset.get('classes', [])

    return JsonResponse({'tax_classes': tax_classes})


@login_required
@require_POST
def finalize(request):
    """Finalize setup: create everything and install blueprint."""
    data = _get_setup_data(request)

    if not data.get('business_name') or not data.get('business_types'):
        return JsonResponse({'success': False, 'error': 'Incomplete setup data'}, status=400)

    try:
        hub_config = HubConfig.get_config()
        store_config = StoreConfig.get_config()

        # Update HubConfig
        hub_config.country_code = data.get('country_code', '')
        hub_config.language = data.get('language', 'en')
        hub_config.timezone = data.get('timezone', 'UTC')
        hub_config.currency = data.get('currency', 'EUR')
        hub_config.business_sector = data.get('sector', '')
        hub_config.selected_business_types = data.get('business_types', [])
        hub_config.save(update_fields=[
            'country_code', 'language', 'timezone', 'currency',
            'business_sector', 'selected_business_types',
        ])

        # Update StoreConfig
        store_config.business_name = data.get('business_name', '')
        store_config.vat_number = data.get('vat_number', '')
        store_config.business_address = data.get('business_address', '')
        store_config.phone = data.get('phone', '')
        store_config.email = data.get('email', '')
        store_config.save(update_fields=[
            'business_name', 'vat_number', 'business_address', 'phone', 'email',
        ])

        # Handle logo upload
        if request.FILES.get('logo'):
            store_config.logo = request.FILES['logo']
            store_config.save(update_fields=['logo'])

        # Tax classes from session (saved in step 4)
        tax_classes_data = data.get('tax_classes_data', [])

        # Finalize: create tax classes, payment methods, invoice series
        sector = data.get('sector', '')
        SetupService.finalize_setup(hub_config, store_config, tax_classes_data, sector)

        # Install modules from blueprint
        type_codes = data.get('business_types', [])
        install_result = {}
        if type_codes:
            install_result = BlueprintService.install_blueprint(
                hub_config, type_codes, include_recommended=True,
            )

        if install_result:
            logger.info('Blueprint install result: %s', install_result)
            if install_result.get('modules_installed', 0) > 0:
                _write_deferred_setup_flag()

        # Clear session setup data
        if 'setup_data' in request.session:
            del request.session['setup_data']

        return JsonResponse({'success': True, 'redirect': '/setup/complete/'})

    except Exception as e:
        logger.exception('Setup finalization failed: %s', e)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
def complete(request):
    """Setup complete page — shows success and redirects."""
    return render(request, 'setup/pages/complete.html', {})
