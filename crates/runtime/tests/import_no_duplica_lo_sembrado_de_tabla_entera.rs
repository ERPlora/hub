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

use erplora_db::{
    testutil::{fresh_db, TestDb},
    Params,
};
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ModuleDataSelection};
use erplora_runtime::import::{import_sections, ImportSelection, SectionStatus};
use erplora_runtime::reset::undo_import;
use erplora_runtime::Runtime;

/// A throwaway module directory, unique per call so tests running in parallel never share one.
fn fixture_dir(tag: &str) -> PathBuf {
    let unique = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .expect("clock")
        .as_nanos();
    let dir = std::env::temp_dir().join(format!(
        "erplora-hub1535-{tag}-{}-{unique}",
        std::process::id()
    ));
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

/// A third shape, the one that keeps the fix from being CATASTROPHIC: a whole-table seed guard
/// **plus a UNIQUE index** on the slot. The seed still says «placeholder», but the unique key makes
/// hub#842 skip every incoming row — the bundle lands nothing — so retiring the placeholder here
/// would leave the hub with no hours at all.
fn modulo_con_marcador_y_clave_unica() -> PathBuf {
    let dir = fixture_dir("gridplan");
    manifest(&dir, "gridplan");
    write(
        &dir,
        "migrations/postgres/001_init.sql",
        "CREATE TABLE IF NOT EXISTS gridplan_hours (\
             id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, day_of_week INTEGER NOT NULL, \
             position INTEGER NOT NULL DEFAULT 0, open_time TEXT NOT NULL, \
             close_time TEXT NOT NULL, is_closed INTEGER NOT NULL DEFAULT 0, \
             is_deleted INTEGER NOT NULL DEFAULT 0, deleted_at TEXT, created_by TEXT, \
             created_at TEXT NOT NULL, updated_by TEXT, updated_at TEXT);\n\
         CREATE UNIQUE INDEX IF NOT EXISTS uq_gridplan_hours_hub_day \
             ON gridplan_hours (hub_id, day_of_week);",
    );
    write(
        &dir,
        "seed/install.postgres.sql",
        "INSERT INTO gridplan_hours \
           (id, hub_id, day_of_week, position, open_time, close_time, is_closed, \
            is_deleted, created_by, created_at, updated_by, updated_at) \
         SELECT (:hub_id || '|gp|' || d.day_of_week), :hub_id, d.day_of_week, 0, \
                d.open_time, d.close_time, d.is_closed, 0, :current_user_id, :now, \
                :current_user_id, :now \
         FROM (VALUES (0, '09:00', '18:00', 0), (1, '09:00', '18:00', 0), \
                      (2, '09:00', '18:00', 0), (3, '09:00', '18:00', 0), \
                      (4, '09:00', '18:00', 0), (5, '00:00', '00:00', 1), \
                      (6, '00:00', '00:00', 1)) \
              AS d(day_of_week, open_time, close_time, is_closed) \
         WHERE NOT EXISTS (SELECT 1 FROM gridplan_hours WHERE hub_id = :hub_id);",
    );
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
    semana_en(rt, hub_id, "weekplan_hours").await
}

async fn semana_en(
    rt: &Runtime,
    hub_id: &str,
    table: &str,
) -> Vec<(i64, String, String, i64, String)> {
    let sql = format!(
        "SELECT day_of_week, open_time, close_time, is_closed, \
                COALESCE(created_by, '') AS created_by \
         FROM {table} WHERE hub_id = '{hub_id}' AND is_deleted = 0 \
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
    owner_sets_hours_en(rt, hub_id, "weekplan_hours").await
}

async fn owner_sets_hours_en(rt: &Runtime, hub_id: &str, table: &str) {
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
            "UPDATE {table} \
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

/// 🔴 The other end of the same rule, and the one that makes retiring the placeholder SAFE:
/// **undoing the import puts the seeded week back.**
///
/// This is the path ADR-0170 exists for — «I import the demo, I look at it, I take it off cleanly».
/// If the undo only deleted the imported rows, the hub would be left with NO hours at all: the
/// placeholder is soft-deleted, and the module's seed guard (`WHERE NOT EXISTS … hub_id = :hub_id`)
/// does not filter `is_deleted`, so it sees the buried row and never plants the week again. The
/// business would come out of «undo» worse than it went in, and silently — «are we open?» would
/// answer nothing at all, which is exactly the state ERPlora/schedules#36 made unreachable.
#[tokio::test]
async fn deshacer_la_importacion_devuelve_el_horario_que_el_modulo_habia_sembrado() {
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
    let sembrada = semana(&destino, "h2").await;
    assert_eq!(
        sembrada.len(),
        7,
        "precondición: la semana sembrada — {sembrada:?}"
    );

    let report = import_sections(
        &mut destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(&["weekplan"]),
        "h2",
    )
    .await
    .expect("best-effort");
    let batch = report
        .batch_id
        .clone()
        .expect("el import abre un lote (ADR-0170) — sin él no hay nada que deshacer");
    let importada = semana(&destino, "h2").await;
    assert_eq!(
        importada.len(),
        7,
        "precondición: tras importar queda SOLO la semana del negocio — {importada:?}"
    );
    assert!(
        importada.iter().all(|r| r.4 != "system"),
        "precondición: el marcador ya se retiró — {importada:?}"
    );

    undo_import(&destino, "h2", &batch)
        .await
        .expect("deshacer la importación");

    let tras_deshacer = semana(&destino, "h2").await;
    assert_eq!(
        tras_deshacer, sembrada,
        "deshacer tiene que dejar el hub COMO ESTABA: con la semana genérica que el módulo sembró \
         al instalarse, no sin horario — {tras_deshacer:?}"
    );
}

/// Y deshacer dos veces no rompe ni resucita nada: el segundo pase no encuentra lote y es un no-op
/// limpio, igual que para las filas importadas (`reset_undo_test`).
#[tokio::test]
async fn deshacer_dos_veces_deja_la_semana_sembrada_igual() {
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
    let sembrada = semana(&destino, "h2").await;
    let report = import_sections(
        &mut destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(&["weekplan"]),
        "h2",
    )
    .await
    .expect("best-effort");
    let batch = report.batch_id.clone().expect("lote del import");

    undo_import(&destino, "h2", &batch).await.expect("deshacer");
    undo_import(&destino, "h2", &batch)
        .await
        .expect("deshacer otra vez es un no-op limpio");

    assert_eq!(
        semana(&destino, "h2").await,
        sembrada,
        "el segundo deshacer no puede duplicar ni volver a enterrar la semana sembrada"
    );
}

/// 🔴 The close that stops this fix from being worse than the bug it fixes: **the placeholder is
/// only retired once the real data is actually IN.**
///
/// A module can perfectly well seed a whole-table placeholder AND keep a unique index on the slot.
/// When it does, hub#842 skips every incoming row of the bundle (an equivalent row is already
/// there), so the section applies without landing anything. Retiring the placeholder on the way out
/// would then leave the business with **no hours at all** — the state ERPlora/schedules#36 exists to
/// make unreachable — and it would happen quietly, right after a screen that said the import went
/// fine. Keeping the generic week is the bad-but-honest outcome; zero rows is the unacceptable one.
#[tokio::test]
async fn si_la_plantilla_no_llega_a_entrar_el_hub_conserva_su_semana() {
    let gp = modulo_con_marcador_y_clave_unica();
    let origen = hub_con("h1", &[&gp]).await;
    owner_sets_hours_en(&origen, "h1", "gridplan_hours").await;
    let bundle = export_hub(
        &origen,
        "h1",
        &seleccion(&["gridplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");

    let mut destino = hub_con("h2", &[&gp]).await;
    let sembrada = semana_en(&destino, "h2", "gridplan_hours").await;
    assert_eq!(
        sembrada.len(),
        7,
        "precondición: instalar el módulo siembra la semana genérica — {sembrada:?}"
    );

    import_sections(
        &mut destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(&["gridplan"]),
        "h2",
    )
    .await
    .expect("best-effort");

    let tras = semana_en(&destino, "h2", "gridplan_hours").await;
    assert!(
        !tras.is_empty(),
        "el import no puede dejar al negocio SIN HORARIO: si la plantilla no llegó a entrar, el \
         marcador se queda — {tras:?}"
    );
    assert_eq!(
        tras, sembrada,
        "y se queda tal cual estaba, sin retirar ni duplicar nada — {tras:?}"
    );
}

/// 🔴 Tenancy (hub#1535): retiring the placeholder is scoped to the hub that imported. On a
/// database SHARED by several hubs (the pre-ADR-0201 layout, still live for legacy hubs and the
/// case hub#260 was written for), the neighbour's seeded week has to stay exactly as it was —
/// after the import AND after undoing it. The retire query selects by `hub_id`; the soft-delete
/// then goes by the ids it found. Drop the `hub_id` filter and the neighbour wakes up with no hours.
#[tokio::test]
async fn retiring_the_placeholder_never_touches_a_sibling_hub_on_the_same_database() {
    let wp = modulo_con_marcador_de_tabla_entera();
    let origen = hub_con("h0", &[&wp]).await;
    owner_sets_hours(&origen, "h0").await;
    let bundle = export_hub(
        &origen,
        "h0",
        &seleccion(&["weekplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla");

    // Two hubs over ONE schema, each with the module installed — and therefore each with its own
    // seeded week signed by the installer.
    let shared = TestDb::new().await;
    let mut vecino = Runtime::with_hub_id(Box::new(shared.adapter().await), "h1");
    vecino
        .install_from_dir(&wp)
        .await
        .expect("instalar en el vecino");
    let mut destino = Runtime::with_hub_id(Box::new(shared.adapter().await), "h2");
    destino
        .install_from_dir(&wp)
        .await
        .expect("instalar en el destino");
    let semana_vecino = semana(&vecino, "h1").await;
    assert_eq!(
        semana_vecino.len(),
        7,
        "precondition: the neighbour has its seeded week — {semana_vecino:?}"
    );
    assert!(
        semana_vecino.iter().all(|r| r.4 == "system"),
        "precondition: the neighbour's week is the installer's — {semana_vecino:?}"
    );

    let report = import_sections(
        &mut destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(&["weekplan"]),
        "h2",
    )
    .await
    .expect("best-effort");
    let batch = report.batch_id.clone().expect("lote del import");
    let tras = semana(&destino, "h2").await;
    assert_eq!(
        tras.len(),
        7,
        "the target adopts the template's week — {tras:?}"
    );
    assert!(
        tras.iter().all(|r| r.4 != "system"),
        "…and its placeholder is gone — {tras:?}"
    );
    assert_eq!(
        semana(&vecino, "h1").await,
        semana_vecino,
        "the neighbour's seeded week must not be retired by ANOTHER hub's import"
    );

    undo_import(&destino, "h2", &batch).await.expect("deshacer");
    assert_eq!(
        semana(&vecino, "h1").await,
        semana_vecino,
        "…nor touched by undoing it"
    );
    let devuelta = semana(&destino, "h2").await;
    assert!(
        devuelta.len() == 7 && devuelta.iter().all(|r| r.4 == "system"),
        "the target gets ITS OWN seeded week back — {devuelta:?}"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// hub#1548 · hub#1550 · hub#1551 — the three other doors into the same symptom.
//
// hub#1535 pinned ONE crossing: the module's placeholder against a template. These three are the
// rest of the rule, and they only make sense together because they are the same statement read at
// its three ends — a whole-table seed guard is the module saying **this table holds ONE hub-wide
// object**, so:
//
// * it travels WHOLE once the business adopted it (export, #1550),
// * an incoming bundle REPLACES it instead of living beside it (import, #1548),
// * and undo only puts back what it took IF the hole is still there (undo, #1551).
//
// Market check (the two business calls, per the `market-decision` skill): every mature product
// keys master-data import and replaces — Odoo upserts by external ID, Shopify matches by handle
// («overwrite products with matching handles», and without the flag the matching product is
// IGNORED, never duplicated), WooCommerce matches by ID/SKU, Business Central's configuration
// packages overwrite existing values on apply. None of them can produce two contradictory
// Mondays, and Square's hours are one setting per weekday. Full table with URLs in the PR body.
// ─────────────────────────────────────────────────────────────────────────────

/// The owner saves the whole Hours screen with one shift — a second, distinguishable template.
async fn owner_sets_whole_week(rt: &Runtime, hub_id: &str, open: &str, close: &str) {
    let sql = format!(
        "UPDATE weekplan_hours \
         SET open_time = '{open}', close_time = '{close}', is_closed = 0, \
             created_by = 'u-owner', updated_by = 'u-owner', \
             updated_at = '2026-08-15T11:00:00Z' \
         WHERE hub_id = '{hub_id}' AND is_deleted = 0"
    );
    rt.db()
        .execute(&sql, &Params::new())
        .await
        .expect("owner saves the whole week");
}

/// The owner saves **one** weekday and leaves the rest of the week as it came — the normal state,
/// because `schedules.business_hours.set` replaces the intervals of a SINGLE day and nobody ever
/// opens Sunday to confirm it is closed.
async fn owner_sets_one_day(rt: &Runtime, hub_id: &str, day: i64, open: &str, close: &str) {
    let sql = format!(
        "UPDATE weekplan_hours \
         SET open_time = '{open}', close_time = '{close}', is_closed = 0, \
             created_by = 'u-owner', updated_by = 'u-owner', \
             updated_at = '2026-08-15T10:00:00Z' \
         WHERE hub_id = '{hub_id}' AND day_of_week = {day} AND is_deleted = 0"
    );
    rt.db()
        .execute(&sql, &Params::new())
        .await
        .expect("owner saves one day");
}

/// Exactly what `schedules.business_hours.set` does to a weekday AFTER an import: soft-delete the
/// intervals that day had (`_clear_business_hours_day`) and insert the new one
/// (`_insert_business_hours`), signed by whoever saved the screen — a row the import batch knows
/// nothing about.
async fn owner_rewrites_day(rt: &Runtime, hub_id: &str, day: i64, open: &str, close: &str) {
    let clear = format!(
        "UPDATE weekplan_hours \
         SET is_deleted = 1, deleted_at = '2026-08-16T09:00:00Z', \
             updated_at = '2026-08-16T09:00:00Z' \
         WHERE hub_id = '{hub_id}' AND day_of_week = {day} AND is_deleted = 0"
    );
    rt.db()
        .execute(&clear, &Params::new())
        .await
        .expect("clear the weekday");
    let insert = format!(
        "INSERT INTO weekplan_hours \
           (id, hub_id, day_of_week, position, open_time, close_time, is_closed, \
            is_deleted, created_by, created_at, updated_by, updated_at) \
         VALUES ('{hub_id}-own-d{day}', '{hub_id}', {day}, 0, '{open}', '{close}', 0, 0, \
                 'u-owner', '2026-08-16T09:00:00Z', 'u-owner', '2026-08-16T09:00:00Z')"
    );
    rt.db()
        .execute(&insert, &Params::new())
        .await
        .expect("insert the weekday");
}

/// 🔴 hub#1548: the business tries the template of its sector, does not like it and tries another.
/// After the SECOND one its week must be **one** week — the last one — not both at once.
///
/// This is the crossing hub#1535 does not cover: there the two weeks were the module's placeholder
/// and a template; here BOTH came from templates, so the `created_by = 'system'` marker the
/// retirement looked for is long gone and every day ends up twice.
#[tokio::test]
async fn un_segundo_blueprint_deja_una_sola_semana() {
    let wp = modulo_con_marcador_de_tabla_entera();

    let a = hub_con("h1", &[&wp]).await;
    owner_sets_hours(&a, "h1").await; // 09:30–20:00, Saturday open
    let plantilla_a = export_hub(
        &a,
        "h1",
        &seleccion(&["weekplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla A");

    let b = hub_con("h3", &[&wp]).await;
    owner_sets_whole_week(&b, "h3", "07:00", "15:00").await;
    let plantilla_b = export_hub(
        &b,
        "h3",
        &seleccion(&["weekplan"]),
        "panaderia",
        "es",
        "2026-08-15T11:00:00Z",
    )
    .await
    .expect("export plantilla B");

    let mut destino = hub_con("h2", &[&wp]).await;
    aplica(&mut destino, &plantilla_a, "h2", &["weekplan"]).await;
    let tras_a = semana(&destino, "h2").await;
    assert_eq!(
        tras_a.len(),
        7,
        "precondición (hub#1535): tras la PRIMERA plantilla queda una sola semana — {tras_a:?}"
    );

    aplica(&mut destino, &plantilla_b, "h2", &["weekplan"]).await;

    let tras = semana(&destino, "h2").await;
    assert_eq!(
        tras.len(),
        7,
        "el lunes sale de 09:30 a 20:00 y de 07:00 a 15:00 a la vez: {} filas vivas donde debe \
         haber 7 — {tras:?}",
        tras.len()
    );
    assert!(
        tras.iter()
            .all(|r| (r.1.as_str(), r.2.as_str()) == ("07:00", "15:00")),
        "la semana que queda tiene que ser la de la ÚLTIMA plantilla, no una mezcla — {tras:?}"
    );
}

/// 🔴 The close that makes replacing SAFE, and the reason it is not a silent deletion of business
/// data: undoing the second template gives the first one back, whole.
#[tokio::test]
async fn deshacer_el_segundo_blueprint_devuelve_la_semana_del_primero() {
    let wp = modulo_con_marcador_de_tabla_entera();

    let a = hub_con("h1", &[&wp]).await;
    owner_sets_hours(&a, "h1").await;
    let plantilla_a = export_hub(
        &a,
        "h1",
        &seleccion(&["weekplan"]),
        "peluqueria",
        "es",
        "2026-08-15T10:00:00Z",
    )
    .await
    .expect("export plantilla A");

    let b = hub_con("h3", &[&wp]).await;
    owner_sets_whole_week(&b, "h3", "07:00", "15:00").await;
    let plantilla_b = export_hub(
        &b,
        "h3",
        &seleccion(&["weekplan"]),
        "panaderia",
        "es",
        "2026-08-15T11:00:00Z",
    )
    .await
    .expect("export plantilla B");

    let mut destino = hub_con("h2", &[&wp]).await;
    aplica(&mut destino, &plantilla_a, "h2", &["weekplan"]).await;
    let con_la_a = semana(&destino, "h2").await;

    let report = import_sections(
        &mut destino,
        &plantilla_b.manifest,
        &plantilla_b.files,
        &import_selection(&["weekplan"]),
        "h2",
    )
    .await
    .expect("best-effort");
    let batch = report.batch_id.clone().expect("lote del segundo import");

    undo_import(&destino, "h2", &batch)
        .await
        .expect("deshacer el segundo blueprint");

    assert_eq!(
        semana(&destino, "h2").await,
        con_la_a,
        "sustituir la semana solo vale si es REVERSIBLE: deshacer la segunda plantilla tiene que \
         devolver la primera entera"
    );
}

/// 🔴 hub#1550: the origin configured only Monday and left the rest of the week as the module
/// planted it. The template has to carry the week the business actually HAS — the days it adopted
/// without touching them included — not just the one row it typed.
///
/// Today `export::is_module_seeded` drops the six `system` rows and the destination ends up with a
/// single day and six days «not configured», which is the state ERPlora/schedules#36 exists to make
/// unreachable. Adopting a table half way is still adopting it.
#[tokio::test]
async fn una_semana_configurada_a_medias_viaja_entera() {
    let wp = modulo_con_marcador_de_tabla_entera();
    let origen = hub_con("h1", &[&wp]).await;
    owner_sets_one_day(&origen, "h1", 0, "09:30", "20:00").await;

    let efectiva = semana(&origen, "h1").await;
    assert_eq!(
        efectiva.len(),
        7,
        "precondición: el hub de origen tiene la semana entera — {efectiva:?}"
    );
    assert_eq!(
        efectiva.iter().filter(|r| r.4 == "system").count(),
        6,
        "precondición: el negocio solo firmó el lunes; los otros seis días son los del módulo — \
         {efectiva:?}"
    );

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

    let tras = semana(&destino, "h2").await;
    assert_eq!(
        tras, efectiva,
        "el hub importado tiene que quedar con la MISMA semana efectiva que el de origen, no solo \
         con el día que el negocio escribió — {tras:?}"
    );
}

/// 🔴 A pristine placeholder still does NOT travel: if the business never touched the week, the
/// table is the module's own data and the destination plants its own at install. Otherwise every
/// template would carry a generic week nobody chose, and hub#1535 would come back through the door
/// hub#1550 opens.
#[tokio::test]
async fn una_semana_que_el_negocio_no_ha_tocado_no_viaja() {
    let wp = modulo_con_marcador_de_tabla_entera();
    let origen = hub_con("h1", &[&wp]).await;

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
        !sql.contains("weekplan_hours"),
        "un marcador que nadie adoptó es dato DEL MÓDULO y no viaja (ADR-0359):\n{sql}"
    );
}

/// 🔴 hub#1551: the business imports a template, edits one weekday on the Hours screen and then
/// undoes the import. Undo must not resurrect the placeholder on top of what the business just
/// wrote — that is the same contradictory Monday hub#1535 closed, coming in through the undo.
///
/// The rule is the mirror of the retirement's: the placeholder is retired only when the real data
/// is IN, so it comes back only while the hole it left is still there.
#[tokio::test]
async fn deshacer_tras_editar_el_horario_no_duplica_el_dia_editado() {
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
    let report = import_sections(
        &mut destino,
        &bundle.manifest,
        &bundle.files,
        &import_selection(&["weekplan"]),
        "h2",
    )
    .await
    .expect("best-effort");
    let batch = report.batch_id.clone().expect("lote del import");

    // The business adjusts Monday on the Hours screen — the imported week is now ITS week.
    owner_rewrites_day(&destino, "h2", 0, "10:00", "19:00").await;

    undo_import(&destino, "h2", &batch)
        .await
        .expect("deshacer la importación");

    let tras = semana(&destino, "h2").await;
    let lunes: Vec<_> = tras.iter().filter(|r| r.0 == 0).collect();
    assert_eq!(
        lunes.len(),
        1,
        "el lunes queda con DOS horarios contradictorios tras deshacer — {lunes:?}"
    );
    assert_eq!(
        (lunes[0].1.as_str(), lunes[0].2.as_str(), lunes[0].4.as_str()),
        ("10:00", "19:00", "u-owner"),
        "y el que se queda es el que el negocio acaba de escribir, no el genérico — {lunes:?}"
    );
    assert!(
        tras.iter().all(|r| r.4 != "system"),
        "deshacer no puede replantar el marcador sobre una semana que el negocio ya hizo suya — \
         {tras:?}"
    );
}
