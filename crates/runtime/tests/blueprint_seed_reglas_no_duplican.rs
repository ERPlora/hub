//! Contrato: los datos de REFERENCIA que un módulo re-siembra en cada hub NO deben viajar en el
//! blueprint y duplicarse al restaurar. Complementa `import_test.rs`, que solo cubre
//! `taxes_category`/`taxes_category_alias` (marcadas `is_system`/`source='shipped'`), ya excluidas
//! por [`export::is_module_seeded`] (PR #191).
//!
//! Hueco que fija ESTE test: `taxes_rule` no lleva `is_system` NI `source` — el heurístico no la
//! reconocía y sus 6 reglas de IVA sembradas SÍ viajaban. Al importar sobre un hub que ya re-sembró
//! las suyas, el guard-por-`id` no las ve (el `id` embebe el hub ORIGEN: `h1|taxrule|…` vs el
//! destino `h2|taxrule|…`) → el destino acaba con 12 reglas y el lookup de IVA es AMBIGUO. No
//! revienta (`taxes_rule` no tiene índice único por clave natural), así que es un fallo SILENCIOSO
//! en un módulo fiscal — peor que un crash.
//!
//! Marcador uniforme de lo sembrado por el módulo: `created_by = 'system'` (lo pone
//! `apply_module_seed`). `hub_settings`/`hub_user` no tienen esa columna, así que excluir por ella
//! no les afecta.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;

fn modules_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

/// Un hub con `taxes` instalado (y por tanto su semilla aplicada) BAJO SU PROPIO `hub_id` —como en
/// producción. El test existente sembraba el destino bajo `h1` e importaba a `h2`, así que origen y
/// destino nunca compartían `(hub_id, …)` y el choque no salía.
async fn hub_con_taxes(hub_id: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt
}

async fn count(rt: &Runtime, sql: &str) -> i64 {
    let res = rt.db().query(sql, &Params::new()).await.expect("count");
    res.rows
        .first()
        .and_then(|r| r.get("n"))
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
}

/// Restaurar un blueprint sobre un hub que ya tiene su semilla NO duplica las reglas de IVA.
#[tokio::test]
async fn importar_blueprint_no_duplica_las_reglas_de_iva_sembradas() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // ORIGEN h1 → bundle con taxes (los `id` embeben 'h1'; created_by='system').
    let a = hub_con_taxes("h1").await;
    let selection = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "taxes".into(),
            with_data: true,
        }],
        purpose: Default::default(),
    };
    let bundle = export_hub(
        &a,
        "h1",
        &selection,
        "barberia",
        "es",
        "2026-07-11T18:00:00Z",
    )
    .await
    .expect("export h1");

    // DESTINO h2, sembrado bajo SU PROPIO hub_id: ya tiene sus 6 reglas ES.
    let mut b = hub_con_taxes("h2").await;
    assert_eq!(
        count(
            &b,
            "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'"
        )
        .await,
        6,
        "precondición: 6 reglas sembradas"
    );

    let import = ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into()],
    };
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import, "h2")
        .await
        .expect("best-effort");
    let taxes = report
        .sections
        .iter()
        .find(|s| s.section == "modules/taxes")
        .expect("taxes en informe");
    assert!(
        matches!(taxes.status, SectionStatus::Applied),
        "sección taxes: {:?}",
        taxes.status
    );

    // Las reglas de IVA sembradas NO se duplican: siguen siendo 6, y ES/product.generic es única.
    assert_eq!(
        count(
            &b,
            "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2'"
        )
        .await,
        6,
        "las reglas de IVA sembradas por el módulo se duplicaron al restaurar el blueprint",
    );
    assert_eq!(
        count(
            &b,
            "SELECT count(*) AS n FROM taxes_rule WHERE hub_id = 'h2' AND country_code = 'ES' \
             AND tax_category_key = 'product.generic' AND parent_id IS NULL AND is_deleted = 0",
        )
        .await,
        1,
        "IVA ambiguo: más de una regla activa para ES/product.generic tras importar el blueprint",
    );
}
