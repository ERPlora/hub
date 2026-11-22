# Whose a shift is: who opened and who closed it by their username, which does not change when they rename. The shifts
# kept before only have the label the screen shows (a name, else an e-mail, else a username): each gets the one person
# of the business whose name, e-mail or username that label is; a label of nobody or of several people stays empty, and
# only whoever sees every shift sees it. Backwards, the two columns go and nothing else changes.

from django.db import migrations, models


def who_opened_and_closed(apps, schema_editor):
    hub_users = apps.get_model("base", "HubUser").objects.using(schema_editor.connection.alias)
    sessions = apps.get_model("cash_register", "Session").objects.using(schema_editor.connection.alias)
    people: dict[str, set[str]] = {}
    for username, name, email in hub_users.values_list("username", "name", "email"):
        for label in {username, name, email} - {""}:
            people.setdefault(label, set()).add(username)
    for by, username in (("opened_by", "opened_by_username"), ("closed_by", "closed_by_username")):
        for label in sessions.exclude(**{by: ""}).order_by().values_list(by, flat=True).distinct():
            named = people.get(label, set())
            if len(named) == 1:
                sessions.filter(**{by: label}).update(**{username: next(iter(named))})


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0020_hub_user"),
        ("cash_register", "0002_auto_close_time_callable_default"),
    ]

    operations = [
        migrations.AddField(
            model_name="session",
            name="opened_by_username",
            field=models.CharField(blank=True, db_default="", default="", max_length=150, verbose_name="opener's account"),
        ),
        migrations.AddField(
            model_name="session",
            name="closed_by_username",
            field=models.CharField(blank=True, db_default="", default="", max_length=150, verbose_name="closer's account"),
        ),
        migrations.RunPython(who_opened_and_closed, migrations.RunPython.noop),
    ]
