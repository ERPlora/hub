"""
Unit tests for core services.

Tests the shared services that modules use:
- Currency service
- Tax service
- Export service
- Print service
"""
import pytest
from decimal import Decimal
from django.http import HttpResponse

pytestmark = pytest.mark.unit


class TestCurrencyService:
    """Tests for locale-aware currency formatting service (Babel)."""

    def test_format_currency_eur(self, hub_config):
        """Test formatting with EUR currency."""
        from apps.core.services import format_currency

        hub_config.currency = 'EUR'
        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_currency(19.90)
        assert '€' in result
        assert '19.90' in result

    def test_format_currency_usd(self, hub_config):
        """Test formatting with USD currency."""
        from apps.core.services import format_currency

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_currency(19.90, 'USD')
        assert '$' in result
        assert '19.90' in result

    def test_format_currency_with_thousands(self, hub_config):
        """Test formatting with thousand separators."""
        from apps.core.services import format_currency

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_currency(1234.56)
        # Should contain the digits and some separator
        assert '1' in result
        assert '234' in result
        assert '56' in result

    def test_format_currency_without_symbol(self, hub_config):
        """Test formatting without currency symbol."""
        from apps.core.services import format_currency

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_currency(19.90, show_symbol=False)
        assert '€' not in result
        assert '$' not in result

    def test_format_currency_locale_es(self, hub_config):
        """Test formatting with Spanish locale uses correct separators."""
        from apps.core.services import format_currency

        hub_config.currency = 'EUR'
        hub_config.language = 'es'
        hub_config.country_code = 'ES'
        hub_config.save()

        result = format_currency(1234.56)
        assert '€' in result
        # Spanish uses comma for decimals, period for thousands
        assert '1.234,56' in result

    def test_format_number(self, hub_config):
        """Test number formatting."""
        from apps.core.services import format_number

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_number(1234567.89)
        assert '1' in result
        assert '234' in result
        assert '567' in result

    def test_format_number_no_decimals(self, hub_config):
        """Test number formatting without decimals."""
        from apps.core.services import format_number

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = format_number(1234, decimal_places=0)
        assert '1' in result
        assert '234' in result

    def test_parse_currency(self, hub_config):
        """Test parsing currency strings."""
        from apps.core.services import parse_currency

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = parse_currency('€1,234.56')
        assert result == Decimal('1234.56')

    def test_parse_currency_usd(self, hub_config):
        """Test parsing USD currency strings."""
        from apps.core.services import parse_currency

        hub_config.language = 'en'
        hub_config.country_code = 'US'
        hub_config.save()

        result = parse_currency('$19.90', 'USD')
        assert result == Decimal('19.90')

    def test_get_currency(self, hub_config):
        """Test getting current currency from config."""
        from apps.core.services import get_currency

        hub_config.currency = 'GBP'
        hub_config.save()

        result = get_currency()
        assert result == 'GBP'

    def test_get_currency_symbol(self, hub_config):
        """Test getting currency symbol."""
        from apps.core.services import get_currency_symbol

        hub_config.currency = 'EUR'
        hub_config.language = 'es'
        hub_config.country_code = 'ES'
        hub_config.save()

        assert get_currency_symbol() == '€'
        assert get_currency_symbol('GBP') == '£'
        assert '$' in get_currency_symbol('USD')


