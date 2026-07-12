//! E2E ROJOS (TDD, plan ADR-0113 Fase 2) del IMPORT de un blueprint en el hub.
//!
//! Contrato: `import_sections` restaura en el hub DESTINO las secciones seleccionadas de un
//! bundle (manifest + data/*.sql), estilo «migrate»: los módulos ya instalados (los instala el
//! server desde el manifest ANTES de llamar aquí), luego el SQL con el `hub_id` destino
//! inyectado. Garantías que fijan estos tests:
//!   - round-trip export→import = estado equivalente bajo el hub_id destino,
//!   - selectividad: solo se aplican las secciones marcadas (lo demás → Skipped),
//!   - BEST-EFFORT: una sección que falla se registra y NO rompe el resto (decisión Ioan:
//!     «si algo falla no se rompe, ignora y sigue adelante»),
//!   - integridad: sha256 que no casa o schema_version desconocida → rechazo SIN efectos,
//!   - un módulo del manifest no instalado en destino → su sección falla con motivo claro.
//!
//! Implementación = columna humano; estos tests van primero y FALLAN (unimplemented!).

use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use sha2::{Digest, Sha256};

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    format!("{:x}", h.finalize())
}

async fn fresh() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1"); // ctx y runtime comparten hub (como en prod)
    rt.install_from_dir(&modules_root().join("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory")).await.expect("instalar inventory");
    rt
}

async fn create_product(rt: &Runtime, hub: &str, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": 10 })),
        &ctx(hub),
    )
    .await
    .unwrap_or_else(|e| panic!("crear producto {name}: {e}"));
}

async fn product_names(rt: &Runtime, hub: &str) -> Vec<String> {
    // `execute_query` devuelve las filas directamente (Vec<Json>), sin envoltorio `rows`.
    let rows = rt
        .execute_query("inventory.products.list", &params(json!({})), &ctx(hub))
        .await
        .expect("listar productos");
    rows.iter().filter_map(|p| p["name"].as_str().map(str::to_string)).collect()
}

fn full_selection() -> ExportSelection {
    ExportSelection {
        users: true,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection { module_id: "taxes".into(), with_data: true },
            ModuleDataSelection { module_id: "inventory".into(), with_data: true },
        ],
    }
}

fn import_all() -> ImportSelection {
    ImportSelection {
        users: true,
        settings: true,
        fiscal: false,
        media: false,
        modules: vec!["taxes".into(), "inventory".into()],
    }
}

const CREATED_AT: &str = "2026-07-11T18:00:00Z";

/// Exporta desde un hub A poblado (h1) y devuelve el bundle listo para importar.
async fn exported_bundle() -> erplora_runtime::export::ExportBundle {
    let a = fresh().await;
    create_product(&a, "h1", "Café", "CAF").await;
    create_product(&a, "h1", "Té verde", "TEV").await;
    export_hub(&a, "h1", &full_selection(), "barberia", "es", CREATED_AT).await.expect("export A")
}

#[tokio::test]
async fn round_trip_restores_equivalent_state_under_target_hub_id() {
    let bundle = exported_bundle().await;

    // Hub destino B, tenant DISTINTO (h2), con los módulos ya instalados (paso del server).
    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B");

    // Las secciones seleccionadas se aplicaron.
    for section in ["modules/taxes", "modules/inventory"] {
        let r = report.sections.iter().find(|s| s.section == section).unwrap_or_else(|| panic!("sin resultado para {section}"));
        assert!(matches!(r.status, SectionStatus::Applied), "{section} no aplicada: {:?}", r.status);
    }

    // El estado es equivalente BAJO EL hub_id DESTINO (la query scoped por h2 lo demuestra:
    // si la sustitución del placeholder fallara, h2 no vería nada).
    let names = product_names(&b, "h2").await;
    assert!(names.contains(&"Café".to_string()) && names.contains(&"Té verde".to_string()),
        "productos no restaurados bajo h2: {names:?}");

    // Y ningún dato se coló bajo el hub_id de ORIGEN.
    let leaked = product_names(&b, "h1").await;
    assert!(leaked.is_empty(), "filas importadas bajo el hub_id de origen: {leaked:?}");
}

