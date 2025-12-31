"""
ERPlora Slot System

A dynamic UI extension system that allows modules to inject HTML/components
into templates of other modules without direct dependencies.

Slots are placeholder points in templates where other modules can register
content to be rendered.

Example - Module defining slots in template:
    {% load slots %}

    <ion-header>
        {% render_slot 'sales.pos_header_start' %}
        <ion-searchbar>...</ion-searchbar>
        {% render_slot 'sales.pos_header_end' %}
    </ion-header>

Example - Module registering content for a slot:
    from apps.core.slots import slots

    class SectionsConfig(AppConfig):
        def ready(self):
            slots.register(
                'sales.pos_header_start',
                template='sections/partials/table_selector.html',
                context_fn=self.get_tables_context,
                priority=5
            )

        def get_tables_context(self, request):
            return {
                'areas': Area.objects.filter(is_active=True),
                'tables': Table.objects.filter(is_active=True),
            }
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Tuple
from django.template.loader import render_to_string
from django.template import TemplateDoesNotExist

logger = logging.getLogger(__name__)


class SlotRegistry:
    """
    Central registry for UI slots.

    Slots allow modules to inject UI components into templates of other
    modules without direct coupling. When a module is deactivated, its
    slot content is simply not rendered.
    """

    def __init__(self):
        # {slot_name: [(priority, module_id, template, context_fn, condition_fn), ...]}
        self._slots: Dict[str, List[Tuple[int, str, str, Optional[Callable], Optional[Callable]]]] = {}

    def register(
        self,
        slot_name: str,
        template: str,
        context_fn: Callable = None,
        condition_fn: Callable = None,
        priority: int = 10,
        module_id: str = None
    ) -> None:
        """
        Register content to be rendered in a slot.

        Args:
            slot_name: Name of the slot (convention: 'module.slot_location')
            template: Path to the template to render
            context_fn: Optional function that returns extra context dict.
                        Signature: context_fn(request) -> dict
            condition_fn: Optional function that determines if slot should render.
                          Signature: condition_fn(request) -> bool
            priority: Render order (lower = earlier, default 10)
            module_id: Identifier of the registering module

        Example:
            slots.register(
                'sales.pos_header_start',
                template='sections/partials/table_selector.html',
                context_fn=lambda req: {'tables': Table.objects.all()},
                condition_fn=lambda req: req.user.has_perm('sections.view_table'),
                priority=5,
                module_id='sections'
            )
        """
        if slot_name not in self._slots:
            self._slots[slot_name] = []

        if module_id is None:
            # Try to infer from template path
            module_id = template.split('/')[0] if '/' in template else 'unknown'

        self._slots[slot_name].append((
            priority,
            module_id,
            template,
            context_fn,
            condition_fn
        ))
        self._slots[slot_name].sort(key=lambda x: x[0])

        logger.debug(
            f"Slot registered: {slot_name} <- {module_id}:{template} (priority {priority})"
        )

    def unregister(
        self,
        slot_name: str,
        template: str = None,
        module_id: str = None
    ) -> int:
        """
        Remove slot registration(s).

        Args:
            slot_name: Name of the slot
            template: Specific template to remove
            module_id: Remove all registrations from this module

        Returns:
            Number of registrations removed
        """
        if slot_name not in self._slots:
            return 0

        original_count = len(self._slots[slot_name])

        if template is not None:
            self._slots[slot_name] = [
                entry for entry in self._slots[slot_name]
                if entry[2] != template
            ]
        elif module_id is not None:
            self._slots[slot_name] = [
                entry for entry in self._slots[slot_name]
                if entry[1] != module_id
            ]

        return original_count - len(self._slots[slot_name])

    def get_slot_content(
        self,
        slot_name: str,
        request=None,
        context: dict = None
    ) -> List[Dict[str, Any]]:
        """
        Get list of content entries for a slot.

        This is used by the template tag to gather what needs to be rendered.

        Args:
            slot_name: Name of the slot
            request: The current request (for context_fn and condition_fn)
            context: Additional context from the template

        Returns:
            List of dicts with 'template' and 'context' keys
        """
        if slot_name not in self._slots:
            return []

        results = []
        base_context = context or {}

        for priority, module_id, template, context_fn, condition_fn in self._slots[slot_name]:
            # Check condition
            if condition_fn is not None:
                try:
                    if not condition_fn(request):
                        continue
                except Exception as e:
                    logger.warning(
                        f"Slot condition error for '{slot_name}' "
                        f"(module: {module_id}): {e}"
                    )
                    continue

            # Build context
            extra_context = {}
            if context_fn is not None:
                try:
                    extra_context = context_fn(request) or {}
                except Exception as e:
                    logger.error(
                        f"Slot context error for '{slot_name}' "
                        f"(module: {module_id}): {e}",
                        exc_info=True
                    )
                    continue

            results.append({
                'template': template,
                'context': {**base_context, **extra_context},
                'module_id': module_id,
                'priority': priority,
            })

        return results

    def render_slot(
        self,
        slot_name: str,
        request=None,
        context: dict = None
    ) -> str:
        """
        Render all content for a slot and return combined HTML.

        Args:
            slot_name: Name of the slot
            request: The current request
            context: Additional context from the template

        Returns:
            Combined HTML string from all slot content
        """
        content_list = self.get_slot_content(slot_name, request, context)

        if not content_list:
            return ''

        rendered_parts = []

        for entry in content_list:
            try:
                html = render_to_string(
                    entry['template'],
                    entry['context'],
                    request=request
                )
                rendered_parts.append(html)
            except TemplateDoesNotExist:
                logger.error(
                    f"Slot template not found: {entry['template']} "
                    f"(slot: {slot_name}, module: {entry['module_id']})"
                )
            except Exception as e:
                logger.error(
                    f"Slot render error for '{slot_name}' "
                    f"(module: {entry['module_id']}): {e}",
                    exc_info=True
                )

        return '\n'.join(rendered_parts)

    def has_content(self, slot_name: str) -> bool:
        """Check if any content is registered for a slot."""
        return slot_name in self._slots and len(self._slots[slot_name]) > 0

    def get_registered_slots(self) -> Dict[str, List[Dict]]:
        """
        Get information about all registered slots.

        Returns:
            Dict mapping slot names to lists of registration info
        """
        return {
            name: [
                {
                    'priority': p,
                    'module': m,
                    'template': t,
                    'has_context_fn': cf is not None,
                    'has_condition_fn': cond is not None,
                }
                for p, m, t, cf, cond in entries
            ]
            for name, entries in self._slots.items()
        }

    def clear_module_slots(self, module_id: str) -> int:
        """
        Remove all slots registered by a specific module.

        Useful when a module is deactivated.

        Args:
            module_id: The module identifier

        Returns:
            Number of registrations removed
        """
        total_removed = 0

        for slot_name in list(self._slots.keys()):
            total_removed += self.unregister(slot_name, module_id=module_id)

        logger.info(f"Cleared {total_removed} slots for module '{module_id}'")
        return total_removed

    def clear_all(self) -> None:
        """Clear all registered slots. Use with caution (mainly for testing)."""
        self._slots.clear()
        logger.warning("All slots cleared")


# ==========================================================================
# GLOBAL INSTANCE
# ==========================================================================

slots = SlotRegistry()


# ==========================================================================
# DECORATOR FOR CONVENIENCE
# ==========================================================================

def slot(slot_name: str, priority: int = 10, condition_fn: Callable = None):
    """
    Decorator to register a function that provides context for a slot.

    The decorated function should return a dict with 'template' and
    optionally 'context'.

    Example:
        @slot('sales.pos_header_start', priority=5)
        def table_selector_slot(request):
            return {
                'template': 'sections/partials/table_selector.html',
                'context': {'tables': Table.objects.all()}
            }
    """
    def decorator(func: Callable) -> Callable:
        def context_fn(request):
            result = func(request)
            return result.get('context', {})

        # Extract template from first call or require it in return
        # This is a simplified approach - the function must return template
        def register_on_first_call():
            # We need to call the function once to get the template
            # This is not ideal but works for simple cases
            pass

        # For now, just return the function - actual registration
        # should be done in AppConfig.ready()
        func._slot_name = slot_name
        func._slot_priority = priority
        func._slot_condition = condition_fn
        return func

    return decorator


# ==========================================================================
# STANDARD SLOT NAMES (Documentation)
# ==========================================================================

"""
Standard slot naming convention: '{module}.{location}'

