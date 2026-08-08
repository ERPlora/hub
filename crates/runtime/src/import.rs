//! Import de un blueprint en el hub (ADR-0113): restaura las secciones SELECCIONADAS de un
//! bundle (manifest + `data/*.sql`) inyectando el `hub_id` DESTINO (patrón ADR-0072), estilo
//! «migrate» de Django. La instalación de los módulos del manifest es del SERVER (flujo
//! `install_from_cloud`, ANTES de llamar aquí); este motor solo aplica datos.
//!
//! BEST-EFFORT (decisión Ioan): una sección que falla se registra en el informe y NO rompe
//! el resto. La INTEGRIDAD sí es dura: sha256 que no casa o `schema_version` desconocida →
//! rechazo entero SIN efectos (patrón ADR-0015: verificar antes de tocar nada).
//!
//! PROPUESTA de superficie (firma = contrato de los e2e `tests/import_test.rs`).
//! La implementación es columna del humano (plan Fase 2); este stub solo fija el contrato.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};

use crate::export::BlueprintManifest;
use crate::Runtime;

/// Selección del formulario de import (checkboxes sobre lo que el bundle trae).
#[derive(Debug, Clone, Default)]
pub struct ImportSelection {
    /// Aplicar `data/hub_users.sql` (empleados + roles + permisos).
    pub users: bool,
    /// Aplicar `data/hub_settings.sql`.
    pub settings: bool,
    /// Restaurar `data/fiscal/` (config VeriFactu + certificado). El certificado lo aplica
    /// el server por su endpoint existente; aquí solo se contabiliza en el informe.
    pub fiscal: bool,
    /// Copiar `media/` (lo hace el server con el gestor media; aquí solo informe).
    pub media: bool,
    /// Módulos cuyos `data/<id>.sql` se aplican (deben estar instalados en destino).
    pub modules: Vec<String>,
}

/// Estado final de una sección tras el import (informe best-effort).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum SectionStatus {
    /// Aplicada correctamente.
    Applied,
    /// No seleccionada (o ausente del bundle): no se tocó.
    Skipped,
    /// Se DESCARTÓ a propósito, aunque venga en el bundle y esté marcada — con el motivo legible
    /// (ADR-0195, hub#305). Distinta de [`Skipped`](Self::Skipped), que es «no la pediste», y de
    /// [`Failed`](Self::Failed), que es «se intentó y salió mal»: aquí el motor **decide** no
    /// aplicarla y tiene que decir por qué. Sin este estado, ignorar en silencio sería
    /// indistinguible de no haberla marcado.
    Ignored(String),
    /// Applied — but not whole: the engine dropped part of its rows on purpose, and says why with
    /// the same stable code an [`Ignored`](Self::Ignored) carries (hub#405).
    ///
    /// It exists because ONE section can legitimately mix what may travel with what may not:
    /// `hub_settings` holds the configuration a template is for AND the fiscal identity of a
    /// single business. Reporting that as `Applied` would tell the user everything landed, and as
    /// `Ignored` would hide that the configuration did land — both are lies about the same row of
    /// the report. The count of what was dropped is in [`SectionResult::discarded_rows`].
    PartiallyApplied(String),
    /// Falló; el motivo es legible para el informe de la UI. El resto del import continuó.
    Failed(String),
}

/// Resultado por sección (`hub_users`, `hub_settings`, `fiscal`, `media`, `modules/<id>`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionResult {
    pub section: String,
    pub status: SectionStatus,
    /// Rows the engine refused to apply, when [`SectionStatus::Ignored`] discarded the section
    /// (0 otherwise). A discard that does not say HOW MUCH it dropped is barely less mute than
    /// no discard at all: «4 accounts kept out» is what tells the user something happened
    /// (hub#331). `#[serde(default)]` ⇒ an older report deserialises as 0.
    #[serde(default)]
    pub discarded_rows: u32,
}

/// Informe final del import: una entrada por sección del bundle (la UI lo pinta tal cual).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
pub struct ImportReport {
    pub sections: Vec<SectionResult>,
}

/// Aplica en el hub las secciones seleccionadas del bundle, bajo el tenant `target_hub_id`
/// (explícito: el import restaura en el hub DESTINO, que no tiene por qué ser el del runtime
/// de pruebas; en producción el server pasa el `hub_id` del despliegue).
///
/// Contrato (fijado por los e2e): verifica `schema_version` y los sha256 del manifest ANTES
/// de aplicar nada (fallo → `Err` sin efectos); después aplica sección a sección con el
/// `hub_id` destino inyectado (via [`crate::export::HUB_ID_PLACEHOLDER`]), best-effort, y
/// devuelve el informe. Una sección de un módulo no instalado falla nombrándolo.
pub async fn import_sections(
    rt: &mut Runtime,
    manifest: &BlueprintManifest,
    files: &BTreeMap<String, Vec<u8>>,
    selection: &ImportSelection,
    target_hub_id: &str,
) -> crate::Result<ImportReport> {
    // ── Integridad DURA, antes de tocar nada (ADR-0015) ─────────────────────
    if manifest.schema_version != crate::export::SCHEMA_VERSION {
        return Err(crate::RuntimeError::Other(format!(
            "import: schema_version {} desconocida (este runtime entiende v{})",
            manifest.schema_version,
            crate::export::SCHEMA_VERSION
        )));
    }
    for (path, bytes) in files {
        match manifest.sha256.get(path) {
            Some(expected) if *expected == crate::export::sha256_hex(bytes) => {}
            Some(_) => {
                return Err(crate::RuntimeError::Other(format!(
                    "import: sha256 de {path} no casa con el manifest — bundle manipulado, rechazado sin efectos"
                )))
            }
            None => {
                return Err(crate::RuntimeError::Other(format!(
                    "import: {path} no aparece en manifest.sha256 — bundle inconsistente, rechazado"
                )))
            }
        }
    }
    for path in manifest.sha256.keys() {
        if !files.contains_key(path) {
            return Err(crate::RuntimeError::Other(format!(
                "import: el manifest declara {path} pero el bundle no lo trae — rechazado"
            )));
        }
    }

    // ── Aplicación sección a sección, BEST-EFFORT (decisión Ioan) ───────────
    // Cada sección valida su SQL contra el subconjunto permitido ANTES de ejecutar nada de ella
    // (`import_sql`, hub#239): DDL o un INSERT en tablas de otra sección dejan la sección entera
    // en `Failed` sin tocar la BD. NO se aborta el import: el best-effort es la decisión de
    // producto (una sección rota no rompe el resto) y la garantía de seguridad —que ese SQL no se
    // ejecute— se cumple igual.
    // Un lote por importación, con el nombre del blueprint: es la unidad que el usuario
    // reconoce y deshace («quitar la demo del restaurante»). Si el registro del lote falla, el
    // import NO se aborta — se pierde la trazabilidad, no los datos.
    let batch_id = crate::reset::begin_batch(rt, target_hub_id, &manifest.name).await.ok();

    let mut report = ImportReport::default();
    // Whose hub is this? Asked ONCE: it is what tells a same-hub restore (which may write back the
    // identity it exported — ADR-0113 §1) from any other bundle (which may not), for both the
    // accounts of hub#331 and the settings of hub#405.
    let same_hub = is_same_hub(manifest, target_hub_id);
    for section in &manifest.sections {
        // The role set of the vertical is NOT a section of data (hub#354): it travels as keys in
        // `manifest.active_roles` and is applied once, after this loop, through the role catalogue's
        // own write door. Skipped here so it does not also report a hollow `Skipped` row.
        if section == crate::export::ROLES_SECTION {
            continue;
        }
        let (status, discarded_rows) = match system_table_not_portable(section)
            .or_else(|| ignored_by_purpose(manifest, section))
            .or_else(|| identity_not_portable(manifest, section, target_hub_id))
            .or_else(|| chain_not_portable(manifest, section, target_hub_id))
        {
            // A discard reports HOW MANY rows it dropped: «4 accounts kept out» is what turns a
            // status the user skims past into something they can act on (hub#331).
            Some(motivo) => (SectionStatus::Ignored(motivo), rows_in_section(section, files)),
            None => {
                apply_section(rt, section, files, selection, target_hub_id, same_hub, batch_id.as_deref())
                    .await
            }
        };
        report.sections.push(SectionResult { section: section.clone(), status, discarded_rows });
    }

    // ── The role set of the vertical (paso 2b, hub#354) ─────────────────────
    // AFTER the sections on purpose: the modules that DECLARE these roles are installed by the
    // server before the engine runs, and a key nobody declares is refused — so the later this is
    // asked, the more of the vertical is already standing. Driven by `active_roles` (the data) and
    // not by the presence of the `roles` section (the label): a hand-made bundle that forgets to
    // list the section gets the same guards, and a bundle that lists it with no keys reports nothing.
    if !manifest.active_roles.is_empty() {
        let (status, discarded_rows) = apply_role_activation(rt, manifest, target_hub_id).await;
        report.sections.push(SectionResult {
            section: crate::export::ROLES_SECTION.to_string(),
            status,
            discarded_rows,
        });
    }
    Ok(report)
}

