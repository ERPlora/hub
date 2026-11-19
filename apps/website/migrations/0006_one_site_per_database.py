from django.db import migrations, models
from django.db.models import Q


def _business(apps, alias: str):
    """The business this database is, from its identity row; ``None`` for a database that names none."""
    identity = apps.get_model("base", "HubIdentity").objects.using(alias).first()
    return identity.hub_id if identity else None


def drop_rows_of_other_businesses(apps, schema_editor):
    """Rows naming another business were copied in when the shared tables were split; no read ever matched them.
    The originals stay in control's database, under the tables' retired names."""
    alias = schema_editor.connection.alias
    business = _business(apps, alias)
    if business is None:
        return
    for name in ("Site", "Image"):
        apps.get_model("website", name).objects.using(alias).exclude(hub_id=business).delete()


def name_the_business_again(apps, schema_editor):
    """The code of before finds its rows by their business: the ones made after this migration get it back."""
    alias = schema_editor.connection.alias
    business = _business(apps, alias)
    if business is None:
        return
    for name in ("Site", "Image"):
        apps.get_model("website", name).objects.using(alias).filter(hub_id=None).update(hub_id=business)


class Migration(migrations.Migration):
    """The business's database holds its one site, so its rows stop naming their business. The column leaves the state
    only: the code of before still writes it while the deploy migrates (``base/tests/test_migration_safety.py``), and
    from now on new rows leave it empty."""

    dependencies = [
        ("website", "0005_image_filename"),
        ("base", "0007_registry_moves_to_control"),
    ]

    operations = [
        migrations.AlterField(
            model_name="site",
            name="hub_id",
            field=models.UUIDField(editable=False, null=True, unique=True, verbose_name="hub"),
        ),
        migrations.AlterField(
            model_name="image",
            name="hub_id",
            field=models.UUIDField(db_index=True, editable=False, null=True, verbose_name="hub"),
        ),
        migrations.RunPython(drop_rows_of_other_businesses, name_the_business_again),
        migrations.AddField(
            model_name="site",
            name="singleton",
            field=models.BooleanField(db_default=True, default=True, editable=False, verbose_name="single row"),
        ),
        migrations.AddConstraint(
            model_name="site",
            constraint=models.UniqueConstraint(fields=("singleton",), name="website_site_single_row"),
        ),
        migrations.AddConstraint(
            model_name="site",
            constraint=models.CheckConstraint(condition=Q(singleton=True), name="website_site_singleton"),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.RemoveField(model_name="site", name="hub_id"),
                migrations.RemoveField(model_name="image", name="hub_id"),
            ]
        ),
    ]
