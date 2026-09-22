//! **hub#1935 — a hub that files for real does not charge a sale it cannot get to the AEAT.**
//!
//! Ioan's rule of 2026-09-19: every ticket has to REACH the tax authority. With the AEAT down the
//! till keeps charging — the road exists and the contingency queue files later. What must not
//! exist is a sale that will never be filed.
//!
//! Before this, the dispatcher's only fiscal gate on the certificate was ADR-0203's, and it sits on
//! the INVOICE (the SQL that stamps the issuer) with `has_certificate` as its question. Measured on
//! `origin/develop` (`fiscal_route_gate_hub1489`): `has_certificate` is «own certificate ∨ machine
//! identity enrolled» — it never looks at the representation grant, and the fiscal cell refuses a
//! `production` envelope whose token carries no grant (verifactu-gateway, `hub_not_authorized`). So
//! a live hub on ERPlora's road with no approved grant charged, invoiced and chained records that
//! never left; and a live hub with no road at all charged and lost the invoice in the dead-letter
//! (ADR-0203's own consequence: «a sale without identity still closes»).
//!
//! This walks the real chain — `sales` + `invoice` from the modules workspace, a provider of the
//! hub's regime, the real relay — through the doors a cashier uses.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, DatabaseAdapter, Params};
use erplora_runtime::certificate::CertificateKind;
use erplora_runtime::fiscal_profile::{self, FiscalStatus};
use erplora_runtime::{RequestContext, Runtime, RuntimeError};
use serde_json::json;

const HUB: &str = "hub-es-1935";

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
fn admin() -> RequestContext {
    RequestContext::new(HUB, "u1", ["*".to_string()])
}
fn wasm() -> bool {
    mdir("sales").join("dist/handler.wasm").exists()
        && mdir("invoice").join("dist/handler.wasm").exists()
}

/// The ways out a hub can have to the AEAT (ADR-0320 §1).
#[derive(Debug, Clone, Copy)]
struct Road {
    own_certificate: bool,
    enrolled: bool,
    grant_approved: bool,
}

const OWN: Road = Road {
    own_certificate: true,
    enrolled: false,
    grant_approved: false,
};
const CELL_WITH_GRANT: Road = Road {
    own_certificate: false,
    enrolled: true,
    grant_approved: true,
};
const NOTHING: Road = Road {
    own_certificate: false,
    enrolled: false,
    grant_approved: false,
};

/// A provider of the hub's regime: what makes the hub owe VeriFactu and what the core learns its
/// trigger events from. The runtime is business-free, so a stand-in with the same SHAPE as
/// `verifactu` (regime + `certificate` capability + a listener on `invoice.created`) is all the
/// gate can see.
fn provider_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-hub1935-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("commands")).unwrap();
    std::fs::create_dir_all(dir.join("queries")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        json!({
            "id": "fiscalprov",
            "name": "fiscalprov",
            "version": "1.0.0",
            "fiscal_regime": { "country": "ES", "regime": "verifactu" },
            "capabilities": { "certificate": { "purpose": "fiscal-sign" } },
            "permissions": ["fiscalprov.ingest", "fiscalprov.configure"],
            "queries": {
                "fiscalprov.config.get": {
                    "permission": "fiscalprov.configure",
                    "sql": "queries/config_get.sql"
                }
            },
            "commands": {
                "fiscalprov.ingest": {
                    "permission": "fiscalprov.ingest",
                    "sql": ["commands/ingest.sql"]
                }
            },
            "events": { "listen": {
                "invoice.created": { "command": "fiscalprov.ingest" },
                "fdoc.issued": { "command": "fiscalprov.ingest" }
            } },
            "setup": {
                "query": "fiscalprov.config.get",
                "configured_when": [{ "field": "ready", "truthy": true }],
                "title": "Configure fiscalprov",
                "route": "/m/fiscalprov/setup",
                "permission": "fiscalprov.configure",
                "order": 60
            }
        })
        .to_string(),
    )
    .unwrap();
    std::fs::write(dir.join("queries/config_get.sql"), "SELECT 1 AS ready").unwrap();
    std::fs::write(
        dir.join("commands/ingest.sql"),
        "INSERT INTO fiscalprov_record (source) VALUES ('invoice.created');",
    )
    .unwrap();
    dir
}

