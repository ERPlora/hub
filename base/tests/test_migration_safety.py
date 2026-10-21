"""Migrations the code of before survives (PLAN-DB §7, expand/contract; README «Migraciones que conviven…»).

The deploy (``.github/scripts/ecs-deploy.sh``) runs ``hub-migrate`` before it replaces the services, and a
rollback puts the code of before back on the migrated schema: for a while, the code of before reads and writes
the tables of the new one. Three kinds of operation break it:

- a column added ``NOT NULL`` with only a Python ``default``: Django fills the rows with that default and then
  drops it from the column, so an INSERT of the code of before, which does not know the column, fails with
  ``null value in column … violates not-null constraint`` until the deploy ends (seen in ``kitchen/0004``,
  hub#115). It needs its default in the database (``db_default``), or ``null=True`` and NOT NULL later;
- a column or a table dropped or renamed (``RemoveField``, ``DeleteModel``, ``RenameField``, ``RenameModel``,
  ``AlterModelTable``): the code of before still names it. It leaves the state first
  (``SeparateDatabaseAndState``) and the database in a later deploy, or keeps its name (``db_column``/``db_table``);
- a column narrowed by ``AlterField`` (NOT NULL, shorter, another type, a new CHECK): the code of before still
  writes what the old one took. It is narrowed in a later deploy, once no code writes such values.

The step of a change that only a later deploy may run (the contract) is the one the code cannot tell apart: it
goes in ``ACCEPTED`` with the PR of its first step as the reason.

Every migration the project loads is checked (``base``, ``live``, the apps and Django's own): ``hub-migrate``
applies all of them. In phase 1 they all live in the control database; with the tenancy of phase 2 the same
migrations run in every hub database, under the same deploy.
"""

import math
from typing import NamedTuple

import pytest
from django.db import connection, migrations, models
from django.db.migrations.loader import MigrationLoader
from django.db.migrations.state import ModelState, ProjectState
from django.db.models import NOT_PROVIDED

