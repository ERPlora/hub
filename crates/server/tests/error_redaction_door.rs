//! What a client is allowed to READ when the hub fails (hub#1074).
//!
//! `/api/command` and `/api/query` used to answer with the `Display` of **any** `RuntimeError`,
//! so a foreign-key violation reached the caller as
//! `db: sqlx: error returned from database: insert or update on table "tasks_comment" violates
//! foreign key constraint "tasks_comment_task_id_fkey" at line 2772` — the engine, its access
//! layer, the table, the constraint and an internal line number, all published outwards. In
//! ERPlora/pricing#29 that text was painted in red in front of the user.
//!
//! The policy this file pins is the one the PUBLIC door already applied (`public_door::
//! domain_detail`): only what a module says ON PURPOSE about the request travels; the hub's own
//! plumbing is redacted to a stable, translatable code and the detail goes to the log.

use std::path::PathBuf;

use axum::body::Body;
use axum::http::Request;
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;
use erplora_server::{app, AppState, AuthMode, HubConfig};
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_dberr")
}

async fn make_app() -> axum::Router {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture()).await.unwrap();
    app(AppState::with_config(rt, HubConfig::from_env_with_auth(AuthMode::Dev)))
}

fn post(uri: &str, body: Value) -> Request<Body> {
    Request::builder()
        .method("POST")
        .uri(uri)
        .header("content-type", "application/json")
        .header("x-hub-id", "h1")
        .header("x-user-id", "u1")
        .header("x-permissions", "*")
        .body(Body::from(body.to_string()))
        .unwrap()
}

async fn call(uri: &str, body: Value) -> Value {
    let resp = make_app().await.oneshot(post(uri, body)).await.unwrap();
    let bytes = resp.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

/// Every fragment that betrays the engine, its driver or the shape of our schema. Asserted on the
/// WHOLE response body, not just on `message`: a leak that moves to another key is still a leak.
const NEVER: [&str; 6] = ["sqlx", "db: ", "constraint", "_fkey", "at line", "dberr_note"];

fn assert_redacted(body: &Value) {
    let raw = body.to_string();
    for needle in NEVER {
        assert!(
            !raw.contains(needle),
            "the response leaks `{needle}` to the client: {raw}"
        );
    }
}

/// 🔴 The bug. A real foreign-key violation inside a declarative command.
#[tokio::test]
async fn a_database_failure_never_reaches_the_caller_as_driver_text() {
    let body = call(
        "/api/command",
        json!({ "name": "dberr.notes.create", "payload": { "topic_id": "no-such-topic" } }),
    )
    .await;

    assert_eq!(body["ok"], json!(false), "{body}");
    assert_redacted(&body);
}

/// The read half of the same door: a query whose SQL cannot run.
#[tokio::test]
async fn a_failing_query_never_reaches_the_caller_as_driver_text() {
    let body = call("/api/query", json!({ "name": "dberr.notes.broken" })).await;

    assert_eq!(body["ok"], json!(false), "{body}");
    assert_redacted(&body);
}

/// Redacting the prose is only half: what survives has to be something the shell can BRANCH on.
/// `{"code": "error"}` is the bucket that made the UI paint the driver text in the first place —
/// with nothing else to show, `error.message` was all it had.
#[tokio::test]
async fn a_redacted_failure_still_carries_a_stable_code() {
    let body = call(
        "/api/command",
        json!({ "name": "dberr.notes.create", "payload": { "topic_id": "no-such-topic" } }),
    )
    .await;

    assert_eq!(
        body["error"]["code"], json!("db"),
        "a database failure keeps the stable code the error registry already publishes: {body}"
    );
    assert!(
        !body["error"]["message"].as_str().unwrap_or_default().is_empty(),
        "the redacted answer still says something: {body}"
    );
}

/// The channel that must NOT be redacted (ADR-0205, hub#139): a module's `expect_rows` rejection
/// is the module saying something true about the request, and it travels with its namespaced code
/// AND its message intact.
#[tokio::test]
async fn a_module_domain_rejection_still_travels_whole() {
    let body = call("/api/command", json!({ "name": "dberr.notes.reject" })).await;

    assert_eq!(body["ok"], json!(false), "{body}");
    assert_eq!(body["error"]["code"], json!("dberr.no_such_note"), "{body}");
    assert_eq!(
        body["error"]["message"],
        json!("That note is not here any more"),
        "the module's own sentence is the one channel that reaches the client: {body}"
    );
}

/// A command that does not exist is not plumbing either: naming it back is how a caller finds its
/// own typo, and the name came from the caller in the first place.
#[tokio::test]
async fn a_missing_command_still_names_what_was_asked_for() {
    let body = call("/api/command", json!({ "name": "dberr.notes.nope" })).await;

    assert_eq!(body["error"]["code"], json!("not_found"), "{body}");
    assert!(
        body["error"]["message"]
            .as_str()
            .unwrap_or_default()
            .contains("dberr.notes.nope"),
        "{body}"
    );
}

/// The same reasoning on the READ door (hub#1173): a param the list does not declare is the
/// caller's own typo, in the same family as a missing required param, and the sentence naming it
/// is the one thing that lets them fix it. Redacting this one would answer a `400` that says
/// nothing about WHICH param was wrong — worse than the bug the error exists to prevent.
///
/// This test is why the arm cannot be flipped by accident: `may_reach_the_client` is exhaustive on
/// purpose so a new variant must declare its side of the door, but "exhaustive" only forces
/// SOMEBODY to choose — it does not remember which side was chosen or why.
#[tokio::test]
async fn an_undeclared_list_param_names_itself_instead_of_being_redacted() {
    // A LIST query on purpose: the vocabulary check is the list engine's (`reject_undeclared_params`
    // only runs on the `Some(spec)` branch), because it is there that ignoring a param silently
    // returns the WHOLE list as though it had filtered. A plain query keeps ignoring extras.
    let body = call(
        "/api/query",
        json!({ "name": "dberr.notes.paged", "params": { "nosuchfilter": "x" } }),
    )
    .await;

    assert_eq!(body["ok"], json!(false), "{body}");
    assert_eq!(body["error"]["code"], json!("unknown_filter"), "{body}");
    let message = body["error"]["message"].as_str().unwrap_or_default();
    assert!(
        message.contains("nosuchfilter"),
        "the rejected param has to be named or the caller cannot find their typo: {body}"
    );
    // The net underneath stays in place: travelling whole is not a licence to leak plumbing.
    assert_redacted(&body);
}
