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
    /// Falló; el motivo es legible para el informe de la UI. El resto del import continuó.
    Failed(String),
}

/// Resultado por sección (`hub_users`, `hub_settings`, `fiscal`, `media`, `modules/<id>`).
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct SectionResult {
    pub section: String,
    pub status: SectionStatus,
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
    let mut report = ImportReport::default();
    for section in &manifest.sections {
        let status = apply_section(rt, section, files, selection, target_hub_id).await;
        report.sections.push(SectionResult { section: section.clone(), status });
    }
    Ok(report)
}

/// Aplica una sección; cualquier fallo queda contenido en su `SectionStatus::Failed`.
async fn apply_section(
    rt: &Runtime,
    section: &str,
    files: &BTreeMap<String, Vec<u8>>,
    selection: &ImportSelection,
    target_hub_id: &str,
) -> SectionStatus {
    // ¿Está marcada en el formulario de import?
    let (selected, path): (bool, Option<String>) = match section {
        "hub_users" => (selection.users, Some("data/hub_users.sql".into())),
        "hub_settings" => (selection.settings, Some("data/hub_settings.sql".into())),
        // fiscal/media las materializa el SERVER (certificado por su endpoint, imágenes por el
        // gestor media); a nivel runtime se registran como Skipped y el server sobrescribe.
        "fiscal" => (false, None),
        "media" => (false, None),
        s => {
            if let Some(id) = s.strip_prefix("modules/") {
                (selection.modules.iter().any(|m| m == id), Some(format!("data/{id}.sql")))
            } else {
                (false, None)
            }
        }
    };
    if !selected {
        return SectionStatus::Skipped;
    }

    // Un módulo del manifest debe estar instalado en destino (lo instala el server ANTES).
    if let Some(id) = section.strip_prefix("modules/") {
        if !rt.registry().is_installed(id) {
            return SectionStatus::Failed(format!("módulo `{id}` no instalado en el hub destino"));
        }
    }

    let Some(path) = path else { return SectionStatus::Skipped };
    let Some(bytes) = files.get(&path) else {
        return SectionStatus::Failed(format!("fichero {path} ausente del bundle"));
    };
    let sql = match std::str::from_utf8(bytes) {
        Ok(s) => s.replace(crate::export::HUB_ID_PLACEHOLDER, target_hub_id),
        Err(_) => return SectionStatus::Failed(format!("{path} no es UTF-8 válido")),
    };
    if sql.trim().is_empty() {
        return SectionStatus::Applied; // sección presente pero sin filas: nada que hacer
    }
    match crate::seed::apply(rt.db(), &sql).await {
        Ok(_) => SectionStatus::Applied,
        Err(e) => SectionStatus::Failed(e.to_string()),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El informe hace round-trip serde: es el contrato JSON que la UI del shell pinta.
    #[test]
    fn report_serde_round_trip() {
        let r = ImportReport {
            sections: vec![
                SectionResult { section: "modules/taxes".into(), status: SectionStatus::Applied },
                SectionResult { section: "hub_users".into(), status: SectionStatus::Skipped },
                SectionResult {
                    section: "modules/inventory".into(),
                    status: SectionStatus::Failed("módulo no instalado".into()),
                },
            ],
        };
        let json = serde_json::to_string(&r).unwrap();
        let back: ImportReport = serde_json::from_str(&json).unwrap();
        assert_eq!(r, back);
    }
}
