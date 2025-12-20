"""
Setup Wizard Views

Initial configuration wizard for new Hub installations.
"""
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.http import JsonResponse
from apps.accounts.decorators import login_required
from apps.configuration.models import StoreConfig


@login_required
def wizard(request):
    """
    Setup wizard - step-by-step store configuration.

    Steps:
    1. Business Info (name, address, VAT) - Required
    2. Tax Configuration (rate, included) - Optional
    3. Receipt Configuration (header, footer) - Optional
    """
    store_config = StoreConfig.get_config()

    # If already configured, redirect to dashboard
    if store_config.is_complete():
        return redirect('main:index')

    if request.method == 'POST':
        action = request.POST.get('action')

        # Step 1: Business Info
        if action == 'save_business':
            store_config.business_name = request.POST.get('business_name', '').strip()
            store_config.business_address = request.POST.get('business_address', '').strip()
            store_config.vat_number = request.POST.get('vat_number', '').strip()
            store_config.phone = request.POST.get('phone', '').strip()
            store_config.email = request.POST.get('email', '').strip()
            store_config.website = request.POST.get('website', '').strip()
            store_config.save()

            return JsonResponse({
                'success': True,
                'next_step': 2,
                'can_finish': store_config.is_complete()
            })

        # Step 2: Tax Config
        if action == 'save_tax':
            try:
                tax_rate = request.POST.get('tax_rate', '0')
                store_config.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('0')
            except InvalidOperation:
                store_config.tax_rate = Decimal('0')

            store_config.tax_included = request.POST.get('tax_included') == 'true'
            store_config.save()

            return JsonResponse({
                'success': True,
                'next_step': 3
            })

        # Step 3: Receipt Config
        if action == 'save_receipt':
            store_config.receipt_header = request.POST.get('receipt_header', '').strip()
            store_config.receipt_footer = request.POST.get('receipt_footer', '').strip()
            store_config.save()

            return JsonResponse({
                'success': True,
                'next_step': 'complete'
            })

        # Finish wizard
        if action == 'finish':
            if store_config.is_complete():
                store_config.is_configured = True
                store_config.save()
                return JsonResponse({
                    'success': True,
                    'redirect': '/dashboard/'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Please complete required fields first'
                }, status=400)

        # Skip to finish (only if required fields are complete)
        if action == 'skip':
            if store_config.is_complete():
                store_config.is_configured = True
                store_config.save()
                return JsonResponse({
                    'success': True,
                    'redirect': '/dashboard/'
                })
            else:
                return JsonResponse({
                    'success': False,
                    'error': 'Please complete required fields first'
                }, status=400)

    return render(request, 'main/setup/pages/wizard.html', {
        'store_config': store_config,
    })
