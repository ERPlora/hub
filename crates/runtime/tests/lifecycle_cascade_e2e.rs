//! Cascada de activación/desactivación (ADR-0128, decisión Ioan 2026-07-14).
//!
//! `depends_on` es un contrato DURO, y por tanto el invariante es: **activo ⇒ todas tus
//! dependencias activas**. El runtime lo mantiene solo, en las dos direcciones:
//!
//!  * **Desactivar arrastra hacia abajo.** Apagar `taxes` apaga a quien no puede vivir sin él
//!    (`inventory`, `sales`…). Los arrastrados caen como AUTO — quieren volver.
//!
//! ⚠️ **Este fichero se mide contra los módulos PUBLICADOS**, y su topología cambia: sales#25
//! (v2.16.36, 27/08) sacó `inventory` de `depends_on` de `sales` —pasa a capacidad OPCIONAL, para
//! que una peluquería de solo servicios no se lleve un almacén—, dejando `taxes` como única dura.
//! Las aserciones de abajo son las de ESE contrato. Lo cazó el job de hub#1216 a las horas de
//! publicarse; antes de él, un desajuste así no lo veía nadie automáticamente.
//!  * **Reactivar devuelve SOLO lo que cayó en cascada.** Lo que el admin apagó A MANO se
//!    respeta: fue su decisión.
//!  * **Activar arrastra hacia arriba.** Encender `sales` enciende sus dependencias.
//!  * Un módulo desactivado responde `ModuleInactive` (código `module_inactive`), que
//!    `queryOptional` trata como ausencia — un consumidor OBLIGATORIO nunca llega a preguntar,
//!    porque la cascada lo apagó con su dependencia.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{ModuleStatus, RequestContext, Runtime, RuntimeError};

fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// taxes ← inventory ← sales → customers (sales depende de los tres; inventory de taxes).
async fn hub_pos() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
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
    if !erplora_runtime::require_modules_workspace() { return; }
    let mut rt = hub_pos().await;
    rt.deactivate("taxes").await.unwrap();

    assert_eq!(status_of(&rt, "taxes"), ModuleStatus::Inactive, "el objetivo cae como decisión MANUAL");
    assert_eq!(status_of(&rt, "inventory"), ModuleStatus::InactiveAuto, "inventory depende de taxes → cae AUTO");
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::InactiveAuto, "sales depende (transitivamente) → cae AUTO");
    assert_eq!(status_of(&rt, "customers"), ModuleStatus::Active, "customers NO depende de taxes → sigue");
}

#[tokio::test]
async fn reactivar_devuelve_solo_lo_que_cayo_en_cascada() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let mut rt = hub_pos().await;
    // sales#25 (2.16.36): `inventory` es capacidad OPCIONAL, no dependencia dura — una peluquería
    // que solo vende servicios no puede llevarse un almacén que no quiere. La única dura es
    // `taxes`: sin regla fiscal ninguna venta cierra. Así que apagar inventory NO toca a sales.
    rt.deactivate("inventory").await.unwrap();
    assert_eq!(
        status_of(&rt, "sales"),
        ModuleStatus::Active,
        "sales ya NO depende de inventory (capacidad opcional, sales#25): sigue vendiendo servicios"
    );
    // Lo que sí lo arrastra es taxes.
    rt.deactivate("taxes").await.unwrap();
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::InactiveAuto, "taxes sigue siendo dura");

    // Reactivar taxes NO devuelve inventory (fue decisión del admin), pero sales sí vuelve: taxes
    // era su única dependencia dura.
    rt.activate("taxes").await.unwrap();
    assert_eq!(status_of(&rt, "inventory"), ModuleStatus::Inactive, "lo apagado A MANO se respeta");
    assert_eq!(status_of(&rt, "sales"), ModuleStatus::Active, "su única dep dura volvió → vuelve");
    assert_eq!(status_of(&rt, "customers"), ModuleStatus::Active, "customers es ajeno a esta cadena");
}

#[tokio::test]
async fn activar_arrastra_hacia_arriba() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let mut rt = hub_pos().await;
    rt.deactivate("inventory").await.unwrap();
    rt.deactivate("taxes").await.unwrap(); // → sales caído por taxes; inventory manual

    // Encender sales enciende lo que NECESITA — y desde sales#25 eso es `taxes`, no el catálogo.
    // `inventory` se queda apagado: era decisión del admin y sales ya no lo exige.
    rt.activate("sales").await.unwrap();
    for m in ["sales", "taxes"] {
        assert_eq!(status_of(&rt, m), ModuleStatus::Active, "{m} debe encenderse con sales");
    }
    assert_eq!(
        status_of(&rt, "inventory"),
        ModuleStatus::Inactive,
        "inventory es OPCIONAL (sales#25): encender sales no revierte la decisión del admin"
    );
}

#[tokio::test]
async fn query_a_modulo_desactivado_es_module_inactive() {
    if !erplora_runtime::require_modules_workspace() { return; }
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

#[tokio::test]
async fn modules_expone_depends_on_para_que_la_ui_avise_de_la_cascada() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // El toggle del shell debe LISTAR qué va a arrastrar ANTES de confirmar («desactivar taxes
    // también desactivará: inventory, sales…»). Para computar el grafo inverso en cliente, la
    // lista de módulos tiene que exponer las dependencias declaradas.
    let rt = hub_pos().await;
    let sales = rt.modules().into_iter().find(|m| m.id == "sales").unwrap();
    assert!(sales.depends_on.iter().any(|d| d == "taxes"), "sales debe declarar taxes");
    // ADR-0141: NO declara los satélites — la asociación la owna el satélite, no el pedido.
    // Y desde sales#25 tampoco `inventory`: es capacidad OPCIONAL, leída con `required: false`,
    // así que no puede aparecer aquí — si apareciera, la cascada volvería a arrastrar un almacén
    // a quien solo vende servicios.
    for no_dep in ["customers", "tables", "inventory"] {
        assert!(!sales.depends_on.iter().any(|d| d == no_dep), "sales no debe declarar {no_dep}");
    }
}
