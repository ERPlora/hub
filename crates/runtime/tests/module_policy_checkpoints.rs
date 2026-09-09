#![allow(non_snake_case)] // los nombres gritan la parte que importa, como el resto de la batería
//! hub#1701 — un módulo declara DÓNDE puede el dueño poner una norma: `policies/*.checkpoint.json`.
//!
//! El contrato es **convención de carpeta, NO una clave del manifest**, por el mismo motivo que
//! `flows/` (ADR-0463) y `locales/`: la raíz del manifest es `additionalProperties: false`
//! (ADR-0286), así que una clave nueva le pondría suelo de versión de hub a **todo** módulo que la
//! declarase. Por carpeta, un módulo publica sin suelo y sin un solo aviso, y sus checkpoints
//! aparecen solos en el primer arranque tras esta release, porque `rehydrate_installed` vuelve a
//! pasar por el instalador en cada boot.
//!
//! ```text
//! policies/
//!   <nombre>.checkpoint.json   { "command": …, "facts": [ … ], "outcomes": [ … ] }
//! ```
//!
//! La carga es **best-effort** —esto sale de un zip de terceros y corre en cada arranque— pero
//! **no muda** (hub#1649): lo descartado sale con su código y su motivo, porque «este módulo no
//! declara ningún punto de control» y «lo declara y el hub lo ha tirado» se ven exactamente igual
//! desde el mostrador.
//!
//! 🔴 **La válvula de la denegación fail-closed vive AQUÍ.** El gate deniega si al ejecutar falta
//! un `fact` que el checkpoint declara (architecture/hub/policies.md §6.1). Para que eso no pueda
//! parar una caja por sorpresa, la carga rechaza un checkpoint cuyos `facts` el command **no
//! declara en su schema**: se ve al instalar, no en mitad de una venta.
use std::fs;
use std::path::{Path, PathBuf};

use erplora_runtime::manifest::Manifest;
use erplora_runtime::policies;

/// Carpeta temporal propia, como el resto de tests del runtime (no hay `tempfile` en dev-deps).
fn tmp_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-policy-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// Un módulo `sales` con UN command que declara su schema de payload.
fn write_module(dir: &Path) -> Manifest {
    fs::create_dir_all(dir.join("schemas")).unwrap();
    fs::write(
        dir.join("schemas/set_discount.json"),
        serde_json::to_string(&serde_json::json!({
            "type": "object",
            "properties": {
                "discount_percent": { "type": "number" },
                "order": { "type": "object" }
            }
        }))
        .unwrap(),
    )
    .unwrap();
    let manifest = serde_json::json!({
        "id": "sales",
        "name": "Sales",
        "version": "1.0.0",
        "commands": {
            "sales.order.set_discount": {
                "permission": "sales.add_sale",
                "schema": "schemas/set_discount.json",
                "sql": ["UPDATE sales_order SET discount = :discount_percent"]
            }
        }
    });
    fs::write(
        dir.join("module.json"),
        serde_json::to_string(&manifest).unwrap(),
    )
    .unwrap();
    Manifest::load(dir).unwrap()
}

fn write_checkpoint(dir: &Path, name: &str, body: serde_json::Value) {
    let folder = dir.join("policies");
    fs::create_dir_all(&folder).unwrap();
    fs::write(
        folder.join(format!("{name}.checkpoint.json")),
        serde_json::to_string(&body).unwrap(),
    )
    .unwrap();
}

#[test]
fn a_module_without_the_folder_declares_nothing_and_discards_nothing_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(
        scan.checkpoints.is_empty() && scan.discards.is_empty(),
        "un módulo sin `policies/` es el caso de 27 de 27 hoy: ni checkpoints ni descartes, {scan:?}"
    );
}

#[test]
fn a_well_formed_checkpoint_is_registered_under_module_slash_name_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "discount_limit",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.discards.is_empty(), "nada que descartar: {scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
    let cp = &scan.checkpoints[0];
    // `<módulo>/<nombre>` — el mismo nombre estable que `_flow.template_ref` (v60): es lo que el
    // módulo ya sabe de sí mismo y no cambia entre releases suyas.
    assert_eq!(cp.id, "sales/discount_limit");
    assert_eq!(cp.command, "sales.order.set_discount");
    assert_eq!(cp.facts, vec!["discount_percent".to_string()]);
}

