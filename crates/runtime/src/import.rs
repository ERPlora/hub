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
    /// The batch this import ran under, so its report can be recovered after navigation/reload
    /// (hub#763). Skipped on the wire: the shell's contract is `sections` (+ the server's
    /// `installed_modules`/`media`/`fiscal`), and a server that does not know the field must still
    /// round-trip. The client reads it through the persisted report, not this field.
    #[serde(default, skip_serializing, skip_deserializing)]
    pub batch_id: Option<String>,
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
        // Same for the capability grants (hub#473): keys in `manifest.capability_grants`, applied
        // after this loop through the granting door, never as rows.
        // Same again for the flows (hub#986): documents in `manifest.flows`, saved after this loop
        // through `flows::store::create`, never as rows.
        if section == crate::export::ROLES_SECTION
            || section == crate::export::CAPABILITY_GRANTS_SECTION
            || section == crate::export::FLOWS_SECTION
        {
            continue;
        }
        // Asked BEFORE the match, not inside it: the answer comes from `rt.registry()` and the
        // arms below hand `rt` out mutably, so the borrow must be over by then. The value is a
        // plain `Option<String>`, so `.or()` is the same decision `.or_else()` would make.
        let installation_bound =
            installation_bound_not_portable(rt.registry(), manifest, section, target_hub_id);
        let (status, discarded_rows) = match system_table_not_portable(section)
            .or_else(|| ignored_by_purpose(manifest, section))
            .or_else(|| identity_not_portable(manifest, section, target_hub_id))
            .or(installation_bound)
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
    // ── The capabilities each module had granted (hub#473) ───────────────────
    // AFTER the sections, for the same reason as the roles: the modules whose `module.json`
    // DECLARES these capabilities are installed by the server before the engine runs, and a
    // capability nobody declares is refused. Driven by the DATA (`capability_grants`) and not by
    // the presence of the section label, so a hand-made bundle that omits the label gets the very
    // same guards.
    if !manifest.capability_grants.is_empty() {
        let (status, discarded_rows) =
            apply_capability_grants(rt, manifest, target_hub_id, same_hub).await;
        report.sections.push(SectionResult {
            section: crate::export::CAPABILITY_GRANTS_SECTION.to_string(),
            status,
            discarded_rows,
        });
    }
    // ── The automations the business had written (hub#986) ───────────────────
    // LAST of the three declarative sections, and the order is load-bearing: a flow names commands
    // and queries of modules the server installs before the engine runs, and its grants are judged
    // against the registry as it stands. Driven by the DATA (`flows`) and not by the section label,
    // so a hand-made bundle that omits the label gets the very same guards.
    if !manifest.flows.is_empty() {
        let (status, discarded_rows) = apply_flows(rt, manifest, target_hub_id, same_hub).await;
        report.sections.push(SectionResult {
            section: crate::export::FLOWS_SECTION.to_string(),
            status,
            discarded_rows,
        });
    }
    // ── Persist the actionable report under its batch (hub#763) ──────────────
    // The engine's report used to live ONLY in the return value — so once the caller navigated
    // away (the Dashboard hero → Settings › Data path), the report was gone and the Data tab could
    // only show the catalogue again. Storing it under the same `batch_id` the batch opened lets
    // the Data tab recover it on mount, after a reload or a new session. A failure here MUST NOT
    // abort the import (the engine already ran): losing it costs this traceability, not the data.
    // The server UPSERTs the EXTENDED report (sections + installed_modules/media/fiscal) over the
    // same `batch_id` once its orchestration finishes, so what a reload reads is the full picture.
    if let Some(ref batch) = batch_id {
        if let Ok(json) = serde_json::to_string(&report) {
            let _ = crate::reset::store_import_report(rt, target_hub_id, batch, &manifest.name, &json).await;
        }
    }
    report.batch_id = batch_id;
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

/// Re-grants the capabilities the backup carried and turns the outcome into a row of the report.
///
/// **Whose hub this is decides first** — the same question, and the same `is_same_hub`, that the
/// identities of ADR-0195 §3 are gated on. A capability grant is not vocabulary of a business (which
/// is why the role set travels in both purposes, ADR-0242 §8): it is the approval THIS deployment's
/// owner gave a module over the host's own primitives. A downloaded blueprint arriving with
/// `certificate` pre-granted would be a file deciding that a module may use your signing key, and it
/// would be the only grant in the system nobody ever clicked. So a bundle that is not this hub's own
/// copy is discarded whole, counted, and reported with its stable code.
///
/// For the hub's own restore the policy lives in [`crate::capabilities::pre_grant`] — this only
/// decides how to SAY it, with the three states the report already has, and counts the pairs left
/// out. A database failure is `Failed`, never a discard.
async fn apply_capability_grants(
    rt: &Runtime,
    manifest: &BlueprintManifest,
    target_hub_id: &str,
    same_hub: bool,
) -> (SectionStatus, u32) {
    let asked: u32 = manifest.capability_grants.values().map(|c| c.len() as u32).sum();
    if !same_hub {
        return (
            SectionStatus::Ignored(ignore_reason::CAPABILITY_GRANTS_NOT_PORTABLE.into()),
            asked,
        );
    }
    match crate::capabilities::pre_grant(
        rt.db(),
        rt.registry(),
        target_hub_id,
        &manifest.capability_grants,
        crate::roles::BLUEPRINT_ACTOR,
    )
    .await
    {
        Ok(outcome) => {
            let discarded = outcome.refused.len() as u32;
            let status = if outcome.refused.is_empty() {
                SectionStatus::Applied
            } else if outcome.granted.is_empty() {
                SectionStatus::Ignored(ignore_reason::CAPABILITIES_NOT_GRANTABLE.into())
            } else {
                SectionStatus::PartiallyApplied(ignore_reason::CAPABILITIES_NOT_GRANTABLE.into())
            };
            (status, discarded)
        }
        Err(e) => (SectionStatus::Failed(e.to_string()), 0),
    }
}

