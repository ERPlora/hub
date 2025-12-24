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
from apps.configuration.models import HubConfig, StoreConfig, BackupConfig, TaxClass


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
            hub_config.dark_mode_auto = False  # User chose manually, disable auto
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

        # Handle backup settings form
        if action == 'update_backup':
            backup_config = BackupConfig.get_solo()
            backup_config.enabled = request.POST.get('backup_enabled') == 'true'
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

            return JsonResponse({'success': True, 'message': 'Backup settings saved'})

        # Handle manual backup trigger
        if action == 'run_backup':
            from apps.configuration.services import backup_service
            success, path, size = backup_service.run_backup()
            if success:
                return JsonResponse({
                    'success': True,
                    'message': 'Backup completed',
                    'path': path,
                    'size': size
                })
            else:
                return JsonResponse({'success': False, 'error': path}, status=500)

        # Handle TaxClass actions
        if action == 'create_tax_class':
            name = request.POST.get('name', '').strip()
            rate = request.POST.get('rate', '0')
            description = request.POST.get('description', '').strip()
            is_default = request.POST.get('is_default') == 'true'

            if not name:
                return JsonResponse({'success': False, 'error': 'Name is required'}, status=400)

            try:
                tax_class = TaxClass.objects.create(
                    name=name,
                    rate=Decimal(rate) if rate else Decimal('0'),
                    description=description,
                    is_default=is_default,
                )
                return JsonResponse({
                    'success': True,
                    'message': 'Tax class created',
                    'tax_class': {
                        'id': tax_class.id,
                        'name': tax_class.name,
                        'rate': str(tax_class.rate),
                        'description': tax_class.description,
                        'is_default': tax_class.is_default,
                    }
                })
            except (InvalidOperation, Exception) as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        if action == 'update_tax_class':
            tax_class_id = request.POST.get('tax_class_id')
            try:
                tax_class = TaxClass.objects.get(id=tax_class_id)
                tax_class.name = request.POST.get('name', tax_class.name).strip()
                tax_class.rate = Decimal(request.POST.get('rate', tax_class.rate))
                tax_class.description = request.POST.get('description', '').strip()
                tax_class.is_default = request.POST.get('is_default') == 'true'
                tax_class.save()
                return JsonResponse({
                    'success': True,
                    'message': 'Tax class updated',
                    'tax_class': {
                        'id': tax_class.id,
                        'name': tax_class.name,
                        'rate': str(tax_class.rate),
                        'description': tax_class.description,
                        'is_default': tax_class.is_default,
                    }
                })
            except TaxClass.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tax class not found'}, status=404)
            except (InvalidOperation, Exception) as e:
                return JsonResponse({'success': False, 'error': str(e)}, status=400)

        if action == 'delete_tax_class':
            tax_class_id = request.POST.get('tax_class_id')
            try:
                tax_class = TaxClass.objects.get(id=tax_class_id)
                tax_class.delete()
                return JsonResponse({'success': True, 'message': 'Tax class deleted'})
            except TaxClass.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tax class not found'}, status=404)

        if action == 'set_default_tax_class':
            tax_class_id = request.POST.get('tax_class_id')
            try:
                if tax_class_id:
                    tax_class = TaxClass.objects.get(id=tax_class_id)
                    store_config.default_tax_class = tax_class
                else:
                    store_config.default_tax_class = None
                store_config.save()
                return JsonResponse({'success': True, 'message': 'Default tax class updated'})
            except TaxClass.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Tax class not found'}, status=404)

        return JsonResponse({'success': True})

    # Get backup config and scheduler status
    backup_config = BackupConfig.get_solo()
    from apps.configuration.scheduler import get_scheduler_status
    scheduler_status = get_scheduler_status()

    # Get all tax classes
    tax_classes = TaxClass.objects.filter(is_active=True).order_by('order', 'rate')

    # Use POPULAR_CURRENCY_CHOICES for the UI (24 most common currencies)
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
        'currency_choices': django_settings.POPULAR_CURRENCY_CHOICES,
        'backup_frequency_choices': BackupConfig.Frequency.choices,
    }
