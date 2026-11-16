# Expand: who a conversation is with, who sent a message from the Hub and who wrote a note hang from the person in the
# business's own database (``base.HubUser``), never from control's user, which no hub's database holds. The same three
# steps as ``staff/0004_hub_users``, the code of before alive all along: the new columns ``*_hub_user_id``, nullable;
# the old fields out of the state, their columns kept, nullable and without a key; the new links take the fields'
# names. The contract, a later deploy's, drops the old columns (``base/tests/test_migration_safety.py``).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('base', '0020_hub_user'),
        ('whatsapp_inbox', '0009_conversation_needs_attention'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='conversation',
            name='assigned_to_hub_user',
            field=models.ForeignKey(blank=True, db_column='assigned_to_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='whatsapp_conversations', to='base.hubuser', verbose_name='assigned to'),
        ),
        migrations.AddField(
            model_name='message',
            name='sent_by_hub_user',
            field=models.ForeignKey(blank=True, db_column='sent_by_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base.hubuser', verbose_name='sent by'),
        ),
        migrations.AddField(
            model_name='note',
            name='author_hub_user',
            field=models.ForeignKey(blank=True, db_column='author_hub_user_id', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='base.hubuser', verbose_name='author'),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='conversation', name='assigned_to'),
                migrations.RemoveField(model_name='message', name='sent_by'),
                migrations.RemoveField(model_name='note', name='author'),
            ],
        ),
        migrations.RenameField(model_name='conversation', old_name='assigned_to_hub_user', new_name='assigned_to'),
        migrations.RenameField(model_name='message', old_name='sent_by_hub_user', new_name='sent_by'),
        migrations.RenameField(model_name='note', old_name='author_hub_user', new_name='author'),
    ]
