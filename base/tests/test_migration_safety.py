"""Migrations the code of before survives (PLAN-DB §7, expand/contract; README «Migraciones que conviven…»).

The deploy (``.github/scripts/ecs-deploy.sh``) runs ``hub-migrate`` before it replaces the services, and a
rollback puts the code of before back on the migrated schema: for a while, the code of before writes to the
tables of the new one. A column added ``NOT NULL`` with only a Python ``default`` breaks it: Django fills the
rows with that default and then drops it from the column, so an INSERT of the code of before, which does not
know the column, fails with ``null value in column … violates not-null constraint`` until the deploy ends (seen
in ``kitchen/0004``, hub#115). The column needs its default in the database (``db_default``), or it is added
``null=True`` and made ``NOT NULL`` in a later deploy (contract).

Every migration the project loads is checked (``base``, ``live``, the apps and Django's own): ``hub-migrate``
applies all of them. In phase 1 they all live in the control database; with the tenancy of phase 2 the same
migrations run in every hub database, under the same deploy.
"""

import pytest
from django.db import migrations, models
from django.db.migrations.loader import MigrationLoader
from django.db.models import NOT_PROVIDED

# Already in production before this rule (hub ``main``@00654ae, deployed on 2026-10-21): the deploys that
# carried them are over and an applied migration is never edited, so the rule cannot reach them. A new entry
# here needs its reason in its own PR; an entry that no longer breaks the rule fails the test below.
ACCEPTED = {
    ("attendance", "0002_correction_author", "correction", "created_by_name"),
    ("attendance", "0002_correction_author", "correction", "is_system"),
    ("flow", "0005_flow_recipe", "flow", "recipe"),
    ("flow", "0005_flow_recipe", "flow", "recipe_digest"),
    ("invoice", "0002_net_prices_and_short_numbers", "invoiceline", "discount_amount"),
    ("invoice", "0004_platform_ref", "invoice", "language"),
    ("payment", "0002_payment_trail", "payment", "approved_by"),
    ("payment", "0002_payment_trail", "payment", "cancelled_by"),
    ("sale", "0004_voucher_lines", "orderline", "voucher_name"),
    ("sale", "0004_voucher_lines", "saleline", "voucher_name"),
    ("sale", "0006_fiscal_document", "refund", "invoice_number"),
    ("sale", "0006_fiscal_document", "refund", "invoice_status"),
    ("sale", "0006_fiscal_document", "refund", "invoice_type"),
    ("sale", "0006_fiscal_document", "sale", "invoice_number"),
    ("sale", "0006_fiscal_document", "sale", "invoice_status"),
    ("sale", "0006_fiscal_document", "sale", "invoice_type"),
    ("sale", "0006_fiscal_document", "sale", "void_invoice_number"),
    ("sale", "0006_fiscal_document", "sale", "void_invoice_status"),
    ("service", "0002_redemption_states", "redemption", "ended_by"),
    ("service", "0002_redemption_states", "redemption", "return_reason"),
    ("service", "0002_redemption_states", "redemption", "status"),
    ("tax", "0003_category_and_alias_is_active", "taxalias", "is_active"),
    ("tax", "0003_category_and_alias_is_active", "taxcategory", "is_active"),
    ("verifactu", "0003_live_paid", "config", "hub_status"),
    ("verifactu", "0003_live_paid", "config", "live_paid"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "conversation", "contact_search"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "conversation", "erase_phone"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "conversation", "erase_status"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "conversation", "last_message_kind"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "message", "template_variables"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "body_examples"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "buttons"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "delete_state"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "header_format"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "submit_error"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "submit_error_code"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "submit_state"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "template", "supported"),
    ("whatsapp_inbox", "0004_message_reply_id", "message", "reply_id"),
    ("whatsapp_inbox", "0005_channel_per_business", "channel", "host"),
    ("whatsapp_inbox", "0006_templates_per_business", "template", "host"),
    ("whatsapp_inbox", "0007_deliveries_per_business", "conversation", "erase_host"),
    ("whatsapp_inbox", "0007_deliveries_per_business", "message", "host"),
}


def _database_operations(operations):
    """The operations that change the database: those of a ``SeparateDatabaseAndState`` included."""
    for operation in operations:
        if isinstance(operation, migrations.SeparateDatabaseAndState):
            yield from _database_operations(operation.database_operations)
        else:
            yield operation


