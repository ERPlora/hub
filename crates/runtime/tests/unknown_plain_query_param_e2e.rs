//! **hub#1913** — a PLAIN query (no `list` block) asked with a parameter name it does not know
//! answered "there is nothing": `200 {"data": []}`, no error anywhere.
//!
//! Measured on hub v1.1.26 with appointments 1.1.78 (QA of sales#316):
//! `appointments.appointments.get` binds `:appointment_id`; asked with `{"id": "<appointment>"}`
//! the `id` was dropped, `:appointment_id` bound NULL and the read matched zero rows. "Charge" from
//! an appointment opened an EMPTY ticket for weeks, and two earlier fixes passed their tests
//! without seeing it — the answer is indistinguishable from "that record does not exist".
//!
//! hub#1173/hub#1182 closed the same silence for the LIST engine (`unknown_filter`); this is the
//! gap it left. Same door, same code: the plain query's vocabulary is what it declares — the binds
//! its SQL references and the properties of its JSON Schema — plus the kernel's system params,
//! which the runtime injects (and overwrites) on every call anyway.
//!
//! Real Postgres, ephemeral schema per test.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_plainparam1913")
        .join("pparam")
}

async fn hub() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture())
        .await
        .expect("install pparam");
    rt
}

fn ctx(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id, "u1", ["*".to_string()])
}

fn params(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut p = Params::new();
    for (k, v) in pairs {
        p.insert((*k).into(), v.clone());
    }
    p
}

/// The acceptance case, in the exact shape of the issue: the read is asked by `id` while its SQL
/// binds `:item_id`. It used to answer `[]`; now it names the offending param and what IS accepted.
#[tokio::test]
async fn a_plain_query_refuses_a_param_its_sql_does_not_bind() {
    let rt = hub().await;

    let err = rt
        .execute_query(
            "pparam.items.get",
            &params(&[("id", json!("i1"))]),
            &ctx("h1"),
        )
        .await
        .expect_err("an unknown param must not answer `no rows` as if the record did not exist");

    match err {
        RuntimeError::UnknownFilter {
            query,
            param,
            accepted,
        } => {
            assert_eq!(query, "pparam.items.get");
            assert_eq!(param, "id", "the refusal names the offending param");
            assert!(
                accepted.iter().any(|a| a == "item_id"),
                "and lists what IS accepted, so the caller can fix it: {accepted:?}"
            );
        }
        other => panic!("expected the stable unknown-param refusal, got {other:?}"),
    }
}

/// Control positive: the same read with the name its SQL binds still answers the row.
#[tokio::test]
async fn a_plain_query_asked_by_its_own_bind_still_answers() {
    let rt = hub().await;

    let rows = rt
        .execute_query(
            "pparam.items.get",
            &params(&[("item_id", json!("i1"))]),
            &ctx("h1"),
        )
        .await
        .expect("a declared bind is accepted");
    assert_eq!(rows.len(), 1, "{rows:?}");
    assert_eq!(rows[0]["name"], json!("coffee"));
}

/// A bind mentioned only in a COMMENT of the SQL is not vocabulary — the `payments.methods.list`
/// `active_only` trap of hub#1173, on the plain path.
#[tokio::test]
async fn a_bind_that_only_lives_in_a_sql_comment_is_not_vocabulary() {
    let rt = hub().await;

    let err = rt
        .execute_query(
            "pparam.items.get",
            &params(&[("item_id", json!("i1")), ("ghost", json!(1))]),
            &ctx("h1"),
        )
        .await
        .expect_err("`:ghost` only exists in a comment");
    assert!(
        matches!(&err, RuntimeError::UnknownFilter { param, .. } if param == "ghost"),
        "{err:?}"
    );
}

/// A property the module wrote in the query's JSON Schema is a deliberate declaration, not the
/// slip this door catches — accepted even though the SQL never binds it (same rule as the list).
#[tokio::test]
async fn a_property_declared_in_the_query_schema_is_accepted() {
    let rt = hub().await;

    let rows = rt
        .execute_query(
            "pparam.items.tagged",
            &params(&[("item_id", json!("i1")), ("audit_tag", json!("pos"))]),
            &ctx("h1"),
        )
        .await
        .expect("a schema property is vocabulary");
    assert_eq!(rows.len(), 1, "{rows:?}");
}

/// The kernel's system params are tolerated — the runtime injects them on every call — and they
/// are still NOT forgeable: a caller that sends `hub_id` of another hub reads its own hub only.
#[tokio::test]
async fn system_params_are_tolerated_and_still_overwritten_by_the_runtime() {
    let rt = hub().await;

    let rows = rt
        .execute_query(
            "pparam.items.get",
            &params(&[
                ("item_id", json!("i2")),
                ("hub_id", json!("h2")),
                ("caller_lang", json!("en")),
            ]),
            &ctx("h1"),
        )
        .await
        .expect("system param names are kernel vocabulary, not an unknown param");
    assert!(
        rows.is_empty(),
        "hub h1 must not read hub h2's row through a forged `hub_id`: {rows:?}"
    );

    let rows = rt
        .execute_query(
            "pparam.items.get",
            &params(&[("item_id", json!("i2")), ("hub_id", json!("h2"))]),
            &ctx("h2"),
        )
        .await
        .expect("the owner hub reads it");
    assert_eq!(rows.len(), 1, "{rows:?}");
}

/// The engine's paging pair is tolerated on a plain query too: the SDK's `queryAll` /
/// `queryAllOptional` read the WHOLE set of any query — list or plain — by sending
/// `{...params, offset: 0}` (and `limit` when the caller caps it), and accept a plain query's bare
/// array as is. Sweep of the 27 modules (`origin/main`, 29/09/2026): the POS reads
/// `inventory.products.for_sale`, `inventory.product_categories` and `inventory.units.list` that
/// way. Refusing `offset` would have turned every POS opening into a catalogue incident.
#[tokio::test]
async fn the_sdk_whole_set_paging_pair_is_tolerated_on_a_plain_query() {
    let rt = hub().await;

    let rows = rt
        .execute_query(
            "pparam.items.get",
            &params(&[
                ("item_id", json!("i1")),
                ("offset", json!(0)),
                ("limit", json!(10)),
            ]),
            &ctx("h1"),
        )
        .await
        .expect("`offset`/`limit` are the engine's own vocabulary, sent by `queryAll`");
    assert_eq!(rows.len(), 1, "{rows:?}");
}
