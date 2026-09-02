//! hub#319 — the certificate fallback `own` → `delegated`, and the THREE readers that have to
//! agree about it (ADR-0202 §2.1, ADR-0203).
//!
//! «Can this hub issue?» is asked in three places, and until hub#319 all three answered it by
//! looking at the **own** slot:
//!
//! 1. the dispatcher's fiscal gate (`commands::execute` → `RequestContext::has_certificate`),
//! 2. the same gate on the paged-query path (`queries::execute_page`),
//! 3. the ⛔ arm of the onboarding checklist (`hub.setup.status`, hub#370).
//!
//! While nothing could write a delegated certificate that was merely *strict*: a hub with no own
//! certificate was refused by the dispatcher **and** shown ⛔, which is uniform, honest and fails
//! closed. hub#317 made a delegated-only hub possible, and from that moment the three answers had
//! to move together — **to `certificate::can_sign`, all at once**. Moving one alone is what starts
//! the lie: a ⛔ that blocks a screen while the runtime accepts the sale, or a runtime that refuses
//! while the checklist says everything is done.
//!
//! So the test that matters here is not "the gate lets a delegated-only hub through". It is that
//! the three answers are **the same answer**, in every one of the four states a hub's two slots can
//! be in. That is what this file pins.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::{self, CertificateKind};
use erplora_runtime::native::DbHost;
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it.
const SESSION: &str = "hub.users.view";

/// The two slots a hub can hold, as the four states this test walks.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
struct Slots {
    own: bool,
    delegated: bool,
}

const NEITHER: Slots = Slots {
    own: false,
    delegated: false,
};
const OWN_ONLY: Slots = Slots {
    own: true,
    delegated: false,
};
const DELEGATED_ONLY: Slots = Slots {
    own: false,
    delegated: true,
};
const BOTH: Slots = Slots {
    own: true,
    delegated: true,
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
    if slots.delegated {
        store_slot(rt.db(), hub_id, CertificateKind::Delegated).await;
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

/// **The property of hub#319: one hub, one answer.** Whatever the two slots hold, the dispatcher
/// gate, the checklist and the fiscal engine say the same thing — and they say `can_sign`.
///
/// This is the assertion the issue asks for explicitly, and the reason it is ONE test rather than
/// three: the failure mode is not «a reader is wrong», it is «two readers stopped agreeing», and
/// that is invisible to any test that only looks at one of them.
async fn assert_the_readers_agree(slots: Slots, expected_can_issue: bool) {
    let hub_id = "hub-fallback";
    let rt = hub(hub_id, slots).await;

    let can_sign = certificate::can_sign(rt.db(), hub_id).await.unwrap();
    let gate = the_gate_accepts(&rt, hub_id).await;
    let blocks = the_checklist_blocks(&rt, hub_id).await;
    let engine = the_engine_can_sign(&rt, hub_id).await;

    assert_eq!(
        can_sign, expected_can_issue,
        "{slots:?}: the core's own answer to «can this hub sign?»"
    );
    assert_eq!(
        gate, can_sign,
        "{slots:?}: the dispatcher gate disagrees with `can_sign`"
    );
    assert_eq!(
        !blocks, can_sign,
        "{slots:?}: the checklist ⛔ disagrees with `can_sign` — a ⛔ that does not block, or a \
         rejection nobody warned about"
    );
    assert_eq!(
        engine, can_sign,
        "{slots:?}: `build_identity` disagrees with `can_sign` — the runtime would accept a sale \
         the fiscal engine then refuses to register, or the reverse"
    );
}

/// **A hub whose ONLY certificate is the delegated one can issue** — the whole point of ADR-0202
/// §2.1. Before hub#319 this hub was refused by the dispatcher and shown ⛔: strict, coherent, and
/// wrong, because ERPlora's certificate signs perfectly well on its behalf.
#[tokio::test]
async fn a_delegated_only_hub_can_issue_and_nothing_shows_a_blocking_warning() {
    assert_the_readers_agree(DELEGATED_ONLY, true).await;
}

/// The hub the fallback is a fallback FROM: its own certificate, exactly as before hub#316.
#[tokio::test]
async fn a_hub_with_its_own_certificate_can_issue() {
    assert_the_readers_agree(OWN_ONLY, true).await;
}

/// Both slots full: still one answer, and it is still «yes».
#[tokio::test]
async fn a_hub_holding_both_certificates_can_issue() {
    assert_the_readers_agree(BOTH, true).await;
}

/// **Neither slot: the hub still cannot issue.** The fallback widens what counts as a certificate,
/// it does not remove the requirement — an empty hub keeps failing CLOSED, and the checklist keeps
/// saying so.
#[tokio::test]
async fn a_hub_with_no_certificate_at_all_still_cannot_issue() {
    assert_the_readers_agree(NEITHER, false).await;
}

/// **The own certificate WINS, and the fallback is not a preference.** Both slots full ⇒ the
/// business's own certificate signs; delete it and the hub falls back to ERPlora's on the very next
/// question, with nothing to reconfigure in between.
#[tokio::test]
async fn the_own_certificate_wins_and_deleting_it_falls_back_without_reconfiguring() {
    let hub_id = "hub-fallback-order";
    let rt = hub(hub_id, BOTH).await;

    assert_eq!(
        certificate::active_kind(rt.db(), hub_id).await.unwrap(),
        Some(CertificateKind::Own),
        "with both slots full the business's own certificate signs"
    );

    certificate::delete(rt.db(), hub_id, CertificateKind::Own)
        .await
        .unwrap();

    assert_eq!(
        certificate::active_kind(rt.db(), hub_id).await.unwrap(),
        Some(CertificateKind::Delegated),
        "deleting your own certificate hands the hub to the delegated one"
    );
    // And the hub keeps INVOICING across that change — which is the difference between a fallback
    // and a setting: nobody had to answer a question.
    assert!(the_gate_accepts(&rt, hub_id).await);
    assert!(!the_checklist_blocks(&rt, hub_id).await);
}

/// **The delegated certificate still never leaves the hub** (hub#316, `may_leave_the_hub`).
///
/// This is the invariant hub#319 could most easily break by accident: a hub that now counts as
/// «has a certificate» must NOT start putting ERPlora's private key into a bundle. A bundle is
/// downloaded, published to the catalogue and imported into somebody else's hub — one leak would
/// compromise the whole fleet rather than one business.
#[tokio::test]
async fn a_delegated_only_hub_that_can_issue_still_exports_no_certificate() {
    let hub_id = "hub-fallback-export";
    let rt = hub(hub_id, DELEGATED_ONLY).await;

    assert!(
        certificate::can_sign(rt.db(), hub_id).await.unwrap(),
        "precondition: this hub can issue"
    );
    assert_eq!(
        certificate::exportable_der_bytes(rt.db(), hub_id)
            .await
            .unwrap(),
        None,
        "the delegated certificate is ERPlora's private key: it never travels in an export"
    );
}