# Already in production before these rules (hub ``main``@00654ae, deployed on 2026-10-21): the deploys that
# carried them are over and an applied migration is never edited, so the rules cannot reach them. A new entry
# here needs its reason in its own PR (a contract step: the PR of its first step); an entry that no longer breaks
# the code of before fails ``test_every_accepted_migration_still_breaks_it``.
ACCEPTED = {
    # Django's own (1.8), applied when the database was made: no code of before ever ran on it.
    ("contenttypes", "0002_remove_content_type_name", "RemoveField", "contenttype.name"),
    ("attendance", "0002_correction_author", "AddField", "correction.created_by_name"),
    ("attendance", "0002_correction_author", "AddField", "correction.is_system"),
    ("flow", "0005_flow_recipe", "AddField", "flow.recipe"),
    ("flow", "0005_flow_recipe", "AddField", "flow.recipe_digest"),
    ("invoice", "0002_net_prices_and_short_numbers", "AddField", "invoiceline.discount_amount"),
    ("invoice", "0004_platform_ref", "AddField", "invoice.language"),
    ("payment", "0002_payment_trail", "AddField", "payment.approved_by"),
    ("payment", "0002_payment_trail", "AddField", "payment.cancelled_by"),
    ("sale", "0004_voucher_lines", "AddField", "orderline.voucher_name"),
    ("sale", "0004_voucher_lines", "AddField", "saleline.voucher_name"),
    ("sale", "0006_fiscal_document", "AddField", "refund.invoice_number"),
    ("sale", "0006_fiscal_document", "AddField", "refund.invoice_status"),
    ("sale", "0006_fiscal_document", "AddField", "refund.invoice_type"),
    ("sale", "0006_fiscal_document", "AddField", "sale.invoice_number"),
    ("sale", "0006_fiscal_document", "AddField", "sale.invoice_status"),
    ("sale", "0006_fiscal_document", "AddField", "sale.invoice_type"),
    ("sale", "0006_fiscal_document", "AddField", "sale.void_invoice_number"),
    ("sale", "0006_fiscal_document", "AddField", "sale.void_invoice_status"),
    ("service", "0002_redemption_states", "AddField", "redemption.ended_by"),
    ("service", "0002_redemption_states", "AddField", "redemption.return_reason"),
    ("service", "0002_redemption_states", "AddField", "redemption.status"),
    ("tax", "0003_category_and_alias_is_active", "AddField", "taxalias.is_active"),
    ("tax", "0003_category_and_alias_is_active", "AddField", "taxcategory.is_active"),
    ("verifactu", "0003_live_paid", "AddField", "config.hub_status"),
    ("verifactu", "0003_live_paid", "AddField", "config.live_paid"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "AddField", "conversation.contact_search"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "AddField", "conversation.erase_phone"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "AddField", "conversation.erase_status"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "AddField", "conversation.last_message_kind"),
    ("whatsapp_inbox", "0002_delivery_and_erasure", "AddField", "message.template_variables"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.body_examples"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.buttons"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.delete_state"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.header_format"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.submit_error"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.submit_error_code"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.submit_state"),
    ("whatsapp_inbox", "0003_templates_made_in_the_hub", "AddField", "template.supported"),
    ("whatsapp_inbox", "0004_message_reply_id", "AddField", "message.reply_id"),
    ("whatsapp_inbox", "0005_channel_per_business", "AddField", "channel.host"),
    ("whatsapp_inbox", "0006_templates_per_business", "AddField", "template.host"),
    ("whatsapp_inbox", "0007_deliveries_per_business", "AddField", "conversation.erase_host"),
    ("whatsapp_inbox", "0007_deliveries_per_business", "AddField", "message.host"),
    # Narrowed or dropped in one deploy, also before these rules.
    ("invoice", "0002_net_prices_and_short_numbers", "AlterField", "invoice.number"),
    ("invoice", "0002_net_prices_and_short_numbers", "AlterField", "invoiceline.unit_price"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "invoice.customer_name"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "invoice.customer_tax_id"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "invoice.issuer_name"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "invoice.issuer_tax_id"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "issuer.legal_name"),
    ("invoice", "0003_verifactu_field_limits", "AlterField", "issuer.tax_id"),
    ("verifactu", "0002_own_certificate", "RemoveField", "config.own_certificate_expires_at"),
    ("verifactu", "0002_own_certificate", "RemoveField", "config.own_certificate_holder"),
    ("verifactu", "0002_own_certificate", "RemoveField", "config.own_certificate_loaded"),
    ("verifactu", "0002_own_certificate", "RemoveField", "config.own_certificate_uploaded_at"),
    ("verifactu", "0004_multiple_taxpayers_always", "RemoveField", "config.multiple_taxpayers"),
    ("whatsapp_inbox", "0005_channel_per_business", "RemoveField", "channel.slot"),
}

ADD_NOT_NULL = (
    "NOT NULL with no default in the database: the code of before inserts rows without it. Give it db_default=… "
    "(keep default=…), or add it null=True and make it NOT NULL in a later deploy"
)
DROP = (
    "the code of before still reads and writes it. Take it out of the state only first "
    "(SeparateDatabaseAndState(state_operations=[…]); a column, nullable or with db_default before that) and drop it "
    "with RunSQL in a later deploy"
)
RENAME = (
    "the code of before still uses the old name. Keep the name in the database (db_column=… or db_table=…), or add "
    "the new one, copy, and drop the old one in a later deploy"
)
SET_NOT_NULL = (
    "NOT NULL on a column the code of before still writes NULL to (a db_default does not help: the INSERT names the "
    "column). Stop writing NULL in one deploy and make it NOT NULL in a later one, listed in ACCEPTED with that reason"
)
NARROW = (
    "{before} → {after}: the code of before still writes what fits {before}. Narrow it in a later deploy, once no "
    "code writes values out of it, listed in ACCEPTED with that reason"
)
# Changes of the column type that take every value of the old one.
WIDER = {("smallint", "integer"), ("smallint", "bigint"), ("integer", "bigint")}


class Finding(NamedTuple):
    """An operation that breaks the code of before; ``key`` is how ``ACCEPTED`` names it."""

    app: str
    migration: str
    operation: str
    target: str
    why: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.app, self.migration, self.operation, self.target)


