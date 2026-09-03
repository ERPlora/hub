//! hub#319 — «can this hub issue?» and the THREE readers that have to agree about it
//! (ADR-0202 §2.1, ADR-0203).
//!
//! «Can this hub issue?» is asked in three places, and until hub#319 all three answered it by
//! looking at the **own** slot:
//!
//! 1. the dispatcher's fiscal gate (`commands::execute` → `RequestContext::has_certificate`),
//! 2. the same gate on the paged-query path (`queries::execute_page`),
//! 3. the ⛔ arm of the onboarding checklist (`hub.setup.status`, hub#370).
//!
//! All three used to answer it by looking at the **own** slot directly, which was merely *strict*
//! while nothing else could sign. hub#317 added a second slot (ERPlora's delegated certificate) and
//! from that moment the three answers had to move together — **to one named function, all at
//! once**. Moving one alone is what starts the lie: a ⛔ that blocks a screen while the runtime
//! accepts the sale, or a runtime that refuses while the checklist says everything is done.
//!
//! **hub#1435 retired that second slot** and the hub is back to one — but the lesson is not: the
//! question still has three askers and they still have to answer identically, which is precisely
//! what a single named function makes structural. hub#1489 then renamed that function to what it
//! actually decides (`certificate::can_transmit` — «has this hub got a ROUTE?», its own certificate
//! or the enrolled cell identity), and the fourth reader parted company on purpose: the fiscal
//! ENGINE gates on the OWN certificate, because on the cell road it signs nothing. So the test that
//! matters here is not «which slot wins»; it is that the three core answers are **the same answer**,
//! in both states this fixture can be in.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, CertificateKind};
use erplora_runtime::native::DbHost;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it.
const SESSION: &str = "hub.users.view";

/// The two states a hub's certificate can be in, as this test walks them.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Slots {
    own: bool,
}

const NEITHER: Slots = Slots { own: false };
const OWN_ONLY: Slots = Slots { own: true };

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
    let dir = std::env::temp_dir().join(format!("erplora-cert-fallback-{}", uuid::Uuid::new_v4()));
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

/// A hub with the business identity configured, the fiscal module installed, and its two
/// certificate slots in the requested state. Its fiscal profile is pinned to **production**:
/// since ADR-0360 (hub#1087) the dispatcher gate demands the certificate in PRODUCTION only — in
/// `testing` there is nothing to authorize — so hub#319's «one hub, one answer» is asserted on
/// the environment where the certificate is still the question.
async fn hub(hub_id: &str, slots: Slots) -> Runtime {
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
        .execute_batch(
            "CREATE TABLE fiscal_doc (issuer_nif TEXT, issuer_name TEXT);\
             CREATE TABLE verifactu_config (\
               hub_id TEXT NOT NULL, environment TEXT NOT NULL DEFAULT 'testing', \
               is_deleted INTEGER NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();

    let dir = fiscal_module("fiscal");
    rt.install_from_dir(&dir).await.unwrap();
    std::fs::remove_dir_all(&dir).ok();

    let mut up = serde_json::Map::new();
    up.insert("business_tax_id".into(), json!("B12345674"));
    up.insert("business_legal_name".into(), json!("ACME SL"));
    rt.set_settings(&up, "u1").await.unwrap();

    if slots.own {
        store_slot(rt.db(), hub_id, CertificateKind::Own).await;
    }
    rt
}

/// Writes one slot straight into the system table. Going through the real writers would need the
/// process-global `HUB_SECRETS_KEY`, and what all three readers look at is the PRESENCE of the row,
/// never its contents.
async fn store_slot(db: &dyn DatabaseAdapter, hub_id: &str, kind: CertificateKind) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("kind".into(), json!(kind.as_str()));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, 'v1:ciphertext', 'v1:ciphertext', '2026-08-07T09:00:00Z', 'x')",
        &p,
    )
    .await
    .expect("the slot is stored");
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
                "the identity is configured: the only thing the gate may still miss is the certificate"
            );
            false
        }
        Err(e) => panic!("unexpected dispatcher error: {e:?}"),
    }
}

