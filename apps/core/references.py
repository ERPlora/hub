"""
ERPlora Reference Index

Automatically discovers all models that reference a given object via ForeignKey,
OneToOneField, or ManyToManyField. Shows users where an object is used before
they delete it.

Usage in views:
    from apps.core.references import get_references

    def delete_product(request, pk):
        product = get_object_or_404(Product, pk=pk)
        refs = get_references(product)

        if refs['total_count'] > 0:
            # Show confirmation with references
            return render(request, 'core/references/confirm_delete.html', {
                'object': product,
                'references': refs,
            })

        product.delete()
        return redirect('inventory:products')

Usage in templates:
    {% load references %}

    {% get_references object as refs %}
    {% if refs.total_count > 0 %}
        <p>This item is used in {{ refs.total_count }} places:</p>
        {% for group in refs.groups %}
            <p>{{ group.label }}: {{ group.count }}</p>
        {% endfor %}
    {% endif %}

The system works by introspecting Django's model registry to find all
ForeignKey/OneToOne/M2M fields that point to the target model, then
querying each one to count (and optionally list) related objects.
"""

import logging
from typing import Any, Dict, List, Optional

from django.apps import apps
from django.db import models
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Models to skip when scanning for references (internal Django models)
SKIP_MODELS = {
    'admin.LogEntry',
    'contenttypes.ContentType',
    'sessions.Session',
    'auth.Permission',
    'auth.Group',
}

# Cache for model relationship map (built once, reused)
_relationship_cache: Dict[str, List[dict]] = {}


def _build_relationship_map(target_model: type) -> List[dict]:
    """
    Find all models with ForeignKey/OneToOne/M2M pointing to target_model.

    Returns list of dicts:
        {
            'model': ModelClass,
            'field': field_instance,
            'field_name': str,
            'accessor': str,  # reverse accessor name
            'relation_type': 'fk' | 'o2o' | 'm2m',
        }
    """
    cache_key = f"{target_model._meta.app_label}.{target_model._meta.model_name}"

    if cache_key in _relationship_cache:
        return _relationship_cache[cache_key]

    relations = []

    for model in apps.get_models():
        model_label = f"{model._meta.app_label}.{model._meta.model_name}"

        # Skip internal Django models
        if f"{model._meta.app_label}.{model.__name__}" in SKIP_MODELS:
            continue

        # Skip migration-related or abstract models
        if model._meta.abstract or model._meta.proxy:
            continue

        for field in model._meta.get_fields():
            # ForeignKey or OneToOneField pointing to target
            if isinstance(field, (models.ForeignKey, models.OneToOneField)):
                if field.related_model == target_model:
                    relations.append({
                        'model': model,
                        'field': field,
                        'field_name': field.name,
                        'accessor': field.name,
                        'relation_type': 'o2o' if isinstance(field, models.OneToOneField) else 'fk',
                        'model_label': model_label,
                    })

            # ManyToManyField pointing to target
            elif isinstance(field, models.ManyToManyField):
                if field.related_model == target_model:
                    relations.append({
                        'model': model,
                        'field': field,
                        'field_name': field.name,
                        'accessor': field.name,
                        'relation_type': 'm2m',
                        'model_label': model_label,
                    })

    _relationship_cache[cache_key] = relations
    return relations