/// Restores the automations the backup carried and turns the outcome into a row of the report
/// (hub#986 — ADR-0345 §2bis, the ⚠️ row of the table).
///
/// **The definition lands; the authority is what depends on whose bundle this is.** ADR-0345 draws
/// the line by asking whether a datum is of the BUSINESS or of THIS DEPLOYMENT, and a flow falls on
/// both sides at once: the document is what its owner wrote (so it travels in a backup, like the
/// customers and the products already do), while its `_flow_grants` are the approval of one
/// deployment's owner over what an automation may do with nobody watching (so they are only re-made
/// for the hub restoring its own copy, `is_same_hub`, exactly like the capability grants of hub#473).
///
/// Four properties, each one deliberate:
///
/// - **The same door as `POST /flows`.** Every document goes through [`crate::flows::store::create`],
///   so a bundle gets the guards the screen gets: a document that does not parse, an unresolvable
///   `cron`, a `query` step naming a read nobody has — all refused here, counted, and the rest of
///   the flows still land. An `INSERT` would have let a zip store what the hub can never execute.
/// - **Created DISABLED, armed last.** The flow is written paused, its grants are re-made, and only
///   then is it armed. The reverse order would leave a window in which the tick could fire a flow
///   whose permissions had not arrived yet — and a flow that runs without its grants fails every
///   step. If any grant did not come back, it simply stays paused, with its reason in the report.
/// - **Additive, never mirroring.** A flow this hub wrote after the backup was taken is left alone;
///   restoring an old copy must not delete an automation somebody created later (hub#473's lesson).
/// - **Idempotent by name + document.** The same flow, by the same name, already live is already
///   there: restoring twice does not hand the owner two copies of the same job, and two runs per
///   event.
///
/// A database failure is `Failed`, never a discard: «I could not write» must not read as «this hub
/// said no».
async fn apply_flows(
    rt: &Runtime,
    manifest: &BlueprintManifest,
    target_hub_id: &str,
    same_hub: bool,
) -> (SectionStatus, u32) {
    use crate::flows::grants::GrantKind;

    let db = rt.db();
    let registry = rt.registry();
    let mut live = match crate::flows::store::list(db, target_hub_id).await {
        Ok(live) => live,
        Err(e) => return (SectionStatus::Failed(e.to_string()), 0),
    };

    // Documents that landed (created here or already present), documents this hub will not save,
    // and the ones that landed but stayed PAUSED because their authority did not come back.
    let (mut landed, mut refused, mut paused) = (0u32, 0u32, 0u32);
    // …and whether the reason for that is that this bundle is not this hub's own copy, which is a
    // different sentence to the user than «that command no longer exists here».
    let mut grants_not_portable = false;

    for spec in &manifest.flows {
        if live
            .iter()
            .any(|f| f.name == spec.name && f.definition == spec.definition)
        {
            landed += 1;
            continue;
        }
        let new = crate::flows::NewFlow {
            name: spec.name.clone(),
            enabled: false, // armed at the end, once its authority is back
            definition: spec.definition.clone(),
        };
        let flow = match crate::flows::store::create(
            db,
            target_hub_id,
            registry,
            &new,
            crate::roles::BLUEPRINT_ACTOR,
        )
        .await
        {
            Ok(flow) => flow,
            Err(e) if is_write_failure(&e) => return (SectionStatus::Failed(e.to_string()), refused),
            Err(_) => {
                refused += 1;
                continue;
            }
        };
        landed += 1;
        live.push(flow.clone());

        // The grants. Only this hub's own copy re-makes them; anybody else's bundle leaves the flow
        // inert, which is what default-deny already means.
        let mut authority_complete = true;
        if !spec.grants.is_empty() && !same_hub {
            grants_not_portable = true;
            authority_complete = false;
        } else {
            for wanted in &spec.grants {
                // One pair at a time, each time re-reading what is already live and offering it
                // back plus the candidate. `grants::replace` is a REPLACE and it refuses a whole
                // list if one pair names nothing — right for a screen somebody typed, wrong for a
                // restore, which is best-effort like every other section here. Asking the REAL door
                // once per pair keeps the judgement in the one place that enforces it; filtering
                // the list first would be a SECOND door, judging by rules that could drift from the
                // ones that matter.
                let Some(kind) = GrantKind::parse(&wanted.kind) else {
                    authority_complete = false;
                    continue;
                };
                let mut candidate: Vec<(GrantKind, String)> = crate::flows::grants::list(
                    db,
                    target_hub_id,
                    &flow.id,
                )
                .await
                .unwrap_or_default()
                .into_iter()
                .filter_map(|g| GrantKind::parse(&g.kind).map(|k| (k, g.value)))
                .collect();
                candidate.push((kind, wanted.value.clone()));
                match crate::flows::grants::replace(
                    db,
                    target_hub_id,
                    &flow.id,
                    registry,
                    &candidate,
                    crate::roles::BLUEPRINT_ACTOR,
                )
                .await
                {
                    Ok(()) => {}
                    Err(e) if is_write_failure(&e) => {
                        return (SectionStatus::Failed(e.to_string()), refused)
                    }
                    Err(_) => authority_complete = false,
                }
            }
        }

        if spec.enabled && authority_complete {
            let armed = crate::flows::NewFlow { enabled: true, ..new };
            match crate::flows::store::update(
                db,
                target_hub_id,
                &flow.id,
                registry,
                &armed,
                crate::roles::BLUEPRINT_ACTOR,
            )
            .await
            {
                Ok(_) => {}
                Err(e) if is_write_failure(&e) => {
                    return (SectionStatus::Failed(e.to_string()), refused)
                }
                Err(_) => paused += 1,
            }
        } else if spec.enabled {
            paused += 1;
        }
    }

    // One row, so the reasons are ordered by what the user has to act on first: a document that did
    // not land at all, then permissions a foreign bundle may not make, then a flow waiting for the
    // permission it lost. `discarded_rows` counts DOCUMENTS left out — a paused flow is in the hub,
    // it is simply not running.
    let status = if refused > 0 && landed == 0 {
        SectionStatus::Ignored(ignore_reason::FLOWS_NOT_RESTORABLE.into())
    } else if refused > 0 {
        SectionStatus::PartiallyApplied(ignore_reason::FLOWS_NOT_RESTORABLE.into())
    } else if grants_not_portable {
        SectionStatus::PartiallyApplied(ignore_reason::FLOW_GRANTS_NOT_PORTABLE.into())
    } else if paused > 0 {
        SectionStatus::PartiallyApplied(ignore_reason::FLOWS_PAUSED_WITHOUT_GRANTS.into())
    } else {
        SectionStatus::Applied
    };
    (status, refused)
}

