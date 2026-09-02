//! **The editor learns what an event carries from the hub's own events** (hub#715).
//!
//! The flow editor (pm#110) has to offer «el Total de la venta — 42,50 €», not `sale.total`. It
//! could not: there is no payload schema (ADR-0127 phase 3, declared and never built), and the
//! payloads that *are* stored in `_event_outbox.payload` were reachable only through
//! `GET /api/hub/events/dead` — failed events, which a healthy hub does not have.
//!
//! So the shape is inferred from **real events of this hub**, and every test here emits them
//! through the real door (`execute_command` → `_event_outbox`), never by writing rows.
//!
//! What it pins:
//!
//! 1. The fields and their types come out of an event that actually happened, with the value the
//!    owner would recognise.
//! 2. **The payload is not handed over.** A value that could be about a person arrives redacted —
//!    the FIELD is still offered (the editor must be able to map it), the example is not.
//! 3. **Tenancy.** A neighbouring hub is kept ALIVE and populated with the same event name while
//!    the read runs: not one of its fields, and not one of its values, may appear. An assertion
//!    against an empty neighbour proves nothing.
//! 4. **«No examples yet» is not «no such event».** A declared event that has never fired answers
//!    with `samples: 0`; one nobody declares and nobody ever emitted answers nothing. Retention
//!    prunes at ninety days (hub#699), so an infrequent event lands in the first case.
use erplora_db::testutil::TestDb;
use erplora_db::Params;
use erplora_runtime::event_shape::EventField;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use std::path::PathBuf;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_eventshape")
        .join(name)
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

/// A hub on `test_db` with the `shop` module installed — the module that emits the sale.
async fn hub_on(test_db: &TestDb, hub_id: &str) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(test_db.adapter().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("shop")).await.unwrap();
    rt
}

fn params(pairs: Vec<(&str, serde_json::Value)>) -> Params {
    let mut p = Params::new();
    for (k, v) in pairs {
        p.insert(k.to_string(), v);
    }
    p
}

/// One sale as a till closes it: money (a STRING — ADR-0123), a count, a couple of lines, and the
/// customer data a salon really keeps about the person it is about to message.
fn a_sale(total: &str, email: &str, phone: &str, note: &str) -> Params {
    params(vec![
        ("total", json!(total)),
        ("line_count", json!(2)),
        ("paid", json!(true)),
        (
            "customer",
            json!({ "id": "c-1", "name": "Marta", "email": email, "phone": phone }),
        ),
        ("note", json!(note)),
        ("lines", json!([{ "sku": "corte" }, { "sku": "tinte" }])),
    ])
}

async fn sell(rt: &Runtime, hub: &str, sale: Params) {
    rt.execute_command("shop.sell", &sale, &ctx(hub))
        .await
        .expect("the till closes the sale");
}

fn field<'a>(fields: &'a [EventField], path: &str) -> &'a EventField {
    fields.iter().find(|f| f.path == path).unwrap_or_else(|| {
        panic!(
            "no field `{path}` in {:?}",
            fields.iter().map(|f| &f.path).collect::<Vec<_>>()
        )
    })
}

/// **The shape comes from a real sale**, with the value the owner would recognise next to the
/// field — which is the entire reason this exists instead of a declared schema.
#[tokio::test]
async fn the_shape_carries_a_real_value_from_a_real_event() {
    let db = TestDb::new().await;
    let rt = hub_on(&db, "hub-shape").await;
    sell(
        &rt,
        "hub-shape",
        a_sale(
            "42.50",
            "marta@example.com",
            "+34600111222",
            "alérgica al amoniaco",
        ),
    )
    .await;

    let shape = rt
        .event_shape("shop.sale_completed", 5)
        .await
        .unwrap()
        .expect("the event happened in this hub");

    assert_eq!(shape.event_name, "shop.sale_completed");
    assert_eq!(shape.samples, 1);
    assert_eq!(
        shape.declared_by,
        vec!["shop".to_string()],
        "the module that declares it in `events.emits` is named, so the editor can group by app"
    );
    assert!(
        shape.last_seen_at.is_some(),
        "an event that happened has a date"
    );

    // Money is a string in this product (ADR-0123) and the shape says so rather than guessing.
    let total = field(&shape.fields, "total");
    assert_eq!(total.kind, "string");
    assert_eq!(
        total.sample,
        Some(json!("42.50")),
        "«Total de la venta — 42,50 €» is the point: the example is the owner's own number"
    );
    assert_eq!(total.seen_in, 1);

    assert_eq!(field(&shape.fields, "line_count").kind, "number");
    assert_eq!(field(&shape.fields, "line_count").sample, Some(json!(2)));
    assert_eq!(field(&shape.fields, "paid").kind, "boolean");
    assert_eq!(field(&shape.fields, "paid").sample, Some(json!(true)));
}

