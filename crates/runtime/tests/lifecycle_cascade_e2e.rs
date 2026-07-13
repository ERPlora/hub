//! Cascada de activación/desactivación (ADR-0128, decisión Ioan 2026-07-14).
//!
//! `depends_on` es un contrato DURO, y por tanto el invariante es: **activo ⇒ todas tus
//! dependencias activas**. El runtime lo mantiene solo, en las dos direcciones:
//!
//!  * **Desactivar arrastra hacia abajo.** Apagar `taxes` apaga a quien no puede vivir sin él
//!    (`inventory`, `sales`…). Los arrastrados caen como AUTO — quieren volver.
//!  * **Reactivar devuelve SOLO lo que cayó en cascada.** Lo que el admin apagó A MANO se
//!    respeta: fue su decisión.
//!  * **Activar arrastra hacia arriba.** Encender `sales` enciende sus dependencias.
//!  * Un módulo desactivado responde `ModuleInactive` (código `module_inactive`), que
//!    `queryOptional` trata como ausencia — un consumidor OBLIGATORIO nunca llega a preguntar,
//!    porque la cascada lo apagó con su dependencia.

use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{ModuleStatus, RequestContext, Runtime, RuntimeError};

fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules")
        .join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// taxes ← inventory ← sales → customers (sales depende de los tres; inventory de taxes).
async fn hub_pos() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    for m in ["taxes", "customers", "inventory", "sales"] {
        rt.install_from_dir(&mdir(m)).await.unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    rt
}

fn status_of(rt: &Runtime, id: &str) -> ModuleStatus {
    rt.modules().into_iter().find(|m| m.id == id).map(|m| m.status).unwrap()
}

#[tokio::test]
async fn desactivar_taxes_arrastra_a_sus_dependientes_activos() {
    let mut rt = hub_pos().await;
    rt.deactivate("taxes").await.unwrap();

    assert_eq!(status_of(&rt, "taxes"), ModuleStatus::Inactive, "el objetivo cae como decisión MANUAL");
    assert_eq!(status_of(&rt, "inventory"), ModuleStatus::InactiveAuto, "inventory depende de taxes → cae AUTO");
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::InactiveAuto, "sales depende (transitivamente) → cae AUTO");
    assert_eq!(status_of(&rt, "customers"), ModuleStatus::Active, "customers NO depende de taxes → sigue");
}

#[tokio::test]
async fn reactivar_devuelve_solo_lo_que_cayo_en_cascada() {
    let mut rt = hub_pos().await;
    // El admin apaga customers A MANO (su decisión) → sales cae en cascada.
    rt.deactivate("customers").await.unwrap();
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::InactiveAuto);
    // Y luego apaga taxes → inventory cae.
    rt.deactivate("taxes").await.unwrap();
    assert_eq!(status_of(&rt, "inventory"), ModuleStatus::InactiveAuto);

    // Reactivar taxes: vuelve inventory (cayó en cascada y sus deps ya están)…
    rt.activate("taxes").await.unwrap();
    assert_eq!(status_of(&rt, "inventory"), ModuleStatus::Active, "cayó AUTO y ya puede volver");
    // …pero NI sales (customers sigue apagado) NI customers (fue decisión del admin).
    assert_eq!(status_of(&rt, "customers"), ModuleStatus::Inactive, "lo apagado A MANO se respeta");
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::InactiveAuto, "sin customers no puede volver");

    // Al reactivar customers, sales revive solo (barrido a punto fijo).
    rt.activate("customers").await.unwrap();
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::Active, "todas sus deps activas → vuelve solo");
}

#[tokio::test]
async fn activar_arrastra_hacia_arriba() {
    let mut rt = hub_pos().await;
    rt.deactivate("customers").await.unwrap();
    rt.deactivate("taxes").await.unwrap(); // → inventory y sales caídos; customers manual

    // Encender sales enciende TODO lo que necesita, incluida la decisión manual sobre customers:
    // el admin acaba de pedir sales explícitamente, y sales no existe sin customers.
    rt.activate("sales").await.unwrap();
    for m in ["sales", "customers", "inventory", "taxes"] {
        assert_eq!(status_of(&rt, m), ModuleStatus::Active, "{m} debe encenderse con sales");
    }
}

#[tokio::test]
async fn query_a_modulo_desactivado_es_module_inactive() {
    let mut rt = hub_pos().await;
    rt.deactivate("taxes").await.unwrap();

    // El propio taxes: inactivo (instalado, con sus datos) ≠ no instalado.
    let err = rt
        .execute_query_page("taxes.rules.list", &Params::new(), &admin())
        .await
        .expect_err("taxes está desactivado");
    assert!(
        matches!(err, RuntimeError::ModuleInactive { ref module, .. } if module == "taxes"),
        "esperaba ModuleInactive, fue: {err:?}"
    );

    // Y el arrastrado también responde como inactivo (nunca como contrato roto).
    let err = rt
        .execute_query_page("sales.list", &Params::new(), &admin())
        .await
        .expect_err("sales cayó en cascada");
    assert!(matches!(err, RuntimeError::ModuleInactive { .. }), "fue: {err:?}");
}
