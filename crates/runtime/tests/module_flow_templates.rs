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
//!   <family>.grants.json      { "grants": [ { kind, value, payload? }, … ] } OBLIGATORIO
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

/// Escribe el `grants.json` de una familia ya escrita, sustituyendo el que dejó `write_family`.
fn write_grants(dir: &Path, family: &str, grants: serde_json::Value) {
    fs::write(
        dir.join("flows").join(format!("{family}.grants.json")),
        serde_json::to_string(&serde_json::json!({ "grants": grants })).unwrap(),
    )
    .unwrap();
}

#[test]
fn the_limit_a_module_puts_on_a_grant_reaches_the_hub() {
    // hub#1654 — un `payload` en el sidecar ACOTA el permiso (hub#1623): no «puede anular citas»
    // sino «puede anular citas COMO CLIENTA». Es lo único que impide que un modelo que redacta el
    // payload leyendo el WhatsApp de una desconocida anule de parte del salón, saltándose la
    // ventana de antelación y sin comprobar de quién es la cita.
    //
    // Si el lector se queda solo con `{kind, value}`, la plantilla se registra pidiendo el permiso
    // ANCHO y **nadie se entera**: `erplora validate` ya dio el pin por bueno, la pantalla de
    // permisos enseña «puede anular citas» sin acotar y el dueño lo concede así.
    let dir = tmp_module();
    write_family(dir.as_path(), "appointment-from-whatsapp");
    write_grants(
        dir.as_path(),
        "appointment-from-whatsapp",
        serde_json::json!([
            { "kind": "command", "value": "appointments.appointments.create" },
            {
                "kind": "command",
                "value": "appointments.appointments.cancel",
                "payload": { "channel": "customer" }
            }
        ]),
    );

    let found = Manifest::load_flow_templates(dir.as_path());

    // Se afirma sobre la forma SERIALIZADA a propósito: es la que `GET /api/hub/flows/templates`
    // sirve tal cual, o sea el contrato que ve quien va a pedir el permiso. Un campo que existe en
    // el tipo pero no sale por el cable no acota nada.
    let grants = serde_json::to_value(&found[0].grants).unwrap();
    let grants = grants.as_array().expect("los permisos viajan como lista");
    assert_eq!(grants.len(), 2, "los dos permisos que pedirá la plantilla");
    // El que no acota nada vale lo que valían todos antes de hub#1623: no fija ningún campo.
    assert_eq!(grants[0]["value"], "appointments.appointments.create");
    assert_eq!(
        grants[0].get("payload").and_then(|p| p.as_object()),
        None,
        "un grant sin `payload` no fija nada, y no se inventa uno"
    );
    // Y el acotado llega ENTERO: es el campo que `check_payload_pin` va a exigir después.
    assert_eq!(grants[1]["value"], "appointments.appointments.cancel");
    assert_eq!(
        grants[1]["payload"],
        serde_json::json!({ "channel": "customer" }),
        "el límite que el módulo declaró llega al hub"
    );
}

#[test]
fn a_pin_that_cannot_be_read_leaves_the_family_out() {
    // Un `payload` que no es un objeto NO puede leerse como «no fija nada»: eso convierte una
    // errata del autor en el permiso ANCHO, en silencio, que es exactamente el fallo que este
    // camino existe para evitar. Se cae la familia entera, como cualquier otro sidecar ilegible
    // (`a_family_without_its_grants_sidecar_is_not_offered`): la puerta se cierra, no se ensancha.
    let dir = tmp_module();
    write_family(dir.as_path(), "appointment-from-whatsapp");
    write_grants(
        dir.as_path(),
        "appointment-from-whatsapp",
        serde_json::json!([{
            "kind": "command",
            "value": "appointments.appointments.cancel",
            "payload": "channel=customer"
        }]),
    );

    assert!(
        Manifest::load_flow_templates(dir.as_path()).is_empty(),
        "un pin ilegible no se degrada a permiso ancho: la familia no se ofrece"
    );
}
