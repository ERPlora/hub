"""
Integration tests for module communication.

Tests that modules correctly communicate via signals, hooks, and slots.
"""

import pytest
from decimal import Decimal
from unittest.mock import MagicMock, patch

from apps.core.hooks import HookRegistry
from apps.core.slots import SlotRegistry
from apps.core.signals import (
    sale_completed,
    table_opened,
    table_closed,
    cash_movement_created
)


class TestSignalIntegration:
    """Tests for signal-based communication between modules."""

    def setup_method(self):
        """Disconnect any existing handlers."""
        self.connected_handlers = []

    def teardown_method(self):
        """Clean up connected handlers."""
        for signal, handler in self.connected_handlers:
            try:
                signal.disconnect(handler)
            except Exception:
                pass

    def _connect(self, signal, handler):
        """Connect handler and track for cleanup."""
        signal.connect(handler)
        self.connected_handlers.append((signal, handler))

    def test_sale_completed_triggers_table_close(self):
        """Test that sale_completed can trigger table close logic."""
        # Simulate tables module listening to sale_completed
        table_actions = []

        def tables_handler(sender, sale, user, payment_method, **kwargs):
            if hasattr(sale, 'context_type') and sale.context_type == 'table':
                table_actions.append({
                    'action': 'close_table',
                    'table_id': sale.context_id,
                    'sale_id': sale.id
                })

        self._connect(sale_completed, tables_handler)

        # Create mock sale with table context
        mock_sale = MagicMock()
        mock_sale.id = 'sale-123'
        mock_sale.context_type = 'table'
        mock_sale.context_id = 5
        mock_sale.total = Decimal('75.00')

        mock_user = MagicMock(id=1)

        # Emit signal
        sale_completed.send(
            sender='sales',
            sale=mock_sale,
            user=mock_user,
            payment_method='cash'
        )

        # Verify tables module would close the table
        assert len(table_actions) == 1
        assert table_actions[0]['table_id'] == 5

    def test_sale_completed_triggers_cash_register(self):
        """Test that sale_completed can trigger cash register logic."""
        # Simulate cash_register module listening
        cash_movements = []

        def cash_register_handler(sender, sale, user, payment_method, **kwargs):
            if payment_method == 'cash':
                cash_movements.append({
                    'amount': sale.total,
                    'sale_id': sale.id,
                    'type': 'sale'
                })

        self._connect(sale_completed, cash_register_handler)

        # Create mock sale
        mock_sale = MagicMock()
        mock_sale.id = 'sale-456'
        mock_sale.total = Decimal('50.00')

        # Emit signal
        sale_completed.send(
            sender='sales',
            sale=mock_sale,
            user=MagicMock(id=1),
            payment_method='cash'
        )

        assert len(cash_movements) == 1
        assert cash_movements[0]['amount'] == Decimal('50.00')

    def test_multiple_modules_receive_same_signal(self):
        """Test that multiple modules can receive the same signal."""
        received_by = []

        def tables_handler(sender, **kwargs):
            received_by.append('tables')

        def cash_handler(sender, **kwargs):
            received_by.append('cash_register')

        def loyalty_handler(sender, **kwargs):
            received_by.append('loyalty')

        self._connect(sale_completed, tables_handler)
        self._connect(sale_completed, cash_handler)
        self._connect(sale_completed, loyalty_handler)

        sale_completed.send(
            sender='sales',
            sale=MagicMock(id='sale-1'),
            user=MagicMock(id=1),
            payment_method='card'
        )

        assert 'tables' in received_by
        assert 'cash_register' in received_by
        assert 'loyalty' in received_by

    def test_signal_chain_table_to_cash(self):
        """Test signal chain: table_closed -> cash_register tracking."""
        tracked_sessions = []

        def track_table_duration(sender, table, duration_minutes, sale, **kwargs):
            # Cash register could track time per table
            tracked_sessions.append({
                'table': table.number,
                'duration': duration_minutes,
                'revenue': sale.total
            })

        self._connect(table_closed, track_table_duration)

        mock_table = MagicMock()
        mock_table.number = '5'

        mock_sale = MagicMock()
        mock_sale.total = Decimal('120.00')

        table_closed.send(
            sender='tables',
            table=mock_table,
            duration_minutes=45,
            sale=mock_sale
        )

        assert len(tracked_sessions) == 1
        assert tracked_sessions[0]['table'] == '5'
        assert tracked_sessions[0]['duration'] == 45


