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

use erplora_db::{
    testutil::{fresh_db, TestDb},
    Params,
};
use erplora_runtime::e2e_support::units;
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;
use sha2::{Digest, Sha256};

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Same resolution as the `require_modules_workspace` guard — it honours `$ERPLORA_MODULES_DIR`.
fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
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
    fresh_as("h1").await
}

/// A hub with the modules installed (and therefore seeded) UNDER ITS OWN hub_id — like in
/// production, where the server installs the manifest modules for the DESTINATION hub before
/// calling the motor (this file's header says so). A destination seeded under a DIFFERENT hub
/// is a state production cannot produce, and it hid the `taxes_rule` FK to its categories until
/// the rules started traveling (hub#576) — same correction `blueprint_seed_reglas_no_duplican`
/// already made for its fixtures.
async fn fresh_as(hub: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub); // ctx y runtime comparten hub (como en prod)
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory"))
        .await
        .expect("instalar inventory");
    rt
}

async fn create_product(rt: &Runtime, hub: &str, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": units(10), "tax_category_key": "product.generic" })),
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
    rows.iter()
        .filter_map(|p| p["name"].as_str().map(str::to_string))
        .collect()
}

fn full_selection() -> ExportSelection {
    ExportSelection {
        users: true,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection {
                module_id: "taxes".into(),
                with_data: true,
                tables: None,
            },
            ModuleDataSelection {
                module_id: "inventory".into(),
                with_data: true,
                tables: None,
            },
        ],
        purpose: Default::default(),
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
    export_hub(&a, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export A")
}

#[tokio::test]
async fn round_trip_restores_equivalent_state_under_target_hub_id() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;

    // Hub destino B, tenant DISTINTO (h2), con los módulos ya instalados (paso del server).
    let mut b = fresh_as("h2").await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B");

    // Las secciones seleccionadas se aplicaron.
    for section in ["modules/taxes", "modules/inventory"] {
        let r = report
            .sections
            .iter()
            .find(|s| s.section == section)
            .unwrap_or_else(|| panic!("sin resultado para {section}"));
        assert!(
            matches!(r.status, SectionStatus::Applied),
            "{section} no aplicada: {:?}",
            r.status
        );
    }

    // El estado es equivalente BAJO EL hub_id DESTINO (la query scoped por h2 lo demuestra:
    // si la sustitución del placeholder fallara, h2 no vería nada).
    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()) && names.contains(&"Té verde".to_string()),
        "productos no restaurados bajo h2: {names:?}"
    );

    // Y ningún dato se coló bajo el hub_id de ORIGEN.
    let leaked = product_names(&b, "h1").await;
    assert!(
        leaked.is_empty(),
        "filas importadas bajo el hub_id de origen: {leaked:?}"
    );
}

/// Round-trip con una columna que es PALABRA RESERVADA de SQL (`order`, en `inventory_category` y
/// `staff_role`). El export escribía la lista de columnas SIN comillas → `INSERT INTO
/// inventory_category (…, order, …)` reventaba con «syntax error» al importar, y como la sección se
/// aplica en bloque se perdía el módulo ENTERO: un blueprint de 19 categorías + 280 productos
/// aterrizaba VACÍO. El round-trip de arriba no lo cazaba porque solo exporta productos, cuya tabla
/// no tiene ninguna columna reservada.
#[tokio::test]
async fn round_trip_survives_reserved_word_columns() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let a = fresh().await;
    a.execute_command(
        "inventory.categories.create",
        &params(
            json!({ "name": "Cafés e infusiones", "slug": "cafes", "icon": "cafe-outline",
                        "color": "#3880ff", "description": "", "order": 3 }),
        ),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría en A");
    create_product(&a, "h1", "Café", "CAF").await;

    let bundle = export_hub(&a, "h1", &full_selection(), "restaurante", "es", CREATED_AT)
        .await
        .expect("export A");

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B");

    let r = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("sin resultado para modules/inventory");
    assert!(
        matches!(r.status, SectionStatus::Applied),
        "inventory no aplicada: {:?}",
        r.status
    );

    let cats = b
        .execute_query("inventory.categories.list", &Params::new(), &ctx("h2"))
        .await
        .unwrap();
    assert_eq!(
        cats.len(),
        1,
        "la categoría con la columna reservada `order` no sobrevivió"
    );
    assert_eq!(cats[0]["name"], json!("Cafés e infusiones"));
    assert_eq!(
        cats[0]["order"],
        json!(3),
        "el valor de la columna reservada se perdió"
    );

    // Y los productos del mismo módulo siguen ahí (la sección no se cayó entera).
    assert_eq!(product_names(&b, "h2").await, vec!["Café".to_string()]);
}

#[tokio::test]
async fn unselected_sections_are_skipped() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
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

    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(matches!(inv.status, SectionStatus::Applied));
    let taxes = report
        .sections
        .iter()
        .find(|s| s.section == "modules/taxes")
        .expect("taxes en informe");
    assert!(
        matches!(taxes.status, SectionStatus::Skipped),
        "taxes debía saltarse: {:?}",
        taxes.status
    );
    // `hub_users` es la excepción, y a propósito (hub#331): el bundle es de OTRO hub, así que sus
    // identidades se descartan mirando el manifest, no la casilla — el resultado para el usuario es
    // el mismo (no se aplica nada), pero el informe dice que el bundle traía cuentas en vez de
    // callarlo detrás de un «Saltado» que solo significa «no la marqué».
    let users = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users en informe");
    assert!(
        matches!(users.status, SectionStatus::Ignored(_)),
        "las identidades de un bundle ajeno se descartan marque o no el usuario: {:?}",
        users.status
    );

    // Los productos sí llegaron.
    let names = product_names(&b, "h2").await;
    assert!(names.contains(&"Café".to_string()));
}

