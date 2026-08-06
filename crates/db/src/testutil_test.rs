//! Tests del helper de test [`crate::testutil`] (ADR-0154). Incluido vía `#[path]` desde
//! `testutil.rs` (escape TDD documentado). Verifica el CONTRATO de aislamiento del que depende toda
//! la suite en paralelo.
use super::*;
use crate::{DatabaseAdapter, Params};

/// Two `fresh_db()` adapters get **separate schemas**: a table created in one is invisible to the
/// other. This is the isolation contract the parallel test suite relies on.
#[tokio::test]
async fn fresh_db_isolates_each_test() {
    let a = fresh_db().await;
    let b = fresh_db().await;
    a.execute_batch("CREATE TABLE only_in_a (id TEXT PRIMARY KEY);")
        .await
        .unwrap();
    let mut p = Params::new();
    p.insert("id".into(), "x".into());
    a.execute("INSERT INTO only_in_a (id) VALUES (:id)", &p).await.unwrap();
    // `a` sees its own row.
    let seen = a.query("SELECT id FROM only_in_a", &Params::new()).await.unwrap();
    assert_eq!(seen.rows.len(), 1);
    // `b` lives in a different schema → the table does not exist there.
    let err = b.query("SELECT id FROM only_in_a", &Params::new()).await;
    assert!(err.is_err(), "el esquema de b no debe ver la tabla de a");
}

/// The same `TestDb` handed out twice keeps the data (simulated restart over the same schema).
#[tokio::test]
async fn same_testdb_persists_across_adapters() {
    let tdb = TestDb::new().await;
    let first = tdb.adapter().await;
    first
        .execute_batch("CREATE TABLE persisted (id TEXT PRIMARY KEY);")
        .await
        .unwrap();
    drop(first);
    // A brand-new adapter on the SAME schema still sees the table (persistence across "restart").
    let second = tdb.adapter().await;
    second.query("SELECT id FROM persisted", &Params::new()).await.unwrap();
}

/// Does a schema with this exact name exist?
async fn schema_exists(conn: &mut sqlx::PgConnection, name: &str) -> bool {
    sqlx::query_scalar::<_, i64>("SELECT count(*) FROM pg_namespace WHERE nspname = $1")
        .bind(name)
        .fetch_one(conn)
        .await
        .unwrap()
        > 0
}

/// Schemas left behind by a DEAD run are garbage-collected; schemas of a LIVE run survive.
/// Killed test processes (fleet SIGKILLs, aborted runs) never clean up after themselves, so a
/// long-lived local container accumulates orphans until catalog queries crawl (2 822 schemas /
/// 30 864 tables on 2026-08-06). CI containers are throwaway; local ones are not.
#[tokio::test]
async fn gc_drops_dead_run_schemas_and_keeps_live_ones() {
    let opts = base_opts();
    ensure_database(&opts).await;
    let mut conn = opts.clone().connect().await.unwrap();

    // A PID that is guaranteed dead: spawn a trivial child and reap it.
    let mut child = std::process::Command::new("true").spawn().unwrap();
    let dead_pid = child.id();
    child.wait().unwrap();

    let dead = format!("t_{dead_pid}_0");
    // High sequence number so it can never collide with this run's own SCHEMA_SEQ schemas.
    let live = format!("t_{}_987654", std::process::id());
    run(
        &mut conn,
        &format!(
            "DROP SCHEMA IF EXISTS \"{dead}\" CASCADE; CREATE SCHEMA \"{dead}\"; \
             DROP SCHEMA IF EXISTS \"{live}\" CASCADE; CREATE SCHEMA \"{live}\";"
        ),
    )
    .await
    .unwrap();

    gc_dead_run_schemas(&mut conn).await.unwrap();

    assert!(
        !schema_exists(&mut conn, &dead).await,
        "the dead run's schema must be dropped by the GC"
    );
    assert!(
        schema_exists(&mut conn, &live).await,
        "a schema whose owning process is alive must survive the GC"
    );

    run(&mut conn, &format!("DROP SCHEMA \"{live}\" CASCADE;")).await.unwrap();
}

/// Only names shaped `t_<pid>_<n>` belong to the harness: anything else is not ours to judge.
#[test]
fn schema_run_pid_parses_only_harness_names() {
    assert_eq!(schema_run_pid("t_1234_0"), Some(1234));
    assert_eq!(schema_run_pid("t_1234_56"), Some(1234));
    assert_eq!(schema_run_pid("t_abc_0"), None, "non-numeric pid");
    assert_eq!(schema_run_pid("t_1234_x"), None, "non-numeric sequence");
    assert_eq!(schema_run_pid("t_1234"), None, "missing sequence");
    assert_eq!(schema_run_pid("t_-5_0"), None, "negative pid");
    assert_eq!(schema_run_pid("tenant_1234_0"), None, "foreign prefix");
}
