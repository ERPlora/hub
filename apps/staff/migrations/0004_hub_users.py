# Expand: a staff record and its approval hang from the person in the business's own database (``base.HubUser``), never
# from control's user, which no hub's database holds (a key between two databases does not exist). In three steps, the
# code of before alive all along:
#
# 1. the new columns ``hub_user_id`` and ``approved_by_hub_user_id``, nullable, keyed to ``base_hubuser``;
# 2. the old fields leave the state; their columns stay, nullable and without a key as they were, for the code of
#    before during the deploy;
# 3. the new links take the fields' names (``user``, ``approved_by``), their columns kept, and «one user, one live
#    record» moves onto ``hub_user_id``.
#
# A hub's own database has no control users to fill the new links from. The contract, a later deploy's, drops the old
# columns (``base/tests/test_migration_safety.py``, ``ACCEPTED``).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0020_hub_user'),
        ('staff', '0003_hourly_rate_verbose_name'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='member',
            name='hub_user',
            field=models.ForeignKey(blank=True, db_column='hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='staff_members', to='base.hubuser', verbose_name='user'),
        ),
        migrations.AddField(
            model_name='timeoff',
            name='approved_by_hub_user',
            field=models.ForeignKey(blank=True, db_column='approved_by_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base.hubuser', verbose_name='approved by'),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(model_name='member', name='staff_member_user_unique'),
                migrations.RemoveField(model_name='member', name='user'),
                migrations.RemoveField(model_name='timeoff', name='approved_by'),
            ],
        ),
        migrations.RenameField(model_name='member', old_name='hub_user', new_name='user'),
        migrations.RenameField(model_name='timeoff', old_name='approved_by_hub_user', new_name='approved_by'),
        migrations.AddConstraint(
            model_name='member',
            constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False), models.Q(('status', 'terminated'), _negated=True)), fields=('user',), name='staff_member_hub_user_unique'),
        ),
    ]