def _database_steps(app_label, operations, state):
    """Each operation that changes the database with the project state just before it (read it before the next
    one): those of a ``SeparateDatabaseAndState`` included, on a copy of the state, as Django runs them. Leaves
    ``state`` past all the operations."""
    for operation in operations:
        if isinstance(operation, migrations.SeparateDatabaseAndState):
            yield from _database_steps(app_label, operation.database_operations, state.clone())
        else:
            yield operation, state
        operation.state_forwards(app_label, state)


def _table(app_label: str, model_state) -> str:
    """The table of a model: its ``db_table`` or Django's ``<app>_<model>``."""
    return model_state.options.get("db_table") or f"{app_label}_{model_state.name_lower}"


def _length(db_type: str) -> float | None:
    """How long a text column of this type can be (unbounded for ``text`` and ``varchar``); ``None`` if not text."""
    if db_type in ("text", "varchar"):
        return math.inf
    return int(db_type[8:-1]) if db_type.startswith("varchar(") else None


def _narrower(before: str, after: str) -> bool:
    """Whether a column of type ``before`` turned ``after`` refuses some value it took."""
    if before == after or (before, after) in WIDER:
        return False
    old, new = _length(before), _length(after)
    return old is None or new is None or new < old


def _narrowing(old, new) -> str | None:
    """Why the field ``new`` refuses a value the field ``old`` took, else ``None``."""
    if old.null and not new.null:
        return SET_NOT_NULL
    if old.is_relation or new.is_relation:
        return None  # The column follows the primary key of its target: only NULL can change.
    before, after = old.db_type(connection), new.db_type(connection)
    if _narrower(before, after) or _check(new) not in (None, _check(old)):
        return NARROW.format(before=_shape(old), after=_shape(new))
    return None


def _check(field) -> str | None:
    """The CHECK its type adds to the column (``"%(column)s" >= 0`` for a positive integer); the field of a
    migration is not bound to a model, so ``Field.db_check`` has no column to name."""
    return connection.data_type_check_constraints.get(field.get_internal_type())


def _shape(field) -> str:
    """The column type and its CHECK, as the message names them: ``smallint CHECK (>= 0)``."""
    check = _check(field)
    return field.db_type(connection) + (f" CHECK ({check.removeprefix('\"%(column)s\" ')})" if check else "")


def _why(app_label: str, operation, state) -> tuple[str, str] | None:
    """``(target, why)`` if the operation breaks the code of before, else ``None``."""
    if isinstance(operation, migrations.AddField):
        field = operation.field
        if (
            not field.null
            and field.db_default is NOT_PROVIDED
            and not field.many_to_many
            and not isinstance(field, models.GeneratedField)
        ):
            return f"{operation.model_name_lower}.{operation.name}", ADD_NOT_NULL
    elif isinstance(operation, migrations.RemoveField):
        return f"{operation.model_name_lower}.{operation.name}", DROP
    elif isinstance(operation, migrations.DeleteModel):
        return operation.name_lower, DROP
    elif isinstance(operation, migrations.RenameField):
        if not state.models[app_label, operation.model_name_lower].fields[operation.old_name].db_column:
            return f"{operation.model_name_lower}.{operation.old_name}", RENAME
    elif isinstance(operation, migrations.RenameModel):
        if not state.models[app_label, operation.old_name_lower].options.get("db_table"):
            return operation.old_name_lower, RENAME
    elif isinstance(operation, migrations.AlterModelTable):
        model_state = state.models[app_label, operation.name_lower]
        if _table(app_label, model_state) != (operation.table or f"{app_label}_{operation.name_lower}"):
            return operation.name_lower, RENAME
    elif isinstance(operation, migrations.AlterField):
        old = state.models[app_label, operation.model_name_lower].fields[operation.name]
        if why := _narrowing(old, operation.field):
            return f"{operation.model_name_lower}.{operation.name}", why
    return None


