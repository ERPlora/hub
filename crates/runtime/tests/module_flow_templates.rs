//! hub#1611 — las automatizaciones que un módulo trae DE FÁBRICA tienen que llegar al hub.
//!
//! Un módulo publica sus plantillas en una carpeta `flows/` de su paquete y desde
//! `module-toolkit#209` esa carpeta **viaja dentro del zip**; el extractor de `erplora-source` no
//! filtra entradas, así que al instalar **ya aterriza en disco**. Lo que faltaba es lo de aquí: que
//! el runtime la LEA. Mientras no la lea, la única forma de que una plantilla de módulo llegue a un
//! cliente es copiarla a mano en la galería del módulo `flows`, y esa copia se quedó atrás tres
//! veces en un solo día (06/09).
//!
//! El contrato de la carpeta lo fijó ERPlora/hub#1611 y es **convención de carpeta, NO una clave
//! del manifest**: la raíz del manifest es un contrato cerrado (`additionalProperties: false`,
//! ADR-0286), así que una clave nueva le pondría un suelo de versión de hub a cada módulo que la
//! declarase. Por carpeta —como `locales/`— un módulo publica sin suelo y sin un solo aviso, y sus
//! plantillas **aparecen solas** en el primer arranque tras esta release, porque
//! `Runtime::rehydrate_installed` vuelve a pasar por el instalador en cada boot.
//!
//! ```text
//! flows/
//!   <family>.en.flow.json     documento, idioma FUENTE (ADR-0055/0199)      OBLIGATORIO
//!   <family>.es.flow.json     su traducción                                 OBLIGATORIO
//!   <family>.<lang>.flow.json más idiomas                                   opcional
//!   <family>.grants.json      { "grants": [ { kind, value }, … ] }          OBLIGATORIO
//!   <family>.requires.json    { "modules": { "<id>": "<SemVer>" } }         opcional
//!   *.md                      documentación                                 opcional
//! ```
//!
//! Lo que `erplora validate` ya garantiza antes de publicar (y por tanto NO se re-defiende aquí):
//! el documento cumple `schemas/flow.schema.json` de este repo, toda familia trae `en` **y** `es`,
//! y todos los idiomas declaran los mismos pasos en el mismo orden con la misma maquinaria —solo
//! cambia la prosa—. Lo que este lado sí tiene que sostener es que un paquete **malformado o
//! ajeno** no rompa el arranque: esto se lee de un zip de terceros, y la carga es best-effort
//! exactamente como `load_locales`.
use std::fs;
use std::path::{Path, PathBuf};

use erplora_runtime::manifest::Manifest;

/// Carpeta temporal propia, como el resto de tests del runtime (no hay `tempfile` en dev-deps).
fn tmp_module() -> PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-flowtpl-{}", uuid::Uuid::new_v4()));
    fs::create_dir_all(&dir).unwrap();
    dir
}

/// Escribe una familia completa (en + es + grants) en `<dir>/flows/`.
fn write_family(dir: &Path, family: &str) {
    let flows = dir.join("flows");
    fs::create_dir_all(&flows).unwrap();
    for (lang, title) in [
        ("en", "Book from WhatsApp"),
        ("es", "Reservar por WhatsApp"),
    ] {
        let doc = serde_json::json!({
            "schema_version": 1,
            "name": title,
            "triggers": [{ "kind": "event", "event": "whatsapp_inbox.message.received" }],
            "steps": [{ "id": "s1", "kind": "command", "command": "appointments.appointments.create" }]
        });
        fs::write(
            flows.join(format!("{family}.{lang}.flow.json")),
            serde_json::to_string(&doc).unwrap(),
        )
        .unwrap();
    }
    let grants = serde_json::json!({
        "_doc": "lo que la plantilla pedirá al dueño",
        "grants": [{ "kind": "command", "value": "appointments.appointments.create" }]
    });
    fs::write(
        flows.join(format!("{family}.grants.json")),
        serde_json::to_string(&grants).unwrap(),
    )
    .unwrap();
}

