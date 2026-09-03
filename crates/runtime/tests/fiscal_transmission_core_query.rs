//! hub#1416 — `hub.fiscal.transmission`: **the core ANSWERS the route, the module PAINTS it.**
//!
//! ADR-0320 §1 gives a hub two EXCLUSIVE ways of reaching the tax authority: the taxpayer signs
//! and files with their own certificate (`own`), or ERPlora files on their behalf with its Sello
//! (`delegated`), which is what the signed Anexo I authorises. The core has decided that since
//! hub#1314 and shows it on its own settings screen — but no module could read it, so a fiscal
//! module's screen could not tell an operator which route their business is on, nor where their
//! grant stands (ERPlora/verifactu#41 is blocked on exactly this).
//!
//! Three properties this query owes its callers, one test each:
//!
//! 1. **The route comes from `certificate::route_of`, never re-derived.** `:has_certificate` is
//!    `can_transmit`, which answers «has this hub got a ROUTE?» (hub#1489): a hub enrolled on the
//!    cell answers `1` there and is on the DELEGATED route, so that 0/1 cannot tell the two roads
//!    apart. Deducing the route from it would be a second rule, and two rules is how the screen
//!    and `go_live` end up disagreeing about which route a business is on.
//! 2. **The grant is served from the MIRRORED copy** (`_hub_fiscal_profile`, hub#836), with no
//!    trip to the control plane. Whoever wants it refreshed opens Ajustes → Negocio, which is
//!    where the `GET` lives; a screen that fetched on every open would put a network call behind
//!    a paint.
//! 3. **It reads with a plain local session** (`hub.users.view`), the same gate as
//!    `hub.fiscal.limits` and for the same reason: the consumer is whoever is looking at the
//!    screen, not an administrator.

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::{json, Value as Json};

/// The `hub.` namespace gate: every principal with a LOCAL session carries it, an API key never
/// does.
const SESSION: &str = "hub.users.view";

const HUB: &str = "hub-a";

async fn runtime() -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt
}

fn ctx(permissions: &[&str]) -> RequestContext {
    RequestContext::new(HUB, "u1", permissions.iter().map(|p| p.to_string()))
}

/// Runs the query and returns the single document.
async fn transmission(rt: &Runtime) -> Json {
    let rows = rt
        .execute_query("hub.fiscal.transmission", &Params::new(), &ctx(&[SESSION]))
        .await
        .expect("the core answers the transmission route");
    assert_eq!(
        rows.len(),
        1,
        "the route is ONE document about this hub, not one row per fact"
    );
    rows.into_iter().next().unwrap()
}

/// Occupies one certificate slot. The bytes do not matter: «this slot holds a certificate» is
/// `pkcs12_b64 <> ''`, which is what the route reads.
async fn occupy_slot(rt: &Runtime, kind: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(HUB));
    p.insert("kind".into(), json!(kind));
    rt.db()
        .execute(
            "INSERT INTO _hub_certificate (hub_id, kind, pkcs12_b64, password, uploaded_at, \
             uploaded_by) VALUES (:hub_id, :kind, 'not-empty', '', '2026-09-01T09:00:00Z', 'test')",
            &p,
        )
        .await
        .unwrap();
}

/// The owner's own `.p12` puts the hub on its own road the moment it is uploaded — nothing to
/// reconfigure — and with it the Anexo I stops applying.
#[tokio::test]
async fn hub1416_an_own_certificate_puts_the_hub_on_its_own_route() {
    let rt = runtime().await;
    occupy_slot(&rt, "own").await;

    assert_eq!(transmission(&rt).await["transmission_route"], json!("own"));
}

/// 🔴 **The regression the issue asks for.** A hub with NO certificate reads `delegated`: it is the
/// road the fiscal cell serves (ADR-0320) and the one a screen has to offer by default. Answering
/// `own` there would send somebody with no certificate to a form they cannot finish, and take the
/// Anexo I panel away from the only business that actually needs one.
///
/// Since hub#1435 this is also the ONLY way to be on the delegated route: the slot that used to
/// hold ERPlora's `.p12` is retired, so «no certificate» and «the cell files for me» are the same
/// state. The route must NOT be re-derived from `can_transmit` — since hub#1489 that answers «has
/// a ROUTE», which an enrolled hub on this very road says `true` to.
#[tokio::test]
async fn hub1416_a_hub_with_no_certificate_at_all_reads_delegated() {
    let rt = runtime().await;

    let doc = transmission(&rt).await;
    assert_eq!(doc["transmission_route"], json!("delegated"));
    assert_eq!(
        doc["representation_status"],
        json!(""),
        "«never asked» is the empty string, not a state the hub invents"
    );
    assert_eq!(doc["representation_at"], json!(""));
}

/// The grant travels as the core stored it — every state, verbatim: the screen programs against
/// these words (ADR-0055 says a caller asserts on codes, never on prose), and `pendiente` and
/// `rechazado` are precisely the two that must NOT read as «you are covered».
#[tokio::test]
async fn hub1416_every_grant_state_travels_verbatim_with_its_instant() {
    let rt = runtime().await;

    for status in ["absent", "pendiente", "vigente", "rechazado", "revocado"] {
        erplora_runtime::fiscal_profile::record_representation(
            rt.db(),
            HUB,
            status,
            "2026-08-11T09:00:00Z",
        )
        .await
        .unwrap();

        let doc = transmission(&rt).await;
        assert_eq!(doc["representation_status"], json!(status));
        assert_eq!(doc["representation_at"], json!("2026-08-11T09:00:00Z"));
    }
}

/// The gate is the namespace's, and it is the SAME one `hub.fiscal.limits` uses: a local session
/// and nothing more. An API key carries no session permission and gets nothing.
#[tokio::test]
async fn hub1416_it_opens_with_a_local_session_and_closes_without_one() {
    let rt = runtime().await;

    let refused = rt
        .execute_query("hub.fiscal.transmission", &Params::new(), &ctx(&[]))
        .await;
    assert!(
        matches!(
            refused,
            Err(erplora_runtime::RuntimeError::PermissionDenied(ref p)) if p == SESSION
        ),
        "a principal with no local session is REFUSED by the namespace gate, and named: {refused:?}"
    );
}