/// Switches on the roles the blueprint asked for and turns the outcome into a row of the report.
///
/// The policy lives in [`crate::roles::pre_activate`] — this only decides how to SAY it, and the
/// three states are the ones the report already has: everything landed (`Applied`), part of it did
/// (`PartiallyApplied`, the same shape `hub_settings` uses when it keeps the configuration and drops
/// the identity) or none of it did (`Ignored`). The count is of ROLES left out, which is what
/// `discarded_rows` means for a section whose rows are keys.
///
/// A database failure is `Failed`, never a discard: the import stays best-effort, and «I could not
/// write» must not be reported as «this hub said no».
async fn apply_role_activation(
    rt: &Runtime,
    manifest: &BlueprintManifest,
    target_hub_id: &str,
) -> (SectionStatus, u32) {
    let outcome = crate::roles::pre_activate(
        rt.db(),
        rt.registry(),
        target_hub_id,
        &manifest.active_roles,
    )
    .await;
    match outcome {
        Ok(outcome) => {
            let discarded = outcome.refused.len() as u32;
            let status = if outcome.refused.is_empty() {
                SectionStatus::Applied
            } else if outcome.activated.is_empty() {
                SectionStatus::Ignored(ignore_reason::ROLES_NOT_ACTIVATABLE.into())
            } else {
                SectionStatus::PartiallyApplied(ignore_reason::ROLES_NOT_ACTIVATABLE.into())
            };
            (status, discarded)
        }
        Err(e) => (SectionStatus::Failed(e.to_string()), 0),
    }
}

/// Stable reason codes carried by [`SectionStatus::Ignored`] — a CONTRACT with the shell, which
/// turns each one into a translated sentence (same lesson as the domain-error channel, hub#139:
/// a code that never changes, plus a message that can live in i18n, instead of prose that the UI
/// can only print raw in whatever language the runtime happened to be written in).
///
/// Reasons produced before this module travel as prose; the shell prints an unknown reason as it
/// comes, so both forms keep working while they migrate.
pub mod ignore_reason {
    /// A bundle produced by ANOTHER hub carried `hub_user` rows (ADR-0195 §3 — hub#331).
    pub const IDENTITY_NOT_PORTABLE: &str = "identity_not_portable";
    /// A bundle produced by ANOTHER hub carried `hub_settings` rows that are not configuration:
    /// the fiscal identity of its business, its contacts or a security switch (ADR-0195 §4 —
    /// hub#405). Only the configuration keys of that section were applied.
    pub const SETTINGS_NOT_PORTABLE: &str = "settings_not_portable";
    /// The bundle asked to pre-activate role keys this hub cannot switch on (paso 2b, hub#354):
    /// keys **no installed module declares** — the blueprint of another vertical, or a module that
    /// failed to install — and the **base/administrative** keys, which a package may never touch.
    /// One code for both, because the answer to the user is the same one: those roles are not part
    /// of this hub's catalogue, so nothing was switched on for them.
    pub const ROLES_NOT_ACTIVATABLE: &str = "roles_not_activatable";
    /// The bundle brought a section over one of the hub's OWN system tables — its fiscal profile,
    /// its certificate store, its import batches (ADR-0273 D8 — hub#560). Those are the identity of
    /// THIS installation, not vocabulary of anybody's business, so no bundle writes them: not a
    /// template, not another hub's backup, not this hub restoring itself.
    pub const SYSTEM_TABLE_NOT_PORTABLE: &str = "system_table_not_portable";
}

/// Is this bundle a restore of the destination hub's OWN state?
///
/// The origin travels in `manifest.hub.hub_id` (hub#312). An EMPTY origin is not a match, ever:
/// bundles older than that field read as unknown origin, and treating «unknown == unknown» as the
/// same hub would hand exactly the artefacts this defends against (the blueprints published before
/// the field existed) the one answer that lets their rows through.
fn is_same_hub(manifest: &BlueprintManifest, target_hub_id: &str) -> bool {
    !manifest.hub.hub_id.is_empty() && manifest.hub.hub_id == target_hub_id
}

/// **The hub's own system tables are not a section, whatever the manifest calls them** —
/// ADR-0273 D8 (hub#560).
///
/// This is the FIRST question asked of every section, before `purpose`, before whose hub this is:
/// those two decide what a bundle may carry ABOUT A BUSINESS, and `_hub_*` is not about a business
/// at all. `_hub_fiscal_profile` is the identity of THIS installation — the taxpayer id the emitted
/// chain is anchored to, its `system_id`, whether it has gone live — and `_hub_fiscal_regime_registry`
/// is what says the country owes a regime in the first place. A bundle able to write them could
/// declare a hub already active, or hand it another installation's `system_id`: adopting somebody
/// else's installation by the back door, which hub#558 makes a deliberate act with a trace.
///
/// Both shapes are caught, because a hand-made zip has both available: a section named after the
/// table (`_hub_fiscal_profile`), and one disguised as a MODULE whose id opens the same namespace
/// (`modules/_hub`). The second is the one that matters — a module section reaches its tables by
/// the very same prefix rule, so `_hub` would reach EVERY `_hub_*` table — and it is why the
/// question asked here is about the leading `_` and not only about `_hub_`: the underscore is the
/// runtime's namespace, and no section of a bundle is named inside it.
///
/// It IGNORES, it does not fail: the import is best-effort by design (a section that oversteps must
/// not take the rest of the blueprint with it), and the report says so with a stable reason code
/// instead of the hollow `Skipped` an unknown section used to get — silence being indistinguishable
/// from «you did not tick it» is exactly what [`SectionStatus::Ignored`] exists to avoid.
fn system_table_not_portable(section: &str) -> Option<String> {
    let name = section.strip_prefix("modules/").unwrap_or(section);
    name.starts_with(crate::export::RESERVED_NAMESPACE_PREFIX)
        .then(|| ignore_reason::SYSTEM_TABLE_NOT_PORTABLE.to_string())
}

/// Identities NEVER land in a hub that is not their own (ADR-0195 §3, consumer plane — hub#331).
///
/// This is the third defense, and the only one that holds for a bundle that never went through the
/// SaaS. The other two read what the bundle SAYS: the producer gate excludes identities when the
/// export is asked for a `template`, and the publisher gate rejects the upload of a bundle carrying
/// forbidden sections. Neither is on the path of «Subir desde archivo», and neither catches the
/// artefacts already out there: the four blueprints published today were built before `purpose`
/// existed, so they read as `backup` — and their `Demo`/**admin** account, whose PIN `0000` is
/// recoverable in 0.00 s from the salt shipped inside the zip itself, was applied to every hub that
/// imported one. A bundle is a file the user supplies; what it claims about itself is not a control.
///
/// So the rule does not ask the bundle what it is for — it asks whose hub this is. Users, roles and
/// PINs are the identity of ONE installation; the only import that may write them is that same
/// installation restoring itself (a redeploy over its own backup), which is what keeps the other
/// half of the engine alive: ADR-0195 explicitly rejected banning `hub_users` outright because a
/// restore without them loses every role and PIN, and `get_or_link_cloud_user` would bring an
/// `employee` back as admin (ADR-0113 §1).
///
/// Sections are matched on the manifest, not on the selection: a checkbox is not a control either.
fn identity_not_portable(
    manifest: &BlueprintManifest,
    section: &str,
    target_hub_id: &str,
) -> Option<String> {
    if section != "hub_users" || is_same_hub(manifest, target_hub_id) {
        return None;
    }
    Some(ignore_reason::IDENTITY_NOT_PORTABLE.into())
}

