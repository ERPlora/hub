//! **A hub whose database predates hub#497 must still boot** (hub#885).
//!
//! `identity::ENSURE_TABLES` — the v0 baseline the runtime lays down on *every* boot, before the
//! migration engine runs at all — creates `hub_user`/`hub_session` **with `hub_id`** and indexes
//! that column in the same batch. On a database created before hub#497 the two tables already
//! exist **without** `hub_id`, so the `CREATE TABLE IF NOT EXISTS` is a no-op (a `CREATE … IF NOT
//! EXISTS` never alters a table that is already there) and the next statement dies:
//!
//! ```text
//! Db(Sqlx(Database(PgDatabaseError { code: "42703",
//!   message: "column \"hub_id\" does not exist",
//!   file: Some("indexcmds.c"), routine: Some("ComputeIndexAttrs") })))
//! ```
//!
//! The migration that *adds* the column (v42 `hub_identity_hub_scoped`) runs **after** the
//! baseline, so it never gets its turn. The process exits 1, Swarm rolls the service back, and the
//! deploy CLI still prints `Service converged` — which is how this reached every hub in the fleet
//! at once, including hubs provisioned today (provisioning serves image `1.0.2`, older than
//! hub#497).
//!
//! # Why the existing tests did not catch it
//!
//! `system_migrations`'s own v42 tests do simulate the old shape (they `DROP COLUMN hub_id`), but
//! they call `apply` **directly**. The real boot calls `identity::ensure_tables` first, and that is
//! where it dies. Everything else boots against a *clean* database, which is exactly the case that
//! works. So this test goes through the door the server goes through —
//! [`Runtime::ensure_system_tables`] — and nothing narrower.
//!
//! # The two failures on this path, not one
//!
//! Ordering is only the first. v42 does `ADD COLUMN IF NOT EXISTS hub_id TEXT` and then
//! `ALTER COLUMN hub_id SET NOT NULL`, and on a table **with rows** that second statement fails
//! 23502 unless something filled them in. So the fixture keeps a person and her open session in
//! the database while the boot runs: fixing only the index order would move the crash one step
//! along and this test would still be red.
use erplora_db::testutil::TestDb;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;

/// The `hub_id` the deployment injects (env `HUB_ID`) — the value v42's backfill seals into the
/// rows that do not say whose they are. It is a fact and not a guess because since ADR-0201 each
/// hub owns its own database.
const DEPLOYED_HUB: &str = "hub-885";

/// Boots a hub over `db` the way `crates/server` boots it.
async fn boot(test_db: &TestDb, hub_id: &str) -> Result<(), erplora_runtime::RuntimeError> {
    let rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await
}

/// Rewinds an up-to-date database to the shape a hub deployed **before** hub#497 carries: the two
/// identity tables without `hub_id` (dropping the column takes its indexes with it, exactly as
/// those hubs have never had them), and the control rows of v42 and everything above it removed so
/// the next boot has them still to apply.
///
/// The version is read from the control table by **name**, never hardcoded: a renumber must not
/// quietly turn this fixture into a no-op. Deleting the versions *above* v42 as well is not
/// cosmetic — `apply` aborts on a catalogue version that is unregistered yet below the maximum
/// applied (hub#573), which is a different failure from the one under test.
async fn rewind_identity_to_pre_hub_497(db: &dyn DatabaseAdapter) {
    db.execute_batch(
        "ALTER TABLE hub_user DROP COLUMN hub_id;\
         ALTER TABLE hub_session DROP COLUMN hub_id;\
         DELETE FROM _hub_system_migrations WHERE version >= \
           (SELECT version FROM _hub_system_migrations WHERE name = 'hub_identity_hub_scoped');",
    )
    .await
    .expect("rebobinar la identidad al esquema pre-hub#497");
}

