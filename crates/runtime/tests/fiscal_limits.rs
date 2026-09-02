//! hub#297 — `hub.fiscal.limits`: **the core ANSWERS, the till DECIDES.**
//!
//! The market decision of hub#297 asks the POS to refuse to close a ≥ 3.000,00 € sale as a
//! *ticket* when there is no recipient NIF. The naive way to build that is for the core to reject
//! `sale.completed` on fiscal grounds — and that is the version the issue rules out, because it
//! would be the core vetoing a business module and would couple the till to the fiscal plane.
//!
//! So the direction is inverted. The core states a **fact about the country** — "in ES a
//! simplified invoice cannot go over 3.000,00" — and the till is the one that chooses to block.
//! `sales` gains no dependency on `verifactu` (it still depends on `[inventory, taxes]`), and the
//! `sale.completed → invoice.created → ingest_invoice` chain is untouched.
//!
//! Three properties this query owes its callers, and each one is a test below:
//!
//! 1. **The ceiling is DATA, not code** (ADR-0273). It lives in `_hub_fiscal_regime_registry`
//!    next to the regime it belongs to, so France is one row the day it matters — not a `match`
//!    on country codes compiled into the runtime.
//! 2. **A country with no row has NO ceiling.** Not "3.000 by default": the absence of a rule is
//!    an answer, and inventing a Spanish limit for a Portuguese hub would block legitimate sales.
//! 3. **It reads with a plain local session.** The consumer is the cashier at the till, who holds
//!    no administrative permission. A gate the cashier cannot pass would make the whole feature
//!    unreachable exactly where it has to work.
//!
//! The wire-level twin of this rule (§15.8 in `crates/plugins/verifactu/src/xsd.rs`, hub#964) is
//! deliberately **not** this number: it validates against 3.010,00 (the ceiling plus the AEAT's
//! +10,00 rounding margin) because that is what the service really rejects. This query publishes
//! the ceiling itself, 3.000,00, because the till must never spend a tolerance that belongs to the
//! agency's own decimals. Two layers, two numbers, neither masking the other.
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::Value as Json;

/// The `hub.` namespace gate: every principal with a LOCAL session carries it
/// (`identity::session_permissions`), an API key never does.
const SESSION: &str = "hub.users.view";

