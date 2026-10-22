# The registry moves from base to control (phase 2, S1; plan docs/plans/2026-10-22-fase-2-tenencia.md).
#
# ``Hub`` and ``DemoCode`` already exist in the database as ``base_hub`` and ``base_democode`` (base/migrations/0004
# and 0005): control takes them over in Django's state only, with the same tables, constraint and index, and
# base/migrations/0007 lets them go from base's state; no table is created, renamed or dropped. Then the registry
# grows what the tenancy needs, every column with its default in the database (the code of before inserts without
# them during the deploy: base/tests/test_migration_safety.py), and the clusters and the hubs due are created.

import uuid

import django.db.models.deletion
from django.db import migrations, models

import control.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("base", "0006_event_delivery"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name="Hub",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                        ("slug", models.CharField(max_length=63, unique=True, validators=[control.models.registry_slug_validator], verbose_name="slug")),
                        ("name", models.CharField(blank=True, max_length=120, verbose_name="name")),
                        ("country", models.CharField(blank=True, max_length=2, verbose_name="country")),
                        ("timezone", models.CharField(blank=True, max_length=64, verbose_name="time zone")),
                        ("language", models.CharField(blank=True, max_length=8, verbose_name="language")),
                        ("vertical", models.CharField(blank=True, max_length=63, verbose_name="vertical")),
                        ("status", models.CharField(choices=[("requested", "Requested"), ("ready", "Ready"), ("failed", "Failed"), ("cancelled", "Cancelled"), ("expired", "Expired"), ("purged", "Purged")], default="requested", max_length=16, verbose_name="status")),
                        ("is_demo", models.BooleanField(default=False, verbose_name="demo")),
                        ("expires_at", models.DateTimeField(blank=True, null=True, verbose_name="expires at")),
                        ("demo_session_key", models.CharField(blank=True, max_length=64, verbose_name="demo session")),
                        ("state", models.JSONField(blank=True, default=dict, verbose_name="state")),
                        ("state_version", models.PositiveBigIntegerField(default=0, verbose_name="state version")),
                        ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
                        ("updated_at", models.DateTimeField(auto_now=True, verbose_name="updated at")),
                        ("ready_at", models.DateTimeField(blank=True, null=True, verbose_name="ready at")),
                        ("cancelled_at", models.DateTimeField(blank=True, null=True, verbose_name="cancelled at")),
                        ("purged_at", models.DateTimeField(blank=True, null=True, verbose_name="purged at")),
                    ],
                    options={
                        "verbose_name": "hub",
                        "verbose_name_plural": "hubs",
                        "db_table": "base_hub",
                        "ordering": ["slug"],
                        "indexes": [models.Index(fields=["is_demo", "status", "expires_at"], name="base_hub_demo_expiry")],
                        "constraints": [models.UniqueConstraint(condition=models.Q(("is_demo", True), ("status", "ready"), models.Q(("demo_session_key", ""), _negated=True)), fields=("demo_session_key",), name="base_hub_one_live_demo_per_session")],
                    },
                ),
                migrations.CreateModel(
                    name="DemoCode",
                    fields=[
                        ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                        ("code_hash", models.CharField(max_length=64, unique=True, verbose_name="code hash")),
                        ("language", models.CharField(blank=True, max_length=8, verbose_name="language")),
                        ("expires_at", models.DateTimeField(verbose_name="expires at")),
                        ("used_at", models.DateTimeField(blank=True, null=True, verbose_name="used at")),
                        ("hub", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="demo_codes", to="control.hub", verbose_name="hub")),
                    ],
                    options={
                        "verbose_name": "demo code",
                        "verbose_name_plural": "demo codes",
                        "db_table": "base_democode",
                        "ordering": ["expires_at"],
                    },
                ),
            ],
            database_operations=[],
        ),
        migrations.CreateModel(
            name="Cluster",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid7, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=63, unique=True, verbose_name="name")),
                ("host", models.CharField(max_length=255, verbose_name="writer host")),
                ("port", models.PositiveIntegerField(default=5432, verbose_name="writer port")),
                ("pooler_host", models.CharField(max_length=255, verbose_name="PgBouncer host")),
                ("pooler_port", models.PositiveIntegerField(default=6432, verbose_name="PgBouncer port")),
                ("is_open", models.BooleanField(default=True, verbose_name="open to new hubs")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="created at")),
            ],
            options={
                "verbose_name": "cluster",
                "verbose_name_plural": "clusters",
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="hub",
            name="db_name",
            field=models.CharField(blank=True, db_default="", default="", max_length=63, validators=[control.models.db_name_validator], verbose_name="database"),
        ),
        migrations.AddField(
            model_name="hub",
            name="schema_state",
            field=models.CharField(choices=[("current", "Current"), ("behind", "Behind")], db_default="current", default="current", max_length=16, verbose_name="schema"),
        ),
        migrations.AddField(
            model_name="hub",
            name="schema_apps",
            field=models.JSONField(blank=True, db_default={}, default=dict, verbose_name="created apps"),
        ),
        migrations.AddField(
            model_name="hub",
            name="is_platform",
            field=models.BooleanField(db_default=False, default=False, verbose_name="platform hub"),
        ),
        migrations.AddField(
            model_name="hub",
            name="cluster",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="hubs", to="control.cluster", verbose_name="cluster"),
        ),
        migrations.CreateModel(
            name="HubDue",
            fields=[
                ("hub", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="due", serialize=False, to="control.hub", verbose_name="hub")),
                ("due_at", models.DateTimeField(verbose_name="due at")),
                ("lease_until", models.DateTimeField(blank=True, null=True, verbose_name="leased until")),
                ("fiscal_oldest_pending_at", models.DateTimeField(blank=True, null=True, verbose_name="oldest fiscal record pending since")),
            ],
            options={
                "verbose_name": "hub due",
                "verbose_name_plural": "hubs due",
                "ordering": ["due_at"],
                "indexes": [models.Index(fields=["due_at"], name="control_hubdue_due_at")],
            },
        ),
    ]