/// 🔴 [ADR-0195, hub#305] **Plano CONSUMIDOR**: el import IGNORA las identidades que lleguen en un
/// bundle `template`, aunque el fichero venga dentro y la casilla esté marcada.
///
/// Defensa en profundidad: el gate del productor (`export_hub`, #304) y el del publicador (el SaaS,
/// saas#1107) cubren lo que se sube al catálogo, pero el import acepta **ficheros locales**
/// («Subir desde archivo»), que no pasan por ninguno de los dos. Un `.blueprint.zip` publicado
/// ANTES del gate —como el `restaurante` v1.0.2, con `Demo`/admin y PIN `0000`— entra por ahí sin
/// filtro.
///
/// El bundle se construye como el real: se exporta un **backup** (que sí lleva `data/hub_users.sql`)
/// y se marca su manifest como `template`. Es exactamente la forma de un artefacto viejo o
/// manipulado.
#[tokio::test]
async fn una_plantilla_no_importa_identidades_aunque_las_traiga() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let a = fresh().await;
    erplora_runtime::hub_users::create(
        a.db(),
        // Registro vacío: estos tests no instalan módulos, así que el catálogo de roles es el
        // base y la guarda de activación (hub#352) no tiene nada que mirar.
        &erplora_runtime::Registry::new(),
        "h1",
        &erplora_runtime::hub_users::NewHubUser {
            name: "Demo".into(),
            role: "admin".into(),
            pin: "4821".into(),
            email: "demo@example.com".into(),
            badge: String::new(),

            local: false,
        }, 0,)
    .await
    .expect("crear el usuario admin del hub de origen");
    create_product(&a, "h1", "Café", "CAF").await;

    let mut bundle = export_hub(&a, "h1", &full_selection(), "restaurante", "es", CREATED_AT)
        .await
        .expect("export A");
    assert!(
        bundle.files.contains_key("data/hub_users.sql"),
        "el backup de partida debe traer identidades, o el test no prueba nada"
    );
    // El artefacto que se quiere cazar: dice ser plantilla y lleva identidades dentro.
    bundle.manifest.purpose = BundlePurpose::Template;

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import de la plantilla");

    // 1. Ninguna identidad aterriza en el hub destino.
    let users = erplora_runtime::hub_users::list(b.db(), "h2")
        .await
        .expect("listar usuarios de h2");
    assert!(
        users.is_empty(),
        "una plantilla repartió identidades en el hub destino: {:?}",
        users
            .iter()
            .map(|u| (&u.name, &u.role, u.has_pin))
            .collect::<Vec<_>>()
    );

    // 2. Y se DICE en el informe, con motivo legible: ni `Applied` (mentiría) ni un `Skipped` mudo
    //    (indistinguible de «no la marqué»).
    let seccion = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users en el informe");
    let SectionStatus::Ignored(motivo) = &seccion.status else {
        panic!(
            "hub_users debía reportarse como Ignored con motivo, y salió {:?}",
            seccion.status
        );
    };
    assert!(
        motivo.contains("plantilla"),
        "el motivo tiene que ser legible para el usuario, y fue: {motivo}"
    );

    // 3. Lo que SÍ es una plantilla llega entero: los datos de negocio.
    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()),
        "la plantilla no aplicó sus datos: {names:?}"
    );
}

/// 🔴 [ADR-0195 §3, hub#331] **Third defense — the consumer one, and the only one that holds for a
/// bundle that never went through the SaaS.** Identities do NOT land in a hub that is not their
/// own, whatever the bundle says about itself.
///
/// The purpose gate (hub#305) only catches a bundle that DECLARES `template`. The four blueprints
/// published today were produced before the `purpose` field existed, so they read as `backup` —
/// their four accounts (`Demo`/**admin**, PIN `0000`, recoverable from the zip itself in 0.00 s)
/// were applied. A bundle is a file the user supplies: what it claims about itself is not a
/// control. The only thing the import can trust is which hub it is running for.
#[tokio::test]
async fn a_foreign_bundle_never_injects_users_even_when_it_claims_to_be_a_backup() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    // Origin hub: exactly what the published blueprint carries — accounts with a role and a PIN.
    let a = fresh().await;
    for (name, role, pin) in [("Demo", "admin", "4821"), ("Manager", "manager", "5390")] {
        erplora_runtime::hub_users::create(
            a.db(),
            &erplora_runtime::Registry::new(),
            "h1",
            &erplora_runtime::hub_users::NewHubUser {
                name: name.into(),
                role: role.into(),
                pin: pin.into(),
                // Usuario de CUENTA: sin la casilla «Local user» el alta pide email (hub#356).
                email: format!("{}@example.com", name.to_lowercase()),
                badge: String::new(),
                local: false,
            }, 0,)
        .await
        .unwrap_or_else(|e| panic!("create {name} in the origin hub: {e}"));
    }
    create_product(&a, "h1", "Café", "CAF").await;

    let bundle = export_hub(&a, "h1", &full_selection(), "restaurante", "es", CREATED_AT)
        .await
        .expect("export A");
    // The artefact we are after: it says "backup" (or says nothing, which reads the same) and
    // carries identities inside. Without both, this test proves nothing.
    assert_eq!(
        bundle.manifest.purpose,
        BundlePurpose::Backup,
        "the bundle must claim to be a backup"
    );
    assert!(
        bundle.files.contains_key("data/hub_users.sql"),
        "the bundle must carry identities"
    );

    // Destination: ANOTHER hub, with its own legitimate user already in place.
    let mut b = fresh().await;
    erplora_runtime::hub_users::create(
        b.db(),
        // Registro vacío: estos tests no instalan módulos, así que el catálogo de roles es el
        // base y la guarda de activación (hub#352) no tiene nada que mirar.
        &erplora_runtime::Registry::new(),
        "h2",
        &erplora_runtime::hub_users::NewHubUser {
            name: "Encargada".into(),
            role: "manager".into(),
            pin: "4821".into(),
            email: "encargada@example.com".into(),
            badge: String::new(),

            local: false,
        }, 0,)
    .await
    .expect("create the destination hub's own user");

    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import of the foreign bundle");

    // 1. Not one identity row landed, and the hub's own user is untouched (same role, same PIN).
    let users = erplora_runtime::hub_users::list(b.db(), "h2")
        .await
        .expect("list h2 users");
    assert_eq!(
        users.len(),
        1,
        "a foreign bundle handed out accounts in this hub: {:?}",
        users
            .iter()
            .map(|u| (&u.name, &u.role, u.has_pin))
            .collect::<Vec<_>>()
    );
    assert_eq!(
        users[0].name, "Encargada",
        "the hub's own user was replaced"
    );
    assert_eq!(
        users[0].role, "manager",
        "the import altered the role of an existing user"
    );
    assert!(
        users[0].has_pin,
        "the import altered the PIN of an existing user"
    );

    // 2. And the report SAYS it: `Ignored` with its reason and the number of discarded rows —
    //    never `Failed` (a `column "hub_id" does not exist` in the Usuarios section, seen live on
    //    2026-08-03, told the user nothing about what had just been kept out).
    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users in the report");
    let SectionStatus::Ignored(reason) = &section.status else {
        panic!(
            "hub_users had to be reported as Ignored, and came out as {:?}",
            section.status
        );
    };
    assert!(
        !reason.trim().is_empty(),
        "an empty reason is a silent discard"
    );
    assert_eq!(
        section.discarded_rows, 2,
        "the report must say HOW MANY identity rows were discarded: {section:?}"
    );

    // 3. The rest of the bundle still lands: this is a filter, not a rejection.
    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()),
        "the business data did not land: {names:?}"
    );
}

