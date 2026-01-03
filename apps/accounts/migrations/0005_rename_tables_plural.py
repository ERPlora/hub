# Migration to rename tables to plural form
# This aligns with the db_table changes in models.py

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0004_permission_description'),
    ]

    operations = [
        # Rename tables to plural
        migrations.AlterModelTable(
            name='permission',
            table='accounts_permissions',
        ),
        migrations.AlterModelTable(
            name='role',
            table='accounts_roles',
        ),
        migrations.AlterModelTable(
            name='rolepermission',
            table='accounts_role_permissions',
        ),
        migrations.AlterModelTable(
            name='localuser',
            table='accounts_local_users',
        ),
    ]
