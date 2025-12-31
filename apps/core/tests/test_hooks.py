"""
Tests for ERPlora Hook System.

Tests the HookRegistry class that provides WordPress-style hooks for
module communication: actions (side effects) and filters (data modification).
"""
import pytest
from unittest.mock import MagicMock, patch, call
from django.core.exceptions import ValidationError

from apps.core.hooks import HookRegistry, hooks, action, filter


class TestHookRegistryActions:
    """Tests for action hooks (side effects, no return value)."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = HookRegistry()

    def test_add_action_registers_callback(self):
        """add_action registers callback for hook."""
        callback = MagicMock()
        self.registry.add_action('test.hook', callback)

        assert self.registry.has_action('test.hook')

    def test_add_action_with_priority(self):
        """Callbacks are sorted by priority."""
        results = []

        def callback_low():
            results.append('low')

        def callback_high():
            results.append('high')

        self.registry.add_action('test.hook', callback_high, priority=20)
        self.registry.add_action('test.hook', callback_low, priority=5)

        self.registry.do_action('test.hook')

        assert results == ['low', 'high']

    def test_add_action_with_module_id(self):
        """Module ID is stored with callback."""
        def my_callback(**kwargs):
            pass

        self.registry.add_action('test.hook', my_callback, module_id='my_module')

        registered = self.registry.get_registered_hooks()
        assert registered['actions']['test.hook'][0]['module'] == 'my_module'

    def test_add_action_infers_module_id(self):
        """Module ID is inferred from callback module."""
        def my_callback(**kwargs):
            pass

        # Manually set the module as if it were defined in sales.handlers
        my_callback.__module__ = 'sales.handlers'
        self.registry.add_action('test.hook', my_callback)

        registered = self.registry.get_registered_hooks()
        assert registered['actions']['test.hook'][0]['module'] == 'sales'

    def test_do_action_executes_callbacks(self):
        """do_action calls all registered callbacks."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        self.registry.add_action('test.hook', callback1)
        self.registry.add_action('test.hook', callback2)

        self.registry.do_action('test.hook', value=42)

        callback1.assert_called_once_with(value=42)
        callback2.assert_called_once_with(value=42)

    def test_do_action_passes_kwargs(self):
        """do_action passes all kwargs to callbacks."""
        callback = MagicMock()
        self.registry.add_action('test.hook', callback)

        self.registry.do_action('test.hook', sale=123, user='test', extra='data')

        callback.assert_called_once_with(sale=123, user='test', extra='data')

    def test_do_action_nonexistent_hook(self):
        """do_action on nonexistent hook does nothing."""
        # Should not raise
        self.registry.do_action('nonexistent.hook', value=42)

    def test_do_action_continues_on_error(self):
        """do_action continues executing after callback error."""
        def failing_callback(**kwargs):
            raise ValueError("Test error")

        callback_after = MagicMock()

        self.registry.add_action('test.hook', failing_callback, priority=1)
        self.registry.add_action('test.hook', callback_after, priority=2)

        # Should not raise, and should call second callback
        self.registry.do_action('test.hook')
        callback_after.assert_called_once()

    def test_remove_action_by_callback(self):
        """remove_action removes specific callback."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        self.registry.add_action('test.hook', callback1)
        self.registry.add_action('test.hook', callback2)

        removed = self.registry.remove_action('test.hook', callback=callback1)

        assert removed == 1
        self.registry.do_action('test.hook')
        callback1.assert_not_called()
        callback2.assert_called_once()

    def test_remove_action_by_module_id(self):
        """remove_action removes all callbacks from module."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        self.registry.add_action('test.hook', callback1, module_id='module_a')
        self.registry.add_action('test.hook', callback2, module_id='module_b')

        removed = self.registry.remove_action('test.hook', module_id='module_a')

        assert removed == 1
        self.registry.do_action('test.hook')
        callback1.assert_not_called()
        callback2.assert_called_once()

    def test_has_action_returns_false_for_empty(self):
        """has_action returns False when no callbacks registered."""
        assert self.registry.has_action('nonexistent.hook') is False


