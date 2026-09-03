//! hub#1489 — «can this hub issue?» is **«has it got a ROUTE?»**, not «has it got its own
//! certificate?» (ADR-0203 gate, ADR-0320 §1).
//!
//! ADR-0320 gave a hub TWO exclusive ways of reaching the AEAT: the taxpayer signs and files with
//! their own `.p12` (`ROUTE_OWN`), or ERPlora files on their behalf through the fiscal cell with
//! its Seal (`ROUTE_DELEGATED`). The core's question only ever looked at the first one, and while
//! ERPlora's certificate was handed down into a local slot that was invisible: a delegated hub
//! held a `.p12` too, so it answered `true` by accident. hub#1435 retired that slot — the key does
//! not travel any more — and the hole came out:
//!
//! * the dispatcher's fiscal gate (`commands::execute`/`queries::execute_page` →
//!   `RequestContext::has_certificate`) rejected the SALE of a hub that transmits perfectly,
//! * the ⛔ arm of the onboarding checklist (`hub.setup.status`, hub#370) painted a wall in front
//!   of it, and
//! * `fiscal_profile::refresh` never made it `READY` (pinned in `fiscal_profile`'s own tests).
//!
//! What makes the cell road open **from this side** is the enrolled machine identity (ADR-0419):
//! the private key generated on the hub, the certificate the operator signed, and the internal CA.
//! Without it there is nothing to present at the cell's mTLS ingress, which is exactly what the
//! engine checks FIRST (`gateway::resolve_access`). So this file walks the four states a hub can
//! be in and pins that both readers answer «has it got a route?» in all of them — including the
//! fail-closed one, where a hub with NEITHER is still refused.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::CertificateKind;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it.
const SESSION: &str = "hub.users.view";

/// The four states of «which way out does this hub have?».
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Routes {
    /// The business uploaded its own `.p12` (`ROUTE_OWN`).
    own_certificate: bool,
    /// The machine identity of ADR-0419 is enrolled: the cell road is open from this side.
    enrolled: bool,
}

const NO_ROUTE: Routes = Routes {
    own_certificate: false,
    enrolled: false,
};
const OWN_ONLY: Routes = Routes {
    own_certificate: true,
    enrolled: false,
};
const CELL_ONLY: Routes = Routes {
    own_certificate: false,
    enrolled: true,
};
const BOTH: Routes = Routes {
    own_certificate: true,
    enrolled: true,
};

fn ctx(hub_id: &str) -> RequestContext {
    RequestContext::new(
        hub_id,
        "u1",
        [
            SESSION.to_string(),
            "fiscal.configure".to_string(),
            "fiscal.issue".to_string(),
        ],
    )
}

/// A module that (a) asks the host for the `certificate` capability — the shape ADR-0203 keys the
/// second arm of the gate on — and (b) owns a command whose SQL stamps the hub's business identity,
/// which is the structural marker that puts that command behind the gate.
fn fiscal_module(id: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-route-gate-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::create_dir_all(dir.join("commands")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        json!({
            "id": id,
            "name": id,
            "version": "1.0.0",
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": [format!("{id}.configure"), format!("{id}.issue")],
            "queries": {
                format!("{id}.config.get"): {
                    "permission": format!("{id}.configure"),
                    "sql": "queries/config_get.sql"
                }
            },
            "commands": {
                format!("{id}.issue"): {
                    "permission": format!("{id}.issue"),
                    "transaction": true,
                    "sql": ["commands/issue.sql"]
                }
            },
            "setup": {
                "query": format!("{id}.config.get"),
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": format!("Configure {id}"),
                "route": format!("/m/{id}/settings"),
                "permission": format!("{id}.configure"),
                "order": 60
            }
        })
        .to_string(),
    )
    .unwrap();
    // The check never passes, so the item stays `pending` across the whole test and only its LEVEL
    // can move — which is exactly the thing under test.
    std::fs::write(dir.join("queries/config_get.sql"), "SELECT 0 AS ready").unwrap();
    // References `:business_legal_name`/`:business_tax_id`: that reference IS what tells the
    // dispatcher this statement issues a fiscal document.
    std::fs::write(
        dir.join("commands/issue.sql"),
        "INSERT INTO fiscal_doc (issuer_nif, issuer_name) \
         VALUES (:business_tax_id, :business_legal_name);",
    )
    .unwrap();
    dir
}

/// A hub with the business identity configured, the fiscal module installed and the requested
/// routes available. Its fiscal profile is pinned to **production**: since ADR-0360 (hub#1087) the
/// gate demands a way to sign in PRODUCTION only — in `testing` there is nothing to authorize.
async fn hub(hub_id: &str, routes: Routes) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    let mut pin = Params::new();
    pin.insert("hub_id".into(), json!(hub_id));
    rt.db()
        .execute(
            "INSERT INTO _hub_fiscal_profile (hub_id, system_id, environment) \
             VALUES (:hub_id, :hub_id, 'production') \
             ON CONFLICT (hub_id) DO UPDATE SET environment = 'production'",
            &pin,
        )
        .await
        .unwrap();
    rt.db()
        .execute_batch("CREATE TABLE fiscal_doc (issuer_nif TEXT, issuer_name TEXT);")
        .await
        .unwrap();

    let dir = fiscal_module("fiscal");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("ACME SL"));
    rt.set_settings(&up, "u1").await.unwrap();

    if routes.own_certificate {
        store_own_certificate(rt.db(), hub_id).await;
    }
    if routes.enrolled {
        enrol_machine_identity(rt.db(), hub_id).await;
    }
    rt
}

