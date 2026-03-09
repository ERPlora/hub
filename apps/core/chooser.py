"""
ERPlora Generic Chooser

A reusable HTMX + Alpine.js component for selecting model instances across modules.
Provides search, pagination, and modal-based selection for any Django model.

Configuration in modules (module.py or a dedicated chooser config):

    # In module's apps.py
    from apps.core.chooser import chooser_registry

    class InventoryConfig(AppConfig):
        def ready(self):
            from inventory.models import Product, Category

            chooser_registry.register(Product, {
                'search_fields': ['name', 'sku', 'barcode'],
                'display_fields': ['name', 'sku', 'price'],
                'icon': 'cube-outline',
                'label': 'Products',
                'filters': {
                    'category': {'field': 'category', 'label': 'Category'},
                    'is_active': {'field': 'is_active', 'label': 'Active'},
                },
                'order_by': ['name'],
                'per_page': 20,
                'image_field': 'image',
            })

Usage in templates:
    {% load chooser %}

    {# Single select #}
    {% chooser "inventory.product" name="product_id" value=form.product_id.value %}

    {# Multiple select #}
    {% chooser "inventory.product" name="products" multiple=True value=selected_ids %}

    {# With filters #}
    {% chooser "customers.customer" name="customer_id" %}

Usage in views (for HTMX endpoints):
    from apps.core.chooser import chooser_registry

    def my_view(request):
        config = chooser_registry.get('inventory.product')
        qs = config.get_queryset(request)
        ...
"""

import logging
from typing import Any, Callable, Dict, List, Optional, Type

from django.db import models
from django.db.models import Q

logger = logging.getLogger(__name__)


class ChooserConfig:
    """Configuration for a model's chooser."""

    def __init__(
        self,
        model: Type[models.Model],
        search_fields: List[str],
        display_fields: Optional[List[str]] = None,
        icon: str = 'search-outline',
        label: Optional[str] = None,
        filters: Optional[Dict[str, dict]] = None,
        order_by: Optional[List[str]] = None,
        per_page: int = 20,
        image_field: Optional[str] = None,
        subtitle_field: Optional[str] = None,
        queryset_fn: Optional[Callable] = None,
        display_fn: Optional[Callable] = None,
    ):
        self.model = model
        self.search_fields = search_fields
        self.display_fields = display_fields or ['__str__']
        self.icon = icon
        self.label = label or model._meta.verbose_name_plural.capitalize()
        self.filters = filters or {}
        self.order_by = order_by or ['pk']
        self.per_page = per_page
        self.image_field = image_field
        self.subtitle_field = subtitle_field
        self.queryset_fn = queryset_fn
        self.display_fn = display_fn

    @property
    def key(self) -> str:
        return f"{self.model._meta.app_label}.{self.model._meta.model_name}"

    def get_queryset(self, request=None) -> models.QuerySet:
        """Get base queryset, optionally customized via queryset_fn."""
        if self.queryset_fn:
            return self.queryset_fn(request)
        qs = self.model.objects.all()
        if hasattr(self.model, 'is_deleted'):
            qs = qs.filter(is_deleted=False)
        if hasattr(self.model, 'is_active'):
            qs = qs.filter(is_active=True)
        return qs.order_by(*self.order_by)

    def search(self, queryset: models.QuerySet, query: str) -> models.QuerySet:
        """Apply search across configured search_fields."""
        if not query or not self.search_fields:
            return queryset

        q = Q()
        for field in self.search_fields:
            q |= Q(**{f"{field}__icontains": query})

        return queryset.filter(q)

    def apply_filters(self, queryset: models.QuerySet, filter_values: dict) -> models.QuerySet:
        """Apply filter values to queryset."""
        for key, value in filter_values.items():
            if key in self.filters and value:
                field = self.filters[key]['field']
                queryset = queryset.filter(**{field: value})
        return queryset

    def get_display_value(self, obj) -> str:
        """Get display string for an object."""
        if self.display_fn:
            return self.display_fn(obj)
        return str(obj)

    def get_subtitle(self, obj) -> str:
        """Get subtitle string for an object."""
        if self.subtitle_field:
            return str(getattr(obj, self.subtitle_field, ''))
        return ''

    def get_image_url(self, obj) -> Optional[str]:
        """Get image URL for an object."""
        if not self.image_field:
            return None
        field = getattr(obj, self.image_field, None)
        if field and hasattr(field, 'url'):
            return field.url
        return None

    def get_filter_choices(self, filter_key: str, request=None) -> list:
        """Get available choices for a filter."""
        if filter_key not in self.filters:
            return []

        filter_config = self.filters[filter_key]
        field_name = filter_config['field']

        # Get the field from the model
        try:
            field = self.model._meta.get_field(field_name)
        except Exception:
            return []

        # ForeignKey — get related model's objects
        if isinstance(field, models.ForeignKey):
            related_model = field.related_model
            qs = related_model.objects.all()
            if hasattr(related_model, 'is_deleted'):
                qs = qs.filter(is_deleted=False)
            return [{'value': str(obj.pk), 'label': str(obj)} for obj in qs[:100]]

        # BooleanField
        if isinstance(field, models.BooleanField):
            return [
                {'value': 'true', 'label': str(filter_config.get('label', field_name))},
                {'value': 'false', 'label': f"Not {filter_config.get('label', field_name)}"},
            ]

        # CharField with choices
        if hasattr(field, 'choices') and field.choices:
            return [{'value': str(v), 'label': str(l)} for v, l in field.choices]

        return []


class ChooserRegistry:
    """Central registry for model chooser configurations."""

    def __init__(self):
        self._configs: Dict[str, ChooserConfig] = {}

    def register(self, model: Type[models.Model], config: dict) -> ChooserConfig:
        """
        Register a model for the chooser system.

        Args:
            model: Django model class
            config: Configuration dict (see ChooserConfig.__init__ for options)

        Returns:
            The created ChooserConfig
        """
        chooser_config = ChooserConfig(model=model, **config)
        self._configs[chooser_config.key] = chooser_config
        logger.debug(f"Chooser registered: {chooser_config.key}")
        return chooser_config

    def get(self, key: str) -> Optional[ChooserConfig]:
        """
        Get chooser config by key (e.g., 'inventory.product').

        Args:
            key: Model key in format 'app_label.model_name'

        Returns:
            ChooserConfig or None
        """
        return self._configs.get(key)

    def get_all(self) -> Dict[str, ChooserConfig]:
        """Get all registered chooser configs."""
        return dict(self._configs)

    def unregister(self, key: str) -> bool:
        """Unregister a model from the chooser system."""
        return self._configs.pop(key, None) is not None

    def clear_module(self, module_id: str) -> int:
        """Remove all chooser configs from a specific module."""
        keys_to_remove = [
            k for k in self._configs if k.startswith(f"{module_id}.")
        ]
        for key in keys_to_remove:
            del self._configs[key]
        return len(keys_to_remove)

    def clear_all(self) -> None:
        """Clear all registered configs. Mainly for testing."""
        self._configs.clear()


# Global instance
chooser_registry = ChooserRegistry()
