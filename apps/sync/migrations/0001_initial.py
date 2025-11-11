# Generated migration for sync app
# This migration references existing tables from core app

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0007_hubconfig_currency'),
    ]

    # No database operations - tables already exist
    database_operations = []

    # Declare models in Django state
    state_operations = [
        migrations.CreateModel(
            name='TokenCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jwt_access_token', models.TextField(blank=True)),
                ('jwt_refresh_token', models.TextField(blank=True)),
                ('jwt_cached_at', models.DateTimeField(blank=True, null=True)),
                ('rsa_public_key', models.TextField(blank=True)),
                ('public_key_cached_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Token Cache',
                'verbose_name_plural': 'Token Cache',
                'db_table': 'core_tokencache',
            },
        ),
        migrations.CreateModel(
            name='SyncQueue',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('operation_type', models.CharField(choices=[('user_register', 'Register User'), ('user_remove', 'Remove User'), ('user_update', 'Update User'), ('plugin_install', 'Plugin Install'), ('plugin_uninstall', 'Plugin Uninstall'), ('sale_sync', 'Sale Sync')], max_length=50)),
                ('endpoint', models.CharField(max_length=500)),
                ('method', models.CharField(default='POST', max_length=10)),
                ('payload', models.JSONField(default=dict)),
                ('headers', models.JSONField(default=dict)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('processing', 'Processing'), ('completed', 'Completed'), ('failed', 'Failed')], default='pending', max_length=20)),
                ('retry_count', models.IntegerField(default=0)),
                ('max_retries', models.IntegerField(default=5)),
                ('last_error', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('next_retry_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Sync Queue Item',
                'verbose_name_plural': 'Sync Queue',
                'ordering': ['created_at'],
                'db_table': 'core_syncqueue',
            },
        ),
        migrations.AddIndex(
            model_name='syncqueue',
            index=models.Index(fields=['status', 'next_retry_at'], name='core_syncqu_status_6f8e25_idx'),
        ),
        migrations.AddIndex(
            model_name='syncqueue',
            index=models.Index(fields=['operation_type', 'status'], name='core_syncqu_operati_f2c3e6_idx'),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        )
    ]
