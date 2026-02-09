"""
Main Settings Views
"""
import json
from decimal import Decimal, InvalidOperation
from django.http import HttpResponse
from django.shortcuts import render
from django.conf import settings as django_settings
from django.utils import translation
from zoneinfo import available_timezones
from apps.core.htmx import htmx_view
from apps.accounts.decorators import login_required
from apps.accounts.models import LocalUser
from apps.configuration.models import HubConfig, StoreConfig, BackupConfig, TaxClass


# Common timezones grouped by region (most used first)
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
    # Put common timezones first, then the rest
    common_set = set(COMMON_TIMEZONES)
    other_tz = [tz for tz in all_tz if tz not in common_set and '/' in tz]
    return COMMON_TIMEZONES + other_tz


def toast_response(message, msg_type='success', status=200, **extra_triggers):
    """Return an empty HTTP response with HX-Trigger to show a toast."""
    triggers = {'showMessage': {'message': message, 'type': msg_type}}
    triggers.update(extra_triggers)
    response = HttpResponse(status=status)
    response['HX-Trigger'] = json.dumps(triggers)
    return response


@login_required
@htmx_view('main/settings/pages/index.html', 'main/settings/partials/content.html')
def index(request):
    """Settings page"""
    user = LocalUser.objects.get(id=request.session['local_user_id'])
    hub_config = HubConfig.get_config()
    store_config = StoreConfig.get_config()

    if request.method == 'POST':
        action = request.POST.get('action')

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

            # Checkbox sends value only when checked
            store_config.tax_included = 'tax_included' in request.POST

            # Handle logo upload
            if 'logo' in request.FILES:
                store_config.logo = request.FILES['logo']

            # Update is_configured based on required fields
            store_config.is_configured = store_config.is_complete()
            store_config.save()

            return toast_response('Store settings saved')

        # Handle user preferences form
        if action == 'update_user':
            language = request.POST.get('language')
            avatar = request.FILES.get('avatar')
            old_language = request.session.get('user_language')

            if language:
                valid_languages = [code for code, name in django_settings.LANGUAGES]
                if language in valid_languages:
                    user.language = language
                    translation.activate(language)
                    request.session['_language'] = language
                    request.session['user_language'] = language

            if avatar:
                user.avatar = avatar

            user.save()

            # If language changed, trigger page reload
            if language and language != old_language:
                response = toast_response('Preferences saved')
                response['HX-Refresh'] = 'true'
                return response

            return toast_response('Preferences saved')

        # Handle hub settings form
        if action == 'update_hub':
            language = request.POST.get('language')
            timezone = request.POST.get('timezone')
            currency = request.POST.get('currency')
            dark_mode = 'dark_mode' in request.POST

            # Validate and set system language
            if language:
                valid_languages = [code for code, name in django_settings.LANGUAGES]
                if language in valid_languages:
                    hub_config.language = language

            # Validate and set timezone
            if timezone:
                all_tz = available_timezones()
                if timezone in all_tz:
                    hub_config.timezone = timezone

            if currency:
                valid_currencies = [code for code, name in django_settings.POPULAR_CURRENCY_CHOICES]
                if currency in valid_currencies:
                    hub_config.currency = currency

            hub_config.dark_mode = dark_mode
            hub_config.dark_mode_auto = False
            hub_config.save()

            return toast_response('Hub settings saved')

        # Handle theme update form (color_theme, dark_mode, auto_print)
        if action == 'update_theme':
            color_theme = request.POST.get('color_theme')
            dark_mode = request.POST.get('dark_mode') == 'true'
            auto_print = request.POST.get('auto_print') == 'true'

            if color_theme:
                hub_config.color_theme = color_theme
            hub_config.dark_mode = dark_mode
            hub_config.auto_print = auto_print
            hub_config.save()

            return toast_response('Theme settings saved')

        # Handle backup settings form
        if action == 'update_backup':
            backup_config = BackupConfig.get_solo()
            backup_config.enabled = 'backup_enabled' in request.POST
            backup_config.frequency = request.POST.get('backup_frequency', 'daily')
            try:
                backup_config.time_hour = int(request.POST.get('backup_hour', 3))
                backup_config.retention_days = int(request.POST.get('retention_days', 30))
                backup_config.max_backups = int(request.POST.get('max_backups', 10))
            except (ValueError, TypeError):
                pass
            backup_config.save()

            # Reschedule the backup job
            from apps.configuration.services import backup_service
            backup_service.reschedule()

            return toast_response('Backup settings saved')

        # Handle manual backup trigger
        if action == 'run_backup':
            from apps.configuration.services import backup_service
            success, path, size = backup_service.run_backup()
            if success:
                size_kb = round(size / 1024) if size else 0
                return toast_response(f'Backup completed ({size_kb} KB)')
            else:
                return toast_response(f'Backup failed: {path}', 'error', status=500)

        # Handle TaxClass actions
        if action == 'create_tax_class':
            name = request.POST.get('name', '').strip()
            rate = request.POST.get('rate', '0')
            description = request.POST.get('description', '').strip()
            is_default = 'is_default' in request.POST

            if not name:
                return toast_response('Name is required', 'error', status=400)

            try:
                TaxClass.objects.create(
                    name=name,
                    rate=Decimal(rate) if rate else Decimal('0'),
                    description=description,
                    is_default=is_default,
                )
                # Return updated tax classes list
                tax_classes = TaxClass.objects.filter(is_active=True).order_by('order', 'rate')
                response = render(request, 'main/settings/partials/tax_classes_list.html', {
                    'tax_classes': tax_classes
                })
                response['HX-Trigger'] = json.dumps({
                    'showMessage': {'message': 'Tax class created', 'type': 'success'}
                })
                return response
            except (InvalidOperation, Exception) as e:
                return toast_response(str(e), 'error', status=400)

        if action == 'delete_tax_class':
            tax_class_id = request.POST.get('tax_class_id')
            try:
                tax_class = TaxClass.objects.get(id=tax_class_id)
                tax_class.delete()
                # Return updated tax classes list
                tax_classes = TaxClass.objects.filter(is_active=True).order_by('order', 'rate')
                response = render(request, 'main/settings/partials/tax_classes_list.html', {
                    'tax_classes': tax_classes
                })
                response['HX-Trigger'] = json.dumps({
                    'showMessage': {'message': 'Tax class deleted', 'type': 'success'}
                })
                return response
            except TaxClass.DoesNotExist:
                return toast_response('Tax class not found', 'error', status=404)

        return toast_response('Settings saved')

    # Get backup config and scheduler status
    backup_config = BackupConfig.get_solo()
    from apps.configuration.scheduler import get_scheduler_status
    scheduler_status = get_scheduler_status()

    # Get all tax classes
    tax_classes = TaxClass.objects.filter(is_active=True).order_by('order', 'rate')

    return {
        'current_section': 'settings',
        'page_title': 'Settings',
        'user': user,
        'hub_config': hub_config,
        'store_config': store_config,
        'backup_config': backup_config,
        'scheduler_status': scheduler_status,
        'tax_classes': tax_classes,
        'language_choices': django_settings.LANGUAGES,
        'system_language_choices': django_settings.LANGUAGES,
        'timezone_choices': get_sorted_timezones(),
        'currency_choices': django_settings.POPULAR_CURRENCY_CHOICES,
        'backup_frequency_choices': BackupConfig.Frequency.choices,
    }