class TestHookRegistryFilters:
    """Tests for filter hooks (value modification)."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = HookRegistry()

    def test_add_filter_registers_callback(self):
        """add_filter registers callback for hook."""
        callback = MagicMock(return_value='modified')
        self.registry.add_filter('test.filter', callback)

        assert self.registry.has_filter('test.filter')

    def test_add_filter_with_priority(self):
        """Filter callbacks are sorted by priority."""
        def add_a(value, **kwargs):
            return value + 'a'

        def add_b(value, **kwargs):
            return value + 'b'

        self.registry.add_filter('test.filter', add_b, priority=20)
        self.registry.add_filter('test.filter', add_a, priority=10)

        result = self.registry.apply_filters('test.filter', 'start')

        assert result == 'startab'  # 'a' first (priority 10), then 'b' (priority 20)

    def test_apply_filters_returns_original_if_no_filters(self):
        """apply_filters returns original value if no filters."""
        result = self.registry.apply_filters('nonexistent.filter', 'original')

        assert result == 'original'

    def test_apply_filters_chains_modifications(self):
        """apply_filters chains modifications through callbacks."""
        def double(value, **kwargs):
            return value * 2

        def add_ten(value, **kwargs):
            return value + 10

        self.registry.add_filter('test.filter', double, priority=1)
        self.registry.add_filter('test.filter', add_ten, priority=2)

        result = self.registry.apply_filters('test.filter', 5)

        assert result == 20  # (5 * 2) + 10

    def test_apply_filters_passes_kwargs(self):
        """apply_filters passes kwargs to callbacks."""
        def modify(value, multiplier=1, **kwargs):
            return value * multiplier

        self.registry.add_filter('test.filter', modify)

        result = self.registry.apply_filters('test.filter', 5, multiplier=3)

        assert result == 15

    def test_apply_filters_continues_on_error(self):
        """apply_filters continues after callback error, keeping value."""
        def failing_filter(value, **kwargs):
            raise ValueError("Test error")

        def add_one(value, **kwargs):
            return value + 1

        self.registry.add_filter('test.filter', failing_filter, priority=1)
        self.registry.add_filter('test.filter', add_one, priority=2)

        # Should continue and apply add_one
        result = self.registry.apply_filters('test.filter', 10)
        assert result == 11

    def test_apply_filters_with_list_modification(self):
        """apply_filters can modify lists (common use case)."""
        def add_item(items, **kwargs):
            return items + [{'id': 999}]

        def filter_items(items, **kwargs):
            return [i for i in items if i.get('active', True)]

        self.registry.add_filter('test.filter', add_item, priority=1)
        self.registry.add_filter('test.filter', filter_items, priority=2)

        original = [{'id': 1, 'active': True}, {'id': 2, 'active': False}]
        result = self.registry.apply_filters('test.filter', original)

        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[1]['id'] == 999

    def test_remove_filter_by_callback(self):
        """remove_filter removes specific callback."""
        def double(value, **kwargs):
            return value * 2

        def triple(value, **kwargs):
            return value * 3

        self.registry.add_filter('test.filter', double)
        self.registry.add_filter('test.filter', triple)

        removed = self.registry.remove_filter('test.filter', callback=double)

        assert removed == 1
        result = self.registry.apply_filters('test.filter', 5)
        assert result == 15  # Only triple applied

    def test_remove_filter_by_module_id(self):
        """remove_filter removes all callbacks from module."""
        def double(value, **kwargs):
            return value * 2

        def triple(value, **kwargs):
            return value * 3

        self.registry.add_filter('test.filter', double, module_id='module_a')
        self.registry.add_filter('test.filter', triple, module_id='module_b')

        removed = self.registry.remove_filter('test.filter', module_id='module_a')

        assert removed == 1
        result = self.registry.apply_filters('test.filter', 5)
        assert result == 15


class TestHookRegistryUtilities:
    """Tests for utility methods."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = HookRegistry()

    def test_disable_hook(self):
        """disable_hook prevents hook execution."""
        callback = MagicMock()
        self.registry.add_action('test.hook', callback)

        self.registry.disable_hook('test.hook')
        self.registry.do_action('test.hook')

        callback.assert_not_called()

    def test_disable_hook_affects_filters(self):
        """disable_hook also prevents filter application."""
        def modify(value, **kwargs):
            return value * 2

        self.registry.add_filter('test.filter', modify)
        self.registry.disable_hook('test.filter')

        result = self.registry.apply_filters('test.filter', 5)

        assert result == 5  # Original value, filter not applied

    def test_enable_hook(self):
        """enable_hook re-enables disabled hook."""
        callback = MagicMock()
        self.registry.add_action('test.hook', callback)

        self.registry.disable_hook('test.hook')
        self.registry.enable_hook('test.hook')
        self.registry.do_action('test.hook')

        callback.assert_called_once()

    def test_get_registered_hooks(self):
        """get_registered_hooks returns all registrations."""
        action_cb = MagicMock()
        action_cb.__name__ = 'my_action'
        filter_cb = MagicMock()
        filter_cb.__name__ = 'my_filter'

        self.registry.add_action('test.action', action_cb, module_id='mod1')
        self.registry.add_filter('test.filter', filter_cb, module_id='mod2')

        result = self.registry.get_registered_hooks()

        assert 'actions' in result
        assert 'filters' in result
        assert len(result['actions']['test.action']) == 1
        assert result['actions']['test.action'][0]['callback'] == 'my_action'
        assert len(result['filters']['test.filter']) == 1
        assert result['filters']['test.filter'][0]['callback'] == 'my_filter'

    def test_clear_module_hooks(self):
        """clear_module_hooks removes all hooks from a module."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        self.registry.add_action('hook1', callback1, module_id='loyalty')
        self.registry.add_action('hook2', callback1, module_id='loyalty')
        self.registry.add_filter('filter1', callback2, module_id='loyalty')
        self.registry.add_action('hook3', callback1, module_id='sales')

        result = self.registry.clear_module_hooks('loyalty')

        assert result['actions'] == 2
        assert result['filters'] == 1

        # Verify loyalty hooks are gone
        assert not self.registry.has_action('hook1')
        assert not self.registry.has_action('hook2')
        assert not self.registry.has_filter('filter1')

        # Verify sales hooks remain
        assert self.registry.has_action('hook3')

    def test_clear_all(self):
        """clear_all removes all hooks and disabled state."""
        self.registry.add_action('test.action', MagicMock())
        self.registry.add_filter('test.filter', MagicMock())
        self.registry.disable_hook('test.action')

        self.registry.clear_all()

        assert not self.registry.has_action('test.action')
        assert not self.registry.has_filter('test.filter')
        assert len(self.registry._disabled_hooks) == 0


class TestHookDecorators:
    """Tests for @action and @filter decorators."""

    def setup_method(self):
        """Clear global hooks before each test."""
        hooks.clear_all()

    def teardown_method(self):
        """Clean up global hooks after each test."""
        hooks.clear_all()

    def test_action_decorator(self):
        """@action decorator registers function as action callback."""
        @action('test.decorated_action', priority=5)
        def my_callback(**kwargs):
            pass

        assert hooks.has_action('test.decorated_action')

    def test_filter_decorator(self):
        """@filter decorator registers function as filter callback."""
        @filter('test.decorated_filter', priority=5)
        def my_filter(value, **kwargs):
            return value

        assert hooks.has_filter('test.decorated_filter')

    def test_decorated_function_still_callable(self):
        """Decorated function can still be called directly."""
        @action('test.action')
        def add_numbers(a, b, **kwargs):
            return a + b

        result = add_numbers(2, 3)
        assert result == 5


class TestGlobalHooksInstance:
    """Tests for the global hooks instance."""

    def setup_method(self):
        """Clear global hooks before each test."""
        hooks.clear_all()

    def teardown_method(self):
        """Clean up global hooks after each test."""
        hooks.clear_all()

    def test_global_hooks_is_hook_registry(self):
        """Global hooks is a HookRegistry instance."""
        assert isinstance(hooks, HookRegistry)

    def test_global_hooks_persists_registrations(self):
        """Global hooks persists registrations."""
        callback = MagicMock()
        hooks.add_action('global.test', callback)

        assert hooks.has_action('global.test')


class TestRealWorldScenarios:
    """Integration tests with real-world usage patterns."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = HookRegistry()

    def test_sales_checkout_flow(self):
        """Simulate sales checkout with hooks."""
        events = []

        def loyalty_before_checkout(cart, request, **kwargs):
            events.append(('loyalty', 'before_checkout', cart['total']))

        def loyalty_filter_items(items, cart, **kwargs):
            # Apply loyalty discount to items
            for item in items:
                item['discount'] = item.get('discount', 0) + 5
            return items

        def sections_validate_table(cart, request, **kwargs):
            if not request.get('table_id'):
                raise ValidationError("Select a table first")
            events.append(('sections', 'validate_table', request['table_id']))

        def analytics_after_payment(sale, **kwargs):
            events.append(('analytics', 'after_payment', sale['id']))

        # Register hooks
        self.registry.add_action('sales.before_checkout', loyalty_before_checkout, priority=10)
        self.registry.add_action('sales.before_checkout', sections_validate_table, priority=5)
        self.registry.add_filter('sales.filter_cart_items', loyalty_filter_items)
        self.registry.add_action('sales.after_payment', analytics_after_payment)

        # Simulate checkout
        cart = {'total': 100}
        request = {'table_id': 5}
        items = [{'id': 1, 'price': 50}, {'id': 2, 'price': 50}]

        # Before checkout (sections first due to lower priority)
        self.registry.do_action('sales.before_checkout', cart=cart, request=request)

        # Filter items
        filtered_items = self.registry.apply_filters('sales.filter_cart_items', items, cart=cart)

        # After payment
        sale = {'id': 123}
        self.registry.do_action('sales.after_payment', sale=sale)

        # Verify events in correct order
        assert events == [
            ('sections', 'validate_table', 5),
            ('loyalty', 'before_checkout', 100),
            ('analytics', 'after_payment', 123),
        ]

        # Verify filter applied discounts
        assert filtered_items[0]['discount'] == 5
        assert filtered_items[1]['discount'] == 5

    def test_module_deactivation(self):
        """Simulate module deactivation clearing hooks."""
        callback1 = MagicMock()
        callback2 = MagicMock()

        self.registry.add_action('sales.after_payment', callback1, module_id='loyalty')
        self.registry.add_action('sales.after_payment', callback2, module_id='analytics')

        # Deactivate loyalty module
        self.registry.clear_module_hooks('loyalty')

        # Trigger hook
        self.registry.do_action('sales.after_payment', sale={'id': 1})

        # Only analytics callback should be called
        callback1.assert_not_called()
        callback2.assert_called_once()