/// Writes the business's own slot straight into the system table. Going through the real writer
/// would need the process-global `HUB_SECRETS_KEY`, and what the readers look at is the PRESENCE
/// of the row, never its contents.
async fn store_own_certificate(db: &dyn DatabaseAdapter, hub_id: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(CertificateKind::Own.as_str()));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, 'v1:ciphertext', 'v1:ciphertext', '2026-09-03T09:00:00Z', 'x')",
        &p,
    )
    .await
    .expect("the own slot is stored");
}

/// Plants the three fields the cell road needs on this side — the same three
/// `gateway_identity::client_identity` demands before it will build an mTLS connection.
async fn enrol_machine_identity(db: &dyn DatabaseAdapter, hub_id: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert(
        "common_name".into(),
        json!(format!("hub-{hub_id}.fiscal.erplora.internal")),
    );
    db.execute(
        "INSERT INTO _hub_gateway_identity \
         (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
         VALUES (:hub_id, 'v1:ciphertext', '-----BEGIN CERTIFICATE-----\nhub\n-----END CERTIFICATE-----', \
                 '-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----', :common_name, \
                 '2026-09-03T09:00:00Z', '2026-09-03T09:00:00Z')",
        &p,
    )
    .await
    .expect("the machine identity is enrolled");
}

/// Reader 1+2 — the dispatcher's fiscal gate. `true` = the hub is allowed to issue.
async fn the_gate_accepts(rt: &Runtime, hub_id: &str) -> bool {
    match rt
        .execute_command("fiscal.issue", &Params::new(), &ctx(hub_id))
        .await
    {
        Ok(_) => true,
        Err(RuntimeError::FiscalPrecondition { missing }) => {
            assert_eq!(
                missing,
                vec!["certificate"],
                "the identity is configured: the only thing the gate may still miss is the way to sign"
            );
            false
        }
        Err(e) => panic!("unexpected dispatcher error: {e:?}"),
    }
}

/// Reader 3 — the ⛔ arm of the onboarding checklist. `true` = the checklist claims the runtime is
/// going to refuse (hub#370).
async fn the_checklist_blocks(rt: &Runtime, hub_id: &str) -> bool {
    let rows = rt
        .execute_query("hub.setup.status", &Params::new(), &ctx(hub_id))
        .await
        .expect("the core answers the setup status");
    let doc: &Json = &rows[0];
    let item = doc["items"]
        .as_array()
        .expect("`items` is an array")
        .iter()
        .find(|i| i["key"] == "fiscal.setup")
        .expect("the fiscal module contributes its setup item");
    // The item is `pending` in every state (its check never passes), so `legal` here means exactly
    // «⛔: the runtime will refuse», which is the claim hub#370 forbids making falsely.
    item["level"] == "legal"
}

/// **One hub, one answer** — whatever way out the hub has, the gate and the checklist say the same
/// thing, and what they say is «has it got a route?».
async fn assert_the_doors_agree(routes: Routes, expected_can_issue: bool) {
    let hub_id = "hub-route-gate";
    let rt = hub(hub_id, routes).await;

    let gate = the_gate_accepts(&rt, hub_id).await;
    let blocks = the_checklist_blocks(&rt, hub_id).await;

    assert_eq!(
        gate, expected_can_issue,
        "{routes:?}: the dispatcher gate does not answer «has this hub got a route?»"
    );
    assert_eq!(
        !blocks, expected_can_issue,
        "{routes:?}: the checklist ⛔ disagrees with the gate — a ⛔ that does not block, or a \
         rejection nobody warned about"
    );
}

/// 🔴 **The hub of hub#1489**: no `.p12` of its own, machine identity enrolled — it transmits
/// through the cell and ERPlora signs on its behalf. It must sell.
#[tokio::test]
async fn a_hub_on_the_cell_route_can_issue() {
    assert_the_doors_agree(CELL_ONLY, true).await;
}

/// The taxpayer who signs and files with their own certificate: unchanged, and still the answer
/// with no cell identity anywhere.
#[tokio::test]
async fn a_hub_with_its_own_certificate_can_issue() {
    assert_the_doors_agree(OWN_ONLY, true).await;
}

/// Both roads open is not a contradiction — `route_of` picks the own certificate — and it must not
/// be a refusal either.
#[tokio::test]
async fn a_hub_with_both_routes_can_issue() {
    assert_the_doors_agree(BOTH, true).await;
}

/// 🔒 **The fail-closed half of the acceptance criterion.** No certificate and nothing enrolled is
/// no way out at all: the gate refuses and the checklist says so. Without this test, «contemplate
/// the second route» would be indistinguishable from «stop checking».
#[tokio::test]
async fn a_hub_with_no_route_at_all_is_still_refused() {
    assert_the_doors_agree(NO_ROUTE, false).await;
}