/// How many rows a section brought — i.e. how many were dropped when it is discarded.
///
/// One statement per row is exactly what `export::rows_to_sql` emits, and the count comes from the
/// SAME splitter the import validates with (`import_sql`), so it can never disagree with what would
/// have been applied. A file that does not parse counts as 0: this is a number for the report, and
/// it must not turn into a second way for a broken bundle to fail.
fn rows_in_section(section: &str, files: &BTreeMap<String, Vec<u8>>) -> u32 {
    let Some(path) = data_file_for_section(section) else { return 0 };
    let Some(bytes) = files.get(&path) else { return 0 };
    let Ok(sql) = std::str::from_utf8(bytes) else { return 0 };
    crate::import_sql::split_statements(sql).map(|s| s.len() as u32).unwrap_or(0)
}

/// The `data/*.sql` a section is applied from, or `None` for the sections with no SQL of their own
/// (`fiscal`/`media`, materialised by the server, and anything the manifest invents).
fn data_file_for_section(section: &str) -> Option<String> {
    match section {
        "hub_users" => Some("data/hub_users.sql".into()),
        "hub_settings" => Some("data/hub_settings.sql".into()),
        // fiscal/media las materializa el SERVER (certificado por su endpoint, imágenes por el
        // gestor media); a nivel runtime se registran como Skipped y el server sobrescribe.
        "fiscal" | "media" => None,
        s => s.strip_prefix("modules/").map(|id| format!("data/{id}.sql")),
    }
}

/// Secciones de IDENTIDAD que un bundle público no puede transportar: los usuarios del hub (con su
/// rol y su `pin_hash`) y la identidad fiscal del negocio (NIF, config VeriFactu, certificado).
/// Misma lista que aplica `export_hub` al producir — las dos puntas de la misma regla.
const SECCIONES_DE_IDENTIDAD: [&str; 2] = ["hub_users", "fiscal"];

/// ¿El PROPÓSITO del bundle prohíbe esta sección? (ADR-0195, plano consumidor — hub#305).
///
/// Tercer plano de la misma regla, y hace falta aunque existan los otros dos: el gate del productor
/// (`export_hub`) y el del publicador (la prevalidación del SaaS) cubren lo que se sube al catálogo,
/// pero el import acepta **ficheros locales** («Subir desde archivo») que no pasan por ninguno de
/// los dos. Un `.blueprint.zip` publicado ANTES del gate —como el `restaurante` v1.0.2, con
/// `Demo`/admin y PIN `0000` en `sha256("{sal}:{pin}")` con la sal dentro del propio zip— entra por
/// ahí sin filtro, y quien lo descargue tiene PIN de administrador en todo hub que lo importe.
///
/// Se mira el **manifest**, no la selección: una casilla no es un control. Y solo con
/// `purpose: template`; un bundle sin propósito es un `backup` y **debe** traer sus usuarios, o
/// restaurar una copia pierde roles y PINs (ADR-0113 §1).
///
/// Devuelve el motivo legible para el informe: el usuario tiene que poder distinguir «no lo apliqué
/// porque es una plantilla» de «no lo marcaste».
fn ignored_by_purpose(manifest: &BlueprintManifest, section: &str) -> Option<String> {
    if manifest.purpose.allows_identity_sections() || !SECCIONES_DE_IDENTIDAD.contains(&section) {
        return None;
    }
    Some(format!(
        "una plantilla no aplica identidades: la sección `{section}` del bundle se ha descartado \
         (usuarios, roles, PIN y datos fiscales son de cada negocio)"
    ))
}

/// The fiscal chain never travels across installations (ADR-0202 §4.2 — hub#312).
///
/// `NumeroInstalacion` = `hub_id`: the `verifactu` data section (chain records, contingency
/// queue, events, AEAT log) is the fiscal history of ONE installation. Applied under another
/// hub, its next record would chain on a `RegistroAnterior` the AEAT never received for that
/// installation — and another hub's pending queue would get transmitted under the wrong
/// `NumeroInstalacion`. A bundle proves its origin only through `manifest.hub.hub_id`
/// (bundles older than that field read as unknown origin and import conservatively); the
/// SAME hub restoring its own backup resumes its own chain (AEAT developer FAQ §4).
fn chain_not_portable(
    manifest: &BlueprintManifest,
    section: &str,
    target_hub_id: &str,
) -> Option<String> {
    if section != "modules/verifactu" || is_same_hub(manifest, target_hub_id) {
        return None;
    }
    Some(
        "la cadena VeriFactu pertenece a la instalación de origen (NumeroInstalacion = hub_id): \
         los registros fiscales de otro hub no se aplican aquí — este hub abre su propia cadena \
         con PrimerRegistro=S"
            .into(),
    )
}