/// The mirror, and the half that stops the fix from breaking backups: a hub restoring **its own**
/// copy does get its users back. Without them a restore loses roles and PINs, and
/// `get_or_link_cloud_user` would bring an `employee` back as admin (ADR-0113 §1) — which is why
/// ADR-0195 explicitly rejected banning `hub_users` outright.
///
/// What hub#331 changes is WHICH restore that is: the same installation
/// (`manifest.hub.hub_id` == the destination hub), not "any bundle that calls itself a backup".
#[tokio::test]
async fn a_hub_restoring_its_own_backup_gets_its_users_back() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let a = fresh().await;
    erplora_runtime::hub_users::create(
        a.db(),
        // Registro vacío: estos tests no instalan módulos, así que el catálogo de roles es el
        // base y la guarda de activación (hub#352) no tiene nada que mirar.
        &erplora_runtime::Registry::new(),
        "h1",
        &erplora_runtime::hub_users::NewHubUser {
            name: "Encargada".into(),
            role: "manager".into(),
            pin: "4821".into(),
            email: "encargada@example.com".into(),
            badge: String::new(),

            local: false,
        }, 0,)
    .await
    .expect("create the manager in the origin hub");

    let bundle = export_hub(&a, "h1", &full_selection(), "copia", "es", CREATED_AT)
        .await
        .expect("export A");
    assert_eq!(
        bundle.manifest.purpose,
        BundlePurpose::Backup,
        "backup is the default"
    );
    assert_eq!(
        bundle.manifest.hub.hub_id, "h1",
        "the bundle must record its origin hub"
    );

    // Same hub, rebuilt from scratch (a redeploy restoring its own backup): the destination is h1.
    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h1")
        .await
        .expect("restore of its own backup");

    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_users")
        .expect("hub_users in the report");
    assert!(
        matches!(section.status, SectionStatus::Applied),
        "a hub restoring its own backup must get its identities back: {:?}",
        section.status
    );

    let users = erplora_runtime::hub_users::list(b.db(), "h1")
        .await
        .expect("list h1 users");
    let manager = users
        .iter()
        .find(|u| u.name == "Encargada")
        .expect("the manager did not survive the restore");
    assert_eq!(manager.role, "manager", "the role was lost on restore");
    assert!(manager.has_pin, "the PIN was lost on restore");
}

#[tokio::test]
async fn best_effort_a_broken_section_does_not_abort_the_rest() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;

    // Rompemos el SQL de taxes (sintaxis inválida) PERO con sha256 coherente: la integridad
    // pasa, la aplicación falla → best-effort: se registra y se sigue con inventory.
    let broken = b"THIS IS NOT SQL;".to_vec();
    bundle
        .manifest
        .sha256
        .insert("data/taxes.sql".into(), sha256_hex(&broken));
    bundle.files.insert("data/taxes.sql".into(), broken);

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("el import NO debe romperse por una sección rota");

    let taxes = report
        .sections
        .iter()
        .find(|s| s.section == "modules/taxes")
        .expect("taxes en informe");
    assert!(
        matches!(taxes.status, SectionStatus::Failed(_)),
        "taxes debía fallar: {:?}",
        taxes.status
    );
    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "inventory debía aplicarse igualmente"
    );

    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()),
        "best-effort no aplicó el resto"
    );
}

#[tokio::test]
async fn sha256_mismatch_rejects_the_import_without_effects() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;
    // Manipulación del bundle: contenido cambiado sin actualizar el hash del manifest.
    bundle
        .files
        .insert("data/inventory.sql".into(), b"tampered".to_vec());

    let mut b = fresh().await;
    let res = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2").await;
    assert!(res.is_err(), "un bundle manipulado debe rechazarse entero");

    // Sin efectos: nada importado bajo el hub destino.
    let names = product_names(&b, "h2").await;
    assert!(names.is_empty(), "el rechazo dejó efectos: {names:?}");
}

