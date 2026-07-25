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
