# Tenancy W10, expand: the creator of a task and the author of a comment hang from the person in the business's own
# database (``base.HubUser``), never from control's user, which no hub's database holds. The same four steps as
# ``staff/0004_hub_users``, the code of before alive all along: the new columns ``*_hub_user_id``, nullable; filled from
# the old ones in phase 1's shared database (a hub's own has none to fill); the old fields out of the state, their
# columns kept, nullable, without their key to ``auth_user``; the new links take the fields' names. The contract, a
# later deploy's, drops the old columns (``base/tests/test_migration_safety.py``).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models, router

#: The local copy of an erplora.com account (``base.services.SAAS_USERNAME_PREFIX``).
SAAS_PREFIX = "saas:"
#: ``(model, old column)`` of every link to control's users.
OLD_LINKS = (("task", "created_by_id"), ("comment", "author_id"),)


def account_id(username: str):
    if not username.startswith(SAAS_PREFIX):
        return None
    try:
        return uuid.UUID(username.removeprefix(SAAS_PREFIX))
    except ValueError:
        return None


def link_hub_users(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)
    if not router.allow_migrate_model(schema_editor.connection.alias, User):
        # A hub's own database: no control users, and no old links to fill.
        return
    HubUser = apps.get_model("base", "HubUser")
    linked = [
        (apps.get_model("task", "task"), "created_by", "created_by_hub_user"),
        (apps.get_model("task", "comment"), "author", "author_hub_user"),
    ]
    user_ids = set()
    for model, old, _new in linked:
        user_ids |= set(
            model.objects.using(schema_editor.connection.alias)
            .filter(**{f"{old}__isnull": False})
            .values_list(f"{old}_id", flat=True)
        )
    for user in User.objects.using(schema_editor.connection.alias).filter(pk__in=user_ids):
        person, _made = HubUser.objects.using(schema_editor.connection.alias).get_or_create(
            username=user.username,
            defaults={
                "account_id": account_id(user.username),
                "name": f"{user.first_name} {user.last_name}".strip()[:150],
                "email": user.email,
                "is_active": user.is_active,
            },
        )
        for model, old, new in linked:
            model.objects.using(schema_editor.connection.alias).filter(**{f"{old}_id": user.pk}).update(**{new: person})


def drop_keys_to_control_users(apps, schema_editor):
    """The old columns' keys to ``auth_user``, where the database has them (phase 1's shared one)."""
    users = apps.get_model(settings.AUTH_USER_MODEL)._meta.db_table
    connection = schema_editor.connection
    for model_name, column in OLD_LINKS:
        table = apps.get_model("task", model_name)._meta.db_table
        with connection.cursor() as cursor:
            constraints = connection.introspection.get_constraints(cursor, table)
        for name, details in constraints.items():
            if details["foreign_key"] and details["foreign_key"][0] == users and details["columns"] == [column]:
                schema_editor.execute(
                    f"ALTER TABLE {schema_editor.quote_name(table)} DROP CONSTRAINT {schema_editor.quote_name(name)}"
                )


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
        migrations.RunPython(link_hub_users, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name='task', name='created_by'),
                migrations.RemoveField(model_name='comment', name='author'),
            ],
            database_operations=[migrations.RunPython(drop_keys_to_control_users, migrations.RunPython.noop)],
        ),
        migrations.RenameField(model_name='task', old_name='created_by_hub_user', new_name='created_by'),
        migrations.RenameField(model_name='comment', old_name='author_hub_user', new_name='author'),
    ]