#[tokio::test]
async fn unknown_schema_version_rejects_without_effects() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;
    bundle.manifest.schema_version = 999;

    let mut b = fresh().await;
    let res = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2").await;
    assert!(res.is_err(), "schema_version desconocida debe rechazarse");
    assert!(product_names(&b, "h2").await.is_empty());
}

#[tokio::test]
async fn module_data_for_uninstalled_module_fails_its_section_only() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;

    // Destino SIN inventory (solo taxes): la sección de inventory falla con motivo claro,
    // la de taxes se aplica. (Instalar módulos que faltan es del server, no de este motor.)
    let db = fresh_db().await;
    let mut b = Runtime::with_hub_id(Box::new(db), "h2");
    b.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");

    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("best-effort también aquí");

    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(&inv.status, SectionStatus::Failed(reason) if reason.contains("inventory")),
        "sección de módulo no instalado debía fallar nombrándolo: {:?}",
        inv.status
    );
    let taxes = report
        .sections
        .iter()
        .find(|s| s.section == "modules/taxes")
        .expect("taxes en informe");
    assert!(matches!(taxes.status, SectionStatus::Applied));
}

/// Importar un bundle cuyo `id` YA existe en el destino no puede reventar la sección.
///
/// Apareció al cablear el bloque `seed` del manifest (ADR-0147): los datos de referencia que un
/// módulo siembra al instalarse llevan el `hub_id` DENTRO del id por convención
/// (`h1|taxcat|restaurant.food`), y el export **no reescribe `id` a propósito** — lo excluye del
/// placeholder porque en Dev `hub_id` vale lo mismo que `created_by` y un replace ciego los
/// arrastraba.
///
/// Resultado: el guard `WHERE NOT EXISTS (id = … AND hub_id = destino)` daba TRUE —no hay fila de
/// ese id en ESE hub— y el INSERT chocaba contra la PK, que no sabe de hubs. La sección entera se
/// perdía: 19 categorías fiscales a la basura por una fila.
///
/// El guard tiene que ir por `id` SOLO: es la clave primaria, y si existe, existe.
#[tokio::test]
async fn una_fila_cuyo_id_ya_existe_no_rompe_la_seccion() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let bundle = exported_bundle().await;

    // Destino con los módulos instalados — y por tanto con su semilla ya aplicada.
    let mut b = fresh_as("h2").await;

    // Se importa DOS veces: la segunda tiene garantizado que cada id ya está.
    import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("primer import");
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("segundo import: re-aplicar el bundle es idempotente por contrato");

    for section in ["modules/taxes", "modules/inventory"] {
        let r = report
            .sections
            .iter()
            .find(|s| s.section == section)
            .unwrap_or_else(|| panic!("sin resultado para {section}"));
        assert!(
            matches!(r.status, SectionStatus::Applied),
            "{section} debe aplicarse aunque las filas ya estén: {:?}",
            r.status
        );
    }
}

// ── BD COMPARTIDA: importar en OTRO hub de la MISMA BD (hub#260) ────────────────────────────

/// Instala taxes + inventory sobre un adaptador nuevo del MISMO esquema y devuelve el runtime con
/// ese hub. Cada llamada abre su propio pool sobre el esquema compartido (como dos hubs de una org
/// en prod), pero las tablas y los datos son los mismos.
async fn fresh_over(db: &TestDb, hub: &str) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(db.adapter().await), hub);
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory"))
        .await
        .expect("instalar inventory");
    rt
}

/// Crea en `hub` un producto + una categoría y los liga (vínculo M2M). Devuelve (sku, nombre).
async fn product_with_category(rt: &Runtime, hub: &str, name: &str, sku: &str, cat: &str) {
    create_product(rt, hub, name, sku).await;
    rt.execute_command(
        "inventory.categories.create",
        &params(json!({ "name": cat, "slug": cat, "icon": "cube-outline",
                        "color": "#3880ff", "description": "", "order": 0 })),
        &ctx(hub),
    )
    .await
    .unwrap();
    let prods = rt
        .execute_query("inventory.products.list", &Params::new(), &ctx(hub))
        .await
        .unwrap();
    let cats = rt
        .execute_query("inventory.categories.list", &Params::new(), &ctx(hub))
        .await
        .unwrap();
    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({
            "product_id": prods[0]["id"].as_str().unwrap(),
            "category_id": cats[0]["id"].as_str().unwrap(),
        })),
        &ctx(hub),
    )
    .await
    .unwrap();
}

