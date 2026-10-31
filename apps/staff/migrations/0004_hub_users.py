# Tenancy W10, expand: a staff record and its approval hang from the person in the business's own database
# (``base.HubUser``), never from control's user, which no hub's database holds (a key between two databases does not
# exist). In four steps, the code of before alive all along:
#
# 1. the new columns ``hub_user_id`` and ``approved_by_hub_user_id``, nullable, keyed to ``base_hubuser``;
# 2. filled from the old ones in phase 1's shared database, each control user with their own ``HubUser``; a hub's own
#    database has no control users and no old links to fill;
# 3. the old fields leave the state; their columns stay, nullable as they were, for the code of before during the
#    deploy, without their key to ``auth_user`` (control may delete a user they still name);
# 4. the new links take the fields' names (``user``, ``approved_by``), their columns kept, and «one user, one live
#    record» moves onto ``hub_user_id``.
#
# The contract, a later deploy's, drops the old columns (``base/tests/test_migration_safety.py``, ``ACCEPTED``).

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models, router

#: The local copy of an erplora.com account (``base.services.SAAS_USERNAME_PREFIX``).
SAAS_PREFIX = "saas:"
#: ``(model, old column)`` of every link to control's users.
OLD_LINKS = (("member", "user_id"), ("timeoff", "approved_by_id"))


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
    Member = apps.get_model("staff", "Member")
    TimeOff = apps.get_model("staff", "TimeOff")
    linked = [
        (Member, "user", "hub_user"),
        (TimeOff, "approved_by", "approved_by_hub_user"),
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
        table = apps.get_model("staff", model_name)._meta.db_table
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
        migrations.RunPython(link_hub_users, migrations.RunPython.noop),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(model_name='member', name='staff_member_user_unique'),
                migrations.RemoveField(model_name='member', name='user'),
                migrations.RemoveField(model_name='timeoff', name='approved_by'),
            ],
            database_operations=[migrations.RunPython(drop_keys_to_control_users, migrations.RunPython.noop)],
        ),
        migrations.RenameField(model_name='member', old_name='hub_user', new_name='user'),
        migrations.RenameField(model_name='timeoff', old_name='approved_by_hub_user', new_name='approved_by'),
        migrations.AddConstraint(
            model_name='member',
            constraint=models.UniqueConstraint(condition=models.Q(('user__isnull', False), models.Q(('status', 'terminated'), _negated=True)), fields=('user',), name='staff_member_hub_user_unique'),
        ),
    ]