/// Aplica una sección; cualquier fallo queda contenido en su `SectionStatus::Failed`. Devuelve
/// además cuántas filas se quedaron fuera a propósito (0 salvo descarte parcial — hub#405).
async fn apply_section(
    rt: &Runtime,
    section: &str,
    files: &BTreeMap<String, Vec<u8>>,
    selection: &ImportSelection,
    target_hub_id: &str,
    same_hub: bool,
    batch_id: Option<&str>,
) -> (SectionStatus, u32) {
    // ¿Está marcada en el formulario de import?
    let selected = match section {
        "hub_users" => selection.users,
        "hub_settings" => selection.settings,
        s => match s.strip_prefix("modules/") {
            Some(id) => selection.modules.iter().any(|m| m == id),
            None => false, // fiscal/media (las materializa el server) y secciones desconocidas
        },
    };
    let path = data_file_for_section(section);
    if !selected {
        return (SectionStatus::Skipped, 0);
    }

    // Un módulo del manifest debe estar instalado en destino (lo instala el server ANTES).
    if let Some(id) = section.strip_prefix("modules/") {
        if !rt.registry().is_installed(id) {
            return (SectionStatus::Failed(format!("módulo `{id}` no instalado en el hub destino")), 0);
        }
    }

    let Some(path) = path else { return (SectionStatus::Skipped, 0) };
    let Some(bytes) = files.get(&path) else {
        return (SectionStatus::Failed(format!("fichero {path} ausente del bundle")), 0);
    };
    let sql = match std::str::from_utf8(bytes) {
        Ok(s) => s.replace(crate::export::HUB_ID_PLACEHOLDER, target_hub_id),
        Err(_) => return (SectionStatus::Failed(format!("{path} no es UTF-8 válido")), 0),
    };
    if sql.trim().is_empty() {
        return (SectionStatus::Applied, 0); // sección presente pero sin filas: nada que hacer
    }
    // Subconjunto SQL del import (hub#239): la sección se valida ENTERA antes de ejecutar su
    // primera fila (solo `INSERT INTO` en sus propias tablas). Validar y ejecutar viven en la
    // misma función para que lo validado sea EXACTAMENTE lo ejecutado (mismo troceo).
    let Some(scope) = crate::import_sql::scope_for_data_file(&path) else {
        return (SectionStatus::Failed(format!("{path} no corresponde a ninguna sección conocida")), 0);
    };
    // ADR-0195 §4 (hub#405): the settings of a bundle that is NOT this hub's own are filtered to
    // the configuration keys. `hub_settings` is the one section that legitimately mixes what may
    // travel (country, currency, language) with what may not (the tax id and legal name of ONE
    // business), so it is filtered row by row instead of discarded whole — discarding it would
    // strip a sector template of the only thing it is for.
    //
    // Same question as hub#331, not a new one: not «what does this bundle claim to be» but «whose
    // hub is this». A hub restoring its own backup writes its own identity back (ADR-0113 §1);
    // everyone else's stays out, whatever the manifest says about itself.
    // hub#376: en un hub de DEMO el filtro se aplica SIEMPRE, venga el bundle de donde venga. El
    // `same_hub` de arriba se lee del `manifest.json` que va DENTRO del zip, y en una demo el
    // visitante conoce su propio `hub_id` (está en el subdominio y en `/api/hub/context`): un
    // bundle hecho a mano que se declare «de este mismo hub» pasaría el filtro y escribiría un NIF
    // ajeno, dejando en nada el cierre de `settings::set_many`. Una demo no tiene identidad fiscal
    // propia por ninguna puerta (ADR-0197 §4).
    let demo_hub = rt.registry().demo_hub;
    let (sql, discarded) = if section == "hub_settings" && (!same_hub || demo_hub) {
        match keep_portable_settings(&sql, &scope) {
            Ok(filtered) => filtered,
            // Invalid section: it fails WHOLE and without touching the BD, exactly as it did
            // before this filter existed (hub#239). The filter narrows a valid section; it is not
            // a way to salvage a broken one.
            Err(e) => return (SectionStatus::Failed(e), 0),
        }
    } else {
        (sql, 0)
    };
    if sql.trim().is_empty() {
        // Nothing survived the filter: the section was identity and nothing else. Reporting that
        // as `Applied` over zero rows would read as «I did what you asked».
        return (SectionStatus::Ignored(ignore_reason::SETTINGS_NOT_PORTABLE.into()), discarded);
    }
    // REGENERAR los `id` del bundle por el hub DESTINO y acotar la guarda por (hub_id, id)
    // (hub#260): en una BD COMPARTIDA por varios hubs de una misma org, los `id` del hub ORIGEN
    // ya existen (bajo un hub hermano) y el INSERT chocaba contra la PK global, o el guard por
    // `id` solo evaluaba a falso y la sección insertaba 0 filas reportando `Applied` (fallo
    // silencioso). La PK de casi toda tabla de módulo es `id TEXT PRIMARY KEY` GLOBAL (no
    // `(hub_id, id)`), así que reutilizar el id de origen es inviable: se genera un uuid NUEVO
    // por fila y se remapean las FK internas del bundle (cualquier columna `id`/`*_id`/`parent_id`
    // cuyo literal apunte a un id reescrito). La guarda pasa a `hub_id = <dest> AND id = <nuevo>`,
    // que sigue siendo idempotente para una re-importación sobre el MISMO hub y deja de colisionar
    // con un hub hermano.
    let sql = remap_section_ids(&sql, target_hub_id);
    // Con lote abierto, el import REGISTRA qué filas inserta (ADR-0170): así esta importación
    // se puede deshacer después sin tocar lo que el usuario cree más tarde. Sin lote (llamadas
    // heredadas), se aplica igual que siempre. Ambas rutas pasan por la MISMA validación.
    let applied = match batch_id {
        Some(batch) => crate::reset::apply_tracked_into(rt, batch, target_hub_id, &sql, &scope)
            .await
            .map(|n| n as usize),
        None => crate::import_sql::apply(rt.db(), &sql, &scope).await,
    };
    match applied {
        // Applied — but say so honestly when part of it was left out on purpose (hub#405).
        Ok(_) if discarded > 0 => (
            SectionStatus::PartiallyApplied(ignore_reason::SETTINGS_NOT_PORTABLE.into()),
            discarded,
        ),
        Ok(_) => (SectionStatus::Applied, 0),
        // A section that failed applied nothing, so nothing was «discarded»: the filter's count
        // would be a number about rows that were never going to land anyway.
        Err(e) => (SectionStatus::Failed(e.to_string()), 0),
    }
}

/// Keeps only the statements of a `hub_settings` section that write a PORTABLE configuration key,
/// returning the surviving SQL and how many rows were dropped (ADR-0195 §4 — hub#405).
///
/// This is the consumer half of the rule, and the only one that reaches a file nobody vetted: the
/// producer gate covers what THIS runtime exports as a template, and the SaaS gate covers what is
/// published, but «upload from file» goes through neither — and a bundle that is honestly someone
/// else's backup carries their tax id with every right to. What it must not do is write it here.
///
/// The section is VALIDATED FIRST and filtered second, and the order is the whole point: an invalid
/// section must keep failing WHOLE, without touching the BD (hub#239). Filtering first would have
/// quietly dropped the `DROP TABLE` — or the `SELECT pin_hash FROM hub_user` — and applied the rest,
/// turning a bundle the user must be told about into a partial import nobody reads. So `Err` here
/// means exactly what it meant before this filter existed: `Failed`, nothing applied.
///
/// After validation every statement is an `INSERT` of literals into `hub_settings`, so a key that
/// still cannot be read is an exotic-but-legal shape the export never emits (a multi-row `VALUES`,
/// a row with no `key` column). Those are DROPPED, not applied: fail-closed, because letting
/// through what the filter cannot read is how an allowlist stops being one.
fn keep_portable_settings(
    sql: &str,
    scope: &crate::import_sql::TableScope,
) -> std::result::Result<(String, u32), String> {
    let stmts = crate::import_sql::validate(sql, scope)?;
    let mut kept = String::with_capacity(sql.len());
    let mut dropped = 0u32;
    for stmt in &stmts {
        if writes_a_portable_setting(stmt) {
            kept.push_str(stmt.trim());
            kept.push('\n');
        } else {
            dropped += 1;
        }
    }
    Ok((kept, dropped))
}

/// Does this statement write a `hub_settings` row whose key is portable configuration?
/// `false` for anything that cannot be read as one — see the fail-closed note above.
fn writes_a_portable_setting(stmt: &str) -> bool {
    let Some(parsed) = parse_insert(stmt) else { return false };
    if parsed.table != "hub_settings" {
        return false;
    }
    let Some(i) = parsed.cols.iter().position(|c| c == "key") else { return false };
    let Some(key) = parsed.vals.get(i).and_then(|v| unquote_string_literal(v)) else {
        return false;
    };
    crate::export::is_portable_setting(&key)
}

/// Reescribe los `id` del SQL de una sección del bundle por ids NUEVOS derivados del hub DESTINO
/// (deterministas: uuid v5 sobre `(hub_id, id_origen)`), remapeando las FK internas del bundle y
/// reescribiendo la guarda de idempotencia para que vaya por `(hub_id, id)` (hub#260).
///
/// Trabaja sobre la forma EXACTA que emite `export::rows_to_sql`:
/// `INSERT INTO <t> ("col", …) SELECT <lit>, … WHERE NOT EXISTS (SELECT 1 FROM <t> WHERE <col> = <lit> [AND …])`.
/// Cualquier sentencia que no case se deja TAL CUAL (degradación segura: la guarda por `id` solo
/// del export sigue siendo idempotente para un re-import sobre el mismo hub; lo único que no se
/// arregla es el cross-hub en BD compartida para esa fila, pero no se rompe nada).
fn remap_section_ids(sql: &str, target_hub_id: &str) -> String {
    let Ok(stmts) = crate::import_sql::split_statements(sql) else {
        return sql.to_string(); // el import lo rechazará igual con el mismo troceo
    };
    if stmts.is_empty() {
        return sql.to_string();
    }

    // 1ª pasada: mapear cada id del bundle (literal de la columna `id`) a un id NUEVO. El nuevo id
    // es DETERMINÍSTICO en (hub DESTINO, id ORIGEN): mismo bundle importado en el mismo hub produce
    // el mismo id → re-import idempotente (la guarda `(hub_id, id)` casa y se salta). Hubs distintos
    // producen ids distintos → nunca colisionan contra la PK global en una BD compartida. Es la
    // versión «barata» del fix de fondo del issue: no reasigna ids al azar (rompería la idempotencia)
    // ni reutiliza los del origen (rompería la PK global). Se hace sobre TODAS las sentencias antes
    // de reescribir, así una fila HIJA que se emita ANTES que su padre sigue remapeando su FK.
    let mut id_map: std::collections::HashMap<String, String> = std::collections::HashMap::new();
    for stmt in &stmts {
        let Some(parsed) = parse_insert(stmt) else { continue };
        // Solo las filas ACOTADAS POR HUB entran al mapa: son las únicas cuyo `id` se remapea.
        // Meter aquí el id de una fila no hub-scoped (`hub_user`) haría que una FK que lo
        // referenciase se reescribiera hacia un id que nunca se insertó.
        if !parsed.cols.iter().any(|c| c == "hub_id") {
            continue;
        }
        if let Some(old) = parsed.id_literal() {
            let derived = derive_id(target_hub_id, &old);
            id_map.entry(old).or_insert(derived);
        }
    }

    // 2ª pasada: reescribir cada sentencia con los nuevos ids y la guarda acotada.
    let mut out = String::with_capacity(sql.len());
    for stmt in &stmts {
        out.push_str(&rewrite_insert(stmt, &id_map, target_hub_id));
    }
    out
}

