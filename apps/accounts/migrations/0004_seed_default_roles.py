"""
Data migration to seed default roles (admin, manager, employee, viewer).

Runs once during deployment. Resolves hub_id from settings.HUB_ID (Docker),
HubConfig (Cloud SSO), or generates a deterministic UUID for local dev.
"""

import uuid as uuid_lib

from django.conf import settings
from django.db import migrations


# Role definitions — must match PermissionService.DEFAULT_ROLES
DEFAULT_ROLES = [
    {
        'name': 'admin',
        'display_name': 'Administrator',
        'description': 'Full system access. Can manage all settings, users, and data.',
        'is_system': True,
        'wildcards': ['*'],
    },
    {
        'name': 'manager',
        'display_name': 'Manager',
        'description': 'Management access. CRUD on main modules, reports, and team oversight.',
        'is_system': True,
        'wildcards': [
            'inventory.*',
            'sales.*',
            'customers.*',
            'cash_register.*',
            'invoicing.*',
            'reports.*',
        ],
    },
    {
        'name': 'employee',
        'display_name': 'Employee',
        'description': 'Basic access. Day-to-day operations like sales and viewing products.',
        'is_system': True,
        'wildcards': [
            'inventory.view_*',
            'sales.view_*',
            'sales.add_sale',
            'sales.process_payment',
            'customers.view_*',
        ],
    },
    {
        'name': 'viewer',
        'display_name': 'Viewer',
        'description': 'Read-only access. Can view all data but cannot create, edit, or delete anything.',
        'is_system': True,
        'wildcards': [
            '*.view_*',
        ],
    },
]


def get_hub_id():
    """Resolve hub_id from settings, HubConfig, or generate a fallback."""
    # 1. Docker env var
    hub_id = getattr(settings, 'HUB_ID', None)
    if hub_id:
        return str(hub_id)

    # 2. HubConfig singleton
    try:
        from apps.configuration.models import HubConfig
        hub_config = HubConfig.get_config()
        if hub_config.hub_id:
            return str(hub_config.hub_id)
    except Exception:
        pass

    # 3. Deterministic fallback for local dev
    return str(uuid_lib.uuid5(uuid_lib.NAMESPACE_DNS, 'erplora.local'))


def seed_roles(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    RolePermission = apps.get_model('accounts', 'RolePermission')

    hub_id = get_hub_id()

    for role_config in DEFAULT_ROLES:
        role, _ = Role.objects.update_or_create(
            hub_id=hub_id,
            name=role_config['name'],
            is_deleted=False,
            defaults={
                'display_name': role_config['display_name'],
                'description': role_config['description'],
                'is_system': role_config['is_system'],
                'source': 'basic',
            },
        )

        for wildcard in role_config.get('wildcards', []):
            RolePermission.objects.get_or_create(
                hub_id=hub_id,
                role=role,
                wildcard=wildcard,
                defaults={'permission': None},
            )


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_add_source_to_role'),
    ]

    operations = [
        migrations.RunPython(seed_roles, migrations.RunPython.noop),
    ]