/// A module whose DECLARATIVE command issues a document the provider files (`fdoc.issued`): the
/// other dispatch path, next to the handler one the sale goes through.
fn declarative_document_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-hub1935-fdoc-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("commands")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        json!({
            "id": "fdoc",
            "name": "fdoc",
            "version": "1.0.0",
            "permissions": ["fdoc.issue"],
            "commands": {
                "fdoc.issue": {
                    "permission": "fdoc.issue",
                    "sql": ["commands/issue.sql"],
                    "emit": ["fdoc.issued"]
                }
            },
            "events": { "emits": ["fdoc.issued"] }
        })
        .to_string(),
    )
    .unwrap();
    std::fs::write(
        dir.join("commands/issue.sql"),
        "INSERT INTO fdoc_doc (source) VALUES ('fdoc.issue');",
    )
    .unwrap();
    dir
}

/// A Spanish hub with its identity, the real sales→invoice chain and a provider mounted.
async fn hub() -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.db()
        .execute_batch(
            "CREATE TABLE fiscalprov_record (source TEXT); CREATE TABLE fdoc_doc (source TEXT);",
        )
        .await
        .unwrap();
    for m in ["taxes", "inventory", "customers", "sales", "invoice"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("install {m}: {e}"));
    }
    let provider = provider_module();
    rt.install_from_dir(&provider).await.unwrap();
    std::fs::remove_dir_all(&provider).ok();
    let fdoc = declarative_document_module();
    rt.install_from_dir(&fdoc).await.unwrap();
    std::fs::remove_dir_all(&fdoc).ok();

    let mut identity = serde_json::Map::new();
    identity.insert("business_tax_id".into(), json!("B12345674"));
    identity.insert("business_legal_name".into(), json!("Bar Manolo SL"));
    rt.set_settings(&identity, "u1").await.unwrap();
    rt
}

async fn store_own_certificate(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("kind".into(), json!(CertificateKind::Own.as_str()));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :kind, 'v1:ciphertext', 'v1:ciphertext', '2026-09-19T09:00:00Z', 'x')",
        &p,
    )
    .await
    .expect("the own slot is stored");
}

async fn enrol_machine_identity(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert(
        "common_name".into(),
        json!(format!("hub-{HUB}.fiscal.erplora.internal")),
    );
    db.execute(
        "INSERT INTO _hub_gateway_identity \
         (hub_id, private_key_pem, certificate_pem, ca_pem, common_name, created_at, updated_at) \
         VALUES (:hub_id, 'v1:ciphertext', '-----BEGIN CERTIFICATE-----\nhub\n-----END CERTIFICATE-----', \
                 '-----BEGIN CERTIFICATE-----\nca\n-----END CERTIFICATE-----', :common_name, \
                 '2026-09-19T09:00:00Z', '2026-09-19T09:00:00Z')",
        &p,
    )
    .await
    .expect("the machine identity is enrolled");
}

async fn forget_machine_identity(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    db.execute(
        "DELETE FROM _hub_gateway_identity WHERE hub_id = :hub_id",
        &p,
    )
    .await
    .expect("the machine identity is forgotten");
}

async fn give_road(rt: &Runtime, road: Road) {
    if road.own_certificate {
        store_own_certificate(rt.db()).await;
    }
    if road.enrolled {
        enrol_machine_identity(rt.db()).await;
    }
    if road.grant_approved {
        fiscal_profile::record_representation(
            rt.db(),
            HUB,
            fiscal_profile::REPRESENTATION_VIGENTE,
            "2026-09-19T09:00:00Z",
        )
        .await
        .unwrap();
    }
}