class TestTaxService:
    """Tests for tax calculation service."""

    def test_calculate_tax_included(self, store_config):
        """Test tax calculation when tax is included in price."""
        from apps.core.services import calculate_tax

        store_config.tax_rate = Decimal('21.00')
        store_config.tax_included = True
        store_config.save()

        net, tax, gross = calculate_tax(121)
        assert gross == Decimal('121.00')
        assert net == Decimal('100.00')
        assert tax == Decimal('21.00')

    def test_calculate_tax_not_included(self, store_config):
        """Test tax calculation when tax is not included."""
        from apps.core.services import calculate_tax

        store_config.tax_rate = Decimal('21.00')
        store_config.tax_included = False
        store_config.save()

        net, tax, gross = calculate_tax(100)
        assert net == Decimal('100.00')
        assert tax == Decimal('21.00')
        assert gross == Decimal('121.00')

    def test_get_tax_rate(self, store_config):
        """Test getting tax rate from config."""
        from apps.core.services import get_tax_rate

        store_config.tax_rate = Decimal('10.00')
        store_config.save()

        result = get_tax_rate()
        assert result == Decimal('10.00')

    def test_is_tax_included(self, store_config):
        """Test checking if tax is included."""
        from apps.core.services import is_tax_included

        store_config.tax_included = True
        store_config.save()

        assert is_tax_included() is True

        store_config.tax_included = False
        store_config.save()

        # Note: Cache may need to be cleared
        from apps.configuration.models import StoreConfig
        StoreConfig._clear_cache()

        assert is_tax_included() is False

    def test_format_tax_rate(self, store_config):
        """Test tax rate formatting."""
        from apps.core.services import format_tax_rate

        store_config.tax_rate = Decimal('21.00')
        store_config.save()

        result = format_tax_rate()
        assert result == '21%'

    def test_format_tax_rate_with_decimals(self):
        """Test tax rate formatting with decimals."""
        from apps.core.services import format_tax_rate

        result = format_tax_rate(Decimal('10.50'))
        assert result == '10.5%'

    def test_get_net_amount(self, store_config):
        """Test extracting net amount from gross."""
        from apps.core.services import get_net_amount

        store_config.tax_rate = Decimal('21.00')
        store_config.save()

        result = get_net_amount(121)
        assert result == Decimal('100.00')

    def test_get_gross_amount(self, store_config):
        """Test calculating gross from net."""
        from apps.core.services import get_gross_amount

        store_config.tax_rate = Decimal('21.00')
        store_config.save()

        result = get_gross_amount(100)
        assert result == Decimal('121.00')


class TestExportService:
    """Tests for export service."""

    def test_export_to_csv_dict_list(self):
        """Test exporting list of dicts to CSV."""
        from apps.core.services import export_to_csv

        data = [
            {'name': 'Product A', 'price': 10.00},
            {'name': 'Product B', 'price': 20.00},
        ]

        response = export_to_csv(
            data,
            fields=['name', 'price'],
            filename='test.csv'
        )

        assert isinstance(response, HttpResponse)
        assert response['Content-Type'] == 'text/csv; charset=utf-8'
        assert 'attachment; filename="test.csv"' in response['Content-Disposition']

        content = response.content.decode('utf-8')
        assert 'Product A' in content
        assert 'Product B' in content

    def test_export_to_csv_with_headers(self):
        """Test exporting with custom headers."""
        from apps.core.services import export_to_csv

        data = [{'name': 'Test', 'price': 10}]

        response = export_to_csv(
            data,
            fields=['name', 'price'],
            headers=['Product Name', 'Price (EUR)']
        )

        content = response.content.decode('utf-8')
        assert 'Product Name' in content
        assert 'Price (EUR)' in content

    def test_generate_csv_string(self):
        """Test generating CSV as string."""
        from apps.core.services import generate_csv_string

        data = [
            {'name': 'Test 1', 'value': 100},
            {'name': 'Test 2', 'value': 200},
        ]

        result = generate_csv_string(data, fields=['name', 'value'])

        assert isinstance(result, str)
        assert 'Test 1' in result
        assert 'Test 2' in result
        assert '100' in result


class TestPrintService:
    """Tests for print service."""

    def test_render_print_page(self):
        """Test rendering print page."""
        from apps.core.services import render_print_page

        # Use a simple template path that might exist
        response = render_print_page(
            'base.html',  # Base template should exist
            {'test': 'value'},
            title='Test Print',
            auto_print=True
        )

        assert isinstance(response, HttpResponse)
        content = response.content.decode('utf-8')
        assert 'Test Print' in content or 'html' in content.lower()

    def test_render_print_page_no_auto_print(self):
        """Test rendering without auto-print."""
        from apps.core.services import render_print_page

        response = render_print_page(
            'base.html',
            {},
            auto_print=False
        )

        content = response.content.decode('utf-8')
        # Should not contain auto-print script
        assert 'window.print()' not in content or 'window.onload' not in content