#[test]
fn a_checkpoint_on_a_command_of_ANOTHER_module_is_refused_hub1701() {
    // Un módulo solo habla en su namespace — la misma regla del ABI de errores de dominio
    // (hub#139) y de la elevación (hub#351). Parar los commands de otro ya tiene su puerta, y es
    // `protects` (hub#775), que el módulo protegido conoce.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "foreign",
        serde_json::json!({
            "command": "inventory.stock.adjust",
            "facts": ["quantity"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_FOREIGN_COMMAND],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_on_a_command_the_manifest_does_not_declare_is_refused_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "ghost",
        serde_json::json!({
            "command": "sales.order.set_tip",
            "facts": ["tip"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_COMMAND_NOT_DECLARED],
        "{scan:?}"
    );
}

#[test]
fn a_fact_the_commands_schema_does_not_declare_is_refused_at_LOAD_hub1701() {
    // 🔴 Esta es la válvula que hace segura la denegación fail-closed del gate: un `fact` que el
    // command no puede aportar se ve al instalar, no en mitad de una venta.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "margin",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent", "margin_pct"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);

    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    let discard = scan.discards.first().expect("un descarte, {scan:?}");
    assert_eq!(discard.code, policies::DISCARD_FACT_NOT_DECLARED);
    assert!(
        discard.detail.contains("margin_pct"),
        "el motivo tiene que NOMBRAR el hecho que falta, o no se puede arreglar: {discard:?}"
    );
}

#[test]
fn a_nested_fact_is_accepted_by_its_ROOT_property_hub1701() {
    // `order.total` es un camino punteado del lenguaje congelado de los flujos: su raíz (`order`)
    // sí la declara el schema, y el resto lo resuelve `resolve_path`.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "order_total",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["order.total"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.discards.is_empty(), "{scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
}

#[test]
fn a_collection_fact_the_frozen_language_cannot_resolve_is_refused_hub1701() {
    // `lines[].margin_pct` NO lo resuelve `flows::def::resolve_path` (camino punteado a secas), así
    // que aceptarlo sería declarar un hecho que el gate no puede leer NUNCA → denegaría siempre.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "lines",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["order[].margin_pct"],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_INVALID_FACT_PATH],
        "{scan:?}"
    );
}

#[test]
fn a_command_without_a_payload_schema_cannot_carry_a_checkpoint_hub1701() {
    // Sin schema no hay `facts` que el command DECLARE, así que no hay nada contra lo que validar
    // la válvula de arriba — y el gate denegaría en cada ejecución.
    let dir = tmp_module();
    fs::write(
        dir.join("module.json"),
        serde_json::to_string(&serde_json::json!({
            "id": "sales", "name": "Sales", "version": "1.0.0",
            "commands": { "sales.void": { "permission": "sales.add_sale", "sql": ["DELETE FROM sales_order"] } }
        }))
        .unwrap(),
    )
    .unwrap();
    let manifest = Manifest::load(&dir).unwrap();
    write_checkpoint(
        &dir,
        "void",
        serde_json::json!({ "command": "sales.void", "facts": ["reason"], "outcomes": ["block"] }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_COMMAND_WITHOUT_SCHEMA],
        "{scan:?}"
    );
}

#[test]
fn an_unreadable_or_malformed_document_is_discarded_not_panicked_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    let folder = dir.join("policies");
    fs::create_dir_all(&folder).unwrap();
    fs::write(folder.join("broken.checkpoint.json"), "{ not json").unwrap();

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_INVALID_DOCUMENT],
        "{scan:?}"
    );
}

#[test]
fn an_outcome_outside_the_closed_vocabulary_is_refused_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "weird",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["allow"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_UNKNOWN_OUTCOME],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_may_still_declare_elevate_even_though_this_core_only_runs_block_hub1701() {
    // `elevate:<permiso>` ES vocabulario del contrato; lo que este core todavía no sabe es
    // EJECUTARLO (hub#1708). Tirar el checkpoint entero por nombrarlo dejaría al módulo sin su
    // `block`, que sí funciona — la puerta que se cierra es la de ESCRIBIR una política así.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "discount_limit",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": ["discount_percent"],
            "outcomes": ["block", "elevate:sales.discount.over_limit"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.discards.is_empty(), "{scan:?}");
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
}

#[test]
fn two_checkpoints_on_the_SAME_command_keep_only_the_first_by_name_hub1701() {
    // Dos gates sobre el mismo command harían que qué norma se aplica dependiese del orden en que
    // el sistema de ficheros devuelve las entradas. Se queda el primero por nombre y el otro se
    // dice; determinista entre dos arranques.
    let dir = tmp_module();
    let manifest = write_module(&dir);
    for name in ["b_second", "a_first"] {
        write_checkpoint(
            &dir,
            name,
            serde_json::json!({
                "command": "sales.order.set_discount",
                "facts": ["discount_percent"],
                "outcomes": ["block"]
            }),
        );
    }

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert_eq!(scan.checkpoints.len(), 1, "{scan:?}");
    assert_eq!(scan.checkpoints[0].id, "sales/a_first", "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_DUPLICATE_COMMAND],
        "{scan:?}"
    );
}

#[test]
fn a_checkpoint_with_no_facts_has_nothing_to_reason_about_hub1701() {
    let dir = tmp_module();
    let manifest = write_module(&dir);
    write_checkpoint(
        &dir,
        "empty",
        serde_json::json!({
            "command": "sales.order.set_discount",
            "facts": [],
            "outcomes": ["block"]
        }),
    );

    let scan = policies::scan_checkpoints(&dir, &manifest);
    assert!(scan.checkpoints.is_empty(), "{scan:?}");
    assert_eq!(
        scan.discards.iter().map(|d| d.code.as_str()).collect::<Vec<_>>(),
        vec![policies::DISCARD_NO_FACTS],
        "{scan:?}"
    );
}
