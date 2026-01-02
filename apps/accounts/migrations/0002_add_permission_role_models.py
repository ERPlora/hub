# Generated migration for Permission, Role, RolePermission models

import uuid
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial_uuid'),
    ]

    operations = [
        # Create Permission model
        migrations.CreateModel(
            name='Permission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('hub_id', models.UUIDField(db_index=True, help_text='Hub this record belongs to')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.UUIDField(blank=True, null=True)),
                ('updated_by', models.UUIDField(blank=True, null=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('codename', models.CharField(help_text="Permission codename (e.g., 'inventory.view_product')", max_length=100)),
                ('name', models.CharField(help_text='Human-readable name', max_length=255)),
                ('description', models.TextField(blank=True, help_text='Detailed description of what this permission allows')),
                ('module_id', models.CharField(help_text='Module that defines this permission', max_length=50)),
            ],
            options={
                'verbose_name': 'Permission',
                'verbose_name_plural': 'Permissions',
                'db_table': 'accounts_permission',
                'ordering': ['module_id', 'codename'],
            },
        ),
        # Create Role model
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('hub_id', models.UUIDField(db_index=True, help_text='Hub this record belongs to')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.UUIDField(blank=True, null=True)),
                ('updated_by', models.UUIDField(blank=True, null=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(help_text="Role name (e.g., 'admin', 'manager', 'cashier')", max_length=50)),
                ('display_name', models.CharField(help_text='Human-readable name for UI', max_length=100)),
                ('description', models.TextField(blank=True, help_text='Role description')),
                ('is_system', models.BooleanField(default=False, help_text='System roles cannot be deleted (admin, manager, employee)')),
                ('is_active', models.BooleanField(default=True, help_text='Inactive roles cannot be assigned to users')),
            ],
            options={
                'verbose_name': 'Role',
                'verbose_name_plural': 'Roles',
                'db_table': 'accounts_role',
                'ordering': ['name'],
            },
        ),
        # Create RolePermission through model
        migrations.CreateModel(
            name='RolePermission',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('hub_id', models.UUIDField(db_index=True, help_text='Hub this record belongs to')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.UUIDField(blank=True, null=True)),
                ('updated_by', models.UUIDField(blank=True, null=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False)),
                ('deleted_at', models.DateTimeField(blank=True, null=True)),
                ('wildcard', models.CharField(blank=True, help_text="Wildcard pattern (e.g., '*', 'inventory.*')", max_length=100)),
                ('permission', models.ForeignKey(blank=True, help_text='Direct permission link (null if using wildcard)', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='permission_roles', to='accounts.permission')),
                ('role', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='role_permissions', to='accounts.role')),
            ],
            options={
                'verbose_name': 'Role Permission',
                'verbose_name_plural': 'Role Permissions',
                'db_table': 'accounts_rolepermission',
            },
        ),
        # Add role_obj FK to LocalUser
        migrations.AddField(
            model_name='localuser',
            name='role_obj',
            field=models.ForeignKey(blank=True, help_text="Role object for granular permissions. If null, uses legacy 'role' field.", null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='users', to='accounts.role'),
        ),
        # Add extra_permissions M2M to LocalUser
        migrations.AddField(
            model_name='localuser',
            name='extra_permissions',
            field=models.ManyToManyField(blank=True, help_text='Additional permissions beyond role (for special cases)', related_name='users_extra', to='accounts.permission'),
        ),
        # Add M2M for Role.permissions (through RolePermission)
        migrations.AddField(
            model_name='role',
            name='permissions',
            field=models.ManyToManyField(blank=True, related_name='roles', through='accounts.RolePermission', to='accounts.permission'),
        ),
        # Add constraints for Permission
        migrations.AddConstraint(
            model_name='permission',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False)), fields=('hub_id', 'codename'), name='unique_permission_codename_per_hub'),
        ),
        # Add index for Permission
        migrations.AddIndex(
            model_name='permission',
            index=models.Index(fields=['hub_id', 'module_id'], name='accounts_pe_hub_id_c8f8a6_idx'),
        ),
        # Add constraint for Role
        migrations.AddConstraint(
            model_name='role',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False)), fields=('hub_id', 'name'), name='unique_role_name_per_hub'),
        ),
        # Add constraints for RolePermission
        migrations.AddConstraint(
            model_name='rolepermission',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False), ('permission__isnull', False)), fields=('hub_id', 'role', 'permission'), name='unique_role_permission'),
        ),
        migrations.AddConstraint(
            model_name='rolepermission',
            constraint=models.UniqueConstraint(condition=models.Q(('is_deleted', False), ('wildcard__gt', '')), fields=('hub_id', 'role', 'wildcard'), name='unique_role_wildcard'),
        ),
    ]
