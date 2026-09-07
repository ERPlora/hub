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

/// Un módulo mínimo SIN plantillas, en la versión que se le pida — el vecino que un suelo nombra.
fn plain_module(id: &str, version: &str) -> std::path::PathBuf {
    let dir = std::env::temp_dir().join(format!("erplora-flowtpl-plain-{}", uuid::Uuid::new_v4()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(
        dir.join("module.json"),
        format!(r#"{{"id":"{id}","name":"{id}","version":"{version}"}}"#),
    )
    .unwrap();
    dir
}

/// Como [`fixture_with_templates`], pero la familia declara un **suelo de versión por plantilla**
/// en su `requires.json` — el caso real de `whatsapp_inbox`, que fija `appointments >= 1.1.69`
/// para su plantilla mientras su `depends_on` es solo `["customers"]`.
fn fixture_requiring(id: &str, module: &str, floor: &str) -> std::path::PathBuf {
    let dir = fixture_with_templates(id);
    std::fs::write(
        dir.join("flows/appointment-from-whatsapp.requires.json"),
        format!(r#"{{"modules":{{"{module}":"{floor}"}}}}"#),
    )
    .unwrap();
    dir
}

#[tokio::test]
async fn a_template_whose_required_module_is_missing_is_not_offered() {
    // El suelo es POR PLANTILLA y a propósito no es el `depends_on` del módulo: la plantilla es
    // opcional, así que el módulo se instala igual y lo único que no pasa es que se ofrezca una
    // automatización que nombraría commands de un módulo que este hub no tiene.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-missing");
    runtime.ensure_system_tables().await.unwrap();

    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "1.1.69"))
        .await
        .unwrap();

    assert!(
        runtime.registry().flow_templates().is_empty(),
        "sin `appointments` instalado, su plantilla no se ofrece"
    );
}

#[tokio::test]
async fn a_template_whose_required_module_is_too_old_is_not_offered() {
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-old");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&plain_module("appointments", "1.1.68"))
        .await
        .unwrap();

    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "1.1.69"))
        .await
        .unwrap();

    assert!(
        runtime.registry().flow_templates().is_empty(),
        "1.1.68 < 1.1.69: el suelo no se cumple y la plantilla no se ofrece"
    );
}

#[tokio::test]
async fn a_template_whose_floor_is_met_is_offered() {
    // 🔴 El control POSITIVO del filtro. Sin él, un filtro que devolviera SIEMPRE vacío dejaría
    // verdes los dos tests de arriba: es la diferencia entre «filtra» y «no ofrece nada nunca».
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-met");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&plain_module("appointments", "1.1.69"))
        .await
        .unwrap();

    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "1.1.69"))
        .await
        .unwrap();

    let offered = runtime.registry().flow_templates();
    assert_eq!(offered.len(), 1, "cumplido el suelo, la plantilla se ofrece");
    assert_eq!(offered[0].1.family, "appointment-from-whatsapp");
}

#[tokio::test]
async fn a_floor_that_cannot_be_read_leaves_the_template_out() {
    // `requires.json` es contenido de un zip de TERCEROS. Si el suelo no se lee como triple, la
    // plantilla se queda fuera: ofrecer una automatización cuyo suelo no se ha podido comprobar es
    // ofrecer una que al ejecutarse nombra commands que este hub quizá no tiene.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-unreadable");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&plain_module("appointments", "1.1.69"))
        .await
        .unwrap();

    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "latest"))
        .await
        .unwrap();

    assert!(
        runtime.registry().flow_templates().is_empty(),
        "un suelo ilegible deja la plantilla fuera, no dentro"
    );
}

#[tokio::test]
async fn a_template_whose_required_module_is_paused_is_not_offered() {
    // hub#1649. Un módulo PAUSADO no ejecuta sus commands: para el suelo de una plantilla cuenta
    // como ausente, no como presente. Es el mismo criterio que `flow_templates()` ya aplica al
    // módulo que TRAE la plantilla — ofrecerla porque el vecino está instalado, aunque esté
    // pausado, es ofrecer una automatización que al ejecutarse llama a una puerta cerrada.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-paused");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&plain_module("appointments", "1.1.69"))
        .await
        .unwrap();
    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "1.1.69"))
        .await
        .unwrap();
    assert_eq!(
        runtime.registry().flow_templates().len(),
        1,
        "control positivo: con el vecino ACTIVO la plantilla sí se ofrece"
    );

    runtime.deactivate("appointments").await.unwrap();

    assert!(
        runtime.registry().flow_templates().is_empty(),
        "con el vecino pausado, su plantilla deja de ofrecerse"
    );
    // Y lo dice, que es la otra mitad de hub#1649: dejar de ofrecerla sin motivo es la
    // desaparición muda que la issue describe.
    let discards = runtime.registry().flow_template_discards();
    assert_eq!(
        discards
            .iter()
            .map(|(m, d)| (*m, d.code.as_str()))
            .collect::<Vec<_>>(),
        [("whatsapp_inbox", "template_floor_module_paused")]
    );
    assert!(
        discards[0].1.detail.contains("appointments"),
        "el motivo nombra al vecino: {}",
        discards[0].1.detail
    );
}

#[tokio::test]
async fn pausing_the_module_that_ships_the_template_says_so_too() {
    // hub#1649. Un módulo pausado ya no ofrecía sus plantillas —correcto— pero tampoco lo decía,
    // así que en la galería se veía igual que un módulo que no trae ninguna.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-owner-paused");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&fixture_with_templates("whatsapp_inbox"))
        .await
        .unwrap();
    assert!(
        runtime.registry().flow_template_discards().is_empty(),
        "control positivo: con el módulo activo no se descarta nada"
    );

    runtime.deactivate("whatsapp_inbox").await.unwrap();

    assert!(runtime.registry().flow_templates().is_empty());
    assert_eq!(
        runtime
            .registry()
            .flow_template_discards()
            .iter()
            .map(|(m, d)| (*m, d.family.as_str(), d.code.as_str()))
            .collect::<Vec<_>>(),
        [(
            "whatsapp_inbox",
            "appointment-from-whatsapp",
            "template_owner_paused"
        )]
    );
}

#[tokio::test]
async fn a_floor_that_is_not_met_says_which_neighbour_and_why() {
    // hub#1649. Los dos motivos que dependen de qué más hay instalado —falta, o es viejo— se
    // nombran por separado: «instala appointments» y «actualiza appointments» son dos arreglos
    // distintos para el dueño.
    let db = fresh_db().await;
    let mut runtime = Runtime::with_hub_id(Box::new(db), "hub-flow-tpl-floor-said");
    runtime.ensure_system_tables().await.unwrap();
    runtime
        .install_from_dir(&fixture_requiring("whatsapp_inbox", "appointments", "1.1.69"))
        .await
        .unwrap();
    assert_eq!(
        runtime
            .registry()
            .flow_template_discards()
            .iter()
            .map(|(_, d)| d.code.as_str())
            .collect::<Vec<_>>(),
        ["template_floor_module_missing"]
    );

    runtime
        .install_from_dir(&plain_module("appointments", "1.1.68"))
        .await
        .unwrap();

    let discards = runtime.registry().flow_template_discards();
    assert_eq!(
        discards
            .iter()
            .map(|(_, d)| d.code.as_str())
            .collect::<Vec<_>>(),
        ["template_floor_module_too_old"],
        "instalado pero viejo es otro motivo que «no está»"
    );
    assert!(
        discards[0].1.detail.contains("1.1.68") && discards[0].1.detail.contains("1.1.69"),
        "dice qué hay y qué hace falta: {}",
        discards[0].1.detail
    );
}