/// Reader 4 — the fiscal ENGINE (`build_identity`, `crates/plugins/verifactu`). `true` = the module would
/// go ahead and transmit to the AEAT.
///
/// Asked through the runtime's REAL host (`DbHost`), not a hand-written stand-in: a twin host would
/// be a second implementation of the very question under test, which is how the two readings of
/// «which certificate?» drifted apart twice already (hub#317, hub#318).
async fn the_engine_can_sign(rt: &Runtime, hub_id: &str) -> bool {
    let host = DbHost {
        db: rt.db(),
        storage: None,
        hub_id,
        module_id: "fiscal",
        static_folder: None,
    };
    erplora_verifactu::can_sign(&host, hub_id)
        .await
        .expect("the engine answers")
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

/// **The property of hub#319: one hub, one answer.** Whatever the hub holds, the dispatcher gate,
/// the checklist say the same thing — and they say `can_transmit`.
///
/// This is the assertion the issue asks for explicitly, and the reason it is ONE test rather than
/// three: the failure mode is not «a reader is wrong», it is «two readers stopped agreeing», and
/// that is invisible to any test that only looks at one of them.
async fn assert_the_readers_agree(slots: Slots, expected_can_issue: bool) {
    let hub_id = "hub-fallback";
    let rt = hub(hub_id, slots).await;

    let can_transmit = certificate::can_transmit(rt.db(), hub_id).await.unwrap();
    let gate = the_gate_accepts(&rt, hub_id).await;
    let blocks = the_checklist_blocks(&rt, hub_id).await;
    let engine = the_engine_can_sign(&rt, hub_id).await;

    assert_eq!(
        can_transmit, expected_can_issue,
        "{slots:?}: the core's own answer to «has this hub got a route?»"
    );
    assert_eq!(
        gate, can_transmit,
        "{slots:?}: the dispatcher gate disagrees with `can_transmit`"
    );
    assert_eq!(
        !blocks, can_transmit,
        "{slots:?}: the checklist ⛔ disagrees with `can_transmit` — a ⛔ that does not block, or a \
         rejection nobody warned about"
    );
    // The ENGINE answers a narrower question and must keep answering it (hub#1489): «can *I* sign
    // with a business certificate?», which is `build_identity`'s gate and only ever the own slot.
    // On the cell road the engine signs NOTHING — the cell does, with ERPlora's Seal — so tying
    // this to `can_transmit` would demand a certificate of the very hub that has no need of one.
    assert_eq!(
        engine, slots.own,
        "{slots:?}: `build_identity` must gate on the OWN certificate, no more and no less"
    );
}

/// The hub that has uploaded its own certificate: it issues, and all three readers say so.
#[tokio::test]
async fn a_hub_with_its_own_certificate_can_issue() {
    assert_the_readers_agree(OWN_ONLY, true).await;
}

/// **No certificate AND nothing enrolled: the hub cannot issue, and the three still agree.** An
/// empty hub fails CLOSED and the checklist says so — the honest, uniform answer.
///
/// ⚠️ «No certificate» is no longer the same thing as «no way out» (hub#1489): a hub on the fiscal
/// cell's road (ADR-0320 §1) holds no certificate either and files perfectly well, so what puts a
/// hub here is having NEITHER road. This fixture has no machine identity enrolled, which is what
/// keeps it in this state — `crates/runtime/tests/fiscal_route_gate_hub1489.rs` walks the other
/// one.
#[tokio::test]
async fn a_hub_with_no_certificate_at_all_still_cannot_issue() {
    assert_the_readers_agree(NEITHER, false).await;
}

/// **Deleting the certificate moves all three readers, on the very next question.** No cache, no
/// setting, nothing to reconfigure: the answer is the row, read fresh — which is what lets a
/// business swap its `.p12` mid-day without the checklist and the gate drifting apart for a while.
#[tokio::test]
async fn deleting_the_certificate_moves_the_three_readers_at_once() {
    let hub_id = "hub-fallback-order";
    let rt = hub(hub_id, OWN_ONLY).await;

    assert_eq!(
        certificate::active_kind(rt.db(), hub_id).await.unwrap(),
        Some(CertificateKind::Own)
    );
    assert!(the_gate_accepts(&rt, hub_id).await);
    assert!(!the_checklist_blocks(&rt, hub_id).await);

    certificate::delete(rt.db(), hub_id, CertificateKind::Own)
        .await
        .unwrap();

    assert_eq!(
        certificate::active_kind(rt.db(), hub_id).await.unwrap(),
        None,
        "the hub holds nothing: there is no second slot to fall back to (hub#1435)"
    );
    assert!(!the_gate_accepts(&rt, hub_id).await);
    assert!(the_checklist_blocks(&rt, hub_id).await);
}