/// El caso real del bug (hub#260): un hub A exporta un blueprint y un hub B que COMPARTE la misma
/// base de datos (misma org, mismo esquema Postgres) lo importa. La PK de `inventory_product` es
/// `id TEXT PRIMARY KEY` GLOBAL (no `(hub_id, id)`), así que los `id` del bundle son los del hub
/// ORIGEN y en la BD compartida YA EXISTEN (bajo el hub hermano).
///
/// Antes del fix: el guard `WHERE NOT EXISTS (… WHERE id = 'src-id')` evaluaba a falso (la fila
/// existe bajo el hub A) → 0 INSERTs, y la sección se reportaba `Applied` (fallo silencioso). Vaciar
/// el hub de origen hacía funcionar el mismo bundle, demostrando que la causa era la colisión de ids.
///
/// Tras el fix: el import regenera cada `id` por el hub DESTINO y acota el guard por `(hub_id, id)`,
/// así el hub B obtiene sus propias filas con ids nuevos, las FK internas (incluido el vínculo M2M
/// `inventory_product_categories`) se remapean, y una re-importación sobre B no duplica.
#[tokio::test]
async fn importar_en_otro_hub_de_la_misma_bd_inserta_sus_filas_con_ids_nuevos() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }

    // UN esquema Postgres compartido entre los dos hubs (como en prod: una BD por organización).
    let shared = TestDb::new().await;

    // Hub A (origen) sobre ese esquema, con dos productos + un vínculo producto↔categoría.
    let a = fresh_over(&shared, "h1").await;
    create_product(&a, "h1", "Café", "CAF").await;
    product_with_category(&a, "h1", "Té verde", "TEV", "Tés").await;
    let bundle = export_hub(&a, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export A");

    // Hub B (destino) sobre el MISMO esquema, con los módulos ya instalados (paso del server).
    let mut b = fresh_over(&shared, "h2").await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B (misma BD que A)");

    // La sección de inventory se aplica de verdad (antes mentía `Applied` con 0 filas).
    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "modules/inventory debe aplicarse en el hub destino de la misma BD: {:?}",
        inv.status
    );

    // El hub B VE los productos BAJO su propio hub_id — con ids NUEVOS (los del origen siguen
    // perteneciendo a A, no se duplican ni se le roban a A).
    let names_b = product_names(&b, "h2").await;
    assert!(
        names_b.contains(&"Café".to_string()) && names_b.contains(&"Té verde".to_string()),
        "B no recibió los productos en una BD compartida: {names_b:?}"
    );

    // El hub A sigue viendo EXACTAMENTE sus dos productos (no se corrompió ni se le añadió nada).
    let names_a = product_names(&a, "h1").await;
    assert_eq!(
        names_a.len(),
        2,
        "el hub origen cambió tras importar en el hermano: {names_a:?}"
    );

    // La FK interna del bundle se remapeó: el producto importado en B conserva su categoría.
    // (Sin remapeo, `inventory_product_categories` apuntaría a un id de A y la FK no casaría.)
    let tev_rows = b
        .execute_query("inventory.products.list", &params(json!({})), &ctx("h2"))
        .await
        .expect("listar productos de B");
    let tev = tev_rows
        .iter()
        .find(|p| p["name"] == "Té verde")
        .expect("Té verde en B");
    let tev_id = tev["id"].as_str().expect("id del Té verde en B");
    // El id de B es DISTINTO del del origen (que siguen siendo los de A): no reutiliza el bundle.
    let tev_a = a
        .execute_query("inventory.products.list", &params(json!({})), &ctx("h1"))
        .await
        .expect("listar productos de A")
        .into_iter()
        .find(|p| p["name"] == "Té verde")
        .expect("Té verde en A");
    assert_ne!(
        tev_id,
        tev_a["id"].as_str().unwrap(),
        "el id importado en B debe ser NUEVO, no el del hub origen (PK global)"
    );

    // Re-importar el MISMO bundle en B es idempotente: no duplica ni falla (guard por (hub_id, id)).
    let report2 = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("re-import idempotente en B");
    let inv2 = report2
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .unwrap();
    assert!(
        matches!(inv2.status, SectionStatus::Applied),
        "re-importar el bundle en el mismo hub no debe fallar: {:?}",
        inv2.status
    );
    let names_b2 = product_names(&b, "h2").await;
    assert_eq!(
        names_b2.len(),
        2,
        "re-import duplicó filas en el hub destino (guard no idempotente): {names_b2:?}"
    );
}

/// En una BD COMPARTIDA, el `Applied` no puede ser una mentira: si la sección trae sentencias pero
/// ninguna inserta (p.ej. por una colisión de guard mal resuelta), el informe debe seguir siendo
/// honesto. Con el fix del guard por (hub_id, id), el cross-hub SÍ inserta, así que `Applied` es
/// verdad y B ve las filas. Este test clava ese contrato sobre el escenario real del bug.
#[tokio::test]
async fn cross_hub_en_bd_compartida_applied_implica_filas_reales_bajo_el_destino() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let shared = TestDb::new().await;
    let a = fresh_over(&shared, "h1").await;
    create_product(&a, "h1", "Café", "CAF").await;
    let bundle = export_hub(&a, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export A");

    let mut b = fresh_over(&shared, "h2").await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B");

    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .unwrap();
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "debe Applied: {:?}",
        inv.status
    );
    // `Applied` solo es cierto si B realmente tiene la fila bajo su hub_id (antes era 0 filas).
    assert_eq!(product_names(&b, "h2").await, vec!["Café".to_string()]);
}

// ── CLAVE NATURAL: el destino ya tiene la fila EQUIVALENTE (hub#753) ─────────────────────────

/// El destino ya tiene un producto con el MISMO `sku` que trae el bundle, pero con otro `id`.
///
/// El guard de idempotencia del import compara por IDENTIDAD TÉCNICA (`hub_id` + `id` derivado del
/// hub destino), y el `id` derivado nunca coincide con el que el destino generó por su cuenta. Así
/// que el guard pasa, el INSERT sale, y revienta contra la CLAVE NATURAL que la tabla sí declara
/// (`ix_inventory_product_sku` sobre `(hub_id, sku)`) — perdiendo la SECCIÓN ENTERA, porque el
/// módulo se aplica en bloque.
///
/// No es un caso raro: hay ~80 índices únicos `(hub_id, <clave natural>)` en los módulos
/// (`inventory_unit(code)`, `services_service(slug)`, `taxes_category(key)`,
/// `invoice_series_series(code)`…). Cualquier catálogo que el destino ya tenga a medias tumba su
/// sección. El guard tiene que ir TAMBIÉN por la clave natural DECLARADA por el esquema del
/// destino: si ya hay una fila equivalente, la fila del bundle se salta; nunca colisiona.
#[tokio::test]
async fn una_fila_con_la_misma_clave_natural_que_el_destino_no_rompe_la_seccion() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }

    // Hub A (origen) con su catálogo.
    let a = fresh().await;
    create_product(&a, "h1", "Café", "CAF").await;
    create_product(&a, "h1", "Té verde", "TEV").await;
    let bundle = export_hub(&a, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export A");

    // Hub B (destino) que YA dio de alta su propio café con el MISMO sku (otro id, otro nombre).
    let mut b = fresh().await;
    create_product(&b, "h2", "Café de la casa", "CAF").await;

    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("import en B");
    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        !matches!(inv.status, SectionStatus::Failed(_)),
        "una fila equivalente en destino no puede tumbar la sección: {:?}",
        inv.status
    );

    // Lo que el destino ya tenía se respeta (no se duplica ni se pisa) y lo que faltaba entra.
    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café de la casa".to_string()),
        "el import pisó/duplicó el producto que el destino ya tenía: {names:?}"
    );
    assert!(
        names.contains(&"Té verde".to_string()),
        "la fila que NO chocaba tenía que entrar igual: {names:?}"
    );
    assert_eq!(
        names.len(),
        2,
        "clave natural duplicada en el destino: {names:?}"
    );
}

