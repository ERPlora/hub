//! Capabilities de módulo (ADR-0079): permisos **módulo→host** que el USUARIO concede.
//!
//! Un módulo declara en `module.json` (bloque `capabilities`) qué primitivos del host necesita
//! (`network`/`certificate`/`printer`/`notify`). El core POSEE esos primitivos; el dueño/admin los
//! concede explícitamente en Ajustes → Permisos (estilo permisos de Android) y el host media la
//! operación (el módulo nunca recibe la clave privada). Grants persistidos en la tabla de sistema
//! `_module_capability_grants` (migración v5), **default-deny**.
//!
//! Enforcement: el dispatcher llama [`enforce`] antes de ejecutar un handler **nativo** (ADR-0009:
//! donde vive el acceso real a certificado/red, p.ej. verifactu→AEAT). Si el módulo declara
//! capabilities no concedidas → [`RuntimeError::CapabilityDenied`] y el handler nunca corre (el
//! certificado no se lee y la red no se toca). Es ortogonal al RBAC de usuario
//! (`permissions`/`role_permissions`), que se chequea aparte en `permissions::check`.
use std::collections::{BTreeMap, HashSet};

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::manifest::CapabilityKind;
use crate::registry::{now_rfc3339, Registry};

/// Capabilities **concedidas** (`granted=1`) a un módulo en un hub.
pub async fn granted_set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    module_id: &str,
) -> Result<HashSet<String>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    let res = db
        .query(
            "SELECT capability FROM _module_capability_grants \
             WHERE hub_id = :hub_id AND module_id = :module_id AND granted = 1",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .iter()
        .filter_map(|r| r["capability"].as_str().map(|s| s.to_string()))
        .collect())
}

/// Everything this hub has **granted** (`granted = 1`), module by module — what a backup has to
/// carry so that restoring it does not come back with every module denied (hub#473).
///
/// Scoped by `hub_id` like every read of this table: the database is SHARED (`tenancy.md`), so a
/// query without it would put the neighbour's approvals inside this hub's backup.
///
/// A **revoked** grant (`granted = 0`) is deliberately not reported: it is indistinguishable from
/// the default state of a hub that was never asked (default-deny), so carrying it would add a row
/// that says nothing. `BTreeMap`/sorted values because this feeds a manifest — two exports of the
/// same hub must produce byte-identical JSON.
pub async fn granted_by_module(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
) -> Result<BTreeMap<String, Vec<String>>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT module_id, capability FROM _module_capability_grants \
             WHERE hub_id = :hub_id AND granted = 1 ORDER BY module_id, capability",
            &p,
        )
        .await?;
    let mut out: BTreeMap<String, Vec<String>> = BTreeMap::new();
    for r in &res.rows {
        let (Some(module), Some(cap)) = (r["module_id"].as_str(), r["capability"].as_str()) else {
            continue;
        };
        out.entry(module.to_string()).or_default().push(cap.to_string());
    }
    Ok(out)
}

/// What the hub did with the capability grants a bundle asked to restore (hub#473).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct PreGrant {
    /// `(module_id, capability)` pairs that are granted now.
    pub granted: Vec<(String, String)>,
    /// Pairs the hub **refused**: an unknown capability, or one the module INSTALLED HERE does not
    /// declare (including «the module is not installed at all», which declares nothing). Kept by
    /// name and not merely counted, so a caller that wants to say *which* ones has them.
    pub refused: Vec<(String, String)>,
}

