//! hub#661 (ADR-0283 K1) + hub#662 (§4) — the six tables the automation kernel stands on.
//!
//! They are **system migrations**, not `CREATE TABLE IF NOT EXISTS` at boot, for the reason
//! hub#37 wrote down: an ensure-create never reaches a hub whose database already exists. Every
//! one of them obeys the row contract of [`tenancy.md`] — `hub_id` on every row, soft-delete,
//! audit — because the flows tables hold what a hub may do to itself without a human present, and
//! that is the last place where "this row belongs to nobody in particular" is acceptable.
//!
//! What this file pins, and why each assertion is not decoration:
//!
//! 1. **The tables exist after `apply`** with the columns the kernel reads by name. A missing
//!    column here is a runtime error in a background tick, which is exactly the failure nobody
//!    sees until a flow silently stops.
//! 2. **`hub_id` is on all six.** One database per hub today (ADR-0201), but the row contract is
//!    not allowed to depend on that.
//! 3. **A live grant is UNIQUE per (hub, flow, kind, value); a revoked one is not.** The partial
//!    index is the mechanism that lets a grant be revoked (soft-delete) and granted again later
//!    without either colliding with its own tombstone or leaving two live rows that disagree.
//! 4. **Idempotence**: re-applying does not re-run them, so a restart is free.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::system_migrations;
use serde_json::json;

const HUB: &str = "hub-flows";

fn p(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut m = Params::new();
    for (k, v) in pairs {
        m.insert((*k).into(), v.clone());
    }
    m
}

/// Columns of `table` as reported by Postgres itself — the schema as it really landed, not as the
/// migration string reads.
async fn columns(db: &dyn DatabaseAdapter, table: &str) -> Vec<String> {
    let res = db
        .query(
            "SELECT column_name FROM information_schema.columns \
             WHERE table_schema = current_schema() AND table_name = :t",
            &p(&[("t", json!(table))]),
        )
        .await
        .unwrap();
    res.rows
        .iter()
        .filter_map(|r| r["column_name"].as_str().map(|s| s.to_string()))
        .collect()
}

/// The v0 baseline the real boot lays down (`Runtime::ensure_system_tables`) plus the versioned
/// migrations on top — the migrations at or below v30 ALTER those baseline tables, so applying
/// them over an empty schema without it fails on `hub_module`, not on anything this file is about.
async fn apply_system_schema(db: &dyn DatabaseAdapter) {
    erplora_runtime::installer::ensure_hub_module_table(db)
        .await
        .unwrap();
    erplora_runtime::identity::ensure_tables(db).await.unwrap();
    system_migrations::apply(db, HUB).await.unwrap();
}

#[tokio::test]
async fn the_flow_tables_land_with_the_row_contract() {
    let tdb = TestDb::new().await;
    let db = tdb.adapter().await;
    apply_system_schema(&db).await;

    // The kernel reads these by name in `flows/`; a rename here is a broken background tick.
    let expected: &[(&str, &[&str])] = &[
        (
            "_flow",
            &["id", "name", "enabled", "schema_version", "definition"],
        ),
        ("_flow_grants", &["id", "flow_id", "kind", "value"]),
        (
            "_flow_triggers",
            &[
                "id",
                "flow_id",
                "trigger_key",
                "kind",
                "event_name",
                "filter",
                "input_map",
                "cron",
                "run_at",
                "enabled",
                "next_run",
                "last_run",
                "claim_expires_at",
            ],
        ),
        (
            "_flow_runs",
            &[
                "id",
                "flow_id",
                "trigger_id",
                "trigger_kind",
                "parent_event_id",
                "status",
                "current_step",
                "input",
                "vars",
                "depth",
                "wake_at",
                "attempts",
                "last_error",
                "claim_expires_at",
                "started_at",
                "finished_at",
            ],
        ),
        (
            "_flow_run_steps",
            &[
                "id",
                "run_id",
                "step_index",
                "step_id",
                "kind",
                "status",
                "input",
                "output",
                "error",
                "started_at",
                "finished_at",
            ],
        ),
        // hub#662 — write-only: `value_enc` holds the `secret_box` envelope and nothing reads it
        // back but the executor, while it builds a request that is about to leave.
        ("_flow_secrets", &["id", "name", "value_enc", "updated_by"]),
    ];

    for (table, cols) in expected {
        let got = columns(&db, table).await;
        assert!(
            !got.is_empty(),
            "`{table}` must exist after the system migrations"
        );
        for col in *cols {
            assert!(
                got.iter().any(|c| c == col),
                "`{table}` must carry `{col}`; it has {got:?}"
            );
        }
        // The row contract of tenancy.md, on every one of them: tenant, soft-delete, audit.
        for contract in ["hub_id", "deleted_at", "created_at"] {
            assert!(
                got.iter().any(|c| c == contract),
                "`{table}` must carry `{contract}` (row contract, tenancy.md); it has {got:?}"
            );
        }
    }
}