// ── SERIES DE FACTURACIÓN: el caso reportado (hub#753) ───────────────────────────────────────

/// Runtime con `invoice_series` instalado sobre un esquema nuevo, bajo `hub`.
async fn fresh_series(hub: &str) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub);
    rt.install_from_dir(&modules_root().join("invoice_series"))
        .await
        .expect("instalar invoice_series");
    rt
}

async fn create_series(rt: &Runtime, hub: &str, code: &str, name: &str, doc_type: &str) {
    rt.execute_command(
        "invoice_series.series.create",
        &params(json!({
            "code": code, "name": name, "document_type": doc_type, "prefix": code,
            "suffix": "", "format": "{prefix}-{year}-{seq:05d}",
            "country_code": "ES", "region_code": "", "fiscal_year": 2026, "is_default": 0,
        })),
        &ctx(hub),
    )
    .await
    .unwrap_or_else(|e| panic!("crear serie {code}: {e}"));
}

/// `(id, code, current_sequence)` de cada serie viva del hub, ordenado por código.
async fn series_fingerprint(rt: &Runtime, hub: &str) -> Vec<(String, String, i64)> {
    let rows = rt
        .execute_query("invoice_series.series.list", &Params::new(), &ctx(hub))
        .await
        .expect("listar series");
    let mut out: Vec<(String, String, i64)> = rows
        .iter()
        .map(|r| {
            (
                r["id"].as_str().unwrap_or_default().to_string(),
                r["code"].as_str().unwrap_or_default().to_string(),
                r["current_sequence"].as_i64().unwrap_or_default(),
            )
        })
        .collect();
    out.sort();
    out
}

fn series_export_selection() -> ExportSelection {
    ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection {
            module_id: "invoice_series".into(),
            with_data: true,
            tables: None,
        }],
        purpose: Default::default(), // Backup: las series SÍ salen en el volcado
    }
}

fn import_series_only() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: vec!["invoice_series".into()],
    }
}

/// **El caso reportado (hub#753).** Un hub que ya tiene sus series naturales `FAC` y `TCK`
/// (con SUS ids) importa un bundle que trae `FAC` y `TCK` de OTRA instalación.
///
/// El guard por `id` pasaba y el INSERT chocaba contra `uq_invoice_series_hub_code (hub_id, code)`:
/// «reset: aplicar sentencia: duplicate key value violates unique constraint
/// "uq_invoice_series_hub_code"». La sección `modules/invoice_series` quedaba en `Failed` y el
/// onboarding terminaba a medias.
///
/// Lo que NO puede pasar, además de no reventar: que la numeración del destino se toque. Las series
/// son FISCALES (RD 1007/2023): fusionar, renumerar o reasignar una serie rompe la correlatividad
/// que exige VeriFactu. La serie del destino conserva su `id`, su `code` y su `current_sequence`
/// exactamente como estaban.
#[tokio::test]
async fn las_series_de_facturacion_del_destino_sobreviven_al_import() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }

    // Hub A (origen): las dos series que trae cualquier plantilla.
    let a = fresh_series("h1").await;
    create_series(&a, "h1", "FAC", "Facturas", "invoice").await;
    create_series(&a, "h1", "TCK", "Tiques", "receipt").await;
    let bundle = export_hub(
        &a,
        "h1",
        &series_export_selection(),
        "peluqueria",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");

    // Hub B (destino): YA tiene FAC y TCK, con ids propios y distintos.
    let mut b = fresh_series("h2").await;
    create_series(&b, "h2", "FAC", "Facturas", "invoice").await;
    create_series(&b, "h2", "TCK", "Tiques", "receipt").await;
    let antes = series_fingerprint(&b, "h2").await;
    assert_eq!(
        antes.len(),
        2,
        "el destino tenía que arrancar con sus dos series"
    );

    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_series_only(),
        "h2",
    )
    .await
    .expect("import en B");
    let sec = report
        .sections
        .iter()
        .find(|s| s.section == "modules/invoice_series")
        .expect("invoice_series en informe");
    assert!(
        !matches!(sec.status, SectionStatus::Failed(_)),
        "las series del destino no pueden tumbar la sección: {:?}",
        sec.status
    );

    // Correlatividad fiscal: ni un id, ni un código, ni un contador se han movido.
    let despues = series_fingerprint(&b, "h2").await;
    assert_eq!(
        antes, despues,
        "el import tocó las series FISCALES del destino (id/código/numeración)"
    );
}