async fn runtime(hub_id: &str) -> Runtime {
    let rt = Runtime::with_hub_id(Box::new(fresh_db().await), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt
}

fn ctx(hub_id: &str, permissions: &[&str]) -> RequestContext {
    RequestContext::new(hub_id, "u1", permissions.iter().map(|p| p.to_string()))
}

/// Runs the query and returns the single limits document.
async fn limits(rt: &Runtime, ctx: &RequestContext) -> Json {
    let rows = rt
        .execute_query("hub.fiscal.limits", &Params::new(), ctx)
        .await
        .expect("the core answers the fiscal limits");
    assert_eq!(
        rows.len(),
        1,
        "the limits are ONE document about this hub, not one row per limit"
    );
    rows.into_iter().next().unwrap()
}

/// Points the hub's country at `code`, the way a hub that finished its setup would.
async fn set_country(rt: &Runtime, hub_id: &str, code: &str) {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    p.insert("country".into(), serde_json::json!(code));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_profile SET country_code = :country WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
}

/// The seeded case, and the only one that ships today: a Spanish hub is told 3.000,00 €.
#[tokio::test]
async fn a_spanish_hub_is_told_the_simplified_invoice_ceiling() {
    let rt = runtime("hub-es").await;

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;

    assert_eq!(doc["country_code"], "ES");
    assert_eq!(doc["regime"], "verifactu");
    assert_eq!(
        doc["simplified_invoice_max_cents"], 300_000,
        "3.000,00 € in cents — the ceiling itself, NOT the 3.010,00 the wire tolerates"
    );
}

/// Property 2. A country nobody has written a row for owes nothing, and saying `null` is the only
/// honest way to say it: a `0` would read as "everything is over the limit" and stop every sale.
#[tokio::test]
async fn a_country_with_no_row_has_no_ceiling_at_all() {
    let rt = runtime("hub-pt").await;
    set_country(&rt, "hub-pt", "PT").await;

    let doc = limits(&rt, &ctx("hub-pt", &[SESSION])).await;

    assert_eq!(doc["country_code"], "PT");
    assert_eq!(doc["regime"], "", "no regime registered for PT");
    assert!(
        doc["simplified_invoice_max_cents"].is_null(),
        "no row means NO ceiling — not a Spanish one borrowed by default: {doc:?}"
    );
}

/// Property 1, and the reason the column is on the registry rather than in a `match`: moving the
/// number is moving a row. Nobody rebuilds the runtime to follow a change in the law.
#[tokio::test]
async fn the_ceiling_is_a_row_anybody_can_move() {
    let rt = runtime("hub-es").await;
    let mut p = Params::new();
    p.insert("max".into(), serde_json::json!(400_00));
    rt.db()
        .execute(
            "UPDATE _hub_fiscal_regime_registry SET simplified_invoice_max_cents = :max \
             WHERE country_code = 'ES'",
            &p,
        )
        .await
        .unwrap();

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;

    assert_eq!(
        doc["simplified_invoice_max_cents"], 40_000,
        "the answer follows the row, so the ceiling is data and not code"
    );
}

/// A registered country that declares no ceiling is `null` too — `0` in the column means "this
/// regime does not cap the simplified invoice", never "cap it at zero".
#[tokio::test]
async fn a_regime_without_a_ceiling_answers_null_not_zero() {
    let rt = runtime("hub-fr").await;
    set_country(&rt, "hub-fr", "FR").await;
    rt.db()
        .execute(
            "INSERT INTO _hub_fiscal_regime_registry (country_code, regime_key, since, note) \
             VALUES ('FR', 'chorus', '', 'test')",
            &Params::new(),
        )
        .await
        .unwrap();

    let doc = limits(&rt, &ctx("hub-fr", &[SESSION])).await;

    assert_eq!(doc["regime"], "chorus");
    assert!(
        doc["simplified_invoice_max_cents"].is_null(),
        "a regime that caps nothing must not read as a cap of zero: {doc:?}"
    );
}

/// Property 3. The consumer is the cashier, not the owner — the person who cannot fix anything is
/// exactly the person this answer is for.
#[tokio::test]
async fn the_cashier_can_read_it_without_administering_the_hub() {
    let rt = runtime("hub-es").await;

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;

    assert_eq!(doc["simplified_invoice_max_cents"], 300_000);
}

/// …and an API key, which carries no local session, still does not get into the `hub.` namespace.
/// Same gate as the rest of the core queries; this one does not punch a new hole in it.
#[tokio::test]
async fn a_principal_without_a_local_session_is_refused() {
    let rt = runtime("hub-es").await;

    let err = rt
        .execute_query("hub.fiscal.limits", &Params::new(), &ctx("hub-es", &[]))
        .await
        .expect_err("no local session, no core namespace");

    assert!(
        err.to_string().contains("hub.users.view"),
        "the refusal must name the permission it wanted: {err}"
    );
}

/// A name that does not exist in the core namespace is a BROKEN CONTRACT, not an absent module:
/// `hub.fiscal.whatever` must blow up rather than come back empty, because `queryOptional` forgives
/// an absent module and would swallow a typo forever.
#[tokio::test]
async fn a_neighbouring_name_in_the_namespace_is_still_not_found() {
    let rt = runtime("hub-es").await;

    let err = rt
        .execute_query(
            "hub.fiscal.ceiling",
            &Params::new(),
            &ctx("hub-es", &[SESSION]),
        )
        .await
        .expect_err("`hub.fiscal.ceiling` does not exist");

    assert!(
        err.to_string().contains("hub.fiscal.ceiling"),
        "the error must name the query that does not exist: {err}"
    );
}

// ── Quién ESCRIBE el techo: el módulo fiscal del país, no una migración del core (hub#1010) ──
//
// La v51 sembró `ES/verifactu → 300000` desde una migración de sistema. Eso deja al core sabiendo
// el número de un país concreto — justo lo que ADR-0357 quería evitar («el techo es DATO, no
// código»): la propiedad del dato queda al revés. Quien conoce el límite de la factura
// simplificada es el módulo que implementa el régimen, que además se actualiza solo en cada
// arranque; la ley cambia el número sin tocar el runtime ni migrar nada.
//
// La query sigue en el core (ADR-0357: la respuesta no puede depender de que un módulo esté
// instalado) y la v51 sigue como suelo transitorio para el hub que aún no ha actualizado su
// `verifactu`. Lo único que cambia es quién escribe la fila.

/// Instalar un proveedor que declara su techo lo escribe en el registro del core.
#[tokio::test]
async fn a_fiscal_module_declares_the_ceiling_and_the_core_stores_it() {
    let rt = runtime("hub-es").await;
    // El suelo transitorio de la v51: lo que hay antes de que ningún módulo hable.
    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;
    assert_eq!(doc["simplified_invoice_max_cents"], 300_000);

    rt.apply_fiscal_regime_declaration("ES", "verifactu", Some(250_000))
        .await
        .expect("un proveedor puede declarar el techo de su régimen");

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;
    assert_eq!(
        doc["simplified_invoice_max_cents"], 250_000,
        "manda lo que declara el módulo del país, no la migración del core"
    );
}

/// Y un proveedor que NO declara techo no pisa el que ya había: callarse no es decir «cero».
#[tokio::test]
async fn a_provider_that_declares_no_ceiling_leaves_the_row_alone() {
    let rt = runtime("hub-es").await;

    rt.apply_fiscal_regime_declaration("ES", "verifactu", None)
        .await
        .expect("declarar el régimen sin techo es legítimo");

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;
    assert_eq!(
        doc["simplified_invoice_max_cents"], 300_000,
        "el silencio del módulo no borra el techo vigente"
    );
}

/// El país es la clave: un proveedor francés no mueve el techo español.
#[tokio::test]
async fn a_provider_of_another_country_does_not_move_this_countrys_ceiling() {
    let rt = runtime("hub-es").await;

    rt.apply_fiscal_regime_declaration("FR", "facturx", Some(100_000))
        .await
        .expect("declarar el régimen de otro país es legítimo");

    let doc = limits(&rt, &ctx("hub-es", &[SESSION])).await;
    assert_eq!(doc["simplified_invoice_max_cents"], 300_000);
}