/// **A nested object is walked; an array is not.** `flows::def::resolve_path` has no array
/// indexing on purpose (v1 maps fields), so offering `lines.0.sku` would be offering a mapping the
/// kernel cannot resolve. The array is still listed, with its length.
#[tokio::test]
async fn it_offers_only_paths_the_mapping_language_can_resolve() {
    let db = TestDb::new().await;
    let rt = hub_on(&db, "hub-paths").await;
    sell(
        &rt,
        "hub-paths",
        a_sale("10.00", "a@b.com", "600111222", ""),
    )
    .await;

    let shape = rt
        .event_shape("shop.sale_completed", 5)
        .await
        .unwrap()
        .unwrap();
    let paths: Vec<&str> = shape.fields.iter().map(|f| f.path.as_str()).collect();

    assert!(
        paths.contains(&"customer.id"),
        "an object IS walked: {paths:?}"
    );
    assert!(
        paths.contains(&"lines"),
        "the array itself is offered — mapping a whole array is legal: {paths:?}"
    );
    assert!(
        !paths.iter().any(|p| p.starts_with("lines.")),
        "nothing may be offered from INSIDE an array: {paths:?}"
    );
    let lines = field(&shape.fields, "lines");
    assert_eq!(lines.kind, "array");
    assert_eq!(
        lines.items,
        Some(2),
        "the editor can say «2 líneas» without the contents"
    );
    assert_eq!(lines.sample, None);
}

/// **The FIELD is offered, the VALUE is not.** The editor has to let the owner map «Email del
/// cliente» into a message; it does not need to show a customer's email to do that. Redaction is
/// by path (a personal container), by key (free text) and by value.
#[tokio::test]
async fn a_value_that_could_be_about_a_person_never_leaves_the_hub() {
    let db = TestDb::new().await;
    let rt = hub_on(&db, "hub-privacy").await;
    sell(
        &rt,
        "hub-privacy",
        a_sale(
            "42.50",
            "marta@example.com",
            "+34600111222",
            "alérgica al amoniaco",
        ),
    )
    .await;

    let shape = rt
        .event_shape("shop.sale_completed", 5)
        .await
        .unwrap()
        .unwrap();

    for path in [
        "customer.email",
        "customer.phone",
        "customer.name",
        "customer.id",
        "note",
    ] {
        let f = field(&shape.fields, path);
        assert!(f.redacted, "`{path}` must be redacted");
        assert_eq!(f.sample, None, "`{path}` handed over a value");
    }

    // …and the whole reply carries none of them, wherever they might have leaked to.
    let body = serde_json::to_string(&shape).unwrap();
    for secret in [
        "marta@example.com",
        "+34600111222",
        "Marta",
        "alérgica al amoniaco",
    ] {
        assert!(
            !body.contains(secret),
            "the shape leaked `{secret}`: {body}"
        );
    }

    // The point of redacting rather than dropping: the mapping is still offerable.
    assert!(
        shape.fields.iter().any(|f| f.path == "customer.email"),
        "a dropped field is a mapping the owner cannot make"
    );
    // And what is NOT about a person keeps its example — a rule that hid everything would be a
    // rule that made the picker useless, which is how it ends up being turned off.
    assert_eq!(field(&shape.fields, "total").sample, Some(json!("42.50")));
}

