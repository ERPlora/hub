"""
ERPlora Hook System

A WordPress-style hook system that allows modules to modify behavior and data
of other modules without direct dependencies.

Two types of hooks:
- Actions (do_action): Execute callbacks at specific points (side effects)
- Filters (apply_filters): Modify and return values through a chain of callbacks

Example - Module defining hook points:
    from apps.core.hooks import hooks

    def checkout(request, cart):
        # Action: let other modules execute code before checkout
        hooks.do_action('sales.before_checkout', cart=cart, request=request)

        # Filter: let other modules modify cart items
        cart.items = hooks.apply_filters('sales.filter_cart_items', cart.items, cart=cart)

        # Process payment...
        sale = process_payment(cart)

        # Action: let other modules react after payment
        hooks.do_action('sales.after_payment', sale=sale)

        return sale

Example - Module registering callbacks:
    from apps.core.hooks import hooks

    class SectionsConfig(AppConfig):
        def ready(self):
            hooks.add_action('sales.before_checkout', self.validate_table, priority=5)
            hooks.add_filter('sales.filter_cart_items', self.add_table_info, priority=10)

        def validate_table(self, cart, request, **kwargs):
            if not request.session.get('current_table_id'):
                raise ValidationError("Please select a table first")

        def add_table_info(self, items, cart, **kwargs):
            # Modify and return items
            for item in items:
                item['table_id'] = cart.table_id
            return items
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from functools import wraps

logger = logging.getLogger(__name__)


class HookRegistry:
    """
    Central registry for hooks (actions and filters).

    Hooks allow modules to:
    - Execute code at specific points (actions)
    - Modify data before it's used (filters)

    Thread-safety: This implementation is NOT thread-safe.
    For production with multiple workers, consider using Django's cache
    or a more robust solution.
    """

    def __init__(self):
        self._actions: Dict[str, List[Tuple[int, str, Callable]]] = {}
        self._filters: Dict[str, List[Tuple[int, str, Callable]]] = {}
        self._disabled_hooks: set = set()

    # ==========================================================================
    # ACTIONS - Execute callbacks, no return value
    # ==========================================================================

    def add_action(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 10,
        module_id: str = None
    ) -> None:
        """
        Register a callback to be executed when an action is triggered.

        Args:
            hook_name: Name of the hook (convention: 'module.action_name')
            callback: Function to execute
            priority: Execution order (lower = earlier, default 10)
            module_id: Optional identifier for the registering module

        Example:
            hooks.add_action('sales.after_payment', my_callback, priority=5)
        """
        if hook_name not in self._actions:
            self._actions[hook_name] = []

        # Determine module_id from callback if not provided
        if module_id is None:
            module_id = getattr(callback, '__module__', 'unknown').split('.')[0]

        self._actions[hook_name].append((priority, module_id, callback))
        self._actions[hook_name].sort(key=lambda x: x[0])

        logger.debug(f"Action registered: {hook_name} <- {module_id} (priority {priority})")

    def remove_action(
        self,
        hook_name: str,
        callback: Callable = None,
        module_id: str = None
    ) -> int:
        """
        Remove action callback(s).

        Args:
            hook_name: Name of the hook
            callback: Specific callback to remove (if None, uses module_id)
            module_id: Remove all callbacks from this module

        Returns:
            Number of callbacks removed
        """
        if hook_name not in self._actions:
            return 0

        original_count = len(self._actions[hook_name])

        if callback is not None:
            self._actions[hook_name] = [
                (p, m, c) for p, m, c in self._actions[hook_name]
                if c != callback
            ]
        elif module_id is not None:
            self._actions[hook_name] = [
                (p, m, c) for p, m, c in self._actions[hook_name]
                if m != module_id
            ]

        return original_count - len(self._actions[hook_name])

    def do_action(self, hook_name: str, **kwargs) -> None:
        """
        Execute all callbacks registered for an action.

        Args:
            hook_name: Name of the hook to trigger
            **kwargs: Arguments to pass to callbacks

        Example:
            hooks.do_action('sales.after_payment', sale=sale, user=request.user)
        """
        if hook_name in self._disabled_hooks:
            return

        if hook_name not in self._actions:
            return

        for priority, module_id, callback in self._actions[hook_name]:
            try:
                callback(**kwargs)
            except Exception as e:
                logger.error(
                    f"Error in action hook '{hook_name}' "
                    f"(module: {module_id}, priority: {priority}): {e}",
                    exc_info=True
                )
                # Continue executing other callbacks

    def has_action(self, hook_name: str) -> bool:
        """Check if any callbacks are registered for an action."""
        return hook_name in self._actions and len(self._actions[hook_name]) > 0

    # ==========================================================================
    # FILTERS - Execute callbacks that modify and return a value
    # ==========================================================================

    def add_filter(
        self,
        hook_name: str,
        callback: Callable,
        priority: int = 10,
        module_id: str = None
    ) -> None:
        """
        Register a callback to filter/modify a value.

        The callback MUST accept the value as first argument and return
        the modified (or unmodified) value.

        Args:
            hook_name: Name of the hook (convention: 'module.filter_name')
            callback: Function that receives value, modifies it, and returns it
            priority: Execution order (lower = earlier, default 10)
            module_id: Optional identifier for the registering module

        Example:
            def add_discount(items, **kwargs):
                for item in items:
                    item['discount'] = 0.1
                return items

            hooks.add_filter('sales.filter_cart_items', add_discount, priority=5)
        """
        if hook_name not in self._filters:
            self._filters[hook_name] = []

        if module_id is None:
            module_id = getattr(callback, '__module__', 'unknown').split('.')[0]

        self._filters[hook_name].append((priority, module_id, callback))
        self._filters[hook_name].sort(key=lambda x: x[0])

        logger.debug(f"Filter registered: {hook_name} <- {module_id} (priority {priority})")

    def remove_filter(
        self,
        hook_name: str,
        callback: Callable = None,
        module_id: str = None
    ) -> int:
        """
        Remove filter callback(s).

        Args:
            hook_name: Name of the hook
            callback: Specific callback to remove (if None, uses module_id)
            module_id: Remove all callbacks from this module

        Returns:
            Number of callbacks removed
        """
        if hook_name not in self._filters:
            return 0

        original_count = len(self._filters[hook_name])

        if callback is not None:
            self._filters[hook_name] = [
                (p, m, c) for p, m, c in self._filters[hook_name]
                if c != callback
            ]
        elif module_id is not None:
            self._filters[hook_name] = [
                (p, m, c) for p, m, c in self._filters[hook_name]
                if m != module_id
            ]

        return original_count - len(self._filters[hook_name])

    def apply_filters(self, hook_name: str, value: Any, **kwargs) -> Any:
        """
        Apply all filter callbacks to a value and return the result.

        Each callback receives the value (potentially modified by previous
        callbacks) and must return the value (modified or not).

        Args:
            hook_name: Name of the hook to trigger
            value: Initial value to filter
            **kwargs: Additional arguments to pass to callbacks

        Returns:
            The filtered value after all callbacks have been applied

        Example:
            cart_items = hooks.apply_filters('sales.filter_cart_items', cart_items, cart=cart)
        """
        if hook_name in self._disabled_hooks:
            return value

        if hook_name not in self._filters:
            return value

        for priority, module_id, callback in self._filters[hook_name]:
            try:
                value = callback(value, **kwargs)
            except Exception as e:
                logger.error(
                    f"Error in filter hook '{hook_name}' "
                    f"(module: {module_id}, priority: {priority}): {e}",
                    exc_info=True
                )
                # Continue with unmodified value from this callback

        return value

    def has_filter(self, hook_name: str) -> bool:
        """Check if any callbacks are registered for a filter."""
        return hook_name in self._filters and len(self._filters[hook_name]) > 0

    # ==========================================================================
    # UTILITY METHODS
    # ==========================================================================

    def disable_hook(self, hook_name: str) -> None:
        """Temporarily disable a hook (useful for testing)."""
        self._disabled_hooks.add(hook_name)

    def enable_hook(self, hook_name: str) -> None:
        """Re-enable a disabled hook."""
        self._disabled_hooks.discard(hook_name)

    def get_registered_hooks(self) -> Dict[str, Dict]:
        """
        Get information about all registered hooks.

        Returns:
            Dict with 'actions' and 'filters' keys, each containing
            hook names and their registered callbacks.
        """
        return {
            'actions': {
                name: [
                    {'priority': p, 'module': m, 'callback': c.__name__}
                    for p, m, c in callbacks
                ]
                for name, callbacks in self._actions.items()
            },
            'filters': {
                name: [
                    {'priority': p, 'module': m, 'callback': c.__name__}
                    for p, m, c in callbacks
                ]
                for name, callbacks in self._filters.items()
            }
        }

    def clear_module_hooks(self, module_id: str) -> Dict[str, int]:
        """
        Remove all hooks registered by a specific module.

        Useful when a module is deactivated.

        Args:
            module_id: The module identifier

        Returns:
            Dict with counts of removed actions and filters
        """
        actions_removed = 0
        filters_removed = 0

        for hook_name in list(self._actions.keys()):
            actions_removed += self.remove_action(hook_name, module_id=module_id)

        for hook_name in list(self._filters.keys()):
            filters_removed += self.remove_filter(hook_name, module_id=module_id)

        logger.info(
            f"Cleared hooks for module '{module_id}': "
            f"{actions_removed} actions, {filters_removed} filters"
        )

        return {'actions': actions_removed, 'filters': filters_removed}

    def clear_all(self) -> None:
        """Clear all registered hooks. Use with caution (mainly for testing)."""
        self._actions.clear()
        self._filters.clear()
        self._disabled_hooks.clear()
        logger.warning("All hooks cleared")


# ==========================================================================
# GLOBAL INSTANCE
# ==========================================================================

# Single global instance for the application
hooks = HookRegistry()


# ==========================================================================
# DECORATORS FOR CONVENIENCE
# ==========================================================================

def action(hook_name: str, priority: int = 10):
    """
    Decorator to register a function as an action callback.

    Example:
        @action('sales.after_payment', priority=5)
        def send_receipt_email(sale, **kwargs):
            # Send email...
            pass
    """
    def decorator(func: Callable) -> Callable:
        hooks.add_action(hook_name, func, priority=priority)
        return func
    return decorator


def filter(hook_name: str, priority: int = 10):
    """
    Decorator to register a function as a filter callback.

    Example:
        @filter('sales.filter_cart_items', priority=5)
        def apply_discount(items, **kwargs):
            for item in items:
                item['discount'] = 0.1
            return items
    """
    def decorator(func: Callable) -> Callable:
        hooks.add_filter(hook_name, func, priority=priority)
        return func
    return decorator


# ==========================================================================
# STANDARD HOOK NAMES (Documentation)
# ==========================================================================

"""
Standard hook naming convention: '{module}.{action_or_filter}'