#[test]
fn a_module_ships_its_automations_and_the_runtime_reads_them() {
    let dir = tmp_module();
    write_family(dir.as_path(), "appointment-from-whatsapp");

    let found = Manifest::load_flow_templates(dir.as_path());

    assert_eq!(found.len(), 1, "la familia de la carpeta se lee");
    let tpl = &found[0];
    assert_eq!(tpl.family, "appointment-from-whatsapp");
    // Los dos idiomas obligatorios llegan, y el nombre sale del documento de CADA uno: es lo que
    // deja al hub servir el idioma del negocio sin cotejar nada.
    assert_eq!(tpl.documents.len(), 2, "en + es");
    assert!(tpl.documents.contains_key("en") && tpl.documents.contains_key("es"));
    assert_eq!(
        tpl.grants.len(),
        1,
        "los permisos que la plantilla pedirá viajan con ella"
    );
}

#[test]
fn the_version_floor_is_per_template_and_never_the_modules_depends_on() {
    // `whatsapp_inbox` fija `appointments >= 1.1.69` para SU plantilla y su `depends_on` es solo
    // `["customers"]`: la plantilla es opcional y el módulo funciona sin ella. Si el suelo se
    // leyera del `depends_on`, instalar el módulo exigiría un vecino que no necesita.
    let dir = tmp_module();
    write_family(dir.as_path(), "appointment-from-whatsapp");
    let requires = serde_json::json!({ "modules": { "appointments": "1.1.69" } });
    fs::write(
        dir.as_path()
            .join("flows/appointment-from-whatsapp.requires.json"),
        serde_json::to_string(&requires).unwrap(),
    )
    .unwrap();

    let found = Manifest::load_flow_templates(dir.as_path());

    assert_eq!(
        found[0].requires.get("appointments").map(String::as_str),
        Some("1.1.69"),
        "el suelo de versión es POR PLANTILLA"
    );
}

#[test]
fn a_family_without_its_grants_sidecar_is_not_offered() {
    // Un grant es lo que abre la puerta de verdad (ADR-0283 §2). Una plantilla sin su sidecar es
    // una automatización que se instalaría sin poder decir qué va a hacer: no se ofrece.
    let dir = tmp_module();
    let flows = dir.as_path().join("flows");
    fs::create_dir_all(&flows).unwrap();
    for lang in ["en", "es"] {
        let doc = serde_json::json!({
            "schema_version": 1,
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "s1", "kind": "command", "command": "tasks.tasks.create" }]
        });
        fs::write(
            flows.join(format!("lonely.{lang}.flow.json")),
            serde_json::to_string(&doc).unwrap(),
        )
        .unwrap();
    }

    assert!(
        Manifest::load_flow_templates(dir.as_path()).is_empty(),
        "sin `grants.json` la familia no se ofrece"
    );
}

#[test]
fn a_broken_package_never_breaks_the_boot() {
    // Esto se lee de un zip de TERCEROS y corre en `rehydrate_installed`, o sea en cada arranque.
    // Best-effort como `load_locales`: lo ilegible se omite y lo válido sobrevive — un módulo roto
    // no puede dejar sin automatizaciones a los demás, ni impedir que el hub levante.
    let dir = tmp_module();
    write_family(dir.as_path(), "good");
    let flows = dir.as_path().join("flows");
    fs::write(flows.join("broken.en.flow.json"), b"{ no soy json").unwrap();
    fs::write(flows.join("broken.es.flow.json"), b"{ no soy json").unwrap();
    fs::write(flows.join("broken.grants.json"), b"{ tampoco").unwrap();
    fs::write(
        flows.join("README.md"),
        b"# documentacion, no una plantilla",
    )
    .unwrap();

    let found = Manifest::load_flow_templates(dir.as_path());

    let families: Vec<&str> = found.iter().map(|t| t.family.as_str()).collect();
    assert_eq!(families, ["good"], "lo roto se omite y lo bueno sobrevive");
}

#[test]
fn a_module_without_the_folder_reads_as_no_templates() {
    // El caso de los 26 módulos que hoy no traen ninguna: ausencia, no error.
    let dir = tmp_module();
    assert!(Manifest::load_flow_templates(dir.as_path()).is_empty());
}
