//! hub#1611 — instalar un módulo con carpeta `flows/` REGISTRA sus automatizaciones de fábrica.
//!
//! El otro fichero (`module_flow_templates.rs`) fija cómo se LEE la carpeta; este fija que esa
//! lectura está **cableada** donde tiene que estar. Son dos preguntas distintas y la segunda es la
//! que de verdad hace aparecer la plantilla en la galería de un negocio: una función que nadie
//! llama es exactamente el estado en el que ya estaban los `flows/*.flow.json` de
//! `whatsapp_inbox` — escritos, empaquetados y sin que los leyera nadie.
//!
//! Se cablea junto a `set_locales`, en `installer::install`, y eso es lo que da la promesa que el
//! contrato de la carpeta hizo: `Runtime::rehydrate_installed` vuelve a pasar por el instalador en
//! **cada arranque**, así que los módulos que ya están instalados hoy publican sus plantillas en el
//! primer boot tras esta release, **sin republicar ni reinstalar nada**.
use erplora_db::testutil::fresh_db;
use erplora_runtime::Runtime;

/// Un módulo mínimo con una familia de plantillas completa en su carpeta `flows/`.
fn fixture_with_templates(id: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-flowtpl-wire-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(dir.join("flows")).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"WhatsApp Inbox","version":"2.1.31"}}"#),
    )
    .unwrap();
    for (lang, name) in [
        ("en", "Book from WhatsApp"),
        ("es", "Reservar por WhatsApp"),
    ] {
        let doc = serde_json::json!({
            "schema_version": 1,
            "name": name,
            "triggers": [{ "kind": "manual" }],
            "steps": [{ "id": "s1", "kind": "command", "command": "tasks.tasks.create" }]
        });
        std::fs::write(
            dir.join(format!("flows/appointment-from-whatsapp.{lang}.flow.json")),
            serde_json::to_string(&doc).unwrap(),
        )
        .unwrap();
    }
    std::fs::write(
        dir.join("flows/appointment-from-whatsapp.grants.json"),
        r#"{"grants":[{"kind":"command","value":"tasks.tasks.create"}]}"#,
    )
    .unwrap();
    dir
}

#[tokio::test]
async fn installing_a_module_registers_the_automations_it_ships() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-templates");
    runtime.ensure_system_tables().await.unwrap();

    runtime
        .install_from_dir(&fixture_with_templates("whatsapp_inbox"))
        .await
        .unwrap();

    let offered = runtime.registry().flow_templates();
    assert_eq!(offered.len(), 1, "la plantilla del módulo queda registrada");
    let (module_id, tpl) = offered[0];
    assert_eq!(module_id, "whatsapp_inbox", "y dice de qué módulo viene");
    assert_eq!(tpl.family, "appointment-from-whatsapp");
    assert!(
        tpl.documents.contains_key("es"),
        "con el idioma del negocio, no solo el fuente"
    );
}

#[tokio::test]
async fn a_module_that_ships_none_offers_none() {
    // Los 26 módulos de hoy. Ausencia, no error: instalar tiene que seguir siendo lo de siempre.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-templates-none");
    runtime.ensure_system_tables().await.unwrap();
    let dir = std::env::temp_dir().join(format!("erplora-flowtpl-bare-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        r#"{"id":"tasks","name":"Tasks","version":"1.0.0"}"#,
    )
    .unwrap();

    runtime.install_from_dir(&dir).await.unwrap();

    assert!(runtime.registry().flow_templates().is_empty());
}

#[tokio::test]
async fn uninstalling_the_module_takes_its_automations_with_it() {
    // Una plantilla que sobreviviera a su módulo se ofrecería para siempre, y al instalarla
    // nombraría commands que este hub ya no tiene.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-templates-gone");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&fixture_with_templates("whatsapp_inbox"))
        .await
        .unwrap();
    assert_eq!(runtime.registry().flow_templates().len(), 1);

    runtime.uninstall("whatsapp_inbox").await.unwrap();

    assert!(
        runtime.registry().flow_templates().is_empty(),
        "al desinstalar el módulo, sus plantillas se van con él"
    );
}