/// Sentencia INSERT parseada a su tabla, columnas y literales (la forma que emite `rows_to_sql`).
/// `None` si no casa con esa forma (se deja intacta).
struct ParsedInsert<'a> {
    table: &'a str,
    cols: Vec<String>,
    vals: Vec<String>,
}

impl<'a> ParsedInsert<'a> {
    /// Valor LITERAL (con sus comillas) de la columna `id`, si la fila la tiene y es una cadena.
    fn id_literal(&self) -> Option<String> {
        let i = self.cols.iter().position(|c| c == "id")?;
        let v = self.vals.get(i)?;
        let s = unquote_string_literal(v)?;
        if s.is_empty() {
            None
        } else {
            Some(s)
        }
    }
}

/// Trocea `INSERT INTO <t> ( "c1", "c2", … ) SELECT <lit1>, <lit2>, …` (sin la guarda, que se
/// reescribe aparte). Acepta también la variante `VALUES (…)` por simetría, aunque el export no la
/// usa. Devuelve la posición de la sentencia justo después del `SELECT <literales>` o `VALUES (…)`.
fn parse_insert(stmt: &str) -> Option<ParsedInsert<'_>> {
    let trimmed = stmt.trim();
    let after_into = trimmed.strip_prefix("INSERT INTO ")?;
    // Tabla: hasta el primer blanco (identificador simple; el export no cualifica por esquema).
    let paren = after_into.find('(')?;
    let table = after_into[..paren].trim();
    if table.is_empty() || table.contains(|c: char| c.is_whitespace()) {
        return None;
    }
    // Lista de columnas entre `(` … `)`.
    let close = matching_paren(after_into, paren)?;
    let cols_inner = &after_into[paren + 1..close];
    let cols: Vec<String> = split_top_level_commas(cols_inner)
        .into_iter()
        .map(|c| unquote_ident(c.trim()))
        .collect();
    let rest = after_into[close + 1..].trim_start();
    // Solo nos interesa la parte de valores para construir el mapa y reescribir; la guarda se
    // descarta aquí y se regenera en `rewrite_insert`.
    let (val_rest, _guard) = split_off_guard(rest);
    let vals = parse_value_list(val_rest.trim())?;
    if vals.len() != cols.len() {
        return None;
    }
    Some(ParsedInsert { table, cols, vals })
}

/// Reescribe una sentencia INSERT: nuevos ids en `id`/`*_id`/`parent_id`, y guarda `(hub_id, id)`.
/// Si la sentencia no casa con la forma esperada se devuelve TAL CUAL.
fn rewrite_insert(stmt: &str, id_map: &std::collections::HashMap<String, String>, target_hub_id: &str) -> String {
    let trimmed = stmt.trim();
    let Some(after_into) = trimmed.strip_prefix("INSERT INTO ") else {
        return format!("{trimmed}\n");
    };
    let Some(paren) = after_into.find('(') else {
        return format!("{trimmed}\n");
    };
    let Some(close) = matching_paren(after_into, paren) else {
        return format!("{trimmed}\n");
    };
    let table = after_into[..paren].trim();
    let cols_inner = &after_into[paren + 1..close];
    let cols: Vec<String> = split_top_level_commas(cols_inner)
        .into_iter()
        .map(|c| unquote_ident(c.trim()))
        .collect();
    let rest = after_into[close + 1..].trim_start();
    let (val_rest, _guard) = split_off_guard(rest);
    let Some(vals) = parse_value_list(val_rest.trim()) else {
        return format!("{trimmed}\n");
    };
    if vals.len() != cols.len() {
        return format!("{trimmed}\n");
    }

    // ¿Esta tabla está acotada por hub? Lo dice la PROPIA fila: el export vuelca `SELECT *`, así
    // que su lista de columnas ES la de la tabla. Autodescriptivo, sin lista negra que mantener.
    //
    // El remap de ids y la guarda `(hub_id, id)` existen SOLO para no colisionar contra la PK
    // global entre hubs hermanos de una BD compartida (hub#260), y eso presupone filas hub-scoped.
    // Sin `hub_id` hay DOS casos, y no se tratan igual:
    //   · identidad del CORE (`hub_user`): tiene `id` propio; NO se remapea (derivarlo metería una
    //     copia de cada persona por cada hub de la org, sobre una tabla que todos comparten) y su
    //     guarda va por `id` a secas. Nombrar `hub_id` ahí tumbaba la sección Usuarios entera con
    //     `column "hub_id" does not exist` (producción, 2026-08-03).
    //   · tabla de VÍNCULO M2M (`inventory_product_categories`): no tiene `id` propio, solo FKs a
    //     filas que SÍ son hub-scoped y que acaban de remapearse. Sus FKs DEBEN remapearse o
    //     apuntan a ids inexistentes (`violates foreign key constraint`, visto importando el
    //     blueprint `restaurante` de verdad).
    // Lo común a ambos: la guarda no puede nombrar una columna que la tabla no tiene.
    let hub_scoped = cols.iter().any(|c| c == "hub_id");

    // Remapear: el `id` propio y cualquier FK interna (columnas `id`/`*_id`/`parent_id`) cuyo
    // literal esté en el mapa. La columna `id` solo se reescribe si la fila es hub-scoped.
    let mut new_vals = vals.clone();
    for (i, col) in cols.iter().enumerate() {
        let is_id_like = col == "id" || col.ends_with("_id");
        if !is_id_like {
            continue;
        }
        let Some(raw) = unquote_string_literal(&vals[i]) else { continue };
        let mapped = if col == "id" && !hub_scoped {
            // Identidad del core: conserva su id (idempotente para toda la organización).
            None
        } else if col == "id" {
            // El propio id: siempre el nuevo (del mapa si se captó en la 1ª pasada; si no, se
            // deriva ahora de forma determinista para no romper la idempotencia del re-import).
            id_map.get(&raw).cloned().or_else(|| {
                if raw.is_empty() { None } else { Some(derive_id(target_hub_id, &raw)) }
            })
        } else {
            // FK interna: solo si apunta a un id del bundle que hemos remapeado.
            id_map.get(&raw).cloned()
        };
        if let Some(new) = mapped {
            new_vals[i] = quote_string_literal(&new);
        }
    }

    // Guarda de idempotencia REGENERADA con los valores ya remapeados. Para tablas CON `id`:
    // `(hub_id, id)` — idempotente por el hub DESTINO (hub#260). Para tablas SIN `id`
    // (`hub_settings` por `key`, vínculos M2M por su tupla): se CONSERVA la guarda ORIGINAL del
    // export (su clave natural: `hub_settings` va por `(key, hub_id)`, no por todas las columnas)
    // y solo se remapean en ella los literales que apuntan a ids del bundle (los `*_id` de un
    // vínculo M2M acaban de cambiar a los ids NUEVOS del hub destino).
    let col_list = cols
        .iter()
        .map(|c| quote_ident(c))
        .collect::<Vec<_>>()
        .join(", ");
    let val_list = new_vals.join(", ");
    let id_idx = cols.iter().position(|c| c == "id");
    let guard = if let Some(i) = id_idx.filter(|_| hub_scoped) {
        let id_lit = &new_vals[i];
        format!(
            " WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE \"hub_id\" = {hub} AND id = {id})",
            hub = quote_string_literal(target_hub_id),
            id = id_lit,
        )
    } else if let Some(i) = id_idx {
        // Sin `hub_id` (identidad del core): guarda por `id` a secas — nombrar una columna que la
        // tabla no tiene rompe la sección entera.
        format!(
            " WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE id = {id})",
            id = &new_vals[i]
        )
    } else {
        // Conserva la guarda original; remapea los ids del bundle que aparezcan como literales
        // (vínculos M2M: `product_id`/`category_id` acaban de pasar a los ids nuevos del destino).
        remap_literals_in_guard(_guard, id_map)
    };
    format!("INSERT INTO {table} ({col_list}) SELECT {val_list}{guard};\n")
}