def not_null_columns_without_db_default(migration) -> list[tuple[str, str, str, str]]:
    """``(app, migration, model, field)`` of each column the migration adds to an existing table as ``NOT NULL``
    with no default in the database. A table created by the same migration is new: no code of before writes to it.
    """
    operations = list(_database_operations(migration.operations))
    created = {op.name_lower for op in operations if isinstance(op, migrations.CreateModel)}
    return [
        (migration.app_label, migration.name, op.model_name_lower, op.name_lower)
        for op in operations
        if isinstance(op, migrations.AddField)
        and op.model_name_lower not in created
        and not op.field.null
        and op.field.db_default is NOT_PROVIDED
        and not op.field.many_to_many
        and not isinstance(op.field, models.GeneratedField)
    ]


def _found() -> set[tuple[str, str, str, str]]:
    loader = MigrationLoader(None, ignore_no_migrations=True)
    return {
        entry
        for migration in loader.disk_migrations.values()
        for entry in not_null_columns_without_db_default(migration)
    }


def test_no_migration_adds_a_not_null_column_without_a_database_default():
    new = sorted(_found() - ACCEPTED)
    assert not new, "\n".join(
        [
            "These migrations add a NOT NULL column with no default in the database: during the deploy, the code "
            "of before inserts rows without it and Postgres refuses them (not-null violation). Give the field "
            "db_default=… (keep default=… too), or add it null=True and make it NOT NULL in a later deploy:"
        ]
        + [f"  {app}/{name}: {model}.{field}" for app, name, model, field in new]
    )


def test_every_accepted_migration_still_adds_such_a_column():
    """The list is alive: an entry whose migration or field is gone, or that now has its ``db_default``, goes."""
    stale = sorted(ACCEPTED - _found())
    assert not stale, "Remove from ACCEPTED, they no longer break the rule: " + ", ".join(
        f"{app}/{name}: {model}.{field}" for app, name, model, field in stale
    )


def _migration(*operations):
    migration = migrations.Migration("0002_change", "shop")
    migration.operations = list(operations)
    return migration


def _add(field, model="product", name="label"):
    return migrations.AddField(model_name=model, name=name, field=field)


@pytest.mark.parametrize(
    "field",
    [
        models.CharField(max_length=20, default=""),
        models.BooleanField(default=False),
        models.JSONField(default=list),
        models.ForeignKey("shop.Brand", on_delete=models.CASCADE),
    ],
    ids=["python-default", "boolean", "json", "foreign-key"],
)
def test_a_not_null_column_with_only_a_python_default_breaks_the_rule(field):
    assert not_null_columns_without_db_default(_migration(_add(field))) == [("shop", "0002_change", "product", "label")]


@pytest.mark.parametrize(
    "field",
    [
        models.CharField(max_length=20, default="", db_default=""),
        models.CharField(max_length=20, null=True),
        models.ManyToManyField("shop.Brand"),
        models.GeneratedField(expression=models.Value(1), output_field=models.IntegerField(), db_persist=True),
    ],
    ids=["db-default", "nullable", "many-to-many", "generated"],
)
def test_a_column_the_code_of_before_can_skip_keeps_the_rule(field):
    assert not_null_columns_without_db_default(_migration(_add(field))) == []


def test_a_column_of_a_table_created_by_the_same_migration_keeps_the_rule():
    migration = _migration(
        migrations.CreateModel(name="Product", fields=[("id", models.UUIDField(primary_key=True))]),
        _add(models.ForeignKey("shop.Brand", on_delete=models.CASCADE), name="brand"),
    )

    assert not_null_columns_without_db_default(migration) == []


def test_a_column_added_through_separate_database_and_state_counts_only_in_the_database():
    field = models.CharField(max_length=20, default="")
    in_database = migrations.SeparateDatabaseAndState(database_operations=[_add(field)])
    in_state = migrations.SeparateDatabaseAndState(state_operations=[_add(field)])

    assert not_null_columns_without_db_default(_migration(in_database)) == [("shop", "0002_change", "product", "label")]
    assert not_null_columns_without_db_default(_migration(in_state)) == []