SALES MODULE HOOKS:
- sales.before_checkout      (action) Before checkout process starts
- sales.after_checkout       (action) After checkout completes
- sales.before_payment       (action) Before payment is processed
- sales.after_payment        (action) After payment is processed
- sales.filter_cart_items    (filter) Modify cart items before processing
- sales.filter_totals        (filter) Modify calculated totals
- sales.filter_payment_methods (filter) Modify available payment methods

INVENTORY MODULE HOOKS:
- inventory.before_stock_change  (action) Before stock is modified
- inventory.after_stock_change   (action) After stock is modified
- inventory.filter_products      (filter) Modify product list
- inventory.filter_stock_alert   (filter) Modify low stock alert threshold

CUSTOMERS MODULE HOOKS:
- customers.before_create    (action) Before customer is created
- customers.after_create     (action) After customer is created
- customers.filter_search    (filter) Modify customer search results

INVOICING MODULE HOOKS:
- invoicing.before_create    (action) Before invoice is created
- invoicing.after_create     (action) After invoice is created
- invoicing.filter_lines     (filter) Modify invoice lines
- invoicing.filter_totals    (filter) Modify invoice totals

SECTIONS MODULE HOOKS:
- sections.table_opened      (action) When a table is opened
- sections.table_closed      (action) When a table is closed
- sections.filter_tables     (filter) Modify available tables list
"""
