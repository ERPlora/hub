# An API key's permissions move from four modes to read, create, update and delete, per app or on every app ("*").
# What a key could do is what it can do: ``full`` is every action on every app, ``read`` reading every app, ``write``
# creating, updating and deleting on every app, and per app the same app by app. The mode leaves the model and stays in
# the database, empty for the keys made after, for the code of before that still runs while the deploy migrates; a
# later deploy drops it. Going back gives every key a mode again, never more than it could do.

from django.db import migrations, models

EVERYTHING = ["read", "create", "update", "delete"]
WRITING = ["create", "update", "delete"]
OF_A_MODE = {"full": EVERYTHING, "read": ["read"], "write": WRITING}


def _actions(kinds) -> list[str]:
    kinds = set(kinds) if isinstance(kinds, list) else set()
    return [action for action in EVERYTHING if action in kinds or (action != "read" and "write" in kinds)]


def _kinds(actions) -> list[str]:
    actions = set(actions) if isinstance(actions, list) else set()
    return [kind for kind, needs in (("read", {"read"}), ("write", set(WRITING))) if needs <= actions]


def to_actions(apps, schema_editor):
    ApiKey = apps.get_model("base", "ApiKey")
    for key in ApiKey.objects.using(schema_editor.connection.alias).all():
        if key.mode in OF_A_MODE:
            key.scopes = {"*": OF_A_MODE[key.mode]}
        else:
            scopes = key.scopes if isinstance(key.scopes, dict) else {}
            key.scopes = {app: actions for app, kinds in scopes.items() if (actions := _actions(kinds))}
        key.save(update_fields=["scopes"])


def to_modes(apps, schema_editor):
    ApiKey = apps.get_model("base", "ApiKey")
    by_kinds = {("read", "write"): "full", ("read",): "read", ("write",): "write"}
    for key in ApiKey.objects.using(schema_editor.connection.alias).all():
        scopes = key.scopes if isinstance(key.scopes, dict) else {}
        everywhere = by_kinds.get(tuple(_kinds(scopes.get("*"))))
        if everywhere:
            key.mode, key.scopes = everywhere, {}
        else:
            key.mode = "per_app"
            key.scopes = {app: kinds for app, actions in scopes.items() if app != "*" and (kinds := _kinds(actions))}
        key.save(update_fields=["mode", "scopes"])


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0026_api_key_owner"),
    ]

    operations = [
        migrations.AlterField(
            model_name="apikey",
            name="mode",
            field=models.CharField(
                blank=True,
                choices=[("full", "Full access"), ("read", "Read only"), ("write", "Write only"), ("per_app", "Per app")],
                max_length=8,
                null=True,
                verbose_name="what it may do",
            ),
        ),
        migrations.RunPython(to_actions, to_modes),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveConstraint(model_name="apikey", name="base_apikey_mode"),
                migrations.RemoveField(model_name="apikey", name="mode"),
            ],
        ),
        migrations.AlterField(
            model_name="apikey",
            name="scopes",
            field=models.JSONField(blank=True, default=dict, verbose_name="what it may do"),
        ),
    ]
