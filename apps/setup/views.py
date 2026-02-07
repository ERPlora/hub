"""
Setup Wizard Views

Multi-step HTMX wizard for initial Hub configuration.
Each step saves to DB on "Next" and loads the next step partial.
"""
import json
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from zoneinfo import available_timezones
from apps.accounts.decorators import login_required
from apps.core.htmx import is_htmx_request
from apps.configuration.models import StoreConfig, HubConfig
from config.countries import get_all_countries, get_locale_map


# =============================================================================
# Timezone data
# =============================================================================

COMMON_TIMEZONES = [
    # Europe
    'Europe/Madrid', 'Europe/London', 'Europe/Paris', 'Europe/Berlin',
    'Europe/Rome', 'Europe/Amsterdam', 'Europe/Brussels', 'Europe/Lisbon',
    'Europe/Vienna', 'Europe/Warsaw', 'Europe/Prague', 'Europe/Stockholm',
    'Europe/Helsinki', 'Europe/Athens', 'Europe/Dublin', 'Europe/Zurich',
    # Americas
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Toronto', 'America/Mexico_City', 'America/Sao_Paulo', 'America/Buenos_Aires',
    'America/Bogota', 'America/Lima', 'America/Santiago',
    # Asia
    'Asia/Tokyo', 'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Singapore',
    'Asia/Dubai', 'Asia/Mumbai', 'Asia/Seoul', 'Asia/Bangkok',
    # Pacific
    'Australia/Sydney', 'Australia/Melbourne', 'Pacific/Auckland',
    # UTC
    'UTC',
]


def get_sorted_timezones():
    """Get timezones sorted with common ones first, then alphabetically."""
    all_tz = sorted(available_timezones())
    common_set = set(COMMON_TIMEZONES)
    other_tz = [tz for tz in all_tz if tz not in common_set and '/' in tz]
    return COMMON_TIMEZONES + other_tz


# =============================================================================
# Step configuration
# =============================================================================

TOTAL_STEPS = 3

STEP_TEMPLATES = {
    1: 'setup/partials/step1_regional.html',
    2: 'setup/partials/step2_business.html',
    3: 'setup/partials/step3_tax.html',
}

STEP_LABELS = [_('Region'), _('Business'), _('Tax')]


# =============================================================================
# Context helpers
# =============================================================================

def _get_completed_steps(hub_config, store_config):
    """Determine which steps are completed based on DB state."""
    completed = set()
    if hub_config.language and hub_config.timezone:
        completed.add(1)
    if store_config.business_name and store_config.business_address and store_config.vat_number:
        completed.add(2)
    if store_config.is_configured:
        completed.add(3)
    return completed


def _get_step_context(step, hub_config, store_config, errors=None):
    """Build context for rendering a step partial."""
    completed = _get_completed_steps(hub_config, store_config)

    # Progress width: step 1 = 0%, step 2 = 50%, step 3 = 100%
    progress_width = ((step - 1) / (TOTAL_STEPS - 1)) * 100 if TOTAL_STEPS > 1 else 0

    context = {
        'current_step': step,
        'total_steps': TOTAL_STEPS,
        'completed_steps': completed,
        'step_labels': STEP_LABELS,
        'progress_width': progress_width,
        'hub_config': hub_config,
        'store_config': store_config,
        'languages': settings.LANGUAGES,
        'errors': errors,
    }

    # Step-specific data
    if step == 1:
        timezones = get_sorted_timezones()
        context['timezones_json'] = json.dumps(timezones)
    elif step == 2:
        countries = get_all_countries()
        locale_map = get_locale_map(settings.LANGUAGES)
        context['countries_json'] = json.dumps(countries, ensure_ascii=False)
        context['locale_map_json'] = json.dumps(locale_map, ensure_ascii=False)

    return context


def _get_full_page_context(step, hub_config, store_config):
    """Build context for the full wizard page wrapping a step."""
    context = _get_step_context(step, hub_config, store_config)
    context['step_template'] = STEP_TEMPLATES[step]

    # Full page needs all JS data for any step the user might navigate to
    timezones = get_sorted_timezones()
    countries = get_all_countries()
    locale_map = get_locale_map(settings.LANGUAGES)

    context['timezones_json'] = json.dumps(timezones)
    context['countries_json'] = json.dumps(countries, ensure_ascii=False)
    context['locale_map_json'] = json.dumps(locale_map, ensure_ascii=False)

    return context


# =============================================================================
# Validation
# =============================================================================

def _validate_step1(data):
    """Validate step 1 (regional settings)."""
    errors = []
    language = data.get('language', '').strip()
    timezone = data.get('timezone', '').strip()

    valid_langs = {code for code, _ in settings.LANGUAGES}
    if language and language not in valid_langs:
        errors.append(_('Invalid language selection.'))

    if timezone and timezone not in available_timezones() and timezone != 'UTC':
        errors.append(_('Invalid timezone.'))

    return errors