class TestHooksIntegration:
    """Tests for hook-based module extension."""

    def setup_method(self):
        """Create fresh hook registry."""
        self.hooks = HookRegistry()

    def test_filter_chain_modifies_data(self):
        """Test multiple modules filtering sale data."""
        # Tables module adds table info
        def add_table_info(data, **kwargs):
            data['table_number'] = kwargs.get('table_number', '')
            return data

        # Cash register adds shift info
        def add_shift_info(data, **kwargs):
            data['shift_id'] = kwargs.get('shift_id')
            return data

        # Loyalty adds customer points
        def add_points(data, **kwargs):
            data['points_earned'] = int(data.get('total', 0) * 0.1)
            return data

        self.hooks.add_filter('sale.process_data', add_table_info, priority=10)
        self.hooks.add_filter('sale.process_data', add_shift_info, priority=20)
        self.hooks.add_filter('sale.process_data', add_points, priority=30)

        result = self.hooks.apply_filters(
            'sale.process_data',
            {'total': 100, 'items': []},
            table_number='5',
            shift_id=42
        )

        assert result['table_number'] == '5'
        assert result['shift_id'] == 42
        assert result['points_earned'] == 10

    def test_action_before_sale_validation(self):
        """Test validation hooks before sale completion."""
        validation_errors = []

        def validate_cash_session(sale, user, **kwargs):
            # Cash register validates active session
            if not kwargs.get('has_open_session', True):
                validation_errors.append("No open cash session")

        def validate_table_required(sale, user, **kwargs):
            # Tables validates table selection if required
            if kwargs.get('require_table') and not kwargs.get('table_id'):
                validation_errors.append("Table selection required")

        self.hooks.add_action('sale.validate', validate_cash_session, priority=10)
        self.hooks.add_action('sale.validate', validate_table_required, priority=20)

        # Test with missing requirements
        self.hooks.do_action(
            'sale.validate',
            sale=MagicMock(),
            user=MagicMock(),
            has_open_session=False,
            require_table=True,
            table_id=None
        )

        assert len(validation_errors) == 2
        assert "cash session" in validation_errors[0].lower()
        assert "Table" in validation_errors[1]


class TestSlotsIntegration:
    """Tests for slot-based UI injection."""

    def setup_method(self):
        """Create fresh slot registry."""
        self.slots = SlotRegistry()

    def test_multiple_modules_inject_to_same_slot(self):
        """Test multiple modules adding content to same slot."""
        # Tables adds floor plan
        self.slots.register(
            'pos.sidebar_left',
            template='tables/floor_plan.html',
            priority=10,
            module_id='tables'
        )

        # Loyalty adds customer info
        self.slots.register(
            'pos.sidebar_left',
            template='loyalty/customer_widget.html',
            priority=20,
            module_id='loyalty'
        )

        content = self.slots.get_slot_content('pos.sidebar_left')

        assert len(content) == 2
        # Priority 10 comes first
        assert content[0]['module_id'] == 'tables'
        assert content[1]['module_id'] == 'loyalty'

    def test_conditional_slot_content(self):
        """Test slot content with conditions."""
        def show_for_tables_mode(request):
            return request.session.get('mode') == 'tables'

        def show_for_retail_mode(request):
            return request.session.get('mode') == 'retail'

        self.slots.register(
            'pos.header',
            template='tables/table_selector.html',
            condition_fn=show_for_tables_mode,
            module_id='tables'
        )

        self.slots.register(
            'pos.header',
            template='retail/quick_sale.html',
            condition_fn=show_for_retail_mode,
            module_id='retail'
        )

        content = self.slots.get_slot_content('pos.header')
        # Both are registered (conditions checked at render time)
        assert len(content) == 2

    def test_slot_with_dynamic_context(self):
        """Test slot content with dynamic context."""
        def get_table_context(request):
            table_id = request.session.get('current_table_id')
            return {
                'table_id': table_id,
                'table_status': 'occupied' if table_id else None
            }

        self.slots.register(
            'pos.cart_header',
            template='tables/table_badge.html',
            context_callable=get_table_context,
            module_id='tables'
        )

        content = self.slots.get_slot_content('pos.cart_header')
        assert len(content) == 1
        assert content[0]['context_callable'] is not None


