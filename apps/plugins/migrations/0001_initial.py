# Generated migration for plugins app
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
            name='Plugin',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('plugin_id', models.CharField(max_length=100, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('description', models.TextField(blank=True)),
                ('version', models.CharField(max_length=50)),
                ('author', models.CharField(blank=True, max_length=255)),
                ('icon', models.CharField(default='extension-puzzle-outline', max_length=50)),
                ('category', models.CharField(default='general', max_length=50)),
                ('is_installed', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
                ('install_path', models.CharField(blank=True, max_length=500)),
                ('menu_label', models.CharField(blank=True, max_length=100)),
                ('menu_icon', models.CharField(blank=True, max_length=50)),
                ('menu_order', models.IntegerField(default=100)),
                ('show_in_menu', models.BooleanField(default=True)),
                ('main_url', models.CharField(blank=True, max_length=200)),
                ('installed_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'Plugin',
                'verbose_name_plural': 'Plugins',
                'ordering': ['menu_order', 'name'],
                'db_table': 'core_plugin',
            },
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=database_operations,
            state_operations=state_operations,
        )
    ]
