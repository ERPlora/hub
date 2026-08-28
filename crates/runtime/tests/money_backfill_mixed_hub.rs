//! 🔴 A hub whose money columns are HALF migrated gets no verdict at all (ERPlora/hub#1209).
//!
//! The euros→cents backfill (ADR-0007, ADR-0123, `contracts/money-contract.md` §8) used to settle
//! the unit of the WHOLE hub with the **first** money column that happened to exist, and returned
//! right there. On a hub where some modules are already `INTEGER` (cents) and others are still
//! `NUMERIC` (euros), that made the answer a function of the order of a hand-written list:
//!
//!   * an integer column wins → the marker is seeded and every module still in euros stays in
//!     euros **forever** (the marker turns every re-run into a no-op);
//!   * a decimal column wins → `ROUND(col*100)` runs over every present column, including the ones
//!     that were **already** in cents, multiplying real customer money by 100.
//!
//! Both outcomes are silent. So the verdict is now taken over EVERY money column present, and a
//! hub that disagrees with itself is **refused** — not converted, not marked, and reported at
//! `unexpected` severity so ops sees it. Guessing is the one thing that is never allowed here.
//!
//! These tests seed real rows in a real Postgres (`test-pg` on :5433) because the failure they
//! describe is about `information_schema` types across several tables: an empty database, or the
//! SQLite the rest of the suite once used, would go green without ever seeing it.
use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params, PgAdapter};
use erplora_runtime::money_backfill::{self, MoneyUnit};

/// Reads a numeric cell whatever its JSON shape: Postgres decodes `NUMERIC` as a **string**
/// (precision contract of `pg_cell`) and integers as numbers.
fn num_i64(v: &serde_json::Value) -> i64 {
    v.as_i64()
        .or_else(|| v.as_f64().map(|f| f.round() as i64))
        .or_else(|| {
            v.as_str()
                .and_then(|s| s.parse::<f64>().ok())
                .map(|f| f.round() as i64)
        })
        .expect("numeric value (int, real or NUMERIC-string)")
}

/// `sales_sale` as a module that ALREADY migrated to cents leaves it: `INTEGER`, values in cents.
async fn sales_in_cents(db: &PgAdapter) {
    db.execute_batch(
        "CREATE TABLE sales_sale (\
            id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
            subtotal INTEGER NOT NULL DEFAULT 0, \
            tax_amount INTEGER NOT NULL DEFAULT 0, \
            discount_amount INTEGER NOT NULL DEFAULT 0, \
            total INTEGER NOT NULL DEFAULT 0, \
            amount_tendered INTEGER NOT NULL DEFAULT 0, \
            change_due INTEGER NOT NULL DEFAULT 0);",
    )
    .await
    .unwrap();
    db.execute_batch(
        "INSERT INTO sales_sale \
         (id, hub_id, subtotal, tax_amount, discount_amount, total, amount_tendered, change_due) \
         VALUES ('s1', 'h', 1234, 259, 0, 1493, 2000, 507);",
    )
    .await
    .unwrap();
}

/// `payments_payment` as a module still on the OLD schema leaves it: `NUMERIC`, values in euros.
async fn payments_in_euros(db: &PgAdapter) {
    db.execute_batch(
        "CREATE TABLE payments_payment (id TEXT PRIMARY KEY, amount NUMERIC NOT NULL DEFAULT 0);",
    )
    .await
    .unwrap();
    db.execute_batch("INSERT INTO payments_payment (id, amount) VALUES ('p1', 9.99);")
        .await
        .unwrap();
}

async fn read_one(db: &PgAdapter, sql: &str) -> i64 {
    let res = db.query(sql, &Params::new()).await.unwrap();
    num_i64(res.rows[0].as_object().unwrap().values().next().unwrap())
}

/// 🔴 The whole point: a hub that disagrees with itself is refused, and nothing is touched.
#[tokio::test]
async fn a_mixed_hub_is_refused_not_guessed_hub1209() {
    let db = fresh_db().await;
    sales_in_cents(&db).await; // already migrated
    payments_in_euros(&db).await; // still on euros

    let err = money_backfill::run(&db)
        .await
        .expect_err("a hub with money columns in BOTH units must be refused, never guessed");

    // The refusal names the evidence, both sides of it — ops has to be able to act on it without
    // opening a psql.
    let message = err.to_string();
    for expected in ["sales_sale.total", "payments_payment.amount"] {
        assert!(
            message.contains(expected),
            "the refusal must name the columns that disagree; `{expected}` is missing from: {message}"
        );
    }

    // Nothing was converted: the cents stay cents (not ×100) and the euros stay euros (not left
    // behind for good).
    assert_eq!(
        read_one(&db, "SELECT total FROM sales_sale WHERE id = 's1'").await,
        1493
    );
    assert_eq!(
        read_one(&db, "SELECT amount FROM payments_payment WHERE id = 'p1'").await,
        10
    );

    // And the marker was NOT seeded: sealing it here would make every future run a no-op and
    // freeze the half-migrated hub in place.
    assert!(
        !money_backfill::is_marked_cents(&db).await.unwrap(),
        "a refused hub must stay unmarked, otherwise the anomaly is sealed in and never revisited"
    );
}