/// Is this error the database (or the disk) failing, rather than the hub REFUSING?
///
/// The distinction is the one every best-effort section here depends on: a policy refusal is
/// reported and the import goes on, while «I could not write» has to surface as `Failed` instead of
/// being dressed up as a decision. Everything the runtime raises on its own — an invalid document,
/// a command that does not exist, an internal one — is a refusal; only the adapter's own errors and
/// I/O are not.
fn is_write_failure(e: &crate::RuntimeError) -> bool {
    matches!(e, crate::RuntimeError::Db(_) | crate::RuntimeError::Io(_))
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
    /// The bundle carried the capability grants of ANOTHER hub (hub#473). `network`, `certificate`,
    /// `printer` and `notify` are primitives of THIS deployment's host, and the grant over them is
    /// the approval its owner gave (ADR-0079, default-deny). A downloaded file may not make one, so
    /// the whole set is discarded — only the hub restoring its own copy gets its permissions back.
    pub const CAPABILITY_GRANTS_NOT_PORTABLE: &str = "capability_grants_not_portable";
    /// This hub's own backup asked to re-grant capabilities it cannot grant (hub#473): unknown
    /// keys, and keys the module INSTALLED HERE does not declare — a module updated to stop asking
    /// for the network, or one that failed to install. The rest were re-granted.
    pub const CAPABILITIES_NOT_GRANTABLE: &str = "capabilities_not_grantable";
    /// The bundle brought a section over one of the hub's OWN system tables — its fiscal profile,
    /// its certificate store, its import batches (ADR-0273 D8 — hub#560). Those are the identity of
    /// THIS installation, not vocabulary of anybody's business, so no bundle writes them: not a
    /// template, not another hub's backup, not this hub restoring itself.
    pub const SYSTEM_TABLE_NOT_PORTABLE: &str = "system_table_not_portable";
    /// A bundle produced by ANOTHER hub carried invoice series and the ledger of numbers they have
    /// already issued (`export::TEMPLATE_EXCLUDED_TABLES`, ADR-0266 — hub#533/#753). Those rows say
    /// how ONE installation numbers what it declares to the tax authority, and RD 1007/2023 wants
    /// that sequence with no gaps and no duplicates — per installation. The destination keeps its
    /// own series, its own `current_sequence` and its own ledger, untouched.
    pub const NUMBERING_NOT_PORTABLE: &str = "numbering_not_portable";
    /// A bundle produced by ANOTHER hub carried the data section of a module that declares
    /// `installation_bound_data` in its `module.json` (hub#380, generalising ADR-0202 §4.2): the
    /// records it chains belong to the installation that emitted them, and this hub opens its own.
    /// Named after the flag so the manifest field and the report row are one grep apart.
    pub const INSTALLATION_BOUND_DATA: &str = "installation_bound_data";
    /// The bundle carried the flow grants of ANOTHER hub (hub#986). What an automation may do —
    /// which commands it runs, which URLs it dials, whose address it may read — is the approval of
    /// THIS deployment's owner (ADR-0283 §2, default-deny), the same argument as
    /// [`CAPABILITY_GRANTS_NOT_PORTABLE`]. The documents landed, so the owner can read them and
    /// decide; they landed **paused**, because arming them was nobody's decision.
    pub const FLOW_GRANTS_NOT_PORTABLE: &str = "flow_grants_not_portable";
    /// This hub's own backup asked to re-grant permissions it cannot grant (hub#986): a command or
    /// a read that is no longer here — a module that did not come back, or one whose new version
    /// renamed it. Those flows are restored **disabled**, because an armed flow missing a permission
    /// fails on every run, at whatever hour its trigger fires, with nobody watching.
    pub const FLOWS_PAUSED_WITHOUT_GRANTS: &str = "flows_paused_without_grants";
    /// The bundle carried flow documents this hub **would refuse at the screen** (hub#986): one that
    /// does not parse, a `cron` the engine cannot resolve, a `query` step naming a read no installed
    /// module has. The import saves through the same door as `POST /flows`, so what the owner could
    /// not type in cannot arrive in a zip either. The rest of the flows still landed.
    pub const FLOWS_NOT_RESTORABLE: &str = "flows_not_restorable";
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

/// Data bound to the installation that produced it never travels (hub#380, generalising
/// ADR-0202 §4.2 — hub#312).
///
/// The module says so itself, through `installation_bound_data` in its `module.json`. This used to
/// ask whether the section was the literal `modules/verifactu`, which put one country's regime
/// inside a generic engine: TicketBai chains its records the same way and NF525 carries the same
/// integrity requirement, so every new regime would have been one more name in the core.
///
/// What the flag means, in the case that motivated it: `NumeroInstalacion` = `hub_id`, so the
/// `verifactu` data section (chain records, contingency queue, events, AEAT log) is the fiscal
/// history of ONE installation. Applied under another hub, its next record would chain on a
/// `RegistroAnterior` the AEAT never received for that installation — and another hub's pending
/// queue would get transmitted under the wrong `NumeroInstalacion`. A bundle proves its origin only
/// through `manifest.hub.hub_id` (bundles older than that field read as unknown origin and import
/// conservatively); the SAME hub restoring its own backup resumes its own chain (AEAT developer
/// FAQ §4).
fn installation_bound_not_portable(
    registry: &crate::Registry,
    manifest: &BlueprintManifest,
    section: &str,
    target_hub_id: &str,
) -> Option<String> {
    let module_id = section.strip_prefix("modules/")?;
    if !is_installation_bound(registry, module_id) || is_same_hub(manifest, target_hub_id) {
        return None;
    }
    Some(ignore_reason::INSTALLATION_BOUND_DATA.into())
}

/// Modules whose data is bound to their installation even though the manifest INSTALLED here does
/// not say so — a bridge, not a rule (hub#380).
///
/// `verifactu` was published before the flag existed, so asking its manifest answers «portable»,
/// and another installation's fiscal chain would land in this hub: precisely what ADR-0202 §4.2
/// forbids and what the literal this function replaces was there to stop. The name keeps it bound
/// until the module is republished declaring `installation_bound_data: true`, and it goes away with
/// that republication. Nothing else may be added here: a second name would be the hard-coding
/// coming back through the door it just left.
const INSTALLATION_BOUND_BY_LEGACY_NAME: [&str; 1] = ["verifactu"];

/// Is this module's data bound to the installation that produced it? Its manifest first, the
/// legacy fallback second.
fn is_installation_bound(registry: &crate::Registry, module_id: &str) -> bool {
    registry.is_installation_bound(module_id)
        || INSTALLATION_BOUND_BY_LEGACY_NAME.contains(&module_id)
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
    //
    // hub#753: y la numeración de OTRA instalación tampoco entra — ver `drop_foreign_numbering`.
    // `reason` es el código estable que explicará el descarte en el informe; solo se lee cuando de
    // verdad se descartó algo (`None` = no había filtro que aplicar, así que no hay nada que decir).
    let demo_hub = rt.registry().demo_hub;
    let (sql, discarded, reason) = if section == "hub_settings" && (!same_hub || demo_hub) {
        match keep_portable_settings(&sql, &scope) {
            Ok((sql, dropped)) => (sql, dropped, Some(ignore_reason::SETTINGS_NOT_PORTABLE)),
            // Invalid section: it fails WHOLE and without touching the BD, exactly as it did
            // before this filter existed (hub#239). The filter narrows a valid section; it is not
            // a way to salvage a broken one.
            Err(e) => return (SectionStatus::Failed(e), 0),
        }
    } else if !same_hub && carries_a_foreign_numbering(&sql) {
        match drop_foreign_numbering(&sql, &scope) {
            Ok((sql, dropped)) => (sql, dropped, Some(ignore_reason::NUMBERING_NOT_PORTABLE)),
            Err(e) => return (SectionStatus::Failed(e), 0),
        }
    } else {
        (sql, 0, None)
    };
    if sql.trim().is_empty() {
        // Nothing survived the filter: the section was identity and nothing else. Reporting that
        // as `Applied` over zero rows would read as «I did what you asked».
        //
        // Sin filtro (`reason == None`) esto solo puede pasar con un fichero de datos en blanco,
        // que ya se atendió arriba con `Applied`/0 filas.
        return (
            SectionStatus::Ignored(reason.unwrap_or(ignore_reason::SETTINGS_NOT_PORTABLE).into()),
            discarded,
        );
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
    //
    // hub#842: y a esas claves se suma la que declara el SEED del módulo, porque hay una que la BD
    // no puede expresar como índice único. **Solo para un bundle AJENO.** Un hub que restaura su
    // propia copia no tiene nada que deduplicar: sus filas sembradas no viajaron nunca
    // (`export::is_module_seeded` las deja fuera), así que todo lo que trae el zip lo creó una
    // persona — incluido un segundo método `card` («Amex») que la clave del seed, aplicada aquí,
    // tiraría. Restaurar tu copia no puede perder nada; adoptar la plantilla de otro sí cede el
    // hueco que el módulo ya te había sembrado.
    let seed_declared = (!same_hub).then(|| rt.registry());
    let keys = natural_keys_for_sql(rt.db(), seed_declared, &sql).await;
    let sql = remap_section_ids(&sql, target_hub_id, &keys);
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
            SectionStatus::PartiallyApplied(
                reason.unwrap_or(ignore_reason::SETTINGS_NOT_PORTABLE).into(),
            ),
            discarded,
        ),
        Ok(_) => {
            // hub#464: the `hub_users` section also carries the profile and the preferences, each in
            // its own data file. They are hub-scoped (`(hub_id, user_id)`) and key off the users the
            // section just wrote, so they MUST follow the same identity gate and only run when the
            // main file succeeded. A failure here fails the whole section — half-restored identity
            // (users without their profiles) is worse than a clear `Failed`.
            if section == "hub_users" {
                for extra in ["data/hub_user_profile.sql", "data/hub_user_pref.sql"] {
                    if let Some(bytes) = files.get(extra) {
                        if let Err(e) = apply_identity_extra(rt, extra, bytes, target_hub_id, batch_id).await {
                            return (SectionStatus::Failed(e.to_string()), 0);
                        }
                    }
                }
            }
            (SectionStatus::Applied, 0)
        }
        // A section that failed applied nothing, so nothing was «discarded»: the filter's count
        // would be a number about rows that were never going to land anyway.
        Err(e) => (SectionStatus::Failed(e.to_string()), 0),
    }
}

