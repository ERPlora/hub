"""
Tests for ERPlora Slot System.

Tests the SlotRegistry class that provides dynamic UI injection points
for module communication.
"""
import pytest
from unittest.mock import MagicMock, patch
from django.template import TemplateDoesNotExist
from django.test import RequestFactory

from apps.core.slots import SlotRegistry, slots, slot


class TestSlotRegistryBasics:
    """Tests for basic slot registration and retrieval."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()
        self.factory = RequestFactory()

    def test_register_slot(self):
        """register adds slot content to registry."""
        self.registry.register(
            'test.slot',
            template='test/partial.html',
            module_id='test_module'
        )

        assert self.registry.has_content('test.slot')

    def test_register_slot_with_priority(self):
        """Slots are sorted by priority."""
        self.registry.register('test.slot', 'template_b.html', priority=20, module_id='b')
        self.registry.register('test.slot', 'template_a.html', priority=5, module_id='a')

        content = self.registry.get_slot_content('test.slot')

        assert len(content) == 2
        assert content[0]['template'] == 'template_a.html'
        assert content[1]['template'] == 'template_b.html'

    def test_register_slot_infers_module_id(self):
        """Module ID is inferred from template path."""
        self.registry.register('test.slot', template='loyalty/partials/badge.html')

        registered = self.registry.get_registered_slots()
        assert registered['test.slot'][0]['module'] == 'loyalty'

    def test_has_content_false_for_empty_slot(self):
        """has_content returns False for unregistered slots."""
        assert self.registry.has_content('nonexistent.slot') is False

    def test_get_slot_content_empty_for_unregistered(self):
        """get_slot_content returns empty list for unregistered slots."""
        content = self.registry.get_slot_content('nonexistent.slot')
        assert content == []


class TestSlotContextFunctions:
    """Tests for slot context functions."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()
        self.factory = RequestFactory()

    def test_context_fn_adds_to_context(self):
        """context_fn result is merged into slot context."""
        def get_extra_context(request):
            return {'extra_value': 42, 'user': 'test'}

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            context_fn=get_extra_context,
            module_id='test'
        )

        request = self.factory.get('/')
        content = self.registry.get_slot_content('test.slot', request=request)

        assert content[0]['context']['extra_value'] == 42
        assert content[0]['context']['user'] == 'test'

    def test_context_fn_receives_request(self):
        """context_fn receives the request object."""
        def get_context(request):
            return {'path': request.path}

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            context_fn=get_context,
            module_id='test'
        )

        request = self.factory.get('/dashboard/')
        content = self.registry.get_slot_content('test.slot', request=request)

        assert content[0]['context']['path'] == '/dashboard/'

    def test_context_fn_error_skips_slot(self):
        """Error in context_fn skips that slot content."""
        def failing_context(request):
            raise ValueError("Test error")

        def working_context(request):
            return {'value': 'works'}

        self.registry.register(
            'test.slot',
            template='test/fail.html',
            context_fn=failing_context,
            priority=1,
            module_id='failing'
        )
        self.registry.register(
            'test.slot',
            template='test/work.html',
            context_fn=working_context,
            priority=2,
            module_id='working'
        )

        request = self.factory.get('/')
        content = self.registry.get_slot_content('test.slot', request=request)

        # Only working slot should be included
        assert len(content) == 1
        assert content[0]['template'] == 'test/work.html'

    def test_base_context_is_preserved(self):
        """Base context is merged with context_fn result."""
        def get_extra(request):
            return {'extra': 'value'}

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            context_fn=get_extra,
            module_id='test'
        )

        request = self.factory.get('/')
        base_context = {'base_key': 'base_value'}
        content = self.registry.get_slot_content('test.slot', request, context=base_context)

        assert content[0]['context']['base_key'] == 'base_value'
        assert content[0]['context']['extra'] == 'value'


