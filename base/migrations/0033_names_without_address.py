# erplora.com names an account without a name by its address, and the Hub kept it as the person's name: on control's
# copy of the account, on the business's person and on «My profile», which copies it when it is first saved. A
# colleague's address only reaches whoever sees the team's contact details, so each keeps what goes before the «@», as
# an account is named from now on when it enters. Only a bare address is cut: a person's name keeps theirs. Backwards,
# nothing changes: the address is kept nowhere to give it back.

from django.db import migrations
from django.db.models import F, Func, Value

#: What was kept for an account without a name: its address, alone.
ADDRESS = r"^[^@\s]+@[^@\s]+$"


def _cut(schema_editor, model, field: str) -> None:
    rows = model.objects.using(schema_editor.connection.alias).filter(**{f"{field}__regex": ADDRESS})
    rows.update(**{field: Func(F(field), Value("@"), Value(1), function="split_part")})


def accounts_without_address(apps, schema_editor):
    _cut(schema_editor, apps.get_model("auth", "User"), "first_name")


def people_without_address(apps, schema_editor):
    _cut(schema_editor, apps.get_model("base", "HubUser"), "name")
    _cut(schema_editor, apps.get_model("base", "Profile"), "first_name")


class Migration(migrations.Migration):

    dependencies = [
        ("base", "0032_approval_by_role"),
    ]

    operations = [
        # The hint makes base.tenancy.router run it on control's database, where the accounts live.
        migrations.RunPython(accounts_without_address, migrations.RunPython.noop, hints={"model_name": "membership"}),
        migrations.RunPython(people_without_address, migrations.RunPython.noop, hints={"model_name": "profile"}),
    ]