/// Re-grant the capabilities a **backup** carried, through the same door the administrator's
/// switch uses (hub#473). The mirror of [`granted_by_module`].
///
/// Three properties, each one deliberate and each one the reason this is not a `data/*.sql`:
///
/// - **It is not a second door.** Every pair goes through [`set_grant`], so a file gets exactly
///   the guards a click gets: an unknown capability and one the installed module does not DECLARE
///   are refused. The authority is the `module.json` that is installed HERE — a module updated to
///   drop `network` does not get it back because an old backup remembers it.
/// - **It never revokes.** The set is additive: a capability this hub granted after the backup was
///   taken stays granted. Mirroring the bundle exactly would let restoring an old copy switch off a
///   permission the owner granted later, and the module would stop working with nobody deciding it.
/// - **It is not all-or-nothing.** A refused pair is skipped and reported; the rest still land. A
///   restore whose kitchen module failed to install must still let the till sign its invoices.
///
/// Who may CALL this is a separate question, and the import answers it: only the hub restoring its
/// own copy (`is_same_hub`). A grant is an approval of THIS deployment's owner over the host's own
/// primitives — the certificate, the network — so a downloaded template must not be able to make
/// one, however well-formed it is.
///
/// A policy refusal lands in [`PreGrant::refused`]; a database failure propagates, because «the row
/// could not be written» must never read as «this hub said no».
pub async fn pre_grant(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    grants: &BTreeMap<String, Vec<String>>,
    by: &str,
) -> Result<PreGrant> {
    let mut out = PreGrant::default();
    for (module_id, capabilities) in grants {
        let declared = requested(registry, module_id);
        let mut seen: HashSet<&str> = HashSet::new();
        for capability in capabilities {
            let capability = capability.trim();
            if !seen.insert(capability) {
                continue; // a bundle naming the same capability twice grants it once
            }
            // Asked BEFORE writing, with the same two questions `set_grant` asks — so a refusal is
            // policy and never gets confused with the database failing underneath.
            let known = crate::manifest::CapabilityKind::parse(capability);
            let pair = (module_id.clone(), capability.to_string());
            match known {
                Some(kind) if declared.contains(&kind) => {
                    set_grant(db, registry, hub_id, module_id, capability, true, by).await?;
                    out.granted.push(pair);
                }
                _ => out.refused.push(pair),
            }
        }
    }
    Ok(out)
}

/// Capabilities que el módulo **declara** necesitar (del manifest en el `Registry`).
fn requested(registry: &Registry, module_id: &str) -> Vec<CapabilityKind> {
    registry
        .installed
        .iter()
        .find(|m| m.id == module_id)
        .map(|m| m.requested_capabilities())
        .unwrap_or_default()
}

/// **Gate** (default-deny): exige que TODAS las capabilities declaradas por el módulo estén
/// concedidas. La llama el dispatcher antes de un handler nativo (cert/red). Si el módulo no
/// declara ninguna, no hay nada que comprobar (los módulos puro-SQL/WASM pasan sin fricción).
pub async fn enforce(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    module_id: &str,
    hub_id: &str,
) -> Result<()> {
    let required = requested(registry, module_id);
    if required.is_empty() {
        return Ok(());
    }
    let granted = granted_set(db, hub_id, module_id).await?;
    for cap in required {
        if !granted.contains(cap.as_str()) {
            return Err(RuntimeError::CapabilityDenied {
                module: module_id.to_string(),
                capability: cap.as_str().to_string(),
            });
        }
    }
    Ok(())
}

/// **Gate de UNA capability concreta** (default-deny): el módulo tiene que **declararla** en su
/// `module.json` **y** tenerla **concedida**. Es el gate que se aplica en el punto donde el host
/// ejerce el primitivo, no donde arranca el módulo.
///
/// Existe por hub#240: `enforce` exige *todas* las capabilities declaradas y solo se llamaba antes
/// de un handler **nativo**, así que el camino `handler WASM → evento `*.reminder.due` → outbox →
/// listener-host de `host.notify`` llegaba a mandar email/SMS/WhatsApp sin pasar por ningún gate.
/// Con esto, emitir un recordatorio (y entregarlo) exige `notify` declarada + concedida.
pub async fn require(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    module_id: &str,
    hub_id: &str,
    kind: CapabilityKind,
) -> Result<()> {
    let denied = || RuntimeError::CapabilityDenied {
        module: module_id.to_string(),
        capability: kind.as_str().to_string(),
    };
    if !requested(registry, module_id).contains(&kind) {
        // No la declara: no se le puede conceder, luego no puede ejercerla.
        return Err(denied());
    }
    if !granted_set(db, hub_id, module_id).await?.contains(kind.as_str()) {
        return Err(denied());
    }
    Ok(())
}