def _validate_step2(data):
    """Validate step 2 (business information)."""
    errors = []
    if not data.get('business_name', '').strip():
        errors.append(_('Business name is required'))
    if not data.get('business_address', '').strip():
        errors.append(_('Address is required'))
    if not data.get('vat_number', '').strip():
        errors.append(_('VAT/Tax ID is required'))
    return errors


def _validate_step3(data):
    """Validate step 3 (tax configuration)."""
    errors = []
    tax_rate = data.get('tax_rate', '').strip()
    if tax_rate:
        try:
            rate = Decimal(tax_rate)
            if rate < 0 or rate > 100:
                errors.append(_('Tax rate must be between 0 and 100.'))
        except InvalidOperation:
            errors.append(_('Invalid tax rate.'))
    return errors


# =============================================================================
# Save helpers
# =============================================================================

def _save_step1(data, hub_config):
    """Save step 1 data to HubConfig."""
    hub_config.language = data.get('language', 'en').strip()
    hub_config.timezone = data.get('timezone', 'UTC').strip()
    hub_config.save()


def _save_step2(data, store_config):
    """Save step 2 data to StoreConfig."""
    store_config.business_name = data.get('business_name', '').strip()
    store_config.business_address = data.get('business_address', '').strip()
    store_config.vat_number = data.get('vat_number', '').strip()
    store_config.phone = data.get('phone', '').strip()
    store_config.email = data.get('email', '').strip()
    store_config.save()


def _save_step3(data, store_config):
    """Save step 3 data to StoreConfig and mark as configured."""
    tax_rate = data.get('tax_rate', '21').strip()
    try:
        store_config.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('21')
    except InvalidOperation:
        store_config.tax_rate = Decimal('21')

    store_config.tax_included = data.get('tax_included') == 'on'
    store_config.is_configured = True
    store_config.save()


# =============================================================================
# Views
# =============================================================================

@login_required
def wizard(request):
    """
    Setup wizard entry point.

    GET /setup/ → Full page with step 1 (or current step based on DB state).
    """
    store_config = StoreConfig.get_config()
    hub_config = HubConfig.get_config()

    if store_config.is_configured:
        return redirect('main:index')

    # Determine which step to show based on completed data
    completed = _get_completed_steps(hub_config, store_config)
    if 2 in completed:
        initial_step = 3
    elif 1 in completed:
        initial_step = 2
    else:
        initial_step = 1

    context = _get_full_page_context(initial_step, hub_config, store_config)
    return render(request, 'setup/pages/wizard.html', context)


@login_required
def wizard_step(request, step):
    """
    Handle individual wizard steps.

    GET  /setup/step/<N>/ → Step partial (HTMX) or full page (direct access)
    POST /setup/step/<N>/ → Validate, save, return next step (or redirect on final)
    """
    if step not in STEP_TEMPLATES:
        return redirect('setup:wizard')

    store_config = StoreConfig.get_config()
    hub_config = HubConfig.get_config()

    if store_config.is_configured:
        return redirect('main:index')

    if request.method == 'POST':
        return _handle_step_post(request, step, hub_config, store_config)

    # GET request
    if is_htmx_request(request):
        context = _get_step_context(step, hub_config, store_config)
        return render(request, STEP_TEMPLATES[step], context)
    else:
        # Direct browser access (refresh/bookmark) → full page
        context = _get_full_page_context(step, hub_config, store_config)
        return render(request, 'setup/pages/wizard.html', context)


def _handle_step_post(request, step, hub_config, store_config):
    """Process a step POST: validate → save → return next step or redirect."""
    data = request.POST

    # Validate
    validators = {1: _validate_step1, 2: _validate_step2, 3: _validate_step3}
    errors = validators[step](data)

    if errors:
        # Re-render same step with errors
        context = _get_step_context(step, hub_config, store_config, errors=errors)
        return render(request, STEP_TEMPLATES[step], context)

    # Save
    savers = {1: _save_step1, 2: _save_step2, 3: _save_step3}
    if step == 1:
        savers[step](data, hub_config)
    else:
        savers[step](data, store_config)

    # Return next step or redirect
    if step < TOTAL_STEPS:
        next_step = step + 1
        # Refresh configs after save
        hub_config.refresh_from_db()
        store_config.refresh_from_db()
        context = _get_step_context(next_step, hub_config, store_config)
        return render(request, STEP_TEMPLATES[next_step], context)
    else:
        # Final step complete → redirect to home
        response = HttpResponse(status=200)
        response['HX-Redirect'] = '/'
        return response