/// A hub that went live **through the real door** (`go_live`), with the road it had then.
async fn live_hub(road: Road) -> Runtime {
    let rt = hub().await;
    give_road(&rt, road).await;
    rt.refresh_fiscal_profile().await.unwrap();
    rt.fiscal_go_live()
        .await
        .unwrap_or_else(|e| panic!("{road:?}: the hub goes live with its road: {e:?}"));
    let profile = rt.fiscal_profile().await.unwrap().unwrap();
    assert_eq!(profile.status, FiscalStatus::Active);
    assert_eq!(profile.environment, fiscal_profile::ENV_PRODUCTION);
    rt
}

/// A hub whose profile reads live in `production` with no road at all — the shape of a hub that went
/// live before the go-live asked for one. `go_live` cannot build it, so the row is written by hand.
async fn live_hub_that_never_had_a_road() -> Runtime {
    let rt = hub().await;
    rt.refresh_fiscal_profile().await.unwrap();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production' \
             WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
    rt
}

async fn cash_method_id(rt: &Runtime) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), &admin())
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub catalogue ships the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

/// The cashier presses «Cobrar»: exactly the payload shape the TPV sends.
async fn charge(rt: &Runtime, key: &str) -> Result<serde_json::Value, RuntimeError> {
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "idempotency_key": key,
            "payment_method_id": cash_method_id(rt).await,
            "tax_included": false,
            "items": [{ "product_name": "Café", "price": 200, "quantity": 1_000_000, "tax_rate": 21.0 }]
        })),
        &admin(),
    )
    .await
}

async fn sale_count(rt: &Runtime) -> usize {
    rt.execute_query("sales.list", &Params::new(), &admin())
        .await
        .unwrap()
        .len()
}

async fn invoice_count(rt: &Runtime) -> usize {
    rt.execute_query("invoice.list", &Params::new(), &admin())
        .await
        .unwrap()
        .len()
}

fn refused_with(result: Result<serde_json::Value, RuntimeError>) -> String {
    match result {
        Err(RuntimeError::Domain { code, .. }) => code,
        other => panic!("the sale must be refused with a domain code, got {other:?}"),
    }
}

/// What `hub.fiscal.transmission` — the core query the TPV reads before charging — says.
async fn filing_blocked(rt: &Runtime) -> serde_json::Value {
    let rows = rt
        .execute_query("hub.fiscal.transmission", &Params::new(), &admin())
        .await
        .expect("the core answers hub.fiscal.transmission");
    rows[0].clone()
}

// ── The refusals ─────────────────────────────────────────────────────────────────────────────

/// 🔴 **The case the issue names.** A live hub whose road is gone: nothing is charged, and the
/// refusal says WHAT is missing with a stable code the screen translates.
#[tokio::test]
async fn a_live_hub_with_no_road_does_not_charge() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub_that_never_had_a_road().await;

    let code = refused_with(charge(&rt, "hub1935-no-road").await);

    // The FIRST thing missing on ERPlora's road is the signed grant — the same order the go-live
    // says it in (hub#817).
    assert_eq!(code, fiscal_profile::NO_REPRESENTATION);
    assert_eq!(sale_count(&rt).await, 0, "nothing was charged");
}

/// 🔴 **What `has_certificate` could not see.** On ERPlora's road with the machine identity
/// enrolled, but the grant was revoked after the go-live: the cell would refuse every record.
#[tokio::test]
async fn a_live_hub_on_the_cell_whose_grant_was_revoked_does_not_charge() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(CELL_WITH_GRANT).await;
    fiscal_profile::record_representation(
        rt.db(),
        HUB,
        fiscal_profile::REPRESENTATION_REVOKED,
        "2026-09-19T10:00:00Z",
    )
    .await
    .unwrap();

    let code = refused_with(charge(&rt, "hub1935-revoked").await);

    assert_eq!(code, fiscal_profile::NO_REPRESENTATION);
    assert_eq!(sale_count(&rt).await, 0, "nothing was charged");
}