/// Lo que trae el bundle NO se aplica en silencio: el informe dice que la numeración de otra
/// instalación se ha quedado fuera, y cuántas filas eran.
///
/// Que el hub destino ya tuviera `FAC` no puede ser la única razón por la que nada aterriza: una
/// serie define **cómo numera un negocio lo que declara a Hacienda** y `invoice_series_allocation`
/// es el libro de números ya entregados que el RD 1007/2023 exige sin huecos ni duplicados. De
/// otra instalación, aquí, son numeración ajena — la misma regla que ya se aplica a la cadena
/// VeriFactu (`installation_bound_not_portable`, ADR-0202 §4.2 generalizada por hub#380).
#[tokio::test]
async fn la_numeracion_de_otra_instalacion_se_descarta_diciendolo() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }

    let a = fresh_series("h1").await;
    create_series(&a, "h1", "FAC", "Facturas", "invoice").await;
    let bundle = export_hub(
        &a,
        "h1",
        &series_export_selection(),
        "peluqueria",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");

    // Destino LIMPIO: aquí no hay ninguna colisión que resolver, y aun así no se aplica.
    let mut b = fresh_series("h2").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_series_only(),
        "h2",
    )
    .await
    .expect("import en B");
    let sec = report
        .sections
        .iter()
        .find(|s| s.section == "modules/invoice_series")
        .expect("invoice_series en informe");
    assert!(
        matches!(&sec.status, SectionStatus::Ignored(r) | SectionStatus::PartiallyApplied(r)
                 if r == "numbering_not_portable"),
        "el descarte tiene que ir con su motivo estable: {:?}",
        sec.status
    );
    assert!(
        sec.discarded_rows > 0,
        "un descarte que no dice CUÁNTAS filas eran es casi mudo"
    );
    assert!(
        series_fingerprint(&b, "h2").await.is_empty(),
        "la serie de otra instalación no puede aterrizar aquí"
    );
}

/// El otro lado de la misma regla: el hub que restaura SU PROPIA copia recupera sus series.
/// Es su numeración volviendo a su sitio (ADR-0113 §1) — sin esto, un redespliegue perdería la
/// serie con la que el negocio venía numerando.
#[tokio::test]
async fn un_hub_que_restaura_su_propia_copia_recupera_sus_series() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }

    let a = fresh_series("h1").await;
    create_series(&a, "h1", "FAC", "Facturas", "invoice").await;
    let bundle = export_hub(
        &a,
        "h1",
        &series_export_selection(),
        "copia",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");
    assert_eq!(
        bundle.manifest.hub.hub_id, "h1",
        "el bundle registra su hub de origen"
    );

    // El MISMO hub, reconstruido desde cero (redespliegue restaurando su copia).
    let mut b = fresh_series("h1").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_series_only(),
        "h1",
    )
    .await
    .expect("restaurar su propia copia");
    let sec = report
        .sections
        .iter()
        .find(|s| s.section == "modules/invoice_series")
        .expect("invoice_series en informe");
    assert!(
        matches!(sec.status, SectionStatus::Applied),
        "debía aplicarse: {:?}",
        sec.status
    );
    let codes: Vec<String> = series_fingerprint(&b, "h1")
        .await
        .into_iter()
        .map(|(_, c, _)| c)
        .collect();
    assert_eq!(
        codes,
        vec!["FAC".to_string()],
        "el hub no recuperó su propia serie: {codes:?}"
    );
}

/// One statement for a table the installed version RETIRED must not sink the section (hub#1947).
///
/// The `peluqueria` template published in the catalogue was built on 2026-08-24 against
/// `appointments` 1.1.53, so `data/appointments.sql` opens with a row for `appointments_schedule`.
/// The module retired that table in `009_drop_own_timetable.sql`, and a hub applying the template
/// today installs 1.1.79: statement 2 of 65 died with «relation "appointments_schedule" does not
/// exist» and took the 63 behind it — the 28 sample appointments included. The salon was born with
/// the agenda the template promises EMPTY and a red banner on the dashboard.
///
/// A published bundle is an immutable artefact and every module that retires a table breaks every
/// bundle exported before it, so the engine is what has to hold: rows for a table that is gone
/// cannot land anywhere, and must not take the rest of the section with them.
#[tokio::test]
async fn rows_for_a_retired_table_do_not_sink_the_rest_of_the_section() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;
    let original = String::from_utf8(
        bundle
            .files
            .get("data/inventory.sql")
            .expect("el bundle trae los datos de inventory")
            .clone(),
    )
    .expect("data/inventory.sql es UTF-8");

    // FIRST, exactly where the real bundle carries it: what dies first is what takes the rest.
    // Same shape `export::rows_to_sql` emits, over a table this hub's `inventory` does not have.
    let retired = "INSERT INTO inventory_retired_shelf (\"hub_id\", \"id\", \"name\") \
                   SELECT '__HUB_ID__', 'shelf-1', 'Estante' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_retired_shelf WHERE id = 'shelf-1');\n";
    let doctored = format!("{retired}{original}").into_bytes();
    bundle
        .manifest
        .sha256
        .insert("data/inventory.sql".into(), sha256_hex(&doctored));
    bundle.files.insert("data/inventory.sql".into(), doctored);

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("el import no se rompe");

    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(&inv.status, SectionStatus::PartiallyApplied(r)
                 if r == "table_gone_in_installed_version"),
        "la sección tiene que entrar diciendo qué se quedó fuera: {:?}",
        inv.status
    );
    assert_eq!(
        inv.discarded_rows, 1,
        "un descarte que no dice CUÁNTAS filas eran es casi mudo"
    );

    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()) && names.contains(&"Té verde".to_string()),
        "las filas de las tablas que SÍ existen tienen que aterrizar: {names:?}"
    );
}

