# A hub's database is made by steps (round 2026-10-30 of PLAN-DB, S2a; PLAN-DB §6): the statuses of its preparation
# (creating, migrating, seeding) and of S2b's way out (archiving, dropping), and what a failed preparation keeps to be
# retried (attempts, last_error, next_attempt_at). A cluster gets its limit of hubs (max_hubs, 0 = none) and the secret
# of its own roles (secret_name, empty = the environment's). Every new column has its default in the database or is
# nullable, so the code of before inserts without them during the deploy (base/tests/test_migration_safety.py); the new
# statuses only widen the choices (no constraint in the database).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('control', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='cluster',
            name='max_hubs',
            field=models.PositiveIntegerField(db_default=0, default=0, help_text='0 = no limit.', verbose_name='hub limit'),
        ),
        migrations.AddField(
            model_name='cluster',
            name='secret_name',
            field=models.CharField(blank=True, db_default='', default='', help_text="The Secrets Manager secret with this cluster's roles; empty, the environment's own.", max_length=255, verbose_name='credentials secret'),
        ),
        migrations.AddField(
            model_name='hub',
            name='attempts',
            field=models.PositiveIntegerField(db_default=0, default=0, verbose_name='attempts'),
        ),
        migrations.AddField(
            model_name='hub',
            name='last_error',
            field=models.TextField(blank=True, db_default='', default='', verbose_name='last error'),
        ),
        migrations.AddField(
            model_name='hub',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='next attempt'),
        ),
        migrations.AlterField(
            model_name='hub',
            name='status',
            field=models.CharField(choices=[('requested', 'Requested'), ('creating', 'Creating'), ('migrating', 'Migrating'), ('seeding', 'Seeding'), ('ready', 'Ready'), ('failed', 'Failed'), ('cancelled', 'Cancelled'), ('expired', 'Expired'), ('purged', 'Purged'), ('archiving', 'Archiving'), ('dropping', 'Dropping')], default='requested', max_length=16, verbose_name='status'),
        ),
    ]
