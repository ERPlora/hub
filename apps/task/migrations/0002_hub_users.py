# Expand: the creator of a task and the author of a comment hang from the person in the business's own database
# (``base.HubUser``), never from control's user, which no hub's database holds. The same three steps as
# ``staff/0004_hub_users``, the code of before alive all along: the new columns ``*_hub_user_id``, nullable; the old
# fields out of the state, their columns kept, nullable and without a key; the new links take the fields' names. The
# contract, a later deploy's, drops the old columns (``base/tests/test_migration_safety.py``).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0020_hub_user'),
        ('task', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='task',
            name='created_by_hub_user',
            field=models.ForeignKey(blank=True, db_column='created_by_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base.hubuser', verbose_name='created by'),
        ),
        migrations.AddField(
            model_name='comment',
            name='author_hub_user',
            field=models.ForeignKey(blank=True, db_column='author_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base.hubuser', verbose_name='author'),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='task', name='created_by'),
                migrations.RemoveField(model_name='comment', name='author'),
            ],
        ),
        migrations.RenameField(model_name='task', old_name='created_by_hub_user', new_name='created_by'),
        migrations.RenameField(model_name='comment', old_name='author_hub_user', new_name='author'),
    ]