/// Reemplaza, dentro del texto de una guarda `NOT EXISTS`, cada literal de cadena `'old'` cuyo
/// `old` sea un id del bundle por `'new'`. Operación segura aquí: los ids son UUIDs v4 y solo
/// aparecen como literales completos `'…'` (el export nunca los embebe dentro de otro dato), así
/// que sustituir el par completo `'old'` no toca subcadenas ajenas.
fn remap_literals_in_guard(guard: &str, id_map: &std::collections::HashMap<String, String>) -> String {
    let mut out = guard.to_string();
    for (old, new) in id_map {
        let from = quote_string_literal(old);
        let to = quote_string_literal(new);
        if out.contains(&from) {
            out = out.replace(&from, &to);
        }
    }
    out.trim_end_matches(';').to_string()
}

/// Divide `rest` en (parte de valores, parte de guarda). La guarda es lo que haya desde el primer
/// ` WHERE ` (a nivel de sentencia, no dentro de `NOT EXISTS`) hasta el final.
fn split_off_guard(rest: &str) -> (&str, &str) {
    match rest.find(" WHERE ") {
        Some(pos) => (&rest[..pos], &rest[pos..]),
        None => (rest, ""),
    }
}

/// Lista de literales de un `SELECT <lit>, <lit>, …` o de `VALUES (…), (…)`. Devuelve los literales
/// de la PRIMERA tupla (el export emite una fila por sentencia). Respeta comillas simples y `''`.
fn parse_value_list(s: &str) -> Option<Vec<String>> {
    let s = s.trim();
    if let Some(inner) = s.strip_prefix("VALUES") {
        let inner = inner.trim_start();
        let open = inner.find('(')?;
        let close = matching_paren(inner, open)?;
        return Some(split_top_level_commas(&inner[open + 1..close]));
    }
    let after_select = s.strip_prefix("SELECT")?;
    Some(split_top_level_commas(after_select.trim_start().trim_end_matches(';')))
}

/// Parte por comas que NO están dentro de `'…'` (un literal puede traer comas) ni de `"…"`.
fn split_top_level_commas(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut cur = String::new();
    let mut chars = s.chars().peekable();
    let mut in_single = false;
    let mut in_double = false;
    while let Some(c) = chars.next() {
        if in_single {
            cur.push(c);
            if c == '\'' {
                if chars.peek() == Some(&'\'') {
                    cur.push(chars.next().unwrap());
                } else {
                    in_single = false;
                }
            }
            continue;
        }
        if in_double {
            cur.push(c);
            if c == '"' {
                in_double = false;
            }
            continue;
        }
        match c {
            '\'' => {
                in_single = true;
                cur.push(c);
            }
            '"' => {
                in_double = true;
                cur.push(c);
            }
            ',' => {
                out.push(std::mem::take(&mut cur));
            }
            _ => cur.push(c),
        }
    }
    out.push(cur);
    out.iter().map(|p| p.trim().to_string()).filter(|p| !p.is_empty()).collect()
}

/// Índice del `)` que cierra el `(` en `pos`, respetando literales e identificadores.
fn matching_paren(s: &str, open: usize) -> Option<usize> {
    let bytes = s.as_bytes();
    if bytes.get(open) != Some(&b'(') {
        return None;
    }
    let mut depth = 0i32;
    let mut in_single = false;
    let mut in_double = false;
    let mut chars = s[open..].chars().peekable();
    let mut consumed = 0usize;
    while let Some(c) = chars.next() {
        consumed += c.len_utf8();
        if in_single {
            if c == '\'' {
                if chars.peek() == Some(&'\'') {
                    consumed += chars.next().unwrap().len_utf8();
                } else {
                    in_single = false;
                }
            }
            continue;
        }
        if in_double {
            if c == '"' {
                in_double = false;
            }
            continue;
        }
        match c {
            '\'' => in_single = true,
            '"' => in_double = true,
            '(' => depth += 1,
            ')' => {
                depth -= 1;
                if depth == 0 {
                    return Some(open + consumed - 1);
                }
            }
            _ => {}
        }
    }
    None
}

/// Quita las comillas dobles de un identificador de columna (`"key"` → `key`).
fn unquote_ident(s: &str) -> String {
    s.trim()
        .trim_matches('"')
        .replace("\"\"", "\"")
}

/// Convierte un literal de cadena SQL (`'Café'`) en su contenido (`Café`). Solo si es tal literal.
fn unquote_string_literal(lit: &str) -> Option<String> {
    let lit = lit.trim();
    let inner = lit.strip_prefix('\'')?.strip_suffix('\'')?;
    Some(inner.replace("''", "'"))
}

/// Pone comillas simples a una cadena para usarla como literal SQL (escapando `'`).
fn quote_string_literal(s: &str) -> String {
    format!("'{}'", s.replace('\'', "''"))
}

/// Entrecomilla un identificador (columna) como hace el export (`quote_ident`).
fn quote_ident(name: &str) -> String {
    format!("\"{}\"", name.replace('"', "\"\""))
}