#[tokio::test]
async fn unselected_sections_are_skipped() {
    let bundle = exported_bundle().await;

    let mut b = fresh().await;
    let sel = ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["inventory".into()], // taxes NO seleccionado
    };
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &sel, "h2")
        .await
        .expect("import selectivo");

    let inv = report.sections.iter().find(|s| s.section == "modules/inventory").expect("inventory en informe");
    assert!(matches!(inv.status, SectionStatus::Applied));
    let taxes = report.sections.iter().find(|s| s.section == "modules/taxes").expect("taxes en informe");
    assert!(matches!(taxes.status, SectionStatus::Skipped), "taxes debía saltarse: {:?}", taxes.status);
    let users = report.sections.iter().find(|s| s.section == "hub_users").expect("hub_users en informe");
    assert!(matches!(users.status, SectionStatus::Skipped));

    // Los productos sí llegaron.
    let names = product_names(&b, "h2").await;
    assert!(names.contains(&"Café".to_string()));
}

#[tokio::test]
async fn best_effort_a_broken_section_does_not_abort_the_rest() {
    let mut bundle = exported_bundle().await;

    // Rompemos el SQL de taxes (sintaxis inválida) PERO con sha256 coherente: la integridad
    // pasa, la aplicación falla → best-effort: se registra y se sigue con inventory.
    let broken = b"THIS IS NOT SQL;".to_vec();
    bundle.manifest.sha256.insert("data/taxes.sql".into(), sha256_hex(&broken));
    bundle.files.insert("data/taxes.sql".into(), broken);

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("el import NO debe romperse por una sección rota");

    let taxes = report.sections.iter().find(|s| s.section == "modules/taxes").expect("taxes en informe");
    assert!(matches!(taxes.status, SectionStatus::Failed(_)), "taxes debía fallar: {:?}", taxes.status);
    let inv = report.sections.iter().find(|s| s.section == "modules/inventory").expect("inventory en informe");
    assert!(matches!(inv.status, SectionStatus::Applied), "inventory debía aplicarse igualmente");

    let names = product_names(&b, "h2").await;
    assert!(names.contains(&"Café".to_string()), "best-effort no aplicó el resto");
}

#[tokio::test]
async fn sha256_mismatch_rejects_the_import_without_effects() {
    let mut bundle = exported_bundle().await;
    // Manipulación del bundle: contenido cambiado sin actualizar el hash del manifest.
    bundle.files.insert("data/inventory.sql".into(), b"tampered".to_vec());

    let mut b = fresh().await;
    let res = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2").await;
    assert!(res.is_err(), "un bundle manipulado debe rechazarse entero");

    // Sin efectos: nada importado bajo el hub destino.
    let names = product_names(&b, "h2").await;
    assert!(names.is_empty(), "el rechazo dejó efectos: {names:?}");
}

#[tokio::test]
async fn unknown_schema_version_rejects_without_effects() {
    let mut bundle = exported_bundle().await;
    bundle.manifest.schema_version = 999;

    let mut b = fresh().await;
    let res = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2").await;
    assert!(res.is_err(), "schema_version desconocida debe rechazarse");
    assert!(product_names(&b, "h2").await.is_empty());
}

#[tokio::test]
async fn module_data_for_uninstalled_module_fails_its_section_only() {
    let bundle = exported_bundle().await;

    // Destino SIN inventory (solo taxes): la sección de inventory falla con motivo claro,
    // la de taxes se aplica. (Instalar módulos que faltan es del server, no de este motor.)
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut b = Runtime::with_hub_id(Box::new(db), "h1");
    b.install_from_dir(&modules_root().join("taxes")).await.expect("instalar taxes");

    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("best-effort también aquí");

    let inv = report.sections.iter().find(|s| s.section == "modules/inventory").expect("inventory en informe");
    assert!(matches!(&inv.status, SectionStatus::Failed(reason) if reason.contains("inventory")),
        "sección de módulo no instalado debía fallar nombrándolo: {:?}", inv.status);
    let taxes = report.sections.iter().find(|s| s.section == "modules/taxes").expect("taxes en informe");
    assert!(matches!(taxes.status, SectionStatus::Applied));
}
