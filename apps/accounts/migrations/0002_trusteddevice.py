import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='TrustedDevice',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('hub_id', models.UUIDField(blank=True, db_index=True, editable=False, help_text='Hub this record belongs to (for multi-tenancy)', null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('created_by', models.UUIDField(blank=True, help_text='UUID of the user who created this record', null=True)),
                ('updated_by', models.UUIDField(blank=True, help_text='UUID of the user who last updated this record', null=True)),
                ('is_deleted', models.BooleanField(db_index=True, default=False, help_text='Soft delete flag - record is hidden but not removed')),
                ('deleted_at', models.DateTimeField(blank=True, help_text='Timestamp when record was soft deleted', null=True)),
                ('device_token', models.CharField(help_text='Opaque token stored in browser localStorage', max_length=128, unique=True)),
                ('device_name', models.CharField(blank=True, help_text="User-friendly name (e.g., 'Chrome on MacBook Pro')", max_length=255)),
                ('user_agent', models.TextField(blank=True, help_text='Browser User-Agent at time of registration')),
                ('last_used', models.DateTimeField(auto_now=True)),
                ('expires_at', models.DateTimeField(help_text='Device trust expires after this date')),
                ('is_revoked', models.BooleanField(default=False, help_text='Admin or user manually revoked trust')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='trusted_devices', to='accounts.localuser')),
            ],
            options={
                'verbose_name': 'Trusted Device',
                'verbose_name_plural': 'Trusted Devices',
                'db_table': 'accounts_trusted_devices',
                'ordering': ['-last_used'],
            },
        ),
        migrations.AddIndex(
            model_name='trusteddevice',
            index=models.Index(fields=['hub_id', 'user'], name='idx_trusted_device_hub_user'),
        ),
    ]