class TestFullIntegrationScenario:
    """End-to-end integration tests for common workflows."""

    def setup_method(self):
        """Setup fresh registries."""
        self.hooks = HookRegistry()
        self.slots = SlotRegistry()
        self.signal_log = []

    def teardown_method(self):
        """Cleanup."""
        pass

    def test_restaurant_sale_flow(self):
        """
        Test complete restaurant sale flow:
        1. Table opened
        2. Items added to cart
        3. Sale completed
        4. Table auto-closed
        5. Cash movement recorded
        """
        # Track all events
        events = []

        # Tables module: listen for sale_completed
        def on_sale_completed_tables(sender, sale, **kwargs):
            if hasattr(sale, 'context_type') and sale.context_type == 'table':
                events.append(f"tables:close:{sale.context_id}")

        # Cash register: listen for sale_completed
        def on_sale_completed_cash(sender, sale, payment_method, **kwargs):
            if payment_method == 'cash':
                events.append(f"cash:record:{sale.total}")

        # Loyalty: listen for sale_completed
        def on_sale_completed_loyalty(sender, sale, **kwargs):
            if hasattr(sale, 'customer_id') and sale.customer_id:
                events.append(f"loyalty:points:{sale.customer_id}")

        sale_completed.connect(on_sale_completed_tables)
        sale_completed.connect(on_sale_completed_cash)
        sale_completed.connect(on_sale_completed_loyalty)

        try:
            # 1. Table opened (tables module emits table_opened)
            table_opened.send(
                sender='tables',
                table=MagicMock(id=5, number='5'),
                area=MagicMock(id=1, name='Main'),
                guests=4,
                user=MagicMock(id=1)
            )

            # 2-3. Sale completed (sales module emits sale_completed)
            mock_sale = MagicMock()
            mock_sale.id = 'sale-001'
            mock_sale.context_type = 'table'
            mock_sale.context_id = 5
            mock_sale.total = Decimal('85.50')
            mock_sale.customer_id = 123

            sale_completed.send(
                sender='sales',
                sale=mock_sale,
                user=MagicMock(id=1),
                payment_method='cash'
            )

            # Verify all modules responded
            assert 'tables:close:5' in events
            assert 'cash:record:85.50' in events
            assert 'loyalty:points:123' in events

        finally:
            sale_completed.disconnect(on_sale_completed_tables)
            sale_completed.disconnect(on_sale_completed_cash)
            sale_completed.disconnect(on_sale_completed_loyalty)

    def test_hooks_modify_checkout_data(self):
        """Test hooks modifying checkout data from multiple modules."""
        # Tables adds table info
        def add_table_data(data, **kwargs):
            data['table_number'] = '5'
            data['guests'] = 4
            return data

        # Cash register adds session info
        def add_session_data(data, **kwargs):
            data['cash_session_id'] = 42
            data['employee_name'] = 'John'
            return data

        # Verifactu adds compliance data
        def add_compliance_data(data, **kwargs):
            data['verifactu_hash'] = 'abc123'
            data['invoice_number'] = 'INV-2024-001'
            return data

        self.hooks.add_filter('checkout.prepare_data', add_table_data, priority=10)
        self.hooks.add_filter('checkout.prepare_data', add_session_data, priority=20)
        self.hooks.add_filter('checkout.prepare_data', add_compliance_data, priority=30)

        # Initial checkout data
        data = {
            'items': [{'id': 1, 'qty': 2}],
            'subtotal': Decimal('50.00'),
            'total': Decimal('60.50')
        }

        # Apply all filters
        result = self.hooks.apply_filters('checkout.prepare_data', data)

        # All modules enriched the data
        assert result['table_number'] == '5'
        assert result['cash_session_id'] == 42
        assert result['verifactu_hash'] == 'abc123'
        # Original data preserved
        assert result['total'] == Decimal('60.50')