class TestSlotConditionFunctions:
    """Tests for slot condition functions."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()
        self.factory = RequestFactory()

    def test_condition_fn_true_includes_slot(self):
        """Slot is included when condition_fn returns True."""
        self.registry.register(
            'test.slot',
            template='test/partial.html',
            condition_fn=lambda req: True,
            module_id='test'
        )

        request = self.factory.get('/')
        content = self.registry.get_slot_content('test.slot', request=request)

        assert len(content) == 1

    def test_condition_fn_false_excludes_slot(self):
        """Slot is excluded when condition_fn returns False."""
        self.registry.register(
            'test.slot',
            template='test/partial.html',
            condition_fn=lambda req: False,
            module_id='test'
        )

        request = self.factory.get('/')
        content = self.registry.get_slot_content('test.slot', request=request)

        assert len(content) == 0

    def test_condition_fn_receives_request(self):
        """condition_fn receives the request object."""
        def check_permission(request):
            return request.user.is_authenticated if hasattr(request, 'user') else False

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            condition_fn=check_permission,
            module_id='test'
        )

        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=True)
        content = self.registry.get_slot_content('test.slot', request=request)

        assert len(content) == 1

    def test_condition_fn_error_skips_slot(self):
        """Error in condition_fn skips that slot."""
        def failing_condition(request):
            raise RuntimeError("Test error")

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            condition_fn=failing_condition,
            module_id='test'
        )

        request = self.factory.get('/')
        content = self.registry.get_slot_content('test.slot', request=request)

        assert len(content) == 0


class TestSlotRendering:
    """Tests for slot rendering."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()
        self.factory = RequestFactory()

    @patch('apps.core.slots.render_to_string')
    def test_render_slot_calls_render_to_string(self, mock_render):
        """render_slot uses render_to_string for each slot."""
        mock_render.return_value = '<div>content</div>'

        self.registry.register(
            'test.slot',
            template='test/partial.html',
            module_id='test'
        )

        request = self.factory.get('/')
        html = self.registry.render_slot('test.slot', request=request)

        mock_render.assert_called_once()
        assert html == '<div>content</div>'

    @patch('apps.core.slots.render_to_string')
    def test_render_slot_combines_multiple_templates(self, mock_render):
        """render_slot combines HTML from multiple templates."""
        mock_render.side_effect = ['<div>first</div>', '<div>second</div>']

        self.registry.register('test.slot', 'first.html', priority=1, module_id='a')
        self.registry.register('test.slot', 'second.html', priority=2, module_id='b')

        request = self.factory.get('/')
        html = self.registry.render_slot('test.slot', request=request)

        assert '<div>first</div>' in html
        assert '<div>second</div>' in html

    @patch('apps.core.slots.render_to_string')
    def test_render_slot_handles_template_not_found(self, mock_render):
        """render_slot handles missing templates gracefully."""
        mock_render.side_effect = TemplateDoesNotExist('missing.html')

        self.registry.register(
            'test.slot',
            template='missing.html',
            module_id='test'
        )

        request = self.factory.get('/')
        html = self.registry.render_slot('test.slot', request=request)

        # Should return empty, not raise
        assert html == ''

    @patch('apps.core.slots.render_to_string')
    def test_render_slot_continues_after_error(self, mock_render):
        """render_slot continues after render error."""
        def side_effect(template, context, request=None):
            if 'failing' in template:
                raise RuntimeError("Render error")
            return f'<div>{template}</div>'

        mock_render.side_effect = side_effect

        self.registry.register('test.slot', 'failing.html', priority=1, module_id='a')
        self.registry.register('test.slot', 'working.html', priority=2, module_id='b')

        request = self.factory.get('/')
        html = self.registry.render_slot('test.slot', request=request)

        assert 'working.html' in html

    def test_render_slot_empty_for_unregistered(self):
        """render_slot returns empty string for unregistered slot."""
        request = self.factory.get('/')
        html = self.registry.render_slot('nonexistent.slot', request=request)

        assert html == ''


class TestSlotUnregistration:
    """Tests for slot unregistration."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()

    def test_unregister_by_template(self):
        """unregister removes specific template."""
        self.registry.register('test.slot', 'a.html', module_id='a')
        self.registry.register('test.slot', 'b.html', module_id='b')

        removed = self.registry.unregister('test.slot', template='a.html')

        assert removed == 1
        content = self.registry.get_slot_content('test.slot')
        assert len(content) == 1
        assert content[0]['template'] == 'b.html'

    def test_unregister_by_module_id(self):
        """unregister removes all templates from module."""
        self.registry.register('test.slot', 'a.html', module_id='loyalty')
        self.registry.register('test.slot', 'b.html', module_id='loyalty')
        self.registry.register('test.slot', 'c.html', module_id='other')

        removed = self.registry.unregister('test.slot', module_id='loyalty')

        assert removed == 2
        content = self.registry.get_slot_content('test.slot')
        assert len(content) == 1
        assert content[0]['module_id'] == 'other'

    def test_unregister_nonexistent_slot(self):
        """unregister returns 0 for nonexistent slot."""
        removed = self.registry.unregister('nonexistent.slot', template='a.html')
        assert removed == 0


class TestSlotUtilities:
    """Tests for utility methods."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()

    def test_get_registered_slots(self):
        """get_registered_slots returns all registrations."""
        def my_context(req):
            return {}

        def my_condition(req):
            return True

        self.registry.register(
            'slot1',
            template='a.html',
            context_fn=my_context,
            condition_fn=my_condition,
            priority=5,
            module_id='mod1'
        )

        result = self.registry.get_registered_slots()

        assert 'slot1' in result
        assert len(result['slot1']) == 1
        assert result['slot1'][0]['template'] == 'a.html'
        assert result['slot1'][0]['priority'] == 5
        assert result['slot1'][0]['module'] == 'mod1'
        assert result['slot1'][0]['has_context_fn'] is True
        assert result['slot1'][0]['has_condition_fn'] is True

    def test_clear_module_slots(self):
        """clear_module_slots removes all slots from a module."""
        self.registry.register('slot1', 'a.html', module_id='loyalty')
        self.registry.register('slot2', 'b.html', module_id='loyalty')
        self.registry.register('slot1', 'c.html', module_id='other')

        removed = self.registry.clear_module_slots('loyalty')

        assert removed == 2
        assert not self.registry.has_content('slot2')

        # Other module's content remains
        content = self.registry.get_slot_content('slot1')
        assert len(content) == 1
        assert content[0]['module_id'] == 'other'

    def test_clear_all(self):
        """clear_all removes all registered slots."""
        self.registry.register('slot1', 'a.html', module_id='a')
        self.registry.register('slot2', 'b.html', module_id='b')

        self.registry.clear_all()

        assert not self.registry.has_content('slot1')
        assert not self.registry.has_content('slot2')


