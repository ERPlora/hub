//! Contract (hub#1535): **a bundle's data section replaces the PLACEHOLDER its module seeded, it
//! does not live beside it.**
//!
//! The defect a business sees: it imports the blueprint of its sector and the opening week comes
//! out duplicated and contradictory — Saturday appears twice, once open 09:30–14:00 and once
//! closed. Nothing reports an error, and from then on «are we open?» answers according to whichever
//! row is read first, so a Saturday booking is taken or refused with no pattern.
//!
//! The sequence is the one a TEMPLATE import runs: the bundle names the module, so the import
//! INSTALLS it first — which applies `seed/install.postgres.sql` and plants the generic week
//! (ERPlora/schedules#36, so that «no hours configured» stops being a reachable state) — and only
//! THEN applies the section with the real hours. Unlike hub#842 there is no natural key to fall
//! back on, and for two legitimate reasons:
//!
//! * **no UNIQUE index** — `schedules` dropped `uq_schedules_business_hours_hub_day` in
//!   `002_business_hours_intervals.sql`, because since schedules#8 a split shift is SEVERAL rows
//!   per weekday, so `export::natural_keys` finds nothing;
//! * **no key declared by the seed** — its guard is the whole table (`WHERE hub_id = :hub_id`) and
//!   `parse_seed_guard` returns no key on purpose when the only column is `hub_id`: as a key it
//!   would skip EVERY incoming row the moment the module had seeded one.
//!
//! So the guard is left with `id` alone, the seeded id never matches the one `derive_id` just
//! rewrote for the destination, and both weeks live: 14 rows where there should be 7.
//!
//! What this pins is the rule, not the module: a whole-table seed guard is the module SAYING that
//! what it plants is a placeholder, and the importer — which is generic and serves the 27 modules —
//! retires it when the real data lands. It is the same rule the starter catalog already writes by
//! hand in SQL (ERPlora/blueprints#24, the salon taking over the seeded week day by day).
//!
//! ⚠️ **The modules are FIXTURES built here, not `modules-workspace`.** The rule under test belongs
//! to the runtime, and `schedules` is a sibling repo on its own release cadence: pointing this at
//! the shared checkout would make the test's meaning depend on how fresh that checkout is — and a
//! checkout that predates schedules#36 has no seed at all, so the scenario would silently stop
//! existing while the test still went green. The fixtures reproduce the two guard shapes exactly.

use std::path::{Path, PathBuf};

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::Runtime;

/// A throwaway module directory, unique per call so tests running in parallel never share one.
fn fixture_dir(tag: &str) -> PathBuf {
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let dir = std::env::temp_dir().join(format!("erplora-hub1535-{tag}-{}-{unique}", std::process::id()));
    std::fs::create_dir_all(dir.join("migrations/postgres")).expect("migrations dir");
    std::fs::create_dir_all(dir.join("seed")).expect("seed dir");
    dir
}

fn write(dir: &Path, rel: &str, body: &str) {
    std::fs::write(dir.join(rel), body).expect("write fixture file");
}

fn manifest(dir: &Path, id: &str) {
    write(
        dir,
        "module.json",
        &format!(
            r#"{{
  "id": "{id}",
  "name": "{id}",
  "version": "1.0.0",
  "migrations": {{ "postgres": ["migrations/postgres/001_init.sql"] }},
  "seed": {{ "postgres": ["seed/install.postgres.sql"] }}
}}"#
        ),
    );
}