/// The other end of the same rule: a section that is NOTHING but retired tables did not «apply».
///
/// Reporting `Applied` over zero rows would tell the salon its data landed. It is the same answer
/// the engine already gives when a filter leaves nothing behind — `Ignored` with the reason.
#[tokio::test]
async fn a_section_that_is_only_retired_tables_is_ignored_not_applied() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;
    let only_retired = "INSERT INTO inventory_retired_shelf (\"hub_id\", \"id\", \"name\") \
                        SELECT '__HUB_ID__', 'shelf-1', 'Estante' \
                        WHERE NOT EXISTS (SELECT 1 FROM inventory_retired_shelf WHERE id = 'shelf-1');\n"
        .as_bytes()
        .to_vec();
    bundle
        .manifest
        .sha256
        .insert("data/inventory.sql".into(), sha256_hex(&only_retired));
    bundle.files.insert("data/inventory.sql".into(), only_retired);

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("el import no se rompe");

    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(&inv.status, SectionStatus::Ignored(r)
                 if r == "table_gone_in_installed_version"),
        "nada aterrizó: decir «aplicada» sería mentir: {:?}",
        inv.status
    );
    assert_eq!(inv.discarded_rows, 1, "y tiene que decir cuántas filas eran");
}

/// Both filters on one section: the report has room for ONE reason, and the ORIGIN rule takes it.
///
/// A foreign bundle's `invoice_series` section is discarded whole because numbering belongs to one
/// installation (hub#753); if that same section also carries a retired table, the count has to add
/// up BOTH — «how much stayed out» is one number, not one per rule — while the reason the owner is
/// told stays the one she can act on. A retired table is the product moving on; somebody else's
/// numbering is why her series were not touched.
#[tokio::test]
async fn when_two_rules_discard_the_same_section_the_origin_one_is_what_is_said() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let a = fresh_series("h1").await;
    create_series(&a, "h1", "FAC", "Facturas", "invoice").await;
    let mut bundle = export_hub(
        &a,
        "h1",
        &series_export_selection(),
        "peluqueria",
        "es",
        CREATED_AT,
    )
    .await
    .expect("export A");

    let original = String::from_utf8(
        bundle
            .files
            .get("data/invoice_series.sql")
            .expect("el bundle trae los datos de invoice_series")
            .clone(),
    )
    .expect("data/invoice_series.sql es UTF-8");
    let retired = "INSERT INTO invoice_series_retired_book (\"hub_id\", \"id\", \"name\") \
                   SELECT '__HUB_ID__', 'book-1', 'Libro' \
                   WHERE NOT EXISTS (SELECT 1 FROM invoice_series_retired_book WHERE id = 'book-1');\n";
    let doctored = format!("{retired}{original}").into_bytes();
    bundle
        .manifest
        .sha256
        .insert("data/invoice_series.sql".into(), sha256_hex(&doctored));
    bundle
        .files
        .insert("data/invoice_series.sql".into(), doctored);

    let mut b = fresh_series("h2").await;
    let report = import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &import_series_only(),
        "h2",
    )
    .await
    .expect("import en B");
    let sec = report
        .sections
        .iter()
        .find(|s| s.section == "modules/invoice_series")
        .expect("invoice_series en informe");
    assert!(
        matches!(&sec.status, SectionStatus::Ignored(r) | SectionStatus::PartiallyApplied(r)
                 if r == "numbering_not_portable"),
        "el motivo accionable es el de origen, no el de la tabla retirada: {:?}",
        sec.status
    );
    assert_eq!(
        sec.discarded_rows, 2,
        "el recuento es de TODO lo que se quedó fuera, no de lo que descartó una sola regla"
    );
    assert!(
        series_fingerprint(&b, "h2").await.is_empty(),
        "la serie de otra instalación no puede aterrizar aquí"
    );
}

/// A table named the way SQL lets you name it — `"inventory_product"` — is the SAME table.
///
/// The import subset accepts a quoted identifier (its tokenizer unquotes before asking the scope),
/// so a bundle may legitimately arrive written that way; a bundle is a file the user supplies, not
/// only something our own export wrote. The filter that leaves out retired tables compares the
/// name against the database catalogue, and comparing `"inventory_product"` WITH its quotes finds
/// nothing — which would read as «retired» and drop rows that have a table waiting for them. A
/// discard rule that is wrong about WHICH table this is loses data silently, which is worse than
/// the failure it was written to prevent.
#[tokio::test]
async fn a_quoted_table_name_is_the_same_table_and_its_rows_land() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let mut bundle = exported_bundle().await;
    let original = String::from_utf8(
        bundle
            .files
            .get("data/inventory.sql")
            .expect("el bundle trae los datos de inventory")
            .clone(),
    )
    .expect("data/inventory.sql es UTF-8");
    let quoted = original.replace("INSERT INTO inventory_product (", "INSERT INTO \"inventory_product\" (");
    assert_ne!(quoted, original, "el fixture tiene que llevar la tabla entrecomillada");
    let quoted = quoted.into_bytes();
    bundle
        .manifest
        .sha256
        .insert("data/inventory.sql".into(), sha256_hex(&quoted));
    bundle.files.insert("data/inventory.sql".into(), quoted);

    let mut b = fresh().await;
    let report = import_sections(&mut b, &bundle.manifest, &bundle.files, &import_all(), "h2")
        .await
        .expect("el import no se rompe");
    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("inventory en informe");
    assert!(
        matches!(inv.status, SectionStatus::Applied),
        "la sección entra entera: nada se ha retirado: {:?}",
        inv.status
    );
    assert_eq!(inv.discarded_rows, 0, "no hay nada que descartar aquí");

    let names = product_names(&b, "h2").await;
    assert!(
        names.contains(&"Café".to_string()) && names.contains(&"Té verde".to_string()),
        "las filas tienen que aterrizar igual: {names:?}"
    );
}