def _model(operation) -> str | None:
    """The model an operation works on (lowercase), if any."""
    for attribute in ("model_name_lower", "old_name_lower", "name_lower"):
        if name := getattr(operation, attribute, None):
            return name
    return None


def breaking_operations(migration, state: ProjectState) -> list[Finding]:
    """What in the migration breaks the code of before, read against ``state`` (the project just before it),
    which it leaves past the migration. A table created by the same migration is new: no code of before uses it."""
    found, created = [], set()
    for operation, before in _database_steps(migration.app_label, migration.operations, state):
        if isinstance(operation, migrations.CreateModel):
            created.add(operation.name_lower)
        elif _model(operation) not in created and (why := _why(migration.app_label, operation, before)):
            found.append(Finding(migration.app_label, migration.name, type(operation).__name__, *why))
    return found


def _found() -> list[Finding]:
    """Every migration of the project, in an order Django could apply them, each against the state before it."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    graph = loader.graph
    plan = dict.fromkeys(node for leaf in graph.leaf_nodes() for node in graph.forwards_plan(leaf))
    state = ProjectState(real_apps=loader.unmigrated_apps)
    return [finding for node in plan for finding in breaking_operations(graph.nodes[node], state)]


def test_no_migration_breaks_the_code_of_before():
    new = [finding for finding in _found() if finding.key not in ACCEPTED]
    assert not new, "\n".join(
        [
            "These migrations break the code of before, which keeps running while the deploy migrates (and comes "
            "back on a rollback):"
        ]
        + [f"  {f.app}/{f.migration}: {f.operation} {f.target} — {f.why}" for f in new]
    )


def test_every_accepted_migration_still_breaks_it():
    """The list is alive: an entry whose migration or field is gone, or that no longer breaks the rule, goes."""
    stale = sorted(ACCEPTED - {finding.key for finding in _found()})
    assert not stale, "Remove from ACCEPTED, they no longer break the code of before: " + ", ".join(
        f"{app}/{name}: {operation} {target}" for app, name, operation, target in stale
    )


def _state() -> ProjectState:
    """A project with ``shop.Product`` and ``shop.Brand`` (its own table name) already deployed."""
    state = ProjectState()
    state.add_model(
        ModelState(
            "shop",
            "Brand",
            [("id", models.UUIDField(primary_key=True))],
            options={"db_table": "shop_maker"},
        )
    )
    state.add_model(
        ModelState(
            "shop",
            "Product",
            [
                ("id", models.UUIDField(primary_key=True)),
                ("name", models.CharField(max_length=20)),
                ("note", models.CharField(max_length=200, null=True)),
                ("units", models.SmallIntegerField(default=0)),
                ("title", models.CharField(max_length=20, db_column="heading")),
                ("brand", models.ForeignKey("shop.Brand", on_delete=models.CASCADE, null=True)),
            ],
        )
    )
    return state


def _keys(*operations, state=None) -> list[tuple[str, str, str, str]]:
    migration = migrations.Migration("0002_change", "shop")
    migration.operations = list(operations)
    return [finding.key for finding in breaking_operations(migration, state or _state())]


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
def test_a_not_null_column_with_only_a_python_default_breaks_it(field):
    assert _keys(_add(field)) == [("shop", "0002_change", "AddField", "product.label")]


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
def test_a_column_the_code_of_before_can_skip_keeps_it_working(field):
    assert _keys(_add(field)) == []


def test_a_column_of_a_table_created_by_the_same_migration_keeps_it_working():
    create = migrations.CreateModel(name="Item", fields=[("id", models.UUIDField(primary_key=True))])

    assert _keys(create, _add(models.ForeignKey("shop.Product", on_delete=models.CASCADE), model="item")) == []


def test_a_column_added_through_separate_database_and_state_counts_only_in_the_database():
    field = models.CharField(max_length=20, default="")
    in_database = migrations.SeparateDatabaseAndState(database_operations=[_add(field)])
    in_state = migrations.SeparateDatabaseAndState(state_operations=[_add(field)])

    assert _keys(in_database) == [("shop", "0002_change", "AddField", "product.label")]
    assert _keys(in_state) == []


@pytest.mark.parametrize(
    "operation, key",
    [
        (migrations.RemoveField(model_name="product", name="name"), ("RemoveField", "product.name")),
        (
            migrations.RenameField(model_name="product", old_name="name", new_name="label"),
            ("RenameField", "product.name"),
        ),
        (migrations.DeleteModel(name="Product"), ("DeleteModel", "product")),
        (migrations.RenameModel(old_name="Product", new_name="Article"), ("RenameModel", "product")),
        (migrations.AlterModelTable(name="product", table="shop_article"), ("AlterModelTable", "product")),
        (
            migrations.SeparateDatabaseAndState(
                database_operations=[migrations.RemoveField(model_name="product", name="name")],
                state_operations=[migrations.RemoveField(model_name="product", name="name")],
            ),
            ("RemoveField", "product.name"),
        ),
    ],
    ids=["remove-field", "rename-field", "delete-model", "rename-model", "alter-model-table", "database-and-state"],
)
def test_dropping_or_renaming_what_the_code_of_before_uses_breaks_it(operation, key):
    assert _keys(operation) == [("shop", "0002_change", *key)]


@pytest.mark.parametrize(
    "operation",
    [
        migrations.RenameField(model_name="product", old_name="title", new_name="caption"),
        migrations.RenameModel(old_name="Brand", new_name="Maker"),
        migrations.AlterModelTable(name="brand", table="shop_maker"),
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.RemoveField(model_name="product", name="name")]
        ),
    ],
    ids=["field-keeps-its-db-column", "model-keeps-its-db-table", "same-table", "removed-from-the-state-only"],
)
def test_a_rename_that_keeps_the_database_name_or_a_drop_from_the_state_only_keeps_it_working(operation):
    assert _keys(operation) == []


def _alter(name, field):
    return migrations.AlterField(model_name="product", name=name, field=field)


@pytest.mark.parametrize(
    "operation",
    [
        _alter("note", models.CharField(max_length=200)),
        _alter("note", models.CharField(max_length=200, default="", db_default="")),
        _alter("brand", models.ForeignKey("shop.Brand", on_delete=models.CASCADE)),
        _alter("name", models.CharField(max_length=10)),
        _alter("name", models.IntegerField(default=0)),
        _alter("units", models.PositiveSmallIntegerField(default=0)),
    ],
    ids=["not-null", "not-null-with-db-default", "foreign-key-not-null", "shorter", "other-type", "new-check"],
)
def test_narrowing_a_column_the_code_of_before_writes_breaks_it(operation):
    assert _keys(operation) == [("shop", "0002_change", "AlterField", f"product.{operation.name}")]


@pytest.mark.parametrize(
    "operation",
    [
        _alter("name", models.CharField(max_length=40)),
        _alter("name", models.TextField()),
        _alter("name", models.CharField(max_length=20, null=True)),
        _alter("name", models.CharField(max_length=20, choices=[("a", "A")], default="a", db_default="a")),
        _alter("units", models.IntegerField(default=0)),
        _alter("units", models.BigIntegerField(default=0)),
        _alter("note", models.CharField(max_length=400, null=True)),
        _alter("brand", models.ForeignKey("shop.Brand", on_delete=models.PROTECT, null=True)),
    ],
    ids=["longer", "text", "nullable", "choices-and-default", "integer", "bigint", "nullable-longer", "on-delete"],
)
def test_widening_or_a_change_outside_the_database_keeps_it_working(operation):
    assert _keys(operation) == []


def test_an_operation_on_a_table_created_by_the_same_migration_keeps_it_working():
    create = migrations.CreateModel(name="Item", fields=[("id", models.UUIDField(primary_key=True))])
    rename = migrations.RenameField(model_name="item", old_name="id", new_name="key")

    assert _keys(create, rename) == []
