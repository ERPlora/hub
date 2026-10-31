# The copies of a hub's data and its nightly use (round 2026-10-30 of PLAN-DB, S2b): HubDump, HubUsageDaily, HubVisit,
# UsageRun and the reset asked on Hub. Expand: new tables and nullable columns only, so the code of before goes on
# writing the registry without them.

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0003_hubdue_lease_owner'),
    ]

    operations = [
        migrations.CreateModel(
            name='UsageRun',
            fields=[
                ('day', models.DateField(primary_key=True, serialize=False, verbose_name='day')),
                ('started_at', models.DateTimeField(verbose_name='started at')),
                ('finished_at', models.DateTimeField(blank=True, null=True, verbose_name='finished at')),
                ('hubs', models.PositiveIntegerField(default=0, verbose_name='hubs measured')),
            ],
            options={
                'verbose_name': 'nightly measurement',
                'verbose_name_plural': 'nightly measurements',
                'ordering': ['-day'],
            },
        ),
        migrations.AddField(
            model_name='hub',
            name='reset_requested_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='reset asked'),
        ),
        migrations.AddField(
            model_name='hub',
            name='reset_sections',
            field=models.JSONField(blank=True, null=True, verbose_name='reset'),
        ),
        migrations.CreateModel(
            name='HubVisit',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ('host', models.CharField(max_length=63, verbose_name='host')),
                ('day', models.DateField(verbose_name='day')),
                ('saas_user_id', models.CharField(max_length=64, verbose_name='SaaS account')),
            ],
            options={
                'verbose_name': 'daily entry',
                'verbose_name_plural': 'daily entries',
                'constraints': [models.UniqueConstraint(fields=('host', 'day', 'saas_user_id'), name='control_hubvisit_one_per_day')],
            },
        ),
        migrations.CreateModel(
            name='HubDump',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('reset', 'Before a reset'), ('offboarding', 'On leaving')], max_length=16, verbose_name='kind')),
                ('key', models.CharField(max_length=512, unique=True, verbose_name='key')),
                ('bytes', models.PositiveBigIntegerField(verbose_name='size (bytes)')),
                ('created_at', models.DateTimeField(verbose_name='made at')),
                ('requested_by', models.CharField(blank=True, default='', max_length=150, verbose_name='asked by')),
                ('hub', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='dumps', to='control.hub', verbose_name='hub')),
            ],
            options={
                'verbose_name': 'data copy',
                'verbose_name_plural': 'data copies',
                'ordering': ['-created_at', '-id'],
                'indexes': [models.Index(fields=['hub', '-created_at'], name='control_hubdump_hub_created')],
            },
        ),
        migrations.CreateModel(
            name='HubUsageDaily',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ('day', models.DateField(verbose_name='day')),
                ('db_bytes', models.PositiveBigIntegerField(default=0, verbose_name='database (bytes)')),
                ('s3_bytes', models.PositiveBigIntegerField(default=0, verbose_name='files (bytes)')),
                ('active_users_1d', models.PositiveIntegerField(default=0, verbose_name='people that day')),
                ('active_users_30d', models.PositiveIntegerField(default=0, verbose_name='people in 30 days')),
                ('measured_at', models.DateTimeField(verbose_name='measured at')),
                ('hub', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='usage', to='control.hub', verbose_name='hub')),
            ],
            options={
                'verbose_name': 'daily use of a hub',
                'verbose_name_plural': 'daily use of the hubs',
                'ordering': ['-day', 'hub_id'],
                'indexes': [models.Index(fields=['day', 'hub'], name='control_hubusagedaily_day_hub')],
                'constraints': [models.UniqueConstraint(fields=('hub', 'day'), name='control_hubusagedaily_one_per_day')],
            },
        ),
    ]