#[tokio::test]
async fn a_revoked_grant_can_be_granted_again_but_two_live_ones_cannot_coexist() {
    let tdb = TestDb::new().await;
    let db = tdb.adapter().await;
    apply_system_schema(&db).await;

    let insert = "INSERT INTO _flow_grants \
        (id, hub_id, flow_id, kind, value, created_at, granted_by) \
        VALUES (:id, :hub_id, 'flow-1', 'command', 'sales.sale.create', :now, 'hub_user:1')";
    let row = |id: &str| {
        p(&[
            ("id", json!(id)),
            ("hub_id", json!(HUB)),
            ("now", json!("2026-08-09T10:00:00+00:00")),
        ])
    };

    db.execute(insert, &row("g1")).await.unwrap();

    // Two LIVE grants for the same command would be two answers to one question.
    let clash = db.execute(insert, &row("g2")).await;
    assert!(
        clash.is_err(),
        "a second live grant for the same (hub, flow, kind, value) must be refused"
    );

    // Revoking is a soft-delete — the audit trail of who could do what and until when survives.
    db.execute(
        "UPDATE _flow_grants SET deleted_at = :now, revoked_by = 'hub_user:1' WHERE id = 'g1'",
        &p(&[("now", json!("2026-08-09T11:00:00+00:00"))]),
    )
    .await
    .unwrap();

    // And granting it again afterwards must work: the tombstone is history, not a reservation.
    db.execute(insert, &row("g3"))
        .await
        .expect("a revoked grant does not block granting the same command again");

    let live = db
        .query(
            "SELECT id FROM _flow_grants WHERE hub_id = :hub_id AND deleted_at IS NULL",
            &p(&[("hub_id", json!(HUB))]),
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(live.len(), 1, "exactly one live grant, the new one");
    assert_eq!(live[0]["id"], json!("g3"));
}

#[tokio::test]
async fn re_applying_the_system_migrations_does_not_re_run_the_flow_tables() {
    let tdb = TestDb::new().await;
    let db = tdb.adapter().await;
    apply_system_schema(&db).await;

    // A flow row survives a "restart": the migrations are registered, not replayed.
    db.execute(
        "INSERT INTO _flow (id, hub_id, name, enabled, schema_version, definition, \
                            created_at, created_by, updated_at, updated_by) \
         VALUES ('f1', :hub_id, 'Nightly', 1, 1, '{}', :now, 'hub_user:1', :now, 'hub_user:1')",
        &p(&[
            ("hub_id", json!(HUB)),
            ("now", json!("2026-08-09T10:00:00+00:00")),
        ]),
    )
    .await
    .unwrap();

    let db2 = tdb.adapter().await;
    system_migrations::apply(&db2, HUB).await.unwrap();

    let rows = db2
        .query("SELECT id FROM _flow", &Params::new())
        .await
        .unwrap()
        .rows;
    assert_eq!(rows.len(), 1, "the flow survives a re-apply");
}


#[tokio::test]
async fn a_hub_holds_one_live_secret_per_name_and_forgetting_one_is_not_a_reservation() {
    // Same partial-unique shape as `_flow_grants`, for the same reason: a credential is removed by
    // SOFT-delete (the row records that it existed and who took it away), so a hub that adds
    // `API_KEY` again next month must not collide with its own tombstone.
    let tdb = TestDb::new().await;
    let db = tdb.adapter().await;
    apply_system_schema(&db).await;

    let insert = "INSERT INTO _flow_secrets (id, hub_id, name, value_enc, created_at, updated_at) \
                  VALUES (:id, :hub_id, 'API_KEY', 'v1:blob', :now, :now)";
    let row = |id: &str| {
        p(&[
            ("id", json!(id)),
            ("hub_id", json!(HUB)),
            ("now", json!("2026-08-09T10:00:00+00:00")),
        ])
    };

    db.execute(insert, &row("s1")).await.unwrap();
    assert!(
        db.execute(insert, &row("s2")).await.is_err(),
        "two live secrets called `API_KEY` would be two answers to `{{secret.API_KEY}}`"
    );

    db.execute(
        "UPDATE _flow_secrets SET deleted_at = :now, deleted_by = 'hub_user:1' WHERE id = 's1'",
        &p(&[("now", json!("2026-08-09T11:00:00+00:00"))]),
    )
    .await
    .unwrap();
    db.execute(insert, &row("s3"))
        .await
        .expect("adding the credential again after forgetting it is not a conflict");

    // And a secret belongs to ITS hub: the same name in another tenant is another secret.
    db.execute(
        insert,
        &p(&[
            ("id", json!("s4")),
            ("hub_id", json!("hub-other")),
            ("now", json!("2026-08-09T10:00:00+00:00")),
        ]),
    )
    .await
    .expect("the uniqueness is per (hub, name)");
}