/// The other half of ERPlora's road: the grant is approved but the secure connection is gone.
#[tokio::test]
async fn a_live_hub_on_the_cell_that_lost_its_connection_does_not_charge() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(CELL_WITH_GRANT).await;
    forget_machine_identity(rt.db()).await;

    let code = refused_with(charge(&rt, "hub1935-no-connection").await);

    assert_eq!(code, erplora_runtime::certificate::GATEWAY_NOT_ENROLLED);
    assert_eq!(sale_count(&rt).await, 0, "nothing was charged");
}

/// The DECLARATIVE path is gated the same way: a command whose declared `emit` is a document the
/// provider files does not run on a live hub with no road, and nothing is written.
#[tokio::test]
async fn a_declarative_command_that_issues_a_document_is_refused_too() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub_that_never_had_a_road().await;

    let code = refused_with(
        rt.execute_command("fdoc.issue", &Params::new(), &admin())
            .await,
    );

    assert_eq!(code, fiscal_profile::NO_REPRESENTATION);
    let written = rt
        .db()
        .query("SELECT COUNT(*) AS c FROM fdoc_doc", &Params::new())
        .await
        .unwrap()
        .rows[0]["c"]
        .as_i64();
    assert_eq!(written, Some(0), "nothing was written");
}

// ── What keeps working ───────────────────────────────────────────────────────────────────────

/// Only what would OPEN a fiscal chain is refused. The rest of the till — here, a quick note for
/// the kitchen — keeps working on a hub with no road: stopping it would push the owner to work
/// around us, and none of it has anything to file.
#[tokio::test]
async fn a_live_hub_with_no_road_keeps_everything_that_files_nothing() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub_that_never_had_a_road().await;

    rt.execute_command(
        "sales.quick_notes.create",
        &params(json!({ "text": "Sin cebolla" })),
        &admin(),
    )
    .await
    .expect("a quick note files nothing and is never refused for the road");
}

/// ERPlora's road, complete: it charges, and the chain carries on to the invoice.
#[tokio::test]
async fn a_live_hub_on_the_cell_with_an_approved_grant_charges_and_invoices() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(CELL_WITH_GRANT).await;

    charge(&rt, "hub1935-cell-ok")
        .await
        .expect("the sale is charged");
    rt.drain_outbox().await.unwrap();

    assert_eq!(sale_count(&rt).await, 1);
    assert_eq!(
        invoice_count(&rt).await,
        1,
        "the invoice of that sale exists"
    );
}

/// The taxpayer's own certificate is a road on its own: no grant is asked for (ADR-0320 §1).
#[tokio::test]
async fn a_live_hub_with_its_own_certificate_charges_without_a_grant() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(OWN).await;

    charge(&rt, "hub1935-own")
        .await
        .expect("the sale is charged");

    assert_eq!(sale_count(&rt).await, 1);
}

/// In pruebas the road always exists (hub#1934): nothing here stops a sale in `testing`.
#[tokio::test]
async fn a_hub_in_testing_charges_with_no_road() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = hub().await;
    give_road(&rt, NOTHING).await;
    rt.refresh_fiscal_profile().await.unwrap();
    assert_eq!(
        rt.fiscal_profile().await.unwrap().unwrap().environment,
        fiscal_profile::ENV_TESTING
    );

    charge(&rt, "hub1935-testing")
        .await
        .expect("the sale is charged");

    assert_eq!(sale_count(&rt).await, 1);
}

/// 🔒 **Closing the door does not strand what already went through it.** A sale charged while the
/// road was open is still invoiced when the road breaks before the relay runs: the gate stops a
/// chain from OPENING, never one that is already open — the record waits for the road instead
/// (verifactu#111), rather than the invoice dying in the dead-letter.
#[tokio::test]
async fn a_sale_charged_before_the_road_broke_is_still_invoiced() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(CELL_WITH_GRANT).await;
    charge(&rt, "hub1935-before")
        .await
        .expect("the sale is charged");
    fiscal_profile::record_representation(
        rt.db(),
        HUB,
        fiscal_profile::REPRESENTATION_REVOKED,
        "2026-09-19T10:00:00Z",
    )
    .await
    .unwrap();

    rt.drain_outbox().await.unwrap();

    assert_eq!(
        invoice_count(&rt).await,
        1,
        "the charged sale keeps its invoice"
    );
    assert_eq!(rt.count_dead_events().await.unwrap(), 0);
}

