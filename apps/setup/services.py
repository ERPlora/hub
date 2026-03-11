"""
Setup Service — orchestrates the finalization of the setup wizard.

Creates tax classes, payment methods, invoice series, and marks the hub as configured.
"""
import logging
from decimal import Decimal

from django.db import transaction

logger = logging.getLogger(__name__)


class SetupService:

    @staticmethod
    def create_tax_classes(tax_classes_data, sector=None):
        """
        Create TaxClass records from wizard data.
        tax_classes_data: list of dicts with code, name, rate, is_default, order, description.
        Returns list of created TaxClass instances.
        """
        from apps.configuration.models import TaxClass

        created = []
        with transaction.atomic():
            # Clear existing tax classes (fresh setup)
            TaxClass.objects.all().delete()

            for tc_data in tax_classes_data:
                tc = TaxClass.objects.create(
                    code=tc_data.get('code', ''),
                    name=tc_data['name'],
                    rate=Decimal(str(tc_data['rate'])),
                    description=tc_data.get('description', ''),
                    is_default=tc_data.get('is_default', False),
                    is_active=True,
                    order=tc_data.get('order', 0),
                )
                created.append(tc)

        logger.info('Created %d tax classes', len(created))
        return created

    @staticmethod
    def set_default_tax_class(sector=None):
        """Set default tax class on StoreConfig based on sector."""
        from apps.configuration.models import StoreConfig, TaxClass

        store_config = StoreConfig.get_config()

        # For hospitality, default to reduced rate
        if sector in ('hospitality',):
            default_tc = TaxClass.objects.filter(
                code='reduced', is_active=True
            ).first()
        else:
            default_tc = TaxClass.objects.filter(
                is_default=True, is_active=True
            ).first()

        if default_tc:
            store_config.default_tax_class = default_tc
            store_config.save(update_fields=['default_tax_class'])

    @staticmethod
    def create_payment_methods():
        """Create default payment methods (Efectivo + Tarjeta) if sales module is loaded."""
        try:
            from django.apps import apps
            PaymentMethod = apps.get_model('sales', 'PaymentMethod')

            created = 0
            defaults = [
                {'name': 'Efectivo', 'type': 'cash', 'is_active': True, 'sort_order': 1, 'opens_cash_drawer': True, 'requires_change': True},
                {'name': 'Tarjeta', 'type': 'card', 'is_active': True, 'sort_order': 2, 'opens_cash_drawer': False, 'requires_change': False},
            ]
            for pm_data in defaults:
                _, was_created = PaymentMethod.objects.get_or_create(
                    type=pm_data['type'],
                    defaults=pm_data,
                )
                if was_created:
                    created += 1

            logger.info('Created %d payment methods', created)
            return created
        except LookupError:
            logger.debug('Sales module not installed, skipping payment methods')
            return 0

    @staticmethod
    def create_invoice_series():
        """Create default invoice series (F, R) if invoicing module is loaded."""
        try:
            from django.apps import apps
            InvoiceSeries = apps.get_model('invoicing', 'InvoiceSeries')

            created = 0
            defaults = [
                {'prefix': 'F', 'name': 'Facturas', 'is_default': True, 'next_number': 1},
                {'prefix': 'R', 'name': 'Facturas Rectificativas', 'is_default': False, 'next_number': 1},
            ]
            for series_data in defaults:
                _, was_created = InvoiceSeries.objects.get_or_create(
                    prefix=series_data['prefix'],
                    defaults=series_data,
                )
                if was_created:
                    created += 1

            logger.info('Created %d invoice series', created)
            return created
        except LookupError:
            logger.debug('Invoicing module not installed, skipping invoice series')
            return 0

    @classmethod
    def finalize_setup(cls, hub_config, store_config, tax_classes_data, sector=None):
        """
        Orchestrate the full setup finalization.
        Called from the wizard's finalize view after all steps are complete.
        """
        # 1. Create tax classes
        cls.create_tax_classes(tax_classes_data, sector)

        # 2. Set default tax class on store config
        cls.set_default_tax_class(sector)

        # 3. Mark store tax_included based on preset
        store_config.tax_included = True
        store_config.is_configured = True
        store_config.save(update_fields=['tax_included', 'is_configured'])

        # 4. Mark hub as configured
        hub_config.is_configured = True
        hub_config.save(update_fields=['is_configured'])

        # 5. Try to create payment methods and invoice series
        # (may fail if modules not yet loaded — deferred flag handles this)
        try:
            cls.create_payment_methods()
        except Exception as e:
            logger.info('Payment methods deferred: %s', e)

        try:
            cls.create_invoice_series()
        except Exception as e:
            logger.info('Invoice series deferred: %s', e)

        logger.info('Setup finalization complete')
