"""
Data migration to create default system roles for all existing hubs.

Creates: admin, manager, employee, accountant, warehouse, cashier
with their corresponding wildcard permissions.
"""
from django.db import migrations


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
        'name': 'accountant',
        'display_name': 'Accountant',
        'description': 'Finance access. Invoicing, reports, and financial data.',
        'is_system': True,
        'wildcards': [
            'invoicing.*',
            'reports.*',
            'sales.view_*',
            'customers.view_*',
            'cash_register.view_*',
        ],
    },
    {
        'name': 'warehouse',
        'display_name': 'Warehouse',
        'description': 'Inventory management. Full inventory access, view sales.',
        'is_system': True,
        'wildcards': [
            'inventory.*',
            'sales.view_*',
        ],
    },
    {
        'name': 'cashier',
        'display_name': 'Cashier',
        'description': 'Point of sale access. Sales, cash register, and product viewing.',
        'is_system': True,
        'wildcards': [
            'sales.*',
            'cash_register.*',
            'inventory.view_*',
            'customers.view_*',
            'customers.add_*',
        ],
    },
]


def create_default_roles(apps, schema_editor):
    """Create default roles for all existing hubs."""
    Role = apps.get_model('accounts', 'Role')
    RolePermission = apps.get_model('accounts', 'RolePermission')
    LocalUser = apps.get_model('accounts', 'LocalUser')
    db_alias = schema_editor.connection.alias

    # Get all unique hub_ids from existing users
    hub_ids = (
        LocalUser.objects.using(db_alias)
        .exclude(hub_id__isnull=True)
        .values_list('hub_id', flat=True)
        .distinct()
    )

    for hub_id in hub_ids:
        for role_config in DEFAULT_ROLES:
            role, created = Role.objects.using(db_alias).get_or_create(
                hub_id=hub_id,
                name=role_config['name'],
                is_deleted=False,
                defaults={
                    'display_name': role_config['display_name'],
                    'description': role_config['description'],
                    'is_system': role_config['is_system'],
                },
            )

            if created:
                for wildcard in role_config.get('wildcards', []):
                    RolePermission.objects.using(db_alias).get_or_create(
                        hub_id=hub_id,
                        role=role,
                        wildcard=wildcard,
                        defaults={'permission': None},
                    )


def reverse_default_roles(apps, schema_editor):
    """Remove default system roles (only if they were created by this migration)."""
    Role = apps.get_model('accounts', 'Role')
    db_alias = schema_editor.connection.alias
    default_names = [r['name'] for r in DEFAULT_ROLES]
    Role.objects.using(db_alias).filter(
        name__in=default_names, is_system=True
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0005_rename_tables_plural'),
    ]

    operations = [
        migrations.RunPython(
            create_default_roles,
            reverse_default_roles,
        ),
    ]