class TestGlobalSlotsInstance:
    """Tests for the global slots instance."""

    def setup_method(self):
        """Clear global slots before each test."""
        slots.clear_all()

    def teardown_method(self):
        """Clean up global slots after each test."""
        slots.clear_all()

    def test_global_slots_is_slot_registry(self):
        """Global slots is a SlotRegistry instance."""
        assert isinstance(slots, SlotRegistry)

    def test_global_slots_persists_registrations(self):
        """Global slots persists registrations."""
        slots.register('global.test', 'test.html', module_id='test')

        assert slots.has_content('global.test')


class TestRealWorldScenarios:
    """Integration tests with real-world usage patterns."""

    def setup_method(self):
        """Create a fresh registry for each test."""
        self.registry = SlotRegistry()
        self.factory = RequestFactory()

    @patch('apps.core.slots.render_to_string')
    def test_pos_header_with_multiple_modules(self, mock_render):
        """Simulate multiple modules injecting into POS header."""
        def render_template(template, context, request=None):
            if 'table' in template:
                return f'<button class="ux-button">Table {context.get("table_id", "?")}</button>'
            if 'loyalty' in template:
                return f'<span class="ux-badge">{context.get("points", 0)} pts</span>'
            return f'<div>{template}</div>'

        mock_render.side_effect = render_template

        # Sections module (HoReCa)
        def get_table_context(request):
            return {'table_id': request.session.get('table_id', 5)}

        def has_table_selected(request):
            return request.session.get('table_id') is not None

        self.registry.register(
            'sales.pos_header_start',
            template='sections/partials/table_selector.html',
            context_fn=get_table_context,
            condition_fn=has_table_selected,
            priority=5,
            module_id='sections'
        )

        # Loyalty module
        def get_loyalty_context(request):
            return {'points': 150, 'tier': 'Gold'}

        def has_customer(request):
            return request.session.get('customer_id') is not None

        self.registry.register(
            'sales.pos_header_start',
            template='loyalty/partials/points_badge.html',
            context_fn=get_loyalty_context,
            condition_fn=has_customer,
            priority=10,
            module_id='loyalty'
        )

        # Create request with session data
        request = self.factory.get('/pos/')
        request.session = {'table_id': 5, 'customer_id': 123}

        html = self.registry.render_slot('sales.pos_header_start', request=request)

        # Both modules should render
        assert 'Table 5' in html
        assert '150 pts' in html

    @patch('apps.core.slots.render_to_string')
    def test_conditional_slot_rendering(self, mock_render):
        """Slots with conditions only render when conditions are met."""
        mock_render.return_value = '<div>content</div>'

        # Only show for authenticated users
        self.registry.register(
            'test.slot',
            template='test.html',
            condition_fn=lambda req: getattr(req, 'user', None) and req.user.is_authenticated,
            module_id='test'
        )

        # Anonymous request
        request = self.factory.get('/')
        request.user = MagicMock(is_authenticated=False)
        html = self.registry.render_slot('test.slot', request=request)
        assert html == ''

        # Authenticated request
        request.user = MagicMock(is_authenticated=True)
        html = self.registry.render_slot('test.slot', request=request)
        assert html == '<div>content</div>'

    def test_module_deactivation_clears_slots(self):
        """When a module is deactivated, its slots are cleared."""
        self.registry.register('slot1', 'a.html', module_id='loyalty')
        self.registry.register('slot2', 'b.html', module_id='loyalty')
        self.registry.register('slot1', 'c.html', module_id='sales')

        # Deactivate loyalty
        self.registry.clear_module_slots('loyalty')

        # Verify loyalty slots are gone
        content1 = self.registry.get_slot_content('slot1')
        assert len(content1) == 1
        assert content1[0]['module_id'] == 'sales'

        content2 = self.registry.get_slot_content('slot2')
        assert len(content2) == 0