SALES MODULE SLOTS (POS):
- sales.pos_header_start     Before search bar
- sales.pos_header_end       After cart button
- sales.pos_sidebar_left     Left sidebar (floor plan, schedule)
- sales.pos_sidebar_right    Right sidebar (if not cart)
- sales.pos_cart_header      Top of cart (table info, customer)
- sales.pos_cart_item        After each cart item (item actions)
- sales.pos_cart_footer      Bottom of cart before totals
- sales.pos_totals_before    Before subtotal line
- sales.pos_totals_after     After total line (tips, donations)
- sales.pos_payment_methods  Additional payment method buttons
- sales.pos_checkout_modal   Inside checkout modal

CUSTOMERS MODULE SLOTS:
- customers.list_toolbar     Toolbar in customer list
- customers.list_filters     Filter section
- customers.card_header      Header of customer card (badges)
- customers.card_actions     Action buttons on card
- customers.detail_tabs      Additional tabs in detail view
- customers.detail_sidebar   Sidebar in detail view

INVENTORY MODULE SLOTS:
- inventory.list_toolbar     Toolbar in product list
- inventory.list_filters     Filter section
- inventory.card_badge       Badge on product card (promo, low stock)
- inventory.detail_tabs      Additional tabs in detail view

INVOICING MODULE SLOTS:
- invoicing.header           Invoice header area
- invoicing.footer           Invoice footer area
- invoicing.line_extra       Extra info per line item
- invoicing.actions          Action buttons

SECTIONS MODULE SLOTS:
- sections.floor_overlay     Overlay on floor plan
- sections.table_card_badge  Badge on table card
- sections.table_actions     Actions for selected table
"""