/// **The neighbour is alive and busy while we read.** Same event name, different values, in a hub
/// sharing the database. Nothing of it may surface — and an assertion against an empty neighbour
/// would pass with unscoped SQL, which is how this class of defect survives review.
#[tokio::test]
async fn a_hub_never_sees_the_events_of_its_neighbour() {
    let db = TestDb::new().await;
    let mine = hub_on(&db, "hub-mine").await;
    let neighbour = hub_on(&db, "hub-neighbour").await;

    // The neighbour trades, with a field of its own so a leak is unmistakable.
    let mut theirs = a_sale("999.99", "vecino@example.com", "+34699999999", "");
    theirs.insert("neighbour_only_field".into(), json!("LEAK"));
    sell(&neighbour, "hub-neighbour", theirs).await;

    // Before we have traded at all: their sale is not our history. The event is KNOWN here (our
    // `shop` declares it) and has zero samples — the neighbour's event must not become ours.
    let before = mine
        .event_shape("shop.sale_completed", 20)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(
        before.samples, 0,
        "the neighbour's sale was counted as this hub's history"
    );
    assert_eq!(before.fields, Vec::new());

    sell(
        &mine,
        "hub-mine",
        a_sale("42.50", "yo@example.com", "+34600111222", ""),
    )
    .await;
    let shape = mine
        .event_shape("shop.sale_completed", 20)
        .await
        .unwrap()
        .unwrap();

    assert_eq!(shape.samples, 1, "only OUR sale was sampled");
    assert!(
        !shape
            .fields
            .iter()
            .any(|f| f.path == "neighbour_only_field"),
        "a field only the neighbour emits appeared in our shape"
    );
    let body = serde_json::to_string(&shape).unwrap();
    assert!(
        !body.contains("999.99") && !body.contains("LEAK"),
        "leaked: {body}"
    );

    // And the neighbour is still there, untouched, seeing its own.
    let theirs = neighbour
        .event_shape("shop.sale_completed", 20)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(theirs.samples, 1);
    assert!(theirs
        .fields
        .iter()
        .any(|f| f.path == "neighbour_only_field"));
}

/// **«Todavía sin ejemplos» is a different answer from «ese evento no existe».**
///
/// `shop.refund_issued` is declared in the manifest and has never fired — which is also what an
/// infrequent event looks like once retention has pruned its last occurrence at ninety days
/// (hub#699). The editor must be able to offer it as a trigger and say it has no examples yet. An
/// event nobody declares and nobody ever emitted is a different thing, and answers nothing.
#[tokio::test]
async fn a_declared_event_with_no_examples_is_not_a_missing_event() {
    let db = TestDb::new().await;
    let rt = hub_on(&db, "hub-empty").await;

    let declared = rt
        .event_shape("shop.refund_issued", 5)
        .await
        .unwrap()
        .expect("a declared event exists even before it first happens");
    assert_eq!(declared.samples, 0);
    assert_eq!(declared.fields, Vec::new());
    assert_eq!(declared.last_seen_at, None);
    assert_eq!(declared.declared_by, vec!["shop".to_string()]);

    assert!(
        rt.event_shape("nobody.declares.this", 5)
            .await
            .unwrap()
            .is_none(),
        "an event that is neither declared nor ever emitted is not a thing this hub has"
    );
}

/// Several samples: the newest supplies the value, and the count says whether a field is
/// OPTIONAL — the thing that quietly breaks a mapping three weeks after somebody drew it.
#[tokio::test]
async fn more_samples_say_which_fields_are_optional() {
    let db = TestDb::new().await;
    let rt = hub_on(&db, "hub-optional").await;

    let mut with_discount = a_sale("10.00", "a@b.com", "600111222", "");
    with_discount.insert("discount".into(), json!("2.00"));
    sell(&rt, "hub-optional", with_discount).await;
    sell(
        &rt,
        "hub-optional",
        a_sale("20.00", "a@b.com", "600111222", ""),
    )
    .await;

    let shape = rt
        .event_shape("shop.sale_completed", 5)
        .await
        .unwrap()
        .unwrap();
    assert_eq!(shape.samples, 2);
    assert_eq!(
        field(&shape.fields, "total").seen_in,
        2,
        "`total` is in every sale"
    );
    assert_eq!(
        field(&shape.fields, "discount").seen_in,
        1,
        "`discount` is not: the editor must be able to warn before somebody maps it"
    );
    assert_eq!(
        field(&shape.fields, "total").sample,
        Some(json!("20.00")),
        "the sample is the NEWEST event's — the sale the owner just made"
    );
}
