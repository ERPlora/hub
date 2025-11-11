# Generated migration for accounts app
# This migration creates tables (they were deleted by core.0008)

from django.db import migrations, models
import django.contrib.auth.hashers


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('core', '0007_hubconfig_currency'),
    ]

    # Create tables (they were deleted by core.0008)
    operations = [
        migrations.CreateModel(
            name='LocalUser',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cloud_user_id', models.IntegerField(unique=True)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('name', models.CharField(max_length=255)),
                ('pin_hash', models.CharField(max_length=255)),
                ('role', models.CharField(default='cashier', max_length=50)),
                ('is_active', models.BooleanField(default=True)),
                ('language', models.CharField(default='en', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('last_login', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name': 'Local User',
                'verbose_name_plural': 'Local Users',
                'ordering': ['name'],
                'db_table': 'core_localuser',
            },
        ),
    ]