def get_references(
    obj: models.Model,
    include_deleted: bool = False,
    max_items: int = 5,
) -> Dict[str, Any]:
    """
    Get all objects that reference the given object.

    Args:
        obj: The model instance to find references for.
        include_deleted: If True, include soft-deleted referencing objects.
        max_items: Max number of items to return per group (for display).

    Returns:
        {
            'total_count': int,
            'groups': [
                {
                    'model': ModelClass,
                    'model_name': str,      # e.g. 'SaleItem'
                    'app_label': str,       # e.g. 'sales'
                    'label': str,           # Human-readable, e.g. 'Sale Items'
                    'field_name': str,      # e.g. 'product'
                    'relation_type': str,   # 'fk', 'o2o', 'm2m'
                    'count': int,
                    'items': list,          # First max_items objects
                    'has_more': bool,
                    'on_delete': str,       # 'CASCADE', 'SET_NULL', 'PROTECT', etc.
                },
                ...
            ],
            'has_protected': bool,   # True if any PROTECT references exist
            'cascade_count': int,    # Number of objects that would be CASCADE deleted
            'set_null_count': int,   # Number of objects that would be SET_NULL'd
        }
    """
    target_model = type(obj)
    relations = _build_relationship_map(target_model)

    groups = []
    total_count = 0
    has_protected = False
    cascade_count = 0
    set_null_count = 0

    for rel in relations:
        model = rel['model']
        field = rel['field']

        try:
            # Build queryset for related objects
            if rel['relation_type'] == 'm2m':
                qs = model.objects.filter(**{rel['field_name']: obj})
            else:
                qs = model.objects.filter(**{rel['field_name']: obj})

            # Exclude soft-deleted if the model supports it
            if not include_deleted and hasattr(model, 'is_deleted'):
                qs = qs.filter(is_deleted=False)

            count = qs.count()

            if count == 0:
                continue

            # Determine on_delete behavior
            on_delete_str = 'unknown'
            if rel['relation_type'] in ('fk', 'o2o'):
                on_delete = field.remote_field.on_delete
                on_delete_map = {
                    models.CASCADE: 'CASCADE',
                    models.PROTECT: 'PROTECT',
                    models.SET_NULL: 'SET_NULL',
                    models.SET_DEFAULT: 'SET_DEFAULT',
                    models.DO_NOTHING: 'DO_NOTHING',
                }
                on_delete_str = on_delete_map.get(on_delete, 'SET')

                if on_delete == models.PROTECT:
                    has_protected = True
                elif on_delete == models.CASCADE:
                    cascade_count += count
                elif on_delete == models.SET_NULL:
                    set_null_count += count
            else:
                on_delete_str = 'CLEAR'  # M2M just removes the association

            # Get sample items for display
            items = list(qs[:max_items])

            # Human-readable label from model verbose_name_plural
            label = model._meta.verbose_name_plural.capitalize()

            groups.append({
                'model': model,
                'model_name': model.__name__,
                'app_label': model._meta.app_label,
                'label': label,
                'field_name': rel['field_name'],
                'relation_type': rel['relation_type'],
                'count': count,
                'items': items,
                'has_more': count > max_items,
                'on_delete': on_delete_str,
            })

            total_count += count

        except Exception as e:
            logger.warning(
                f"Error scanning references for {target_model.__name__} "
                f"in {model.__name__}.{rel['field_name']}: {e}"
            )
            continue

    # Sort groups: PROTECT first, then CASCADE, then by count descending
    priority = {'PROTECT': 0, 'CASCADE': 1, 'SET_NULL': 2, 'CLEAR': 3}
    groups.sort(key=lambda g: (priority.get(g['on_delete'], 9), -g['count']))

    return {
        'total_count': total_count,
        'groups': groups,
        'has_protected': has_protected,
        'cascade_count': cascade_count,
        'set_null_count': set_null_count,
    }


def can_delete(obj: models.Model) -> tuple[bool, Dict[str, Any]]:
    """
    Check if an object can be safely deleted.

    Returns:
        (can_delete: bool, references: dict)

    If can_delete is False, references['has_protected'] will be True,
    meaning at least one PROTECT relationship prevents deletion.

    Usage:
        ok, refs = can_delete(product)
        if not ok:
            messages.error(request, f"Cannot delete: used in {refs['total_count']} places")
    """
    refs = get_references(obj)
    return not refs['has_protected'], refs


def clear_cache(model: type = None) -> None:
    """
    Clear the relationship cache.

    Call this if models change at runtime (e.g., module activation/deactivation).

    Args:
        model: Clear cache for specific model, or all if None.
    """
    if model is None:
        _relationship_cache.clear()
    else:
        cache_key = f"{model._meta.app_label}.{model._meta.model_name}"
        _relationship_cache.pop(cache_key, None)
