"""
Setup Wizard Views

Initial configuration wizard for new Hub installations.
Simple single-form approach with HTMX.
"""
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, redirect
from django.http import HttpResponse
from apps.accounts.decorators import login_required
from apps.configuration.models import StoreConfig


@login_required
def wizard(request):
    """
    Setup wizard - single form to configure the store.

    Required fields: business_name, business_address, vat_number
    Optional fields: phone, email, tax_rate, tax_included
    """
    store_config = StoreConfig.get_config()

    # If already configured, redirect to dashboard
    if store_config.is_configured:
        return redirect('main:index')

    if request.method == 'POST':
        # Get all form fields
        business_name = request.POST.get('business_name', '').strip()
        business_address = request.POST.get('business_address', '').strip()
        vat_number = request.POST.get('vat_number', '').strip()
        phone = request.POST.get('phone', '').strip()
        email = request.POST.get('email', '').strip()
        tax_rate = request.POST.get('tax_rate', '21').strip()
        tax_included = request.POST.get('tax_included') == 'on'

        # Validate required fields
        errors = []
        if not business_name:
            errors.append('Business name is required')
        if not business_address:
            errors.append('Address is required')
        if not vat_number:
            errors.append('VAT/Tax ID is required')

        if errors:
            # Return error response for HTMX
            error_html = '<div class="text-danger ion-padding">'
            for error in errors:
                error_html += f'<p><ion-icon name="alert-circle-outline"></ion-icon> {error}</p>'
            error_html += '</div>'
            return HttpResponse(error_html, status=400)

        # Save all fields
        store_config.business_name = business_name
        store_config.business_address = business_address
        store_config.vat_number = vat_number
        store_config.phone = phone
        store_config.email = email

        try:
            store_config.tax_rate = Decimal(tax_rate) if tax_rate else Decimal('21')
        except InvalidOperation:
            store_config.tax_rate = Decimal('21')

        store_config.tax_included = tax_included
        store_config.is_configured = True
        store_config.save()

        # Redirect to dashboard via HX-Redirect header
        response = HttpResponse(status=200)
        response['HX-Redirect'] = '/dashboard/'
        return response

    return render(request, 'main/setup/pages/wizard.html', {
        'store_config': store_config,
    })
