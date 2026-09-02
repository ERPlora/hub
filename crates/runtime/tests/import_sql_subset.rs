//! El IMPORT de un blueprint NO ejecuta SQL arbitrario (ERPlora/hub#239).
//!
//! Un `.blueprint.zip` lo aporta el usuario y su `manifest.json` (con los sha256) lo fabrica quien
//! fabrica el bundle, así que la integridad NO dice nada de lo que el SQL hace. Antes, los
//! `data/*.sql` iban crudos a `execute_batch`: DDL incluido.
//!
//! Contrato que fijan estos tests:
//!  - un bundle legítimo (INSERT en la tabla de su sección) sigue aplicándose,
//!  - DDL (`DROP TABLE`, `ALTER`), `UPDATE`/`DELETE` y una sentencia colada tras el `;` dejan la
//!    sección en `Failed` **sin ejecutar NADA de ella** (ni la parte legítima del fichero),
//!  - una sección no puede escribir en tablas de otra sección.
//!
//! Por qué `Failed` de sección y no rechazo del bundle entero: el import es **best-effort** por
//! decisión de producto (`import_test::best_effort_a_broken_section_does_not_abort_the_rest` —
//! una sección rota no rompe el resto). La garantía de seguridad —que ese SQL no llegue a la
//! BD— se cumple igual, y el informe nombra la sección y el motivo.
//!
//! Sin modules-workspace: se usa la sección `hub_settings`, que existe en todo hub (migración de
//! sistema v4), de modo que el test corre también en CI aislado.

use std::collections::BTreeMap;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{BlueprintManifest, HubMeta, SCHEMA_VERSION};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;
use sha2::{Digest, Sha256};

fn sha256_hex(bytes: &[u8]) -> String {
    let mut h = Sha256::new();
    h.update(bytes);
    format!("{:x}", h.finalize())
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.ensure_system_tables().await.expect("tablas de sistema");
    rt
}

/// Bundle mínimo de una sola sección `hub_settings` con el SQL dado.
fn bundle(sql: &str) -> (BlueprintManifest, BTreeMap<String, Vec<u8>>) {
    let mut files = BTreeMap::new();
    files.insert("data/hub_settings.sql".to_string(), sql.as_bytes().to_vec());
    let mut sha256 = BTreeMap::new();
    for (path, bytes) in &files {
        sha256.insert(path.clone(), sha256_hex(bytes));
    }
    let manifest = BlueprintManifest {
        purpose: Default::default(),
        schema_version: SCHEMA_VERSION,
        name: "malicioso".into(),
        locale: "es".into(),
        hub: HubMeta {
            name: "Demo".into(),
            country: "ES".into(),
            currency: "EUR".into(),
            hub_id: String::new(),
        },
        created_at: "2026-07-31T00:00:00Z".into(),
        modules: vec![],
        sections: vec!["hub_settings".into()],
        active_roles: Vec::new(),
        capability_grants: Default::default(),
        flows: Vec::new(),
        sha256,
    };
    (manifest, files)
}

fn only_settings() -> ImportSelection {
    ImportSelection {
        users: false,
        settings: true,
        fiscal: false,
        media: false,
        modules: vec![],
    }
}

/// SQL tal y como lo emite el export (`rows_to_sql`): INSERT idempotente con guard NOT EXISTS.
///
/// ⚠️ La `key` de estos fixtures tiene que ser una **clave de configuración portable**
/// (`language`, `currency`, `country_code`… — `export::PORTABLE_SETTING_KEYS`). Estos bundles
/// vienen de un origen desconocido, y desde ADR-0195 §4 (hub#405) un bundle ajeno solo puede
/// escribir configuración: con la `business_name` de antes, la fila legítima se descartaría y estos
/// tests dejarían de comprobar lo suyo —que el SUBCONJUNTO SQL deja pasar lo legítimo y para lo
/// demás— para comprobar por accidente la lista blanca de claves (que tiene sus propios tests en
/// `settings_portability_e2e.rs`).
fn legit_sql(key: &str, value: &str) -> String {
    format!(
        "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\", \"updated_at\", \"updated_by\") \
         SELECT '__HUB_ID__', '{key}', '{value}', '2026-07-31T00:00:00Z', 'system' \
         WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = '{key}' AND hub_id = '__HUB_ID__');"
    )
}