/// The `schedules` shape: one row per weekday, **no unique index** on the slot (schedules#8), and a
/// seed guarded by the WHOLE TABLE — «plant the generic week only while this hub has nothing».
fn modulo_con_marcador_de_tabla_entera() -> PathBuf {
    let dir = fixture_dir("weekplan");
    manifest(&dir, "weekplan");
    write(
        &dir,
        "migrations/postgres/001_init.sql",
        "CREATE TABLE IF NOT EXISTS weekplan_hours (\
             id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, day_of_week INTEGER NOT NULL, \
             position INTEGER NOT NULL DEFAULT 0, open_time TEXT NOT NULL, \
             close_time TEXT NOT NULL, is_closed INTEGER NOT NULL DEFAULT 0, \
             is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT, created_by TEXT, \
             created_at TEXT NOT NULL, updated_by TEXT, updated_at TEXT);\n\
         CREATE INDEX IF NOT EXISTS idx_weekplan_hours_hub ON weekplan_hours (hub_id, is_deleted);",
    );
    write(
        &dir,
        "seed/install.postgres.sql",
        "INSERT INTO weekplan_hours \
           (id, hub_id, day_of_week, position, open_time, close_time, is_closed, \
            is_deleted, created_by, created_at, updated_by, updated_at) \
         SELECT (:hub_id || '|wp|' || d.day_of_week), :hub_id, d.day_of_week, 0, \
                d.open_time, d.close_time, d.is_closed, 0, :current_user_id, :now, \
                :current_user_id, :now \
         FROM (VALUES (0, '09:00', '18:00', 0), (1, '09:00', '18:00', 0), \
                      (2, '09:00', '18:00', 0), (3, '09:00', '18:00', 0), \
                      (4, '09:00', '18:00', 0), (5, '00:00', '00:00', 1), \
                      (6, '00:00', '00:00', 1)) \
              AS d(day_of_week, open_time, close_time, is_closed) \
         WHERE NOT EXISTS (SELECT 1 FROM weekplan_hours WHERE hub_id = :hub_id);",
    );
    dir
}

/// The `taxes`/`inventory` shape, and the one that must NOT be touched: reference rows with a seed
/// guard **per row** (`(hub_id, code)`). Deleting these would take out canonical data other modules
/// resolve by key — the failure this fix has to stay away from.
fn modulo_con_datos_de_referencia() -> PathBuf {
    let dir = fixture_dir("unitcat");
    manifest(&dir, "unitcat");
    write(
        &dir,
        "migrations/postgres/001_init.sql",
        "CREATE TABLE IF NOT EXISTS unitcat_unit (\
             id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, code TEXT NOT NULL, name TEXT NOT NULL, \
             is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT, created_by TEXT, \
             created_at TEXT NOT NULL, updated_by TEXT, updated_at TEXT);",
    );
    let mut seed = String::new();
    for (code, name) in [("ud", "Unit"), ("kg", "Kilogram"), ("l", "Litre")] {
        seed.push_str(&format!(
            "INSERT INTO unitcat_unit (id, hub_id, code, name, is_deleted, created_by, created_at, \
              updated_by, updated_at) \
             SELECT (:hub_id || '|u|{code}'), :hub_id, '{code}', '{name}', 0, :current_user_id, \
                    :now, :current_user_id, :now \
             WHERE NOT EXISTS (SELECT 1 FROM unitcat_unit WHERE hub_id = :hub_id AND code = '{code}');\n"
        ));
    }
    write(&dir, "seed/install.postgres.sql", &seed);
    dir
}

async fn hub_con(hub_id: &str, dirs: &[&Path]) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    for dir in dirs {
        rt.install_from_dir(dir).await.expect("instalar el módulo");
    }
    rt
}

/// The live week, as the «are we open?» reader sees it: `(day, open, close, is_closed, created_by)`.
async fn semana(rt: &Runtime, hub_id: &str) -> Vec<(i64, String, String, i64, String)> {
    let sql = format!(
        "SELECT day_of_week, open_time, close_time, is_closed, \
                COALESCE(created_by, '') AS created_by \
         FROM weekplan_hours WHERE hub_id = '{hub_id}' AND is_deleted = 0 \
         ORDER BY day_of_week, position, open_time"
    );
    let res = rt.db().query(&sql, &Params::new()).await.expect("semana");
    res.rows
        .iter()
        .map(|r| {
            let s = |k: &str| {
                r.get(k)
                    .and_then(|v| v.as_str())
                    .unwrap_or_default()
                    .to_string()
            };
            let i = |k: &str| r.get(k).and_then(|v| v.as_i64()).unwrap_or(-1);
            (
                i("day_of_week"),
                s("open_time"),
                s("close_time"),
                i("is_closed"),
                s("created_by"),
            )
        })
        .collect()
}

