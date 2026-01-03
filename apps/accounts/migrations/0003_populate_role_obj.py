"""
Data migration to populate role_obj from legacy role field.

This migration assigns the appropriate Role object to each LocalUser
based on their legacy 'role' field value.
"""
from django.db import migrations
from django.db.models import Q


def populate_role_obj(apps, schema_editor):
    """
    Assign role_obj to all LocalUsers based on their legacy role field.

    Maps:
    - 'admin' -> Role(name='admin')
    - 'manager' -> Role(name='manager')
    - 'employee' -> Role(name='employee')
    """
    LocalUser = apps.get_model('accounts', 'LocalUser')
    Role = apps.get_model('accounts', 'Role')

    # Get all users without role_obj using raw SQL to avoid model field issues
    db_alias = schema_editor.connection.alias

    # Get all users without role_obj
    users_to_update = LocalUser.objects.using(db_alias).filter(
        role_obj__isnull=True,
    ).exclude(is_deleted=True)

    for user in users_to_update:
        # Find matching role by name
        role_name = user.role if user.role else 'employee'
        try:
            role = Role.objects.using(db_alias).filter(
                name=role_name,
                hub_id=user.hub_id,
            ).exclude(is_deleted=True).first()

            if role:
                user.role_obj = role
                user.save(update_fields=['role_obj'])
            else:
                # If role doesn't exist, try to find 'employee' role as fallback
                role = Role.objects.using(db_alias).filter(
                    name='employee',
                    hub_id=user.hub_id,
                ).exclude(is_deleted=True).first()

                if role:
                    user.role_obj = role
                    user.save(update_fields=['role_obj'])
                # No roles exist yet for this hub, skip
        except Exception:
            # Skip on any error
            pass


def reverse_populate_role_obj(apps, schema_editor):
    """
    Reverse migration - clear role_obj (data will still be in legacy role field).
    """
    LocalUser = apps.get_model('accounts', 'LocalUser')
    db_alias = schema_editor.connection.alias
    LocalUser.objects.using(db_alias).filter(role_obj__isnull=False).update(role_obj=None)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_add_permission_role_models'),
    ]

    operations = [
        migrations.RunPython(
            populate_role_obj,
            reverse_populate_role_obj,
        ),
    ]