async fn setting_value(rt: &Runtime, hub: &str, key: &str) -> Option<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), serde_json::json!(hub));
    p.insert("key".into(), serde_json::json!(key));
    let res = rt
        .db()
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = :key",
            &p,
        )
        .await
        .ok()?;
    res.rows.first()?.get("value")?.as_str().map(str::to_string)
}

/// ¿Sigue existiendo `hub_settings`? (si un DROP se hubiera colado, esto falla).
async fn settings_table_exists(rt: &Runtime) -> bool {
    rt.db()
        .query("SELECT COUNT(*) AS c FROM hub_settings", &Params::new())
        .await
        .is_ok()
}

/// (f) Un bundle legítimo sigue aplicándose igual que antes.
#[tokio::test]
async fn un_bundle_legitimo_se_aplica() {
    let mut rt = fresh().await;
    let (manifest, files) = bundle(&legit_sql("language", "en"));
    let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
        .await
        .expect("el bundle legítimo se importa");
    let section = report
        .sections
        .iter()
        .find(|s| s.section == "hub_settings")
        .expect("informe de la sección");
    assert!(
        matches!(section.status, SectionStatus::Applied),
        "{:?}",
        section.status
    );
    assert_eq!(
        setting_value(&rt, "h2", "language").await.as_deref(),
        Some("en"),
        "la fila aterriza bajo el hub_id destino"
    );
}

/// Motivo del `Failed` de una sección (o pánico con el estado real).
fn failure_reason(report: &erplora_runtime::import::ImportReport, section: &str) -> String {
    let entry = report
        .sections
        .iter()
        .find(|s| s.section == section)
        .unwrap_or_else(|| panic!("sin informe para {section}: {report:?}"));
    match &entry.status {
        SectionStatus::Failed(msg) => msg.clone(),
        other => panic!("{section} debía fallar, fue {other:?}"),
    }
}

/// (e) DDL en `data/*.sql` → la sección falla SIN ejecutar nada de ella.
#[tokio::test]
async fn el_ddl_no_se_ejecuta_y_deja_la_seccion_en_failed() {
    for payload in [
        "DROP TABLE hub_settings;",
        "ALTER TABLE hub_settings ADD COLUMN pwned TEXT;",
        "CREATE TABLE pwned (id TEXT);",
        "UPDATE hub_settings SET value = 'pwned';",
        "DELETE FROM hub_settings;",
        "GRANT ALL ON hub_settings TO PUBLIC;",
    ] {
        let mut rt = fresh().await;
        let sql = format!("{}\n{payload}", legit_sql("language", "en"));
        let (manifest, files) = bundle(&sql);
        let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
            .await
            .expect("best-effort: el import no aborta, la sección falla");
        let reason = failure_reason(&report, "hub_settings");
        assert!(
            reason.contains("INSERT INTO"),
            "`{payload}`: el motivo explica el subconjunto: {reason}"
        );
        assert!(
            settings_table_exists(&rt).await,
            "`{payload}`: la tabla sigue existiendo"
        );
        assert_eq!(
            setting_value(&rt, "h2", "language").await,
            None,
            "`{payload}`: no se ejecuta NADA de la sección (ni la parte legítima)"
        );
    }
}

/// Una sección no puede escribir en la tabla de otra (escalada vía `hub_user`).
#[tokio::test]
async fn una_seccion_no_puede_escribir_en_otra_tabla() {
    let mut rt = fresh().await;
    let sql = "INSERT INTO hub_user (id, name, role, pin_hash, is_active) \
               SELECT 'mallory', 'Mallory', 'owner', '', 1;";
    let (manifest, files) = bundle(sql);
    let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
        .await
        .expect("best-effort: el import no aborta");
    let reason = failure_reason(&report, "hub_settings");
    assert!(reason.contains("hub_user"), "{reason}");
}