/// Capabilities **declaradas** por un módulo con su estado de grant (para
/// `GET /api/modules/{id}/capabilities`). Cada entrada: `(capability_canónica, granted)`.
pub async fn list_for_module(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    module_id: &str,
) -> Result<Vec<(String, bool)>> {
    let granted = granted_set(db, hub_id, module_id).await?;
    Ok(requested(registry, module_id)
        .into_iter()
        .map(|c| {
            let id = c.as_str().to_string();
            let g = granted.contains(&id);
            (id, g)
        })
        .collect())
}

/// Concede/revoca una capability para un módulo (upsert). Rechaza capabilities desconocidas y las
/// que el módulo NO declara (no se concede lo que no se pide). El gate de rol (admin) lo aplica el
/// server. `by` = `hub_user:<id>` que hace el cambio. Idéntico SQLite/Postgres (ERPlora SQL).
pub async fn set_grant(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    module_id: &str,
    capability: &str,
    granted: bool,
    by: &str,
) -> Result<()> {
    let kind = CapabilityKind::parse(capability)
        .ok_or_else(|| RuntimeError::Other(format!("capability desconocida: {capability}")))?;
    if !requested(registry, module_id).contains(&kind) {
        return Err(RuntimeError::Other(format!(
            "el módulo `{module_id}` no solicita la capability `{capability}`"
        )));
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    p.insert("capability".into(), json!(capability));
    p.insert("granted".into(), json!(if granted { 1 } else { 0 }));
    p.insert("granted_at".into(), json!(now_rfc3339()));
    p.insert("granted_by".into(), json!(by));
    db.execute(
        "INSERT INTO _module_capability_grants \
           (hub_id, module_id, capability, granted, granted_at, granted_by) \
         VALUES (:hub_id, :module_id, :capability, :granted, :granted_at, :granted_by) \
         ON CONFLICT (hub_id, module_id, capability) DO UPDATE SET \
           granted = excluded.granted, granted_at = excluded.granted_at, granted_by = excluded.granted_by",
        &p,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::manifest::Manifest;
    use erplora_db::{testutil::fresh_db, PgAdapter};

    async fn db_with_migrations() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        // hub_session baseline (v0): la migración v8 (device_id, ADR-0154) lo ALTERa.
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test").await.unwrap();
        db
    }

    fn manifest(json: &str) -> Manifest {
        serde_json::from_str(json).unwrap()
    }

    fn registry_with(m: Manifest) -> Registry {
        let mut r = Registry::new();
        r.installed.push(m);
        r
    }

    #[tokio::test]
    async fn gate_default_deny_then_grant_then_revoke() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(
            r#"{"id":"verifactu","name":"VeriFactu","version":"1.0.0",
                "capabilities":{"certificate":{"purpose":"fiscal-sign"},"network":{"allow":["https://x"]}}}"#,
        ));
        let (hub, mid) = ("hub-test", "verifactu");

        // Default-deny: declara certificate+network, sin grants → denegado.
        assert!(matches!(
            enforce(&db, &reg, mid, hub).await.unwrap_err(),
            RuntimeError::CapabilityDenied { .. }
        ));

        // Conceder solo network → sigue denegado (falta certificate).
        set_grant(&db, &reg, hub, mid, "network", true, "hub_user:admin").await.unwrap();
        assert!(enforce(&db, &reg, mid, hub).await.is_err());

        // Conceder certificate también → pasa.
        set_grant(&db, &reg, hub, mid, "certificate", true, "hub_user:admin").await.unwrap();
        enforce(&db, &reg, mid, hub).await.unwrap();

        // Revocar network → vuelve a denegar.
        set_grant(&db, &reg, hub, mid, "network", false, "hub_user:admin").await.unwrap();
        assert!(enforce(&db, &reg, mid, hub).await.is_err());
    }

    #[tokio::test]
    async fn cannot_grant_undeclared_or_unknown() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(
            r#"{"id":"verifactu","name":"VeriFactu","version":"1.0.0",
                "capabilities":{"certificate":{"purpose":"fiscal-sign"}}}"#,
        ));
        // No declarada por el módulo → rechazada.
        assert!(set_grant(&db, &reg, "hub-test", "verifactu", "printer", true, "x").await.is_err());
        // Capability inexistente → rechazada.
        assert!(set_grant(&db, &reg, "hub-test", "verifactu", "telepathy", true, "x").await.is_err());
    }

    #[tokio::test]
    async fn module_without_capabilities_passes_freely() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(r#"{"id":"sales","name":"Sales","version":"1.0.0"}"#));
        enforce(&db, &reg, "sales", "hub-test").await.unwrap();
        assert!(list_for_module(&db, &reg, "hub-test", "sales").await.unwrap().is_empty());
    }

    /// `require` gatea UNA capability: hace falta declararla Y tenerla concedida. Un módulo con
    /// otras capabilities concedidas no cuela (hub#240: el camino a `host.notify`).
    #[tokio::test]
    async fn require_needs_the_capability_declared_and_granted() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(
            r#"{"id":"appt","name":"Appointments","version":"1.0.0",
                "capabilities":{"notify":{"channels":["email"]},"network":{"allow":["https://x"]}}}"#,
        ));
        let (hub, mid) = ("hub-test", "appt");

        // Declarada pero sin conceder → denegada.
        assert!(matches!(
            require(&db, &reg, mid, hub, CapabilityKind::Notify).await.unwrap_err(),
            RuntimeError::CapabilityDenied { capability, .. } if capability == "notify"
        ));

        // Conceder OTRA capability no abre `notify`.
        set_grant(&db, &reg, hub, mid, "network", true, "hub_user:admin").await.unwrap();
        assert!(require(&db, &reg, mid, hub, CapabilityKind::Notify).await.is_err());

        // Concedida → pasa. Y revocarla vuelve a cerrar.
        set_grant(&db, &reg, hub, mid, "notify", true, "hub_user:admin").await.unwrap();
        require(&db, &reg, mid, hub, CapabilityKind::Notify).await.unwrap();
        set_grant(&db, &reg, hub, mid, "notify", false, "hub_user:admin").await.unwrap();
        assert!(require(&db, &reg, mid, hub, CapabilityKind::Notify).await.is_err());
    }

    /// Un módulo que NO declara la capability no puede ejercerla (no hay grant que conceder).
    #[tokio::test]
    async fn require_rejects_undeclared_capability() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(r#"{"id":"notes","name":"Notes","version":"1.0.0"}"#));
        assert!(matches!(
            require(&db, &reg, "notes", "hub-test", CapabilityKind::Notify).await.unwrap_err(),
            RuntimeError::CapabilityDenied { .. }
        ));
    }

    #[tokio::test]
    async fn list_reports_declared_with_grant_state() {
        let db = db_with_migrations().await;
        let reg = registry_with(manifest(
            r#"{"id":"verifactu","name":"VeriFactu","version":"1.0.0",
                "capabilities":{"certificate":{},"network":{}}}"#,
        ));
        let list = list_for_module(&db, &reg, "hub-test", "verifactu").await.unwrap();
        assert_eq!(list.len(), 2);
        assert!(list.iter().all(|(_, g)| !*g), "default-deny: nada concedido");
        set_grant(&db, &reg, "hub-test", "verifactu", "network", true, "x").await.unwrap();
        let list = list_for_module(&db, &reg, "hub-test", "verifactu").await.unwrap();
        assert!(list.iter().any(|(id, g)| id == "network" && *g));
    }
}