/// A person and the session she left open, written before the column existed — so they carry no
/// `hub_id` at all. A table with **no** rows would let `SET NOT NULL` succeed with no backfill
/// whatsoever, and this test would stop watching half of what it is for.
async fn a_person_from_before_the_column(db: &dyn DatabaseAdapter) {
    db.execute_batch(
        "INSERT INTO hub_user (id, name, pin_hash, role, is_active, created_at) \
           VALUES ('u-legacy', 'Ana', '', 'admin', 1, '2026-01-01T00:00:00Z');\
         INSERT INTO hub_session (token, user_id, created_at, expires_at) \
           VALUES ('t-legacy', 'u-legacy', '2026-01-01T00:00:00Z', '2099-01-01T00:00:00Z');",
    )
    .await
    .expect("sembrar la identidad heredada");
}

async fn count(db: &dyn DatabaseAdapter, sql: &str) -> i64 {
    db.query(sql, &Params::new()).await.expect(sql).rows[0]["n"]
        .as_i64()
        .expect("count devuelve un entero")
}

/// The whole point: the image boots on a database it did not create.
#[tokio::test]
async fn a_hub_deployed_before_hub_497_boots_on_the_new_image() {
    let test_db = TestDb::new().await;
    boot(&test_db, DEPLOYED_HUB)
        .await
        .expect("el primer arranque, sobre BD limpia, es el caso que YA funciona");

    {
        let db = test_db.adapter().await;
        rewind_identity_to_pre_hub_497(&db).await;
        a_person_from_before_the_column(&db).await;
    }

    // The update: the same hub, a new process, the new image, the database it already had.
    boot(&test_db, DEPLOYED_HUB).await.expect(
        "un hub con `hub_user`/`hub_session` sin `hub_id` (anterior a hub#497) tiene que arrancar: \
         el baseline v0 no puede indexar una columna que su `CREATE TABLE IF NOT EXISTS` no ha \
         creado, y la v42 tiene que rellenar las filas antes del `SET NOT NULL`",
    );

    let db = test_db.adapter().await;

    // Nobody was lost, and every row now says whose it is.
    assert_eq!(
        count(&db, "SELECT count(*) AS n FROM hub_user").await,
        1,
        "Ana sigue ahí: actualizar no borra personas"
    );
    assert_eq!(
        count(
            &db,
            &format!("SELECT count(*) AS n FROM hub_user WHERE hub_id = '{DEPLOYED_HUB}'")
        )
        .await,
        1,
        "y su fila quedó sellada con el hub_id del despliegue"
    );
    assert_eq!(
        count(
            &db,
            &format!("SELECT count(*) AS n FROM hub_session WHERE hub_id = '{DEPLOYED_HUB}'")
        )
        .await,
        1,
        "su sesión abierta también: migrar no echa a nadie del hub"
    );

    // The session is once again only good in its own hub — the `WHERE` the column exists for.
    assert!(
        erplora_runtime::identity::resolve_session(&db, DEPLOYED_HUB, "t-legacy")
            .await
            .unwrap()
            .is_some(),
        "la sesión heredada sigue valiendo en su hub"
    );
    assert!(
        erplora_runtime::identity::resolve_session(&db, "hub-otro", "t-legacy")
            .await
            .unwrap()
            .is_none(),
        "y no abre otro hub"
    );

    // `SET NOT NULL` really landed: an insert that forgets the tenant fails loudly instead of
    // writing an unattributable row on an authentication table.
    assert!(
        db.execute(
            "INSERT INTO hub_user (id, name, pin_hash, role, is_active, created_at) \
             VALUES ('u-2', 'Sin hub', '', 'admin', 1, '2026-01-02T00:00:00Z')",
            &Params::new(),
        )
        .await
        .is_err(),
        "hub_id volvió a ser NOT NULL: un INSERT que se olvida del tenant no puede colar"
    );

    // And the indexes the migration owns are there — whichever step ends up creating them, the
    // upgraded hub must not be left reading `hub_user` by sequential scan.
    for index in ["ix_hub_user_hub", "ix_hub_session_hub"] {
        assert_eq!(
            count(
                &db,
                &format!(
                    "SELECT count(*) AS n FROM pg_indexes \
                     WHERE schemaname = current_schema() AND indexname = '{index}'"
                )
            )
            .await,
            1,
            "`{index}` tiene que existir tras la actualización"
        );
    }
}