/// EXFILTRACIÓN entre secciones: un `INSERT` en la tabla PERMITIDA cuya FUENTE es otra tabla
/// (`SELECT … FROM hub_user`) es léxicamente un INSERT legal en `hub_settings`, así que un filtro
/// que solo mire el prefijo lo deja pasar — y copia los hashes de PIN a una tabla que cualquier
/// módulo lee luego. El subconjunto solo admite LITERALES como fuente.
#[tokio::test]
async fn un_insert_que_lee_de_otra_tabla_no_exfiltra() {
    let mut rt = fresh().await;
    // Un usuario real en el hub destino, con su secreto.
    rt.db()
        .execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, role, pin_hash, is_active, created_at) \
             VALUES ('u1', 'h2', 'Ioan', 'owner', 'hash-secreto', 1, '2026-07-31T00:00:00Z');",
        )
        .await
        .expect("usuario de partida");

    let sql = "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") \
               SELECT '__HUB_ID__', 'robado', pin_hash FROM hub_user;";
    let (manifest, files) = bundle(sql);
    let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
        .await
        .expect("best-effort: el import no aborta");

    let reason = failure_reason(&report, "hub_settings");
    assert!(
        reason.contains("literales"),
        "el motivo explica el subconjunto: {reason}"
    );
    assert_eq!(
        setting_value(&rt, "h2", "robado").await,
        None,
        "el secreto de otra tabla NO se copia"
    );
}

/// CTE que MODIFICA dentro del INSERT (`INSERT INTO … WITH x AS (DELETE …) SELECT …`, válido en
/// Postgres): borra filas de otra sección pasando por un prefijo `INSERT INTO` impecable.
#[tokio::test]
async fn un_cte_que_borra_no_se_ejecuta() {
    let mut rt = fresh().await;
    rt.db()
        .execute_batch(
            "INSERT INTO hub_user (id, hub_id, name, role, pin_hash, is_active, created_at) \
             VALUES ('u1', 'h2', 'Ioan', 'owner', 'hash', 1, '2026-07-31T00:00:00Z');",
        )
        .await
        .expect("usuario de partida");

    let sql = "INSERT INTO hub_settings (\"key\") \
               WITH victima AS (DELETE FROM hub_user RETURNING id) SELECT id FROM victima;";
    let (manifest, files) = bundle(sql);
    let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
        .await
        .expect("best-effort: el import no aborta");
    let _ = failure_reason(&report, "hub_settings");

    let users = rt
        .db()
        .query("SELECT COUNT(*) AS c FROM hub_user", &Params::new())
        .await
        .expect("conteo de usuarios");
    let count = users.rows[0]["c"]
        .as_i64()
        .or_else(|| users.rows[0]["c"].as_str().and_then(|s| s.parse().ok()));
    assert_eq!(count, Some(1), "el DELETE del CTE no se ejecutó");
}

/// Un `data/*.sql` que ninguna sección del manifest referencia NO se ejecuta jamás: el bundle no
/// puede colar SQL «suelto» aunque su sha256 case.
#[tokio::test]
async fn un_fichero_de_datos_no_referenciado_nunca_se_ejecuta() {
    let mut rt = fresh().await;
    let (mut manifest, mut files) = bundle(&legit_sql("language", "en"));
    let extra = b"DROP TABLE hub_settings;".to_vec();
    manifest
        .sha256
        .insert("data/suelto.sql".into(), sha256_hex(&extra));
    files.insert("data/suelto.sql".into(), extra);

    let report = import_sections(&mut rt, &manifest, &files, &only_settings(), "h2")
        .await
        .expect("el fichero suelto no participa del import");
    assert!(
        report
            .sections
            .iter()
            .all(|s| s.section != "data/suelto.sql"),
        "no hay sección para un fichero suelto: {report:?}"
    );
    assert!(settings_table_exists(&rt).await, "el DROP no se ejecutó");
    assert_eq!(
        setting_value(&rt, "h2", "language").await.as_deref(),
        Some("en"),
        "la sección legítima sí se aplicó"
    );
}