/// Id NUEVO y DETERMINÍSTICO para una fila del bundle bajo el hub DESTINO (uuid v5 sobre
/// `(hub_id, id_origen)`). Es la pieza que hace que el cross-hub en una BD compartida no colisione
/// contra la PK global (`id TEXT PRIMARY KEY`) SIN romper la idempotencia del re-import: el mismo
/// bundle en el mismo hub produce siempre el mismo id (la guarda `(hub_id, id)` casa y se salta),
/// y dos hubs distintos producen ids distintos. El `id_origen` queda embebido en el nombre del v5,
/// así no hay dependencia del orden de import ni colisión entre filas.
fn derive_id(target_hub_id: &str, source_id: &str) -> String {
    // Namespace fijo propio del motor (no se deriva del hub: el hub va en el NOMBRE, para que dos
    // hubs den ids distintos a partir del mismo id origen).
    const NS: uuid::Uuid = uuid::Uuid::from_bytes([
        0x48, 0x55, 0x42, 0x42, 0x4c, 0x55, 0x45, 0x50, 0x52, 0x49, 0x4e, 0x54, 0x32, 0x36, 0x30,
        0x21,
    ]);
    let name = format!("{target_hub_id}\x1f{source_id}"); // \x1F separa hub de id (no aparece en ids)
    uuid::Uuid::new_v5(&NS, name.as_bytes()).to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El informe hace round-trip serde: es el contrato JSON que la UI del shell pinta.
    #[test]
    fn report_serde_round_trip() {
        let r = ImportReport {
            sections: vec![
                SectionResult {
                    section: "modules/taxes".into(),
                    status: SectionStatus::Applied,
                    discarded_rows: 0,
                },
                SectionResult {
                    section: "hub_users".into(),
                    status: SectionStatus::Ignored("identity_not_portable".into()),
                    discarded_rows: 4,
                },
                SectionResult {
                    section: "modules/inventory".into(),
                    status: SectionStatus::Failed("módulo no instalado".into()),
                    discarded_rows: 0,
                },
            ],
        };
        let json = serde_json::to_string(&r).unwrap();
        let back: ImportReport = serde_json::from_str(&json).unwrap();
        assert_eq!(r, back);
    }

    /// A manifest whose only interesting part is where it comes from (hub#331 gate).
    fn manifest_from(origin_hub_id: &str) -> BlueprintManifest {
        BlueprintManifest {
            schema_version: crate::export::SCHEMA_VERSION,
            purpose: crate::export::BundlePurpose::Backup,
            name: "restaurante".into(),
            locale: "es".into(),
            hub: crate::export::HubMeta {
                name: "Bar Pepe".into(),
                country: "ES".into(),
                currency: "EUR".into(),
                hub_id: origin_hub_id.into(),
            },
            created_at: "2026-08-06T00:00:00Z".into(),
            modules: Vec::new(),
            sections: vec!["hub_users".into()],
            active_roles: Vec::new(),
            sha256: BTreeMap::new(),
        }
    }

    /// Identities belong to ONE installation: only that installation restoring itself may write
    /// them (hub#331). Everything else — a published blueprint, another hub's backup, a hand-made
    /// zip — is discarded whatever its `purpose` says.
    #[test]
    fn identities_travel_only_within_the_same_hub() {
        assert_eq!(
            identity_not_portable(&manifest_from("h1"), "hub_users", "h1"),
            None,
            "a hub restoring its own backup keeps its users (ADR-0113 §1)"
        );
        assert_eq!(
            identity_not_portable(&manifest_from("h1"), "hub_users", "h2").as_deref(),
            Some(ignore_reason::IDENTITY_NOT_PORTABLE),
            "another hub's identities must never be applied here"
        );
        // The gate is about identities: the rest of the bundle is not its business.
        assert_eq!(identity_not_portable(&manifest_from("h1"), "modules/inventory", "h2"), None);
        assert_eq!(identity_not_portable(&manifest_from("h1"), "hub_settings", "h2"), None);
    }

    /// 🔴 An UNKNOWN origin is not «the same hub». Bundles older than `manifest.hub.hub_id`
    /// (hub#312) read as an empty origin, and those are precisely the artefacts this defends
    /// against — the four blueprints published with `Demo`/admin inside. If an empty origin could
    /// ever match, a bundle would only need to omit the field to get its accounts in.
    #[test]
    fn an_unknown_origin_is_never_the_same_hub() {
        assert!(!is_same_hub(&manifest_from(""), ""), "unknown origin must not match anything");
        assert_eq!(
            identity_not_portable(&manifest_from(""), "hub_users", "").as_deref(),
            Some(ignore_reason::IDENTITY_NOT_PORTABLE)
        );
        assert_eq!(
            identity_not_portable(&manifest_from(""), "hub_users", "h2").as_deref(),
            Some(ignore_reason::IDENTITY_NOT_PORTABLE)
        );
    }

    /// The report says HOW MANY rows a discard dropped, counted with the SAME splitter the import
    /// validates with — so the number can never disagree with what would have been applied.
    #[test]
    fn a_discard_counts_the_rows_it_dropped() {
        let sql = "INSERT INTO hub_user (\"id\", \"name\") SELECT 'u1', 'Demo';\n\
                   INSERT INTO hub_user (\"id\", \"name\") SELECT 'u2', 'Manager';\n";
        let mut files: BTreeMap<String, Vec<u8>> = BTreeMap::new();
        files.insert("data/hub_users.sql".into(), sql.as_bytes().to_vec());
        assert_eq!(rows_in_section("hub_users", &files), 2);
        // A section with no file of its own, or absent from the bundle, counts as nothing dropped.
        assert_eq!(rows_in_section("fiscal", &files), 0);
        assert_eq!(rows_in_section("modules/inventory", &files), 0);
        // An unparseable file must not turn the count into a second failure path.
        files.insert("data/hub_users.sql".into(), b"INSERT INTO hub_user SELECT 'unclosed".to_vec());
        assert_eq!(rows_in_section("hub_users", &files), 0);
    }

    /// A `hub_settings` statement, in the exact shape `export::rows_to_sql` emits.
    fn settings_row(key: &str, value: &str) -> String {
        format!(
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\", \"updated_at\", \"updated_by\") \
             SELECT 'h2', '{key}', '{value}', '2026-08-06T10:00:00Z', 'system' \
             WHERE NOT EXISTS (SELECT 1 FROM hub_settings WHERE \"key\" = '{key}' AND hub_id = 'h2');\n"
        )
    }

    fn settings_scope() -> crate::import_sql::TableScope {
        crate::import_sql::scope_for_data_file("data/hub_settings.sql").expect("settings scope")
    }

    /// 🔴 ADR-0195 §4 (hub#405): of a FOREIGN bundle's settings, only the configuration survives.
    /// The tax id is the row that matters — the dispatcher's fiscal gate (ADR-0203) reads exactly
    /// that key to decide the hub may issue, so injecting it does not just mislabel a screen: it
    /// makes this hub invoice, and chain to the AEAT, under another company's NIF.
    #[test]
    fn a_foreign_settings_section_keeps_only_the_configuration() {
        let sql = format!(
            "{}{}{}{}",
            settings_row("country_code", "ES"),
            settings_row("business_tax_id", "B12345678"),
            settings_row("language", "es"),
            settings_row("business_legal_name", "Bar Pepe SL"),
        );
        let (kept, dropped) = keep_portable_settings(&sql, &settings_scope()).expect("valid section");

        assert_eq!(dropped, 2, "two identity rows had to be dropped:\n{kept}");
        assert!(kept.contains("'country_code'") && kept.contains("'language'"), "the configuration must survive:\n{kept}");
        assert!(!kept.contains("business_tax_id"), "the tax id of another business must not be written:\n{kept}");
        assert!(!kept.contains("B12345678"), "…nor its value:\n{kept}");
        assert!(!kept.contains("Bar Pepe SL"), "…nor the legal name:\n{kept}");
        // What survives is still exactly what the import will validate and run (same grammar).
        assert!(
            crate::import_sql::validate(&kept, &settings_scope()).is_ok(),
            "the surviving SQL must still pass the import subset:\n{kept}"
        );
    }

    /// An unclassified key is dropped, and so is a legal-but-unreadable row (here: no `key` column
    /// at all). The filter only lets through what it can positively identify as configuration —
    /// letting through what it cannot read is how an allowlist stops being one.
    #[test]
    fn an_unreadable_or_unknown_settings_row_does_not_get_through() {
        let sql = format!(
            "{}{}",
            settings_row("printer_ip", "192.168.1.50"),
            "INSERT INTO hub_settings (\"hub_id\", \"value\") SELECT 'h2', 'x';\n",
        );
        let (kept, dropped) = keep_portable_settings(&sql, &settings_scope()).expect("valid section");
        assert_eq!(dropped, 2, "both rows had to be dropped:\n{kept}");
        assert!(kept.trim().is_empty(), "nothing may survive:\n{kept}");
    }

    /// 🔴 An INVALID section still fails WHOLE (hub#239): the filter runs AFTER the grammar, never
    /// instead of it. Filtering first would have dropped the `DROP TABLE` on the floor and applied
    /// the rest — a bundle the user has to be warned about, turned into a quiet partial import.
    #[test]
    fn an_invalid_settings_section_still_fails_whole_instead_of_being_trimmed() {
        for payload in [
            "DROP TABLE hub_settings;",
            "INSERT INTO hub_user (\"id\", \"name\") SELECT 'x', 'y';",
            // Exfiltration: lexically an INSERT into its own section, reading another table.
            "INSERT INTO hub_settings (\"hub_id\", \"key\", \"value\") SELECT 'h2', 'leak', pin_hash FROM hub_user;",
            "INSERT INTO hub_settings (\"key\") SELECT 'unclosed",
        ] {
            let sql = format!("{}{payload}", settings_row("country_code", "ES"));
            assert!(
                keep_portable_settings(&sql, &settings_scope()).is_err(),
                "`{payload}` had to fail the whole section, not be filtered away"
            );
        }
    }

    /// `derive_id` es determinista: mismo `(hub, id)` → mismo id, siempre (la idempotencia del
    /// re-import depende de ello). Y distinto hub → distinto id (sin colisión de PK global).
    #[test]
    fn derive_id_es_determinista_y_distinta_por_hub() {
        let a1 = derive_id("h2", "src-1");
        let a2 = derive_id("h2", "src-1");
        assert_eq!(a1, a2, "mismo (hub,id) → mismo id derivado (idempotencia)");
        let b = derive_id("h3", "src-1");
        assert_ne!(a1, b, "distinto hub → distinto id (sin colisión de PK global)");
        let c = derive_id("h2", "src-2");
        assert_ne!(a1, c, "distinto id origen → distinto id");
        assert!(!a1.is_empty());
    }

    /// `remap_section_ids` reescribe el `id` por uno derivado del hub destino, deja intactas las
    /// columnas que no son id/FK (`name`, `sku`), remapea la FK interna (`category_id`) y acota la
    /// guarda por `(hub_id, id)` (hub#260).
    #[test]
    fn remap_reescribe_id_acota_guard_y_deja_los_datos() {
        // Forma real que emite `export::rows_to_sql` (placeholder ya sustituido por el hub destino).
        let sql = "INSERT INTO inventory_product (\"id\", \"hub_id\", \"name\", \"sku\") \
                   SELECT 'src-prod', 'h2', 'Café', 'CAF' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'src-prod');";
        let out = remap_section_ids(sql, "h2");
        // El id de origen NO aparece (fue reescrito por el derivado).
        assert!(!out.contains("'src-prod'"), "el id origen debe reescribirse: {out}");
        // Los datos del usuario se conservan.
        assert!(out.contains("'Café'") && out.contains("'CAF'"), "se perdieron datos: {out}");
        // La guarda va por (hub_id, id) destino — id ya NO va solo.
        assert!(
            out.contains("\"hub_id\" = 'h2' AND id = "),
            "la guarda debe acotarse por (hub_id, id): {out}"
        );
        // Idempotencia: misma entrada → misma salida (el id derivado es estable).
        assert_eq!(out, remap_section_ids(sql, "h2"), "el remap debe ser determinista");
    }

    /// 🔴 El SQL que rompía la sección **Usuarios** en producción (2026-08-03):
    /// `reset: aplicar sentencia: sqlx: … column "hub_id" does not exist`.
    ///
    /// `rewrite_insert` metía `"hub_id" = <destino>` en la guarda de TODA tabla con `id`, pero
    /// `hub_user` es identidad del CORE y **no tiene columna `hub_id`** (`identity.rs`: id, name,
    /// pin_hash, role, cloud_user_id, is_active, created_at, email).
    #[test]
    fn una_tabla_sin_hub_id_no_puede_llevarlo_en_la_guarda() {
        // Forma REAL del `data/hub_users.sql` del blueprint `restaurante` publicado.
        let sql = "INSERT INTO hub_user (\"cloud_user_id\", \"created_at\", \"id\", \"name\", \"role\") \
                   SELECT NULL, '2026-01-01T00:00:00+00:00', 'bp-user-manager-000000000000000', 'Manager', 'manager' \
                   WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE id = 'bp-user-manager-000000000000000');";
        let out = remap_section_ids(sql, "56f2bbe7-792e-44d3-adfe-c18891cfc925");

        assert!(
            !out.contains("hub_id"),
            "`hub_user` no tiene columna hub_id: nombrarla revienta la sección entera:\n{out}"
        );
        // Su id se CONSERVA: sin hub_id no hay colisión entre hermanos que evitar, y derivarlo
        // metería un «Manager» duplicado por cada hub de la organización (la tabla es compartida).
        assert!(
            out.contains("'bp-user-manager-000000000000000'"),
            "una fila no-hub-scoped conserva su id (idempotencia para toda la org):\n{out}"
        );
    }

    /// 🔴 Regresión detectada importando de VERDAD el blueprint `restaurante` (2026-08-03):
    /// `inventory` falló con `violates foreign key constraint
    /// inventory_product_categories_product_id_fkey`.
    ///
    /// «Sin `hub_id`» agrupa DOS cosas que no se pueden tratar igual: la identidad del core
    /// (`hub_user`, con `id` propio que NO se remapea) y las tablas de VÍNCULO M2M (sin `id`
    /// propio, solo FKs a filas hub-scoped que SÍ acaban de remapearse). Lo único común es que
    /// ninguna puede nombrar `hub_id` en su guarda.
    #[test]
    fn una_tabla_de_vinculo_sin_hub_id_si_remapea_sus_fk() {
        let sql = "INSERT INTO inventory_product (\"id\", \"hub_id\", \"name\") \
                   SELECT 'src-prod', 'h2', 'Café' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'src-prod');\n\
                   INSERT INTO inventory_product_categories (\"product_id\", \"category_id\") \
                   SELECT 'src-prod', 'src-cat' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product_categories WHERE product_id = 'src-prod');";
        let out = remap_section_ids(sql, "h2");

        assert!(!out.contains("'src-prod'"), "el producto (hub-scoped) debe remapearse:\n{out}");
        let prod = out.lines().find(|l| l.contains("INSERT INTO inventory_product ")).unwrap();
        let nuevo = prod
            .split("SELECT ").nth(1).unwrap().trim()
            .strip_prefix('\'').unwrap().split('\'').next().unwrap().to_string();
        let link = out.lines().find(|l| l.contains("inventory_product_categories")).unwrap();
        assert!(
            link.contains(&format!("'{nuevo}'")),
            "la FK del vínculo debe apuntar al id NUEVO del producto ({nuevo}):\n{link}"
        );
        assert!(!link.contains("hub_id"), "el vínculo no tiene columna hub_id:\n{link}");
    }

    /// Una FK interna (columna `*_id`) que apunta a otro id DEL BUNDLE se remapea al nuevo id;
    /// una que apunta a un id AJENO al bundle (un `tax_rate_id` cuya fila no viaja) se conserva.
    /// El remap solo conoce los ids de las filas PRESENTES en la sección (las que tienen `id`).
    #[test]
    fn remap_remapea_fk_interna_y_conserva_referencia_ajena() {
        // La categoría `src-cat` SÍ viaja en el bundle (otra fila con ese `id`); `ext-rate` no.
        // El fixture lleva `hub_id` porque el export lo emite SIEMPRE en una tabla de módulo (el
        // runtime lo auto-inyecta en toda fila — contrato de fila, tenancy.md §2.5), igual que el
        // fixture del test hermano. Omitirlo describía una fila que el export no puede producir, y
        // desde el fix de la guarda la ausencia de la columna SIGNIFICA «tabla no acotada por hub».
        // La intención del test —FK interna se remapea, FK ajena se conserva— no cambia.
        let sql = "INSERT INTO inventory_category (\"id\", \"hub_id\") SELECT 'src-cat', 'h2' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_category WHERE id = 'src-cat');\n\
                   INSERT INTO inventory_product (\"id\", \"hub_id\", \"category_id\", \"tax_rate_id\") \
                   SELECT 'src-prod', 'h2', 'src-cat', 'ext-rate' \
                   WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = 'src-prod');";
        let out = remap_section_ids(sql, "h2");

        // `ext-rate` no es id de ninguna fila del bundle → se conserva (referencia externa).
        assert!(out.contains("'ext-rate'"), "una FK ajena al bundle no debe tocarse: {out}");

        // Los ids del bundle ya no aparecen con su valor origen.
        assert!(
            !out.contains("'src-cat'") && !out.contains("'src-prod'"),
            "los ids del bundle deben reescribirse: {out}"
        );

        // La FK interna `category_id` apunta ahora al MISMO id nuevo que la fila categoría: la
        // guarda de la categoría lleva su id nuevo, y ese mismo literal aparece como valor del
        // `category_id` del producto (la FK casa con el padre recién reescrito).
        let cat_line = out.lines().find(|l| l.contains("INSERT INTO inventory_category")).unwrap();
        let new_cat_id = cat_line
            .split("SELECT ")
            .nth(1)
            .and_then(|s| s.trim().strip_prefix('\''))
            .and_then(|s| s.split('\'').next())
            .expect("id nuevo de la categoría");
        let prod_line = out.lines().find(|l| l.contains("INSERT INTO inventory_product")).unwrap();
        assert!(
            prod_line.contains(&format!("'{}'", new_cat_id)),
            "category_id debe quedar remapeado al id nuevo de la categoría ({new_cat_id}):\n{prod_line}"
        );
    }
}