async fn unidades(rt: &Runtime, hub_id: &str) -> Vec<String> {
    let sql = format!(
        "SELECT code FROM unitcat_unit WHERE hub_id = '{hub_id}' AND is_deleted = 0 ORDER BY code"
    );
    let res = rt.db().query(&sql, &Params::new()).await.expect("unidades");
    res.rows
        .iter()
        .filter_map(|r| r.get("code").and_then(|v| v.as_str()).map(str::to_string))
        .collect()
}

/// The owner saves the Hours screen: the seeded week stops being a placeholder and becomes a fact
/// about the business (`created_by` = a user, not `system`). That is what makes it TRAVEL —
/// `export::is_module_seeded` keeps the module's own placeholder out of every bundle.
async fn owner_sets_hours(rt: &Runtime, hub_id: &str) {
    for (day, open, close, closed) in [
        (0, "09:30", "20:00", 0),
        (1, "09:30", "20:00", 0),
        (2, "09:30", "20:00", 0),
        (3, "09:30", "20:00", 0),
        (4, "09:30", "20:00", 0),
        // Saturday OPEN — the generic seed has it closed. That contradiction is the symptom.
        (5, "09:30", "14:00", 0),
        (6, "00:00", "00:00", 1),
    ] {
        let sql = format!(
            "UPDATE weekplan_hours \
             SET open_time = '{open}', close_time = '{close}', is_closed = {closed}, \
                 created_by = 'u-owner', updated_by = 'u-owner', \
                 updated_at = '2026-08-15T10:00:00Z' \
             WHERE hub_id = '{hub_id}' AND day_of_week = {day}"
        );
        rt.db()
            .execute(&sql, &Params::new())
            .await
            .expect("owner saves the hours screen");
    }
}

async fn owner_adds_unit(rt: &Runtime, hub_id: &str, code: &str) {
    let sql = format!(
        "INSERT INTO unitcat_unit (id, hub_id, code, name, is_deleted, created_by, created_at, \
          updated_by, updated_at) \
         VALUES ('{hub_id}-own-{code}', '{hub_id}', '{code}', '{code}', 0, 'u-owner', \
                 '2026-08-15T10:00:00Z', 'u-owner', '2026-08-15T10:00:00Z')"
    );
    rt.db()
        .execute(&sql, &Params::new())
        .await
        .expect("owner adds a unit");
}

fn seleccion(modules: &[&str]) -> ExportSelection {
    ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: modules
            .iter()
            .map(|id| ModuleDataSelection {
                module_id: (*id).to_string(),
                with_data: true,
                tables: None,
            })
            .collect(),
        purpose: BundlePurpose::Template,
    }
}

fn import_selection(modules: &[&str]) -> ImportSelection {
    ImportSelection {
        users: false,
        settings: false,
        fiscal: false,
        media: false,
        modules: modules.iter().map(|id| (*id).to_string()).collect(),
    }
}

async fn aplica(
    destino: &mut Runtime,
    bundle: &erplora_runtime::export::ExportBundle,
    hub_id: &str,
    modules: &[&str],
) {
    let report = import_sections(
        destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(modules),
        hub_id,
    )
    .await
    .expect("best-effort");
    for id in modules {
        let name = format!("modules/{id}");
        let s = report
            .sections
            .iter()
            .find(|s| s.section == name)
            .unwrap_or_else(|| panic!("{name} en el informe: {:?}", report.sections));
        assert!(
            matches!(s.status, SectionStatus::Applied),
            "sección {name}: {:?}",
            s.status
        );
    }
}