/// 🔴 The verdict is a property of the DATABASE, not of where a table sits in `MONEY_COLUMNS`.
///
/// Two mirrored hubs: one where the table at the HEAD of the inventory is in cents and a table far
/// down it is in euros, and one with the two units swapped. Before hub#1209 the first returned
/// "cents" (seal the marker, strand the euros) and the second returned "euros" (multiply the cents
/// by 100) — same anomaly, opposite catastrophes, decided by list position alone.
#[tokio::test]
async fn the_verdict_does_not_depend_on_the_order_of_money_columns_hub1209() {
    // (a) head of the inventory in cents, tail in euros.
    let head_cents = fresh_db().await;
    head_cents
        .execute_batch(
            "CREATE TABLE appointments_appointment (id TEXT PRIMARY KEY, service_price INTEGER NOT NULL DEFAULT 0);\
             CREATE TABLE verifactu_record (id TEXT PRIMARY KEY, base_amount NUMERIC NOT NULL DEFAULT 0, \
                tax_amount NUMERIC NOT NULL DEFAULT 0, total_amount NUMERIC NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
    head_cents
        .execute_batch(
            "INSERT INTO appointments_appointment (id, service_price) VALUES ('a1', 2500);\
             INSERT INTO verifactu_record (id, base_amount, tax_amount, total_amount) \
             VALUES ('v1', 20.66, 4.34, 25.00);",
        )
        .await
        .unwrap();

    // (b) the same anomaly with the two units swapped.
    let head_euros = fresh_db().await;
    head_euros
        .execute_batch(
            "CREATE TABLE appointments_appointment (id TEXT PRIMARY KEY, service_price NUMERIC NOT NULL DEFAULT 0);\
             CREATE TABLE verifactu_record (id TEXT PRIMARY KEY, base_amount INTEGER NOT NULL DEFAULT 0, \
                tax_amount INTEGER NOT NULL DEFAULT 0, total_amount INTEGER NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
    head_euros
        .execute_batch(
            "INSERT INTO appointments_appointment (id, service_price) VALUES ('a1', 25.00);\
             INSERT INTO verifactu_record (id, base_amount, tax_amount, total_amount) \
             VALUES ('v1', 2066, 434, 2500);",
        )
        .await
        .unwrap();

    let a = money_backfill::detect_money_unit(&head_cents)
        .await
        .unwrap();
    let b = money_backfill::detect_money_unit(&head_euros)
        .await
        .unwrap();

    assert!(
        matches!(a, MoneyUnit::Mixed { .. }),
        "cents at the head + euros at the tail is a MIXED hub, not a cents hub: {a:?}"
    );
    assert!(
        matches!(b, MoneyUnit::Mixed { .. }),
        "euros at the head + cents at the tail is a MIXED hub, not a euros hub: {b:?}"
    );

    // Neither run touches a single row.
    assert!(money_backfill::run(&head_cents).await.is_err());
    assert!(money_backfill::run(&head_euros).await.is_err());
    assert_eq!(
        read_one(
            &head_cents,
            "SELECT total_amount FROM verifactu_record WHERE id = 'v1'"
        )
        .await,
        25,
        "the euros side must not be sealed away as if it were already cents"
    );
    assert_eq!(
        read_one(
            &head_euros,
            "SELECT total_amount FROM verifactu_record WHERE id = 'v1'"
        )
        .await,
        2500,
        "the cents side must not be multiplied by 100"
    );
}

/// 🔴 Boot must not seal a mixed hub — and must not brick it either.
///
/// `seed_marker_if_cents` runs on the boot path every hub takes (`ensure_system_tables`), where an
/// `Err` means a till that does not open. So the refusal there is a **loud no-op**: the marker is
/// not seeded (the anomaly stays visible and `--backfill-money` still refuses), the event is
/// reported at `unexpected` severity, and the hub keeps serving.
#[tokio::test]
async fn boot_neither_marks_nor_bricks_a_mixed_hub_hub1209() {
    let db = fresh_db().await;
    sales_in_cents(&db).await;
    payments_in_euros(&db).await;

    let marked = money_backfill::seed_marker_if_cents(&db).await.expect(
        "boot must not fail on a mixed hub: a hub that does not open is a shop that cannot charge",
    );

    assert!(!marked, "a mixed hub must not be marked as cents at boot");
    assert!(!money_backfill::is_marked_cents(&db).await.unwrap());
}

/// A hub that is uniformly in one unit still gets its verdict — the consensus rule must not turn
/// the normal cases into refusals (the four `money_backfill::tests` cover the conversion itself).
#[tokio::test]
async fn a_uniform_hub_still_gets_a_verdict_hub1209() {
    let cents = fresh_db().await;
    sales_in_cents(&cents).await;
    assert_eq!(
        money_backfill::detect_money_unit(&cents).await.unwrap(),
        MoneyUnit::Cents
    );

    let euros = fresh_db().await;
    payments_in_euros(&euros).await;
    assert_eq!(
        money_backfill::detect_money_unit(&euros).await.unwrap(),
        MoneyUnit::Euros
    );

    let empty = fresh_db().await;
    assert_eq!(
        money_backfill::detect_money_unit(&empty).await.unwrap(),
        MoneyUnit::NoMoneyColumns
    );
}

/// 🔴 The sweep ops runs over the fleet must be safe on ANY live hub: it reports and writes nothing.
///
/// This is the half of hub#1209 that answers "is a mixed hub already out there?". `--backfill-money`
/// cannot answer it — on an old euros hub it would CONVERT — so the audit is its own read-only door
/// (`erplora-server --check-money-unit`). If it ever started touching `_hub_meta`, running the
/// sweep would itself decide the verdict it was sent to observe.
#[tokio::test]
async fn the_read_only_check_writes_nothing_hub1209() {
    // An old hub in euros: the one the conversion WOULD rewrite.
    let euros = fresh_db().await;
    payments_in_euros(&euros).await;

    assert_eq!(
        money_backfill::check_logged(&euros).await.unwrap(),
        MoneyUnit::Euros
    );

    // Not converted (still 9.99 €, not 999) …
    assert_eq!(
        read_one(
            &euros,
            "SELECT amount FROM payments_payment WHERE id = 'p1'"
        )
        .await,
        10
    );
    // … and `_hub_meta` was not even created, so the check cannot have sealed anything.
    let meta = euros
        .query(
            "SELECT count(*) AS n FROM information_schema.tables \
             WHERE table_schema = current_schema() AND table_name = '_hub_meta'",
            &Params::new(),
        )
        .await
        .unwrap();
    assert_eq!(
        num_i64(&meta.rows[0]["n"]),
        0,
        "the read-only check must not create `_hub_meta`: an audit that writes is not an audit"
    );

    // And on a mixed hub it refuses, with the same evidence the backfill gives.
    let mixed = fresh_db().await;
    sales_in_cents(&mixed).await;
    payments_in_euros(&mixed).await;
    let err = money_backfill::check_logged(&mixed)
        .await
        .expect_err("the sweep must flag a half-migrated hub");
    assert!(err.to_string().contains("payments_payment.amount"), "{err}");
}

/// 🔴 A marker already sealed does NOT make a mixed hub safe, and the sweep must keep flagging it.
///
/// This is the trap the audit has to avoid. A sealed marker fits TWO stories with identical types:
/// the benign one (the hub converted long ago — the conversion moves the DATA to cents but leaves
/// the column `NUMERIC` — and later installed a module whose `001` is `INTEGER`), and the
/// catastrophic one (the hub was sealed BY the hub#1209 defect, and those decimal columns are
/// still holding euros). Only the magnitudes tell them apart, so dismissing a marked hub would
/// hide exactly the damage the sweep exists to find.
#[tokio::test]
async fn a_sealed_marker_does_not_excuse_a_mixed_hub_hub1209() {
    let db = fresh_db().await;
    sales_in_cents(&db).await;
    payments_in_euros(&db).await;
    // Seal it, the way the old first-column-decides code would have.
    money_backfill::ensure_meta_table(&db).await.unwrap();
    db.execute_batch("INSERT INTO _hub_meta (key, value) VALUES ('money_unit', 'cents');")
        .await
        .unwrap();
    assert!(money_backfill::is_marked_cents(&db).await.unwrap());

    // `run()` is a no-op here by design — the marker guards it, and that is the whole reason the
    // stranded euros would never be revisited …
    assert!(money_backfill::run(&db).await.unwrap().already_marked);

    // … which is precisely why the AUDIT must not follow the marker.
    let err = money_backfill::check_logged(&db)
        .await
        .expect_err("a sealed mixed hub is the hub#1209 damage, not a hub that is fine");
    assert!(err.to_string().contains("payments_payment.amount"), "{err}");
}