/// Applies a hub-scoped identity data file (`hub_user_profile` / `hub_user_pref`) that follows the
/// `hub_users` section. Same pipeline as the main section — validate against its scope, swap the
/// `hub_id` placeholder for the target, remap ids — but these tables key on `(hub_id, user_id)`, so
/// there is no global-PK collision and the remap is a passthrough. Empty files are a no-op: a hub
/// with no profiles set exports nothing for them.
async fn apply_identity_extra(
    rt: &Runtime,
    path: &str,
    bytes: &[u8],
    target_hub_id: &str,
    batch_id: Option<&str>,
) -> Result<(), crate::RuntimeError> {
    let raw = std::str::from_utf8(bytes).map_err(|_| {
        crate::RuntimeError::Other(format!("{path} no es UTF-8 válido"))
    })?;
    let sql = raw.replace(crate::export::HUB_ID_PLACEHOLDER, target_hub_id);
    if sql.trim().is_empty() {
        return Ok(()); // sin filas: nada que hacer
    }
    let scope = crate::import_sql::scope_for_data_file(path)
        .ok_or_else(|| crate::RuntimeError::Other(format!("{path} no corresponde a ninguna sección conocida")))?;
    // Sin claves de seed (hub#842): estas son tablas de IDENTIDAD del core, que ningún módulo
    // siembra — y esta ruta solo corre para la copia del PROPIO hub (`identity_not_portable`).
    let keys = natural_keys_for_sql(rt.db(), None, &sql).await;
    let sql = remap_section_ids(&sql, target_hub_id, &keys);
    match batch_id {
        Some(batch) => {
            crate::reset::apply_tracked_into(rt, batch, target_hub_id, &sql, &scope).await?;
        }
        None => {
            crate::import_sql::apply(rt.db(), &sql, &scope).await?;
        }
    }
    Ok(())
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

/// Cheap pre-check: ¿esta sección menciona siquiera una tabla de numeración fiscal? Evita pagar la
/// validación completa en las secciones que no pueden traerla (que son casi todas).
fn carries_a_foreign_numbering(sql: &str) -> bool {
    crate::export::TEMPLATE_EXCLUDED_TABLES.iter().any(|t| sql.contains(t))
}

/// La mitad CONSUMIDORA de [`crate::export::TEMPLATE_EXCLUDED_TABLES`] (hub#753).
///
/// El productor ya deja fuera las series de facturación y su libro de números al exportar una
/// PLANTILLA (ADR-0266, hub#533), pero eso solo cubre lo que ESTE runtime produce a partir de ahora:
/// la plantilla oficial `Peluquería 1.0.4` se publicó antes y sigue trayendo `FAC` y `TCK` dentro,
/// los bundles son INMUTABLES una vez publicados (ADR-0121) y «Subir desde archivo» no pasa por
/// ningún gate. Es exactamente la misma lección que `keep_portable_settings` para los ajustes: un
/// gate en el productor no protege al que importa.
///
/// La pregunta no es «¿qué dice el bundle que es?» sino **«¿de quién es este hub?»** —igual que en
/// [`identity_not_portable`] y [`installation_bound_not_portable`]—, porque lo que hace peligrosas
/// a estas filas no es la etiqueta del manifest: una serie define **cómo se numera cada documento
/// que un negocio emite ante Hacienda** y `invoice_series_allocation` es el libro de números ya
/// entregados que el RD 1007/2023 exige sin huecos ni duplicados. De OTRA instalación, aquí, son
/// numeración ajena. El MISMO hub restaurando su copia sí las recupera: es su numeración volviendo
/// a su sitio (ADR-0113 §1), que es justo lo que `installation_bound_not_portable` hace con la
/// cadena VeriFactu.
///
/// Qué pasa con los números: **nada**. Las series del destino conservan su `id`, su `code`, su
/// `current_sequence` y su libro; las del bundle no se aplican, no se fusionan y no renumeran nada.
/// Un hub que aún no tenga series las crea por su propia puerta (ítem obligatorio de numeración de
/// la checklist — `invoice.setup` desde invoice#41, `invoice_series.setup` en su día —, ADR-0222)
/// — una tarea visible es infinitamente mejor que un falso «hecho» heredado de otro negocio.
///
/// Se valida ANTES y se filtra después, por el mismo motivo que en `keep_portable_settings`: una
/// sección inválida tiene que seguir fallando ENTERA y sin tocar la BD (hub#239).
fn drop_foreign_numbering(
    sql: &str,
    scope: &crate::import_sql::TableScope,
) -> std::result::Result<(String, u32), String> {
    let stmts = crate::import_sql::validate(sql, scope)?;
    let mut kept = String::with_capacity(sql.len());
    let mut dropped = 0u32;
    for stmt in &stmts {
        // Fail-closed: una sentencia que el filtro no sepa leer se DESCARTA. Aquí eso solo puede
        // pasar con formas que el export nunca emite, y dejar pasar lo ilegible es como no filtrar.
        let table = parse_insert(stmt).map(|p| p.table.to_ascii_lowercase());
        let excluded = table
            .as_deref()
            .map(|t| crate::export::TEMPLATE_EXCLUDED_TABLES.iter().any(|x| *x == t))
            .unwrap_or(false);
        if excluded {
            dropped += 1;
        } else {
            kept.push_str(stmt.trim());
            kept.push('\n');
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
///
/// `keys` son las CLAVES NATURALES que el esquema del hub DESTINO declara para cada tabla
/// (`natural_keys_for_sql`): con ellas la guarda deja de preguntar solo «¿está ya este id?» y
/// pregunta también «¿está ya esta fila?» — ver [`natural_key_guards`].
fn remap_section_ids(
    sql: &str,
    target_hub_id: &str,
    keys: &std::collections::HashMap<String, Vec<crate::export::NaturalKey>>,
) -> String {
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
        out.push_str(&rewrite_insert(stmt, &id_map, target_hub_id, keys));
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
fn rewrite_insert(
    stmt: &str,
    id_map: &std::collections::HashMap<String, String>,
    target_hub_id: &str,
    keys: &std::collections::HashMap<String, Vec<crate::export::NaturalKey>>,
) -> String {
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

    // 🔴 hub#497: `hub_user` y `hub_session` GANARON `hub_id NOT NULL`, y los bundles ya publicados
    // traen la forma vieja (sin la columna). Ese `INSERT` moriría ahora contra el `NOT NULL` y se
    // llevaría la sección Usuarios entera — exactamente el fallo de 2026-08-03, del revés. Así que
    // se INYECTA el hub destino cuando el bundle no lo trae: importar a una persona ES darla de
    // alta en el hub que importa, que es lo mismo que `__HUB_ID__` hace en todas las demás tablas.
    //
    // Se inyecta **solo el valor**, y no se toca nada más: el `id` se sigue conservando (derivarlo
    // rompería la idempotencia del re-import y dejaría colgadas las FKs de
    // `hub_user_profile`/`hub_user_pref` del mismo bundle, que apuntan a él) y la guarda sigue
    // yendo por `id` a secas. Por eso va aquí y no en la 1ª pasada de `remap_section_ids`: aquella
    // decide QUÉ ids se remapean, y estas filas siguen sin remapearse.
    //
    // La lista es explícita —no «toda tabla del core»— porque es un puente de compatibilidad con
    // una forma concreta de bundle: un bundle nuevo ya trae la columna y esta rama ni se mira.
    //
    // ⚠️ `hub_scoped` se decide con la lista de columnas que trae EL BUNDLE, capturada ANTES de
    // inyectar. Si la inyección la hiciera cierta, esta fila pasaría además a remapear su `id` y a
    // llevar guarda `(hub_id, id)` — y ninguna de las dos cosas puede cambiar aquí: el `id` es a
    // quien apuntan `hub_user_profile`/`hub_user_pref` del MISMO bundle (que no se remapean, porque
    // la 1ª pasada solo mapea filas que el bundle ya declaraba hub-scoped), así que derivarlo los
    // dejaría colgados; y cambiar la guarda rompería la idempotencia de un bundle ya importado.
    let bundle_says_hub_scoped = cols.iter().any(|c| c == "hub_id");
    let (cols, vals) = if matches!(table, "hub_user" | "hub_session") && !bundle_says_hub_scoped {
        let mut cols = cols;
        let mut vals = vals;
        cols.push("hub_id".to_string());
        vals.push(quote_string_literal(target_hub_id));
        (cols, vals)
    } else {
        (cols, vals)
    };

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
    let hub_scoped = bundle_says_hub_scoped;

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
    // …y, encadenada, una guarda por cada CLAVE NATURAL que el destino declara (hub#753).
    let guard = format!(
        "{guard}{}",
        natural_key_guards(table, &cols, &new_vals, keys.get(table).map(Vec::as_slice).unwrap_or(&[]))
    );
    format!("INSERT INTO {table} ({col_list}) SELECT {val_list}{guard};\n")
}

/// Guardas `AND NOT EXISTS (…)` por CLAVE NATURAL de la tabla destino (hub#753).
///
/// El problema que resuelven: el import compara por identidad TÉCNICA —`(hub_id, id)` con el `id`
/// derivado del hub destino— y esa identidad, por construcción, nunca coincide con la que el hub
/// destino se generó por su cuenta. Así que el guard pasa, el INSERT sale, y muere contra la clave
/// natural que la tabla sí declara: `duplicate key value violates unique constraint
/// "uq_invoice_series_hub_code"`, y con él la SECCIÓN ENTERA (el módulo se aplica en bloque). No es
/// un caso raro: `FAC`/`TCK` existen en cualquier hub, y hay ~80 índices únicos
/// `(hub_id, <clave natural>)` repartidos por los módulos.
///
/// Semántica: **si ya hay una fila equivalente, la del bundle se SALTA**. No se fusiona, no se
/// actualiza, no se renumera nada — el subconjunto SQL del import no admite `UPDATE` a propósito
/// (hub#239) y para una serie de facturación adoptar la fila ajena sería exactamente lo prohibido:
/// la correlatividad que exige VeriFactu es de la fila que YA está, con su `current_sequence` y su
/// libro de números. La que llega no la toca.
///
/// Una clave se descarta —no genera guarda— cuando no se puede evaluar con certeza sobre ESTA
/// fila: le falta alguna columna, alguna vale `NULL` (Postgres considera distintos los NULL, así
/// que esa fila no puede chocar por ese índice) o la fila cae FUERA del predicado de un índice
/// parcial. Descartar deja el comportamiento anterior; inventar una guarda saltaría filas buenas.
fn natural_key_guards(
    table: &str,
    cols: &[String],
    vals: &[String],
    keys: &[crate::export::NaturalKey],
) -> String {
    let value_of = |col: &str| -> Option<&String> { cols.iter().position(|c| c == col).map(|i| &vals[i]) };
    let mut out = String::new();
    for key in keys {
        // `None` en el valor de una condición = `columna IS NULL` (hub#576).
        let mut conds: Vec<(String, Option<String>)> = Vec::new();
        let mut usable = true;
        for col in &key.cols {
            match value_of(col) {
                // `NULL` no choca contra un índice único en Postgres (NULLS DISTINCT por
                // defecto)… salvo que el índice declare `NULLS NOT DISTINCT` (hub#576): ahí
                // NULL = NULL ES identidad y la guarda pregunta `columna IS NULL`.
                Some(v) if v.eq_ignore_ascii_case("NULL") => {
                    if key.nulls_not_distinct {
                        conds.push((col.clone(), None));
                    } else {
                        usable = false;
                    }
                }
                Some(v) => conds.push((col.clone(), Some(v.clone()))),
                None => usable = false,
            }
            if !usable {
                break;
            }
        }
        // Índice PARCIAL: la fila solo puede chocar si ella misma cumple el predicado — también
        // cuando la condición es `columna IS NULL` (la fila debe traer NULL ahí, hub#576).
        for (col, lit) in &key.predicate {
            if !usable {
                break;
            }
            match (value_of(col), lit) {
                (Some(v), Some(lit)) if v == lit => {
                    if !conds.iter().any(|(c, _)| c == col) {
                        conds.push((col.clone(), Some(lit.clone())));
                    }
                }
                (Some(v), None) if v.eq_ignore_ascii_case("NULL") => {
                    if !conds.iter().any(|(c, _)| c == col) {
                        conds.push((col.clone(), None));
                    }
                }
                _ => usable = false,
            }
        }
        // 🌱 hub#842: la clave que declara el SEED de un módulo no pregunta por cualquier fila
        // equivalente — pregunta por **la que sembró el módulo**. `(hub_id, type)` identifica la
        // forma de pago que el seed planta, pero no es única para el negocio: un salón cobra con
        // `Visa` y con `Amex`, las dos `card`. Sin este `created_by = 'system'`, la fila del
        // bundle cedería también ante el `Visa` del dueño, y adoptar una plantilla se comería una
        // forma de pago que nadie pidió tirar.
        //
        // El marcador es el mismo que ya usa `export::is_module_seeded` y lo pone
        // `seed::apply_module_seed` en TODA fila que siembra un módulo, así que no hay una segunda
        // convención que mantener. Si la tabla no tiene esa columna, la clave se descarta: la
        // guarda no puede nombrar una columna que no existe (es el error que tumbó la sección
        // Usuarios entera en producción el 2026-08-03) y sin ella no sabríamos distinguir lo
        // sembrado de lo del dueño, que es justo lo que esta clave necesita saber.
        if key.seeded_only {
            match value_of(SEEDED_ROW_MARKER_COLUMN) {
                Some(_) => conds.push((
                    SEEDED_ROW_MARKER_COLUMN.to_string(),
                    Some(quote_string_literal(SEEDED_ROW_MARKER)),
                )),
                None => usable = false,
            }
        }
        if !usable || conds.is_empty() {
            continue;
        }
        let where_clause = conds
            .iter()
            .map(|(c, v)| match v {
                Some(v) => format!("{} = {v}", quote_ident(c)),
                None => format!("{} IS NULL", quote_ident(c)),
            })
            .collect::<Vec<_>>()
            .join(" AND ");
        out.push_str(&format!(" AND NOT EXISTS (SELECT 1 FROM {table} WHERE {where_clause})"));
    }
    out
}

/// La columna y el valor con que `seed::apply_module_seed` firma TODA fila que siembra un módulo
/// (`created_by = 'system'`, ver [`crate::export::is_module_seeded`]) — el marcador que separa lo
/// que planta el módulo de lo que crea una persona (hub#842).
const SEEDED_ROW_MARKER_COLUMN: &str = "created_by";
const SEEDED_ROW_MARKER: &str = "system";

/// Claves naturales de cada tabla que toca `sql`, leídas del catálogo del hub DESTINO.
///
/// Se pregunta a la BD de destino, no al bundle: lo que decide si un INSERT choca es el índice que
/// está creado AQUÍ. Una tabla que no se pueda leer devuelve la lista vacía y su fila conserva el
/// comportamiento anterior (best-effort, como el resto del import).
///
/// A ellas se suman las que declara el SEED del módulo dueño de la tabla (`seed_declared`,
/// hub#842) — `None` cuando el bundle es la copia de ESTE MISMO hub, que no tiene nada que
/// deduplicar.
async fn natural_keys_for_sql(
    db: &dyn erplora_db::DatabaseAdapter,
    seed_declared: Option<&crate::Registry>,
    sql: &str,
) -> std::collections::HashMap<String, Vec<crate::export::NaturalKey>> {
    let mut out: std::collections::HashMap<String, Vec<crate::export::NaturalKey>> =
        std::collections::HashMap::new();
    let Ok(stmts) = crate::import_sql::split_statements(sql) else { return out };
    for stmt in &stmts {
        let Some(parsed) = parse_insert(stmt) else { continue };
        if out.contains_key(parsed.table) {
            continue;
        }
        let mut keys = crate::export::natural_keys(db, parsed.table).await;
        if let Some(registry) = seed_declared {
            keys.extend(registry.seed_natural_keys_for(parsed.table));
        }
        out.insert(parsed.table.to_string(), keys);
    }
    out
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
            batch_id: None,
        };
        let json = serde_json::to_string(&r).unwrap();
        let back: ImportReport = serde_json::from_str(&json).unwrap();
        assert_eq!(r, back);

        // `batch_id` NO viaja por el cable (hub#763): el contrato del shell son las `sections` (más
        // lo que el servidor añade encima), y un servidor que no conozca el campo tiene que poder
        // hacer round-trip igual. El cliente lo lee del informe PERSISTIDO, no de aquí.
        assert!(!json.contains("batch_id"), "el batch_id no se serializa: {json}");
    }

    /// Y el lote sí acompaña al informe DENTRO del proceso, que es como el motor se lo pasa al
    /// servidor para que haga el UPSERT del informe extendido sobre el mismo `batch_id`.
    #[test]
    fn the_batch_travels_in_memory_but_not_on_the_wire() {
        let r = ImportReport { sections: Vec::new(), batch_id: Some("b-1".into()) };

        let back: ImportReport = serde_json::from_str(&serde_json::to_string(&r).unwrap()).unwrap();

        assert_eq!(r.batch_id.as_deref(), Some("b-1"));
        assert_eq!(back.batch_id, None, "al deserializar no se inventa un lote que no vino");
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
            capability_grants: Default::default(),
            flows: Vec::new(),
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

    /// A destination registry where one module is installed, declaring (or not) that its data
    /// belongs to the installation that produced it.
    ///
    /// The manifest is built through `serde` on purpose: what the engine asks about must be the
    /// field a real `module.json` writes, not a struct literal a rename could leave behind.
    fn registry_with(module_id: &str, bound: bool) -> crate::Registry {
        let mut registry = crate::Registry::new();
        registry.installed.push(
            serde_json::from_str(&format!(
                r#"{{ "id": "{module_id}", "name": "{module_id}", "version": "1.0.0",
                      "installation_bound_data": {bound} }}"#
            ))
            .expect("manifest parses"),
        );
        registry
    }

    /// hub#380 — the engine asks the INSTALLED MANIFEST, and never names a module.
    ///
    /// The literal `modules/verifactu` made a Spanish regime part of a generic engine; TicketBai
    /// chains its records the same way and NF525 has the same integrity requirement, so the next
    /// two regimes would each have been one more `||` in the core. `ticketbai` is used here
    /// precisely because nothing in the runtime has ever heard of it: what discards its section is
    /// the flag, not the name.
    #[test]
    fn installation_bound_data_is_declared_by_the_module_not_named_by_the_core() {
        let bound = registry_with("ticketbai", true);
        assert_eq!(
            installation_bound_not_portable(&bound, &manifest_from("h1"), "modules/ticketbai", "h2")
                .as_deref(),
            Some(ignore_reason::INSTALLATION_BOUND_DATA),
            "another installation's bound records must not be applied here"
        );
        // The SAME installation restoring its own backup resumes its own chain (ADR-0113 §1).
        assert_eq!(
            installation_bound_not_portable(&bound, &manifest_from("h1"), "modules/ticketbai", "h1"),
            None,
            "a hub restoring its own backup gets its own records back"
        );
        // A module that declares nothing travels: the shape of every published manifest today.
        let portable = registry_with("inventory", false);
        assert_eq!(
            installation_bound_not_portable(
                &portable,
                &manifest_from("h1"),
                "modules/inventory",
                "h2"
            ),
            None
        );
        // And this gate is about MODULE sections only; the others have their own.
        assert_eq!(
            installation_bound_not_portable(&bound, &manifest_from("h1"), "hub_settings", "h2"),
            None
        );
    }

    /// 🔴 Compatibility (hub#380): the PUBLISHED `verifactu` predates the flag, so asking its
    /// manifest answers «portable» — and the fiscal chain of another installation would land here,
    /// which is exactly what ADR-0202 §4.2 forbids. Until the module is republished declaring the
    /// flag, the name keeps it bound.
    ///
    /// A fallback, not the rule: it only ADDS to what the manifest says and disappears with the
    /// republication. Nothing else in the engine may grow a second name.
    #[test]
    fn verifactu_stays_bound_while_its_published_manifest_has_no_flag() {
        let published = registry_with("verifactu", false);
        assert_eq!(
            installation_bound_not_portable(
                &published,
                &manifest_from("h1"),
                "modules/verifactu",
                "h2"
            )
            .as_deref(),
            Some(ignore_reason::INSTALLATION_BOUND_DATA),
            "the VeriFactu chain never travels across installations (ADR-0202 §4.2)"
        );
        assert_eq!(
            installation_bound_not_portable(
                &published,
                &manifest_from("h1"),
                "modules/verifactu",
                "h1"
            ),
            None,
            "the same hub restoring its own backup resumes its own chain"
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
        let out = remap_section_ids(sql, "h2", &Default::default());
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
        assert_eq!(out, remap_section_ids(sql, "h2", &Default::default()), "el remap debe ser determinista");
    }

    /// 🔴 El SQL que rompía la sección **Usuarios** en producción (2026-08-03):
    /// `reset: aplicar sentencia: sqlx: … column "hub_id" does not exist`.
    ///
    /// `rewrite_insert` metía `"hub_id" = <destino>` en la guarda de TODA tabla con `id`, y
    /// `hub_user` no tenía esa columna, así que la sección Usuarios entera moría con
    /// `column "hub_id" does not exist` (producción, 2026-08-03).
    ///
    /// 🔴 **Y desde hub#497 sí la tiene, `NOT NULL`** — lo que da la vuelta al problema: un bundle
    /// **ya publicado** (los cuatro blueprints) trae la forma VIEJA, sin `hub_id`, y su `INSERT`
    /// moriría ahora contra el `NOT NULL`, perdiendo otra vez la sección entera. Así que el import
    /// **inyecta** el hub destino cuando el bundle no lo trae: importar a una persona ES darla de
    /// alta en el hub que importa. Este es el test que lo sujeta, con la forma REAL del
    /// `data/hub_users.sql` del blueprint `restaurante` publicado.
    #[test]
    fn un_bundle_viejo_sin_hub_id_lo_recibe_del_hub_destino() {
        let sql = "INSERT INTO hub_user (\"cloud_user_id\", \"created_at\", \"id\", \"name\", \"role\") \
                   SELECT NULL, '2026-01-01T00:00:00+00:00', 'bp-user-manager-000000000000000', 'Manager', 'manager' \
                   WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE id = 'bp-user-manager-000000000000000');";
        let out = remap_section_ids(sql, "56f2bbe7-792e-44d3-adfe-c18891cfc925", &Default::default());

        assert!(
            out.contains("\"hub_id\"") && out.contains("'56f2bbe7-792e-44d3-adfe-c18891cfc925'"),
            "la fila del bundle viejo tiene que salir con el hub DESTINO o el NOT NULL la tumba:\n{out}"
        );
        // Su id se CONSERVA. Derivarlo por hub rompería la idempotencia del re-import de un bundle
        // ya importado, y las FKs de `hub_user_profile`/`hub_user_pref` del mismo bundle apuntan a
        // él: el remap solo alcanza a las filas que el bundle YA declaraba hub-scoped.
        assert!(
            out.contains("'bp-user-manager-000000000000000'"),
            "el id de la persona se conserva:\n{out}"
        );
        // Y la guarda sigue yendo por `id` a secas: la que el bundle traía, sin inventar columnas.
        assert!(
            out.contains("WHERE id = 'bp-user-manager-000000000000000'"),
            "la guarda de idempotencia no cambia:\n{out}"
        );
    }

    /// Un bundle NUEVO ya trae `hub_id` (el export vuelca `SELECT *`), y entonces manda el camino
    /// de siempre: `__HUB_ID__` → destino, sin que la inyección se meta por medio.
    #[test]
    fn un_bundle_nuevo_ya_trae_su_hub_id_y_no_se_duplica() {
        let sql = "INSERT INTO hub_user (\"hub_id\", \"id\", \"name\", \"role\") \
                   SELECT '__HUB_ID__', 'u-1', 'Ana', 'admin' \
                   WHERE NOT EXISTS (SELECT 1 FROM hub_user WHERE id = 'u-1');";
        let out = remap_section_ids(sql, "hub-destino", &Default::default());

        assert_eq!(
            out.matches("\"hub_id\"").count(),
            2,
            "una en la lista de columnas y una en la guarda — ni una tercera inyectada:\n{out}"
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
        let out = remap_section_ids(sql, "h2", &Default::default());

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
        let out = remap_section_ids(sql, "h2", &Default::default());

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

    // ── Guarda por CLAVE NATURAL (hub#753) ──────────────────────────────────────────────────

    fn keys_for(
        table: &str,
        keys: Vec<crate::export::NaturalKey>,
    ) -> std::collections::HashMap<String, Vec<crate::export::NaturalKey>> {
        std::collections::HashMap::from([(table.to_string(), keys)])
    }

    /// Una fila del bundle se pregunta por sus DOS identidades: la técnica (`hub_id`, `id`
    /// derivado) y la natural que el destino declara (`(hub_id, code)` con `is_deleted = 0`).
    /// Preguntar solo por la técnica es lo que dejaba salir el INSERT contra un `FAC` que ya estaba.
    #[test]
    fn la_guarda_pregunta_tambien_por_la_clave_natural() {
        let sql = "INSERT INTO invoice_series_series (\"id\", \"hub_id\", \"code\", \"is_deleted\") \
                   SELECT 'src-fac', 'h2', 'FAC', 0 \
                   WHERE NOT EXISTS (SELECT 1 FROM invoice_series_series WHERE id = 'src-fac');";
        let keys = keys_for(
            "invoice_series_series",
            vec![crate::export::NaturalKey {
                cols: vec!["hub_id".into(), "code".into()],
                predicate: vec![("is_deleted".into(), Some("0".into()))],
                nulls_not_distinct: false,
            seeded_only: false,
            }],
        );
        let out = remap_section_ids(sql, "h2", &keys);

        assert!(out.contains("\"hub_id\" = 'h2' AND id = "), "sigue la guarda técnica: {out}");
        assert!(
            out.contains("AND NOT EXISTS (SELECT 1 FROM invoice_series_series WHERE \"hub_id\" = 'h2' AND \"code\" = 'FAC' AND \"is_deleted\" = 0)"),
            "falta la guarda por clave natural (con el predicado del índice parcial): {out}"
        );
        // Y lo que se emite sigue pasando el subconjunto SQL del import (hub#239).
        let scope = crate::import_sql::scope_for_data_file("data/invoice_series.sql").unwrap();
        crate::import_sql::validate(&out, &scope).expect("la guarda encadenada es SQL admitido");
    }

    /// Una clave que no se puede evaluar sobre ESTA fila no genera guarda: mejor el comportamiento
    /// de antes que una guarda inventada que salte filas legítimas en silencio.
    ///   · columna ausente de la fila,
    ///   · valor `NULL` (Postgres considera distintos los NULL: esa fila no choca por ese índice),
    ///   · fila FUERA del predicado de un índice parcial (una serie borrada no reserva su código).
    #[test]
    fn una_clave_natural_que_no_aplica_a_la_fila_no_genera_guarda() {
        let cols = vec!["id".to_string(), "hub_id".to_string(), "code".to_string(), "is_deleted".to_string()];
        let vals = vec!["'x'".to_string(), "'h2'".to_string(), "NULL".to_string(), "1".to_string()];
        let nk = |c: Vec<&str>, p: Vec<(&str, &str)>| crate::export::NaturalKey {
            cols: c.into_iter().map(str::to_string).collect(),
            predicate: p.into_iter().map(|(a, b)| (a.to_string(), Some(b.to_string()))).collect(),
            nulls_not_distinct: false,
            seeded_only: false,
        };

        for (caso, key) in [
            ("columna ausente", nk(vec!["hub_id", "sku"], vec![])),
            ("valor NULL", nk(vec!["hub_id", "code"], vec![])),
            ("fuera del predicado parcial", nk(vec!["hub_id"], vec![("is_deleted", "0")])),
        ] {
            let out = natural_key_guards("t", &cols, &vals, &[key]);
            assert!(out.is_empty(), "{caso}: no debía generar guarda, salió `{out}`");
        }
    }

    // ── NULLS NOT DISTINCT + `IS NULL` predicate (hub#576) ──────────────────────────────────

    /// The shape `taxes_rule` declares: a partial unique index over root rules
    /// (`WHERE parent_id IS NULL AND is_deleted = 0`) with `NULLS NOT DISTINCT`, because
    /// `region_code NULL` (whole country) and `valid_from NULL` (since forever) ARE identity.
    /// A NULL row value must guard with `col IS NULL` instead of silencing the key — otherwise
    /// the INSERT sails past the guard and dies against the index, taking the section with it.
    #[test]
    fn a_nulls_not_distinct_key_guards_null_values_with_is_null() {
        let cols: Vec<String> = ["id", "hub_id", "country_code", "tax_category_key", "region_code", "valid_from", "parent_id", "is_deleted"]
            .into_iter().map(str::to_string).collect();
        let vals: Vec<String> = ["'r1'", "'h2'", "'ES'", "'product.generic'", "NULL", "'2012-09-01'", "NULL", "0"]
            .into_iter().map(str::to_string).collect();
        let key = crate::export::NaturalKey {
            cols: ["hub_id", "country_code", "tax_category_key", "region_code", "valid_from"]
                .into_iter().map(str::to_string).collect(),
            predicate: vec![("parent_id".into(), None), ("is_deleted".into(), Some("0".into()))],
            nulls_not_distinct: true,
            seeded_only: false,
        };
        let out = natural_key_guards("taxes_rule", &cols, &vals, &[key]);
        assert_eq!(
            out,
            " AND NOT EXISTS (SELECT 1 FROM taxes_rule WHERE \"hub_id\" = 'h2' AND \"country_code\" = 'ES' \
             AND \"tax_category_key\" = 'product.generic' AND \"region_code\" IS NULL \
             AND \"valid_from\" = '2012-09-01' AND \"parent_id\" IS NULL AND \"is_deleted\" = 0)",
            "a NULL key value under NULLS NOT DISTINCT must guard with IS NULL"
        );
    }

    /// A COMPONENT row (`parent_id` set) falls OUTSIDE the `parent_id IS NULL` predicate: the
    /// index cannot reject it, so no guard is emitted — inventing one would silently skip
    /// legitimate components.
    #[test]
    fn a_row_outside_an_is_null_predicate_gets_no_guard() {
        let cols: Vec<String> = ["id", "hub_id", "country_code", "tax_category_key", "region_code", "valid_from", "parent_id", "is_deleted"]
            .into_iter().map(str::to_string).collect();
        let vals: Vec<String> = ["'c1'", "'h2'", "'ES'", "'product.generic'", "'ES-CN'", "NULL", "'root-igic'", "0"]
            .into_iter().map(str::to_string).collect();
        let key = crate::export::NaturalKey {
            cols: ["hub_id", "country_code", "tax_category_key", "region_code", "valid_from"]
                .into_iter().map(str::to_string).collect(),
            predicate: vec![("parent_id".into(), None), ("is_deleted".into(), Some("0".into()))],
            nulls_not_distinct: true,
            seeded_only: false,
        };
        let out = natural_key_guards("taxes_rule", &cols, &vals, &[key]);
        assert!(out.is_empty(), "a component row cannot collide on the roots-only index: `{out}`");
    }

    /// Under the DEFAULT (`NULLS DISTINCT`) nothing changes: a NULL key value still cannot
    /// collide, so the key is discarded for that row — hub#753 behavior, verbatim.
    #[test]
    fn a_nulls_distinct_key_still_discards_null_values() {
        let cols: Vec<String> = ["id", "hub_id", "code"].into_iter().map(str::to_string).collect();
        let vals: Vec<String> = ["'x'", "'h2'", "NULL"].into_iter().map(str::to_string).collect();
        let key = crate::export::NaturalKey {
            cols: vec!["hub_id".into(), "code".into()],
            predicate: vec![],
            nulls_not_distinct: false,
            seeded_only: false,
        };
        let out = natural_key_guards("t", &cols, &vals, &[key]);
        assert!(out.is_empty(), "NULLS DISTINCT: a NULL value must keep discarding the key, got `{out}`");
    }

    // ── Claves declaradas por el SEED del módulo (hub#842) ──────────────────────────────────

    /// Columnas y valores de una forma de pago del bundle `peluqueria` («Efectivo», `cash`).
    fn fila_forma_de_pago(nombre: &str, kind: &str, autor: &str) -> (Vec<String>, Vec<String>) {
        let cols = ["id", "hub_id", "name", "type", "is_deleted", "created_by"]
            .into_iter()
            .map(str::to_string)
            .collect();
        let vals = vec![
            "'pm-1'".to_string(),
            "'h2'".to_string(),
            format!("'{nombre}'"),
            format!("'{kind}'"),
            "0".to_string(),
            format!("'{autor}'"),
        ];
        (cols, vals)
    }

    /// La clave del seed (`hub_id, type, is_deleted`) pregunta por la fila que **sembró el
    /// módulo**, no por cualquier equivalente: sin `created_by = 'system'`, la «Tarjeta» del bundle
    /// cedería también ante el «Visa» que creó el dueño.
    #[test]
    fn una_clave_de_seed_solo_pregunta_por_la_fila_que_sembro_el_modulo() {
        let (cols, vals) = fila_forma_de_pago("Efectivo", "cash", "u-owner");
        let key = crate::export::NaturalKey {
            cols: vec!["hub_id".into(), "type".into(), "is_deleted".into()],
            predicate: vec![],
            nulls_not_distinct: false,
            seeded_only: true,
        };
        let out = natural_key_guards("sales_payment_method", &cols, &vals, &[key]);
        assert_eq!(
            out,
            " AND NOT EXISTS (SELECT 1 FROM sales_payment_method WHERE \"hub_id\" = 'h2' \
             AND \"type\" = 'cash' AND \"is_deleted\" = 0 AND \"created_by\" = 'system')",
            "la guarda del seed tiene que acotarse a lo sembrado por el módulo"
        );
        // …y encadenada a la guarda por `id`, como la emite `rewrite_insert`, sigue siendo SQL que
        // el subconjunto del import admite (hub#239): una guarda que no se pudiera ejecutar
        // tumbaría la sección entera.
        let scope = crate::import_sql::scope_for_data_file("data/sales.sql").unwrap();
        crate::import_sql::validate(
            &format!(
                "INSERT INTO sales_payment_method (\"id\") SELECT 'x' \
                 WHERE NOT EXISTS (SELECT 1 FROM sales_payment_method WHERE \"hub_id\" = 'h2' AND id = 'x'){out};"
            ),
            &scope,
        )
        .expect("la guarda del seed es SQL admitido por el subconjunto del import");
    }

    /// Una tabla sin `created_by` no puede distinguir lo sembrado de lo del dueño, y la guarda no
    /// puede nombrar una columna que no existe: la clave se descarta y esa tabla se comporta como
    /// antes de hub#842.
    #[test]
    fn una_clave_de_seed_se_descarta_si_la_tabla_no_marca_quien_creo_la_fila() {
        let cols: Vec<String> = ["id", "hub_id", "type"].into_iter().map(str::to_string).collect();
        let vals: Vec<String> = ["'x'", "'h2'", "'cash'"].into_iter().map(str::to_string).collect();
        let key = crate::export::NaturalKey {
            cols: vec!["hub_id".into(), "type".into()],
            predicate: vec![],
            nulls_not_distinct: false,
            seeded_only: true,
        };
        assert!(
            natural_key_guards("t", &cols, &vals, &[key]).is_empty(),
            "sin `created_by` la clave del seed no se puede evaluar"
        );
    }

    /// Una clave del CATÁLOGO (índice único) sigue preguntando por CUALQUIER fila equivalente: es
    /// el índice quien rechazaría el INSERT, le dé igual quién creó la fila (hub#753, intacto).
    #[test]
    fn una_clave_del_catalogo_no_se_acota_a_lo_sembrado() {
        let (cols, vals) = fila_forma_de_pago("Efectivo", "cash", "u-owner");
        let key = crate::export::NaturalKey {
            cols: vec!["hub_id".into(), "type".into()],
            predicate: vec![],
            nulls_not_distinct: false,
            seeded_only: false,
        };
        let out = natural_key_guards("sales_payment_method", &cols, &vals, &[key]);
        assert!(
            !out.contains("created_by"),
            "una clave de índice único no mira quién creó la fila: `{out}`"
        );
    }
}