/// 🔴 The golden one: importing the template over a hub that just installed the module leaves
/// **seven** rows, not fourteen — and the week that stays is the one the BUSINESS set, Saturday
/// included.
#[tokio::test]
async fn importar_una_plantilla_no_duplica_el_horario_sembrado() {
    let wp = modulo_con_marcador_de_tabla_entera();
    let origen = hub_con("h1", &[&wp]).await;
    owner_sets_hours(&origen, "h1").await;
    let bundle = export_hub(
        &origen,
        "h1",
        &seleccion(&["weekplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");

    let sql = String::from_utf8(bundle.files["data/weekplan.sql"].clone()).unwrap();
    assert!(
        sql.contains("'09:30'"),
        "premise: the template carries the hours its owner set:\n{sql}"
    );
    assert!(
        !sql.contains("'system'"),
        "premise: the module's OWN seeded rows never travel (export::is_module_seeded):\n{sql}"
    );

    // DESTINO: a hub where installing the module planted the generic week — step 2 of every
    // template import, and the step an `export`→`import` between two live hubs never performs.
    let mut destino = hub_con("h2", &[&wp]).await;
    let sembrada = semana(&destino, "h2").await;
    assert_eq!(
        sembrada.len(),
        7,
        "precondición: instalar el módulo siembra los 7 días — {sembrada:?}"
    );
    assert_eq!(
        sembrada[5],
        (5, "00:00".into(), "00:00".into(), 1, "system".into()),
        "precondición: el sábado sembrado está CERRADO y firmado por el instalador"
    );

    aplica(&mut destino, &bundle, "h2", &["weekplan"]).await;

    let tras = semana(&destino, "h2").await;
    assert_eq!(
        tras.len(),
        7,
        "el sábado sale abierto y cerrado a la vez: {} filas vivas donde debe haber 7 — {tras:?}",
        tras.len()
    );
    let sabados: Vec<_> = tras.iter().filter(|r| r.0 == 5).collect();
    assert_eq!(
        sabados.len(),
        1,
        "«¿estamos abiertos el sábado?» contesta según la fila que le toque: {sabados:?}"
    );
    assert_eq!(
        (sabados[0].1.as_str(), sabados[0].2.as_str(), sabados[0].3),
        ("09:30", "14:00", 0),
        "el horario que gana tiene que ser el del negocio, no el marcador genérico"
    );
}

/// 🔴 The other half, and the one that keeps the fix from being worse than the bug: a seed that
/// declares a key PER ROW is reference data, not a placeholder. Its rows stay — including the ones
/// the bundle says nothing about — because other modules resolve them by key.
#[tokio::test]
async fn los_datos_de_referencia_de_un_modulo_no_se_retiran() {
    let uc = modulo_con_datos_de_referencia();
    let origen = hub_con("h1", &[&uc]).await;
    owner_adds_unit(&origen, "h1", "box").await;
    let bundle = export_hub(
        &origen,
        "h1",
        &seleccion(&["unitcat"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");

    let mut destino = hub_con("h2", &[&uc]).await;
    assert_eq!(
        unidades(&destino, "h2").await,
        vec!["kg", "l", "ud"],
        "precondición: instalar el módulo siembra sus unidades canónicas"
    );

    aplica(&mut destino, &bundle, "h2", &["unitcat"]).await;

    assert_eq!(
        unidades(&destino, "h2").await,
        vec!["box", "kg", "l", "ud"],
        "las unidades canónicas del módulo NO son un marcador: la plantilla añade la suya y las \
         tres sembradas siguen ahí"
    );
}

/// Re-importing the same bundle keeps being a no-op: after the first pass there is no placeholder
/// left to retire and no row left to insert.
#[tokio::test]
async fn reimportar_la_misma_plantilla_sigue_siendo_idempotente() {
    let wp = modulo_con_marcador_de_tabla_entera();
    let origen = hub_con("h1", &[&wp]).await;
    owner_sets_hours(&origen, "h1").await;
    let bundle = export_hub(
        &origen,
        "h1",
        &seleccion(&["weekplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");

    let mut destino = hub_con("h2", &[&wp]).await;
    aplica(&mut destino, &bundle, "h2", &["weekplan"]).await;
    let tras_el_primero = semana(&destino, "h2").await;
    aplica(&mut destino, &bundle, "h2", &["weekplan"]).await;
    assert_eq!(
        semana(&destino, "h2").await,
        tras_el_primero,
        "re-importar el mismo bundle no puede añadir filas"
    );
}
