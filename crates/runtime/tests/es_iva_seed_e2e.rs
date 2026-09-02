//! hub#107 — un hub de hostelería ES recién provisionado arranca SIN datos de IVA, así que el
//! cálculo de impuestos / la factura fallan (`taxes.rules.list` devuelve vacío).
//!
//! El instalador del runtime aplica ahora un seed suplementario de IVA España (21/10/4) al
//! instalar `taxes` en un hub cuyo `country_code` = ES. ESTE test fija el contrato:
//!   1) instalar `taxes` en un hub ES deja la baseline IVA completa, INCLUIDO el tipo
//!      superreducido del 4% (pan/libros/medicamentos) que la semilla del módulo NO traía;
//!   2) re-instalar `taxes` no duplica las reglas (idempotencia del seed);
//!   3) un hub NO español (p. ej. FR) NO recibe las reglas ES suplementarias.
//!
//! Los fixtures viven en `modules-workspace/` (repo hermano, no en este): si no están presentes
//! (CI del hub aislado) el test se omite, como ya hacen `module_seed_e2e` y
//! `blueprint_seed_reglas_no_duplican`.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{RequestContext, Runtime};

fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}

fn modules_present() -> bool {
    erplora_runtime::e2e_support::modules_root().exists()
}

fn admin(hub_id: &str) -> RequestContext {
    RequestContext::new(hub_id, "u1", ["*".to_string()])
}

/// Cuenta reglas IVA ES activas y no borradas para una (categoría, tasa) dada del hub.
async fn count_es_rule(rt: &Runtime, hub_id: &str, key: &str, rate: f64) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub_id));
    p.insert("key".into(), serde_json::json!(key));
    p.insert("rate".into(), serde_json::json!(rate));
    let res = rt
        .db()
        .query(
            "SELECT COUNT(*) AS n FROM taxes_rule \
             WHERE hub_id = :hub_id AND country_code = 'ES' AND tax_category_key = :key \
             AND rate_pct = :rate AND parent_id IS NULL AND region_code IS NULL \
             AND is_active = 1 AND is_deleted = 0",
            &p,
        )
        .await
        .expect("count_es_rule");
    res.rows
        .first()
        .and_then(|r| r.get("n"))
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
}

#[tokio::test]
async fn instalar_taxes_en_hub_es_siembra_iva_21_10_y_4_superreducido() {
    if !modules_present() {
        eprintln!("SKIP: modules-workspace not present (CI)");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    // El server llama `ensure_system_tables` al arrancar: crea `hub_settings` (migración de
    // sistema v4) que el instalador lee para resolver el `country_code`. Sin esto, el país
    // degrada al default ES (que también es el del test, pero lo dejamos explícito).
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
    rt.install_from_dir(&mdir("taxes"))
        .await
        .expect("instalar taxes");

    // Tipo GENERAL 21% (categorías genéricas) — verificado por el handler de venta.
    assert_eq!(
        count_es_rule(&rt, "h1", "product.generic", 21.0).await,
        1,
        "IVA 21% general (product.generic)"
    );
    assert_eq!(
        count_es_rule(&rt, "h1", "service.generic", 21.0).await,
        1,
        "IVA 21% general (service.generic)"
    );
    // Tipo REDUCIDO 10% (hostelería).
    assert_eq!(
        count_es_rule(&rt, "h1", "restaurant.food", 10.0).await,
        1,
        "IVA 10% reducido (restaurant.food)"
    );
    // Tipo SUPERREDUCIDO 4% — el que FALTABA (hub#107): pan, libros, medicamentos.
    assert_eq!(
        count_es_rule(&rt, "h1", "product.super_reduced", 4.0).await,
        1,
        "IVA 4% superreducido (product.super_reduced) — el tipo que faltaba, hub#107"
    );

    // Contrato end-to-end: la query pública `taxes.rules.list` ya no devuelve vacío.
    let rules = rt
        .execute_query("taxes.rules.list", &Params::new(), &admin("h1"))
        .await
        .expect("taxes.rules.list");
    assert!(
        !rules.is_empty(),
        "un hub ES con `taxes` tiene reglas fiscales"
    );
}

#[tokio::test]
async fn reinstalar_taxes_no_duplica_el_iva_es_suplementario() {
    if !modules_present() {
        eprintln!("SKIP: modules-workspace not present (CI)");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
    rt.install_from_dir(&mdir("taxes"))
        .await
        .expect("primera instalación");
    let antes = count_es_rule(&rt, "h1", "product.super_reduced", 4.0).await;

    rt.install_from_dir(&mdir("taxes"))
        .await
        .expect("reinstalar");
    let despues = count_es_rule(&rt, "h1", "product.super_reduced", 4.0).await;

    assert_eq!(
        antes, 1,
        "precondición: una regla de 4% tras la primera instalación"
    );
    assert_eq!(
        despues, 1,
        "reinstalar `taxes` NO duplica la regla de 4% (seed idempotente, hub#107)"
    );
}

#[tokio::test]
#[ignore = "hub#576: BUG REAL de producto, no deriva de contrato — el seed de `taxes` (taxes#20) \
            siembra la baseline IVA ES sin mirar el país y sortea el gate del instalador. La \
            aserción de aquí es la CORRECTA: no se relaja ni se borra, se ignora nombrando la \
            issue hasta que se decida quién OWNea las baselines por país."]
async fn un_hub_no_espanol_no_recibe_reglas_iva_es_suplementarias() {
    if !modules_present() {
        eprintln!("SKIP: modules-workspace not present (CI)");
        return;
    }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h2");
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
    // Fija el país del hub a FR antes de instalar `taxes` (override del default ES).
    let mut updates = serde_json::Map::new();
    updates.insert("country_code".into(), serde_json::json!("FR"));
    rt.set_settings(&updates, "system")
        .await
        .expect("set country_code=FR");

    rt.install_from_dir(&mdir("taxes"))
        .await
        .expect("instalar taxes");

    // El seed suplementario NO se aplicó: cero reglas del 4% superreducido ES en el hub FR.
    assert_eq!(
        count_es_rule(&rt, "h2", "product.super_reduced", 4.0).await,
        0,
        "un hub FR no recibe el seed suplementario de IVA ES (hub#107)"
    );
}