// ── The TPV asks before charging ─────────────────────────────────────────────────────────────

/// **One rule, two readers.** The core query the TPV reads when it opens says the same thing the
/// dispatcher answers when it charges — and where the owner fixes it, taken from the provider's own
/// setup route so `sales` never names the fiscal module.
#[tokio::test]
async fn the_till_learns_before_charging_what_the_dispatcher_would_refuse() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(CELL_WITH_GRANT).await;
    let open = filing_blocked(&rt).await;
    assert_eq!(
        open["filing_blocked"],
        json!(""),
        "a road: nothing to say: {open}"
    );

    forget_machine_identity(rt.db()).await;
    let broken = filing_blocked(&rt).await;
    let refused = refused_with(charge(&rt, "hub1935-agree").await);

    assert_eq!(broken["filing_blocked"], json!(refused), "{broken}");
    assert_eq!(
        broken["filing_fix_route"],
        json!("/m/fiscalprov/setup"),
        "{broken}"
    );
}

// ── hub#1940: the own road with an expired certificate ───────────────────────────────────────

/// Every road at once: the own certificate AND ERPlora's cell with its grant, so the owner can
/// hand filing to ERPlora when their certificate runs out.
const OWN_AND_CELL: Road = Road {
    own_certificate: true,
    enrolled: true,
    grant_approved: true,
};

/// The own certificate's `notAfter`, as the upload door stores it, a day in the past.
async fn expire_own_certificate(db: &dyn DatabaseAdapter) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert(
        "not_after".into(),
        json!((chrono::Utc::now() - chrono::Duration::days(1))
            .format("%Y-%m-%dT%H:%M:%SZ")
            .to_string()),
    );
    db.execute(
        "UPDATE _hub_certificate SET not_after = :not_after WHERE hub_id = :hub_id AND kind = 'own'",
        &p,
    )
    .await
    .expect("the own certificate expired");
}

/// 🔴 **hub#1940.** A live hub signing with its own certificate lets it expire: the AEAT refuses
/// every record it would sign, so the till does not charge — and says WHY with its own code.
#[tokio::test]
async fn a_live_hub_whose_own_certificate_expired_does_not_charge() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(OWN).await;
    expire_own_certificate(rt.db()).await;

    let told = filing_blocked(&rt).await;
    let code = refused_with(charge(&rt, "hub1940-expired").await);

    assert_eq!(code, erplora_runtime::certificate::OWN_CERTIFICATE_EXPIRED);
    assert_eq!(
        told["filing_blocked"],
        json!(code),
        "the till was told first: {told}"
    );
    assert_eq!(sale_count(&rt).await, 0, "nothing was charged");
}

/// The way out the issue names besides renewing: hand filing to ERPlora. Switched off, the expired
/// certificate signs nothing and the sale goes through ERPlora's road.
#[tokio::test]
async fn handing_filing_to_erplora_charges_again_with_the_certificate_expired() {
    if !erplora_runtime::require_modules_workspace() || !wasm() {
        eprintln!("SKIP: modules workspace or handler.wasm missing");
        return;
    }
    let rt = live_hub(OWN_AND_CELL).await;
    expire_own_certificate(rt.db()).await;
    assert_eq!(
        refused_with(charge(&rt, "hub1940-before-switch").await),
        erplora_runtime::certificate::OWN_CERTIFICATE_EXPIRED
    );

    rt.set_business_certificate_use(false)
        .await
        .expect("ERPlora may file for this live hub: grant approved and connection enrolled");

    charge(&rt, "hub1940-after-switch")
        .await
        .expect("the sale is charged on ERPlora's road");
    assert_eq!(sale_count(&rt).await, 1);
}
