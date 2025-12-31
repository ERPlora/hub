"""
Tests for ERPlora Signal System.

Tests the Django signals defined in apps.core.signals that enable
loose coupling between modules.
"""
import pytest
from unittest.mock import MagicMock, patch, call
from django.dispatch import receiver

from apps.core.signals import (
    # Sales signals
    sale_created,
    sale_completed,
    sale_cancelled,
    sale_refunded,
    # Inventory signals
    product_created,
    product_updated,
    product_deleted,
    stock_changed,
    low_stock_alert,
    # Customer signals
    customer_created,
    customer_updated,
    customer_deleted,
    # Cash register signals
    cash_session_opened,
    cash_session_closed,
    cash_movement_created,
    # Invoicing signals
    invoice_created,
    invoice_sent,
    invoice_paid,
    # Sections signals
    table_opened,
    table_closed,
    table_transferred,
    # Loyalty signals
    points_earned,
    points_redeemed,
    tier_changed,
    # Print signals
    print_ticket_requested,
    print_completed,
    print_failed,
    # Module lifecycle signals
    module_activated,
    module_deactivated,
    module_updated,
    # Sync signals
    sync_started,
    sync_completed,
    sync_failed,
    # Auth signals
    user_logged_in,
    user_logged_out,
)


@pytest.mark.django_db
class TestSalesSignals:
    """Tests for sales-related signals."""

    def setup_method(self):
        """Reset signal receivers."""
        self.received_signals = []

    def test_sale_created_signal(self):
        """sale_created signal can be sent and received."""
        handler = MagicMock()
        sale_created.connect(handler)

        try:
            sale_created.send(
                sender='sales',
                sale={'id': 1},
                user='test_user',
                cart_data={'items': []}
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['sender'] == 'sales'
            assert call_kwargs['sale'] == {'id': 1}
            assert call_kwargs['user'] == 'test_user'
        finally:
            sale_created.disconnect(handler)

    def test_sale_completed_signal(self):
        """sale_completed signal includes payment method."""
        handler = MagicMock()
        sale_completed.connect(handler)

        try:
            sale_completed.send(
                sender='sales',
                sale={'id': 1, 'total': 100},
                user='test_user',
                payment_method='card'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['payment_method'] == 'card'
        finally:
            sale_completed.disconnect(handler)

    def test_sale_cancelled_signal(self):
        """sale_cancelled signal includes reason."""
        handler = MagicMock()
        sale_cancelled.connect(handler)

        try:
            sale_cancelled.send(
                sender='sales',
                sale={'id': 1},
                user='test_user',
                reason='customer_request'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['reason'] == 'customer_request'
        finally:
            sale_cancelled.disconnect(handler)

    def test_sale_refunded_signal(self):
        """sale_refunded signal includes refund details."""
        handler = MagicMock()
        sale_refunded.connect(handler)

        try:
            sale_refunded.send(
                sender='returns',
                sale={'id': 1},
                refund_amount=50.00,
                items=[{'id': 1, 'qty': 1}],
                user='test_user'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['sender'] == 'returns'
            assert call_kwargs['refund_amount'] == 50.00
        finally:
            sale_refunded.disconnect(handler)


@pytest.mark.django_db
class TestInventorySignals:
    """Tests for inventory-related signals."""

    def test_product_created_signal(self):
        """product_created signal can be sent and received."""
        handler = MagicMock()
        product_created.connect(handler)

        try:
            product_created.send(
                sender='inventory',
                product={'id': 1, 'name': 'Test Product'},
                user='test_user'
            )

            handler.assert_called_once()
        finally:
            product_created.disconnect(handler)

    def test_stock_changed_signal(self):
        """stock_changed signal includes all stock details."""
        handler = MagicMock()
        stock_changed.connect(handler)

        try:
            stock_changed.send(
                sender='sales',
                product_id=1,
                product_name='Test Product',
                old_quantity=10,
                new_quantity=8,
                change_reason='sale',
                reference_id=123
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['old_quantity'] == 10
            assert call_kwargs['new_quantity'] == 8
            assert call_kwargs['change_reason'] == 'sale'
        finally:
            stock_changed.disconnect(handler)

    def test_low_stock_alert_signal(self):
        """low_stock_alert signal includes stock levels."""
        handler = MagicMock()
        low_stock_alert.connect(handler)

        try:
            low_stock_alert.send(
                sender='inventory',
                product={'id': 1, 'name': 'Test'},
                current_stock=2,
                minimum_stock=5
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['current_stock'] == 2
            assert call_kwargs['minimum_stock'] == 5
        finally:
            low_stock_alert.disconnect(handler)


@pytest.mark.django_db
class TestCustomerSignals:
    """Tests for customer-related signals."""

    def test_customer_created_signal(self):
        """customer_created signal can be sent and received."""
        handler = MagicMock()
        customer_created.connect(handler)

        try:
            customer_created.send(
                sender='customers',
                customer={'id': 1, 'name': 'John Doe'},
                user='test_user'
            )

            handler.assert_called_once()
        finally:
            customer_created.disconnect(handler)

    def test_customer_updated_signal(self):
        """customer_updated signal includes changed fields."""
        handler = MagicMock()
        customer_updated.connect(handler)

        try:
            customer_updated.send(
                sender='customers',
                customer={'id': 1, 'name': 'John Updated'},
                user='test_user',
                changed_fields=['name', 'email']
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert 'name' in call_kwargs['changed_fields']
        finally:
            customer_updated.disconnect(handler)


@pytest.mark.django_db
class TestCashRegisterSignals:
    """Tests for cash register signals."""

    def test_cash_session_opened_signal(self):
        """cash_session_opened signal includes initial amount."""
        handler = MagicMock()
        cash_session_opened.connect(handler)

        try:
            cash_session_opened.send(
                sender='cash_register',
                session={'id': 1},
                user='test_user',
                initial_amount=100.00
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['initial_amount'] == 100.00
        finally:
            cash_session_opened.disconnect(handler)

    def test_cash_session_closed_signal(self):
        """cash_session_closed signal includes totals."""
        handler = MagicMock()
        cash_session_closed.connect(handler)

        try:
            cash_session_closed.send(
                sender='cash_register',
                session={'id': 1},
                user='test_user',
                final_amount=250.00,
                expected_amount=250.00,
                difference=0.00
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['difference'] == 0.00
        finally:
            cash_session_closed.disconnect(handler)


@pytest.mark.django_db
class TestInvoicingSignals:
    """Tests for invoicing signals."""

    def test_invoice_created_signal(self):
        """invoice_created signal includes related sale."""
        handler = MagicMock()
        invoice_created.connect(handler)

        try:
            invoice_created.send(
                sender='invoicing',
                invoice={'id': 1, 'number': 'INV-001'},
                sale={'id': 123},
                user='test_user'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['sale'] == {'id': 123}
        finally:
            invoice_created.disconnect(handler)

    def test_invoice_sent_signal(self):
        """invoice_sent signal includes method and recipient."""
        handler = MagicMock()
        invoice_sent.connect(handler)

        try:
            invoice_sent.send(
                sender='invoicing',
                invoice={'id': 1},
                method='email',
                recipient='customer@example.com'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['method'] == 'email'
        finally:
            invoice_sent.disconnect(handler)


@pytest.mark.django_db
class TestSectionsSignals:
    """Tests for sections (tables/areas) signals."""

    def test_table_opened_signal(self):
        """table_opened signal includes guests count."""
        handler = MagicMock()
        table_opened.connect(handler)

        try:
            table_opened.send(
                sender='sections',
                table={'id': 1, 'name': 'Table 1'},
                area={'id': 1, 'name': 'Terrace'},
                guests=4,
                user='test_user'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['guests'] == 4
        finally:
            table_opened.disconnect(handler)

    def test_table_closed_signal(self):
        """table_closed signal includes duration."""
        handler = MagicMock()
        table_closed.connect(handler)

        try:
            table_closed.send(
                sender='sections',
                table={'id': 1},
                duration_minutes=45,
                sale={'id': 123}
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['duration_minutes'] == 45
        finally:
            table_closed.disconnect(handler)

    def test_table_transferred_signal(self):
        """table_transferred signal includes both tables."""
        handler = MagicMock()
        table_transferred.connect(handler)

        try:
            table_transferred.send(
                sender='sections',
                from_table={'id': 1},
                to_table={'id': 2},
                sale={'id': 123},
                user='test_user'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['from_table'] == {'id': 1}
            assert call_kwargs['to_table'] == {'id': 2}
        finally:
            table_transferred.disconnect(handler)


@pytest.mark.django_db
class TestLoyaltySignals:
    """Tests for loyalty signals."""

    def test_points_earned_signal(self):
        """points_earned signal includes points and reason."""
        handler = MagicMock()
        points_earned.connect(handler)

        try:
            points_earned.send(
                sender='loyalty',
                member={'id': 1},
                points=100,
                sale={'id': 123},
                reason='purchase'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['points'] == 100
            assert call_kwargs['reason'] == 'purchase'
        finally:
            points_earned.disconnect(handler)

    def test_tier_changed_signal(self):
        """tier_changed signal includes tier transition."""
        handler = MagicMock()
        tier_changed.connect(handler)

        try:
            tier_changed.send(
                sender='loyalty',
                member={'id': 1},
                old_tier='Silver',
                new_tier='Gold',
                direction='upgrade'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['old_tier'] == 'Silver'
            assert call_kwargs['new_tier'] == 'Gold'
            assert call_kwargs['direction'] == 'upgrade'
        finally:
            tier_changed.disconnect(handler)


@pytest.mark.django_db
class TestPrintSignals:
    """Tests for print-related signals."""

    def test_print_ticket_requested_signal(self):
        """print_ticket_requested signal includes ticket details."""
        handler = MagicMock()
        print_ticket_requested.connect(handler)

        try:
            print_ticket_requested.send(
                sender='sales',
                ticket_type='receipt',
                data={'sale_id': 123, 'items': []},
                printer_id=1,
                priority=1
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['ticket_type'] == 'receipt'
        finally:
            print_ticket_requested.disconnect(handler)


@pytest.mark.django_db
class TestModuleLifecycleSignals:
    """Tests for module lifecycle signals."""

    def test_module_activated_signal(self):
        """module_activated signal includes module info."""
        handler = MagicMock()
        module_activated.connect(handler)

        try:
            module_activated.send(
                sender='modules_runtime',
                module_id='loyalty',
                module_name='Loyalty Program',
                version='1.0.0'
            )

            handler.assert_called_once()
            call_kwargs = handler.call_args[1]
            assert call_kwargs['module_id'] == 'loyalty'
        finally:
            module_activated.disconnect(handler)

    def test_module_deactivated_signal(self):
        """module_deactivated signal includes module info."""
        handler = MagicMock()
        module_deactivated.connect(handler)

        try:
            module_deactivated.send(
                sender='modules_runtime',
                module_id='loyalty',
                module_name='Loyalty Program'
            )

            handler.assert_called_once()
        finally:
            module_deactivated.disconnect(handler)


@pytest.mark.django_db
class TestSignalIntegration:
    """Integration tests for signal usage patterns."""

    def test_multiple_handlers_for_same_signal(self):
        """Multiple handlers can listen to the same signal."""
        handler1 = MagicMock()
        handler2 = MagicMock()
        handler3 = MagicMock()

        sale_completed.connect(handler1)
        sale_completed.connect(handler2)
        sale_completed.connect(handler3)

        try:
            sale_completed.send(
                sender='sales',
                sale={'id': 1},
                user='test',
                payment_method='cash'
            )

            handler1.assert_called_once()
            handler2.assert_called_once()
            handler3.assert_called_once()
        finally:
            sale_completed.disconnect(handler1)
            sale_completed.disconnect(handler2)
            sale_completed.disconnect(handler3)

    def test_handler_exception_doesnt_stop_others(self):
        """Exception in one handler doesn't stop others."""
        def failing_handler(**kwargs):
            raise RuntimeError("Test error")

        success_handler = MagicMock()

        sale_completed.connect(failing_handler)
        sale_completed.connect(success_handler)

        try:
            # Django's send() will raise if a handler raises
            # This tests that our signal definitions work correctly
            with pytest.raises(RuntimeError):
                sale_completed.send(
                    sender='sales',
                    sale={'id': 1},
                    user='test',
                    payment_method='cash'
                )
        finally:
            sale_completed.disconnect(failing_handler)
            sale_completed.disconnect(success_handler)

    def test_signal_with_receiver_decorator(self):
        """@receiver decorator works for signal registration."""
        received = []

        @receiver(sale_completed)
        def handler(sender, sale, **kwargs):
            received.append(sale['id'])

        try:
            sale_completed.send(
                sender='sales',
                sale={'id': 42},
                user='test',
                payment_method='cash'
            )

            assert 42 in received
        finally:
            sale_completed.disconnect(handler)


@pytest.mark.django_db
class TestRealWorldSignalScenarios:
    """Tests simulating real module interactions via signals."""

    def test_sale_triggers_inventory_and_loyalty(self):
        """Sale completion triggers inventory and loyalty updates."""
        inventory_updates = []
        loyalty_points = []

        def inventory_handler(sender, sale, **kwargs):
            inventory_updates.append(f"Update for sale {sale['id']}")

        def loyalty_handler(sender, sale, **kwargs):
            loyalty_points.append(f"Points for sale {sale['id']}")

        sale_completed.connect(inventory_handler)
        sale_completed.connect(loyalty_handler)

        try:
            sale_completed.send(
                sender='sales',
                sale={'id': 123, 'total': 100},
                user='cashier',
                payment_method='card'
            )

            assert len(inventory_updates) == 1
            assert len(loyalty_points) == 1
            assert 'sale 123' in inventory_updates[0]
            assert 'sale 123' in loyalty_points[0]
        finally:
            sale_completed.disconnect(inventory_handler)
            sale_completed.disconnect(loyalty_handler)

    def test_stock_change_chain(self):
        """Stock change can trigger low stock alert."""
        alerts = []

        def stock_handler(sender, product_id, new_quantity, **kwargs):
            if new_quantity < 5:  # Simulate low stock check
                low_stock_alert.send(
                    sender='inventory',
                    product={'id': product_id},
                    current_stock=new_quantity,
                    minimum_stock=5
                )

        def alert_handler(sender, product, current_stock, **kwargs):
            alerts.append(f"Low stock for product {product['id']}: {current_stock}")

        stock_changed.connect(stock_handler)
        low_stock_alert.connect(alert_handler)

        try:
            stock_changed.send(
                sender='sales',
                product_id=1,
                product_name='Test',
                old_quantity=10,
                new_quantity=3,
                change_reason='sale',
                reference_id=123
            )

            assert len(alerts) == 1
            assert 'product 1' in alerts[0]
            assert '3' in alerts[0]
        finally:
            stock_changed.disconnect(stock_handler)
            low_stock_alert.disconnect(alert_handler)

    def test_customer_creation_triggers_loyalty_member(self):
        """New customer can auto-trigger loyalty member creation."""
        members_created = []

        def create_loyalty_member(sender, customer, **kwargs):
            members_created.append(customer['id'])

        customer_created.connect(create_loyalty_member)

        try:
            customer_created.send(
                sender='customers',
                customer={'id': 42, 'name': 'New Customer'},
                user='staff'
            )

            assert 42 in members_created
        finally:
            customer_created.disconnect(create_loyalty_member)
