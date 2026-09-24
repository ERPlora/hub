//! Keeps this task's module registry in step with `hub_module` (hub#1875).
//!
//! The registry lives in memory and `hub_module` in the hub's database, and while a hub runs as ONE
//! process both move together: every install/update writes the row and the registry in the same
//! step. A rolling deploy breaks that assumption. The new task starts first and builds its registry
//! from `hub_module` as it boots; the old one keeps serving until it has drained. Measured on
//! `banco-pre` on 2026-09-15: an «Update» of `verifactu` 1.5.38 → 1.5.39 landed on the draining
//! task, which moved the row to 1.5.39 — and the task that stayed alive went on listing and SERVING
//! 1.5.38 until the owner pressed the button again, eleven minutes later. The same happens with an
//! install: the module simply does not exist on the task that stays.
//!
//! The database is the record of what this hub runs (it is what the next boot loads), so this
//! task follows it: every pass compares both and reloads what drifted, at exactly the recorded
//! version. Where the package comes from, in order: this task's own download cache, the copy the
//! other task stored in the database when it installed it (hub#571), and only then the marketplace.
//!
//! What it does NOT do: follow a module that another task **uninstalled**, or an activation change
//! on its own — the version is what drifted in the report, and it is what decides which code runs.

use std::collections::HashMap;
use std::sync::Mutex;

use erplora_runtime::registry::ModuleStatus;
use serde_json::json;

use crate::{auth, install, AppState};

/// Seconds between two passes of the reconciliation in `serve()`.
pub const INTERVAL_ENV: &str = "HUB_MODULE_RECONCILE_SECS";
/// A rolling deploy overlaps the two tasks for about a minute; a few seconds of drift is the price
/// of a query that costs one indexed read of a table with a row per installed module.
const DEFAULT_INTERVAL_SECS: u64 = 15;
const MIN_INTERVAL_SECS: u64 = 5;

/// `HUB_MODULE_RECONCILE_SECS` → seconds. Unset or unreadable → the default.
pub fn interval_secs(raw: Option<&str>) -> u64 {
    raw.and_then(|v| v.trim().parse::<u64>().ok())
        .map(|secs| secs.max(MIN_INTERVAL_SECS))
        .unwrap_or(DEFAULT_INTERVAL_SECS)
}

/// Starts the reconciliation `serve()` runs for as long as the task lives. The first pass comes one
/// `period` after now, not at once: the boot restore has just brought the registry to `hub_module`.
pub fn spawn(state: AppState, period: std::time::Duration) -> tokio::task::JoinHandle<()> {
    tracing::info!(
        every_secs = period.as_secs_f64(),
        "module reconciliation started: this task follows what another task of the hub installs or updates (hub#1875)"
    );
    tokio::spawn(async move {
        let reconciler = ModuleReconciler::new();
        let mut tick = tokio::time::interval_at(tokio::time::Instant::now() + period, period);
        tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        loop {
            tick.tick().await;
            reconciler.reconcile_once(&state).await;
        }
    })
}

/// What one pass did.
#[derive(Debug, Default, Clone, PartialEq, Eq)]
pub struct Report {
    /// `(module_id, version)` now registered at the version `hub_module` records.
    pub reloaded: Vec<(String, String)>,
    /// `(module_id, version, reason)` that could not be loaded. The module keeps serving what it
    /// had: a failed install puts the previous version back (hub#516).
    pub failed: Vec<(String, String, String)>,
}

/// The reconciliation, with its memory of what it could not load.
#[derive(Default)]
pub struct ModuleReconciler {
    /// `module_id → version` whose load failed. Not retried until `hub_module` records another
    /// version: without it, a version nobody can provide would hit the marketplace every tick for
    /// as long as the task lives.
    gave_up: Mutex<HashMap<String, String>>,
}

impl ModuleReconciler {
    pub fn new() -> Self {
        Self::default()
    }

    /// One pass: reload every module whose recorded version is not the registered one.
    pub async fn reconcile_once(&self, state: &AppState) -> Report {
        let mut report = Report::default();
        let hub_id = state.hub_id();
        let drifted = {
            let rt = state.runtime.read().await;
            match drifted_modules(&rt, &hub_id).await {
                Ok(drifted) => drifted,
                Err(e) => {
                    tracing::warn!(error = %e, "module reconciliation: cannot read hub_module (hub#1875)");
                    return report;
                }
            }
        };

        // `hub_module` keeps no topological order, and registering needs the `depends_on` already
        // registered: a dependent read before its dependency fails for its turn, not for good. So
        // passes repeat while the previous one loaded something — the boot restore does the same
        // (`install::restore_from_local_packages`) — and only what still fails is written off.
        let mut pending: Vec<String> = drifted
            .into_iter()
            .filter(|(id, version, _)| !self.already_gave_up(id, version))
            .map(|(id, _, _)| id)
            .collect();
        let mut failed: Vec<(String, String, String)> = Vec::new();
        while !pending.is_empty() {
            let mut progressed = false;
            failed.clear();
            for module_id in std::mem::take(&mut pending) {
                let mut rt = state.runtime.write().await;
                // Checked again under the write lock: an install of THIS task may have been holding
                // it and have just written the same version, or the row may have moved meanwhile.
                let current = match drifted_modules(&rt, &hub_id).await {
                    Ok(drifted) => drifted.into_iter().find(|(id, _, _)| *id == module_id),
                    Err(e) => {
                        tracing::warn!(error = %e, "module reconciliation: cannot read hub_module (hub#1875)");
                        return report;
                    }
                };
                let Some((_, version, status)) = current else {
                    continue;
                };
                if self.already_gave_up(&module_id, &version) {
                    continue;
                }

                let loaded = match load(state, &mut rt, &module_id, &version).await {
                    Ok(()) => rt
                        .restore_persisted_status(&module_id, status)
                        .await
                        .map_err(|e| e.to_string()),
                    Err(e) => Err(e),
                };
                drop(rt);
                match loaded {
                    Ok(()) => {
                        progressed = true;
                        self.gave_up().remove(&module_id);
                        tracing::info!(module_id = %module_id, version = %version, "module reloaded at the version this hub records (hub#1875)");
                        // The event the shell already listens to for refreshing the nav and the
                        // entitlement: for whoever is connected to THIS task, the module changed now.
                        state.broadcast(
                            json!({ "type": "module.installed", "module_id": module_id }),
                        );
                        report.reloaded.push((module_id, version));
                    }
                    Err(reason) => failed.push((module_id, version, reason)),
                }
            }
            if !progressed {
                break;
            }
            pending = failed.iter().map(|(id, _, _)| id.clone()).collect();
        }

        for (module_id, version, reason) in failed {
            tracing::warn!(module_id = %module_id, version = %version, error = %reason, "module reconciliation failed; the module keeps serving what it had (hub#1875)");
            self.gave_up().insert(module_id.clone(), version.clone());
            report.failed.push((module_id, version, reason));
        }
        report
    }

    /// The memo of failures. A poisoned lock only means a pass panicked mid-update of a plain map:
    /// its content is still a valid map, so it is used as is.
    fn gave_up(&self) -> std::sync::MutexGuard<'_, HashMap<String, String>> {
        self.gave_up
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner)
    }

    fn already_gave_up(&self, module_id: &str, version: &str) -> bool {
        self.gave_up().get(module_id).is_some_and(|v| v == version)
    }
}

/// Rows of `hub_module` whose version is not the one registered here (or not registered at all).
async fn drifted_modules(
    rt: &erplora_runtime::Runtime,
    hub_id: &str,
) -> erplora_runtime::errors::Result<Vec<(String, String, ModuleStatus)>> {
    let persisted = erplora_runtime::installer::installed_status_versioned(rt.db(), hub_id).await?;
    let registry = rt.registry();
    Ok(persisted
        .into_iter()
        .filter(|(id, version, _)| {
            !registry.is_installed(id) || registry.module_version(id) != *version
        })
        .collect())
}

/// Registers `module_id@version`, from the cheapest source that has exactly that version.
async fn load(
    state: &AppState,
    rt: &mut erplora_runtime::Runtime,
    module_id: &str,
    version: &str,
) -> Result<(), String> {
    let cache_root = state.config.module_cache.clone();
    let policy = state.config.signature_policy();
    let installed = rt.registry().is_installed(module_id);
    let updating = installed.then_some(module_id);

    // 1. This task already extracted and verified that version (it ran it before).
    let cached = cache_root.join(module_id).join(version);
    if cached.join("module.json").exists() {
        install::register(rt, &cached, module_id, updating)
            .await
            .map_err(|e| e.to_string())?;
        return registered_at(rt, module_id, version);
    }

    // 2. The copy the other task stored when it installed it (hub#571): same checks as a download.
    let stored = erplora_runtime::module_package::load(rt.db(), rt.hub_id(), module_id)
        .await
        .map_err(|e| e.to_string())?;
    if stored.is_some_and(|p| p.version == version) {
        install::restore_one(&cache_root, rt, module_id, &policy)
            .await
            .map_err(|e| e.to_string())?;
        return registered_at(rt, module_id, version);
    }

    // 3. The marketplace, at the recorded version — never "the latest": the version is the other
    //    task's decision, already recorded.
    let Some(machine) = auth::machine_auth(state) else {
        return Err(format!(
            "{module_id}@{version} is neither cached nor stored, and the hub has no machine credential to download it"
        ));
    };
    let cloud = state.config.cloud_base_url.clone();
    let no_progress = |_: &str, _: &str| {};
    if installed {
        install::update_from_cloud(
            &state.http,
            &cloud,
            &cache_root,
            &machine,
            rt,
            module_id,
            version,
            &no_progress,
            &policy,
        )
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())?;
    } else {
        install::install_from_cloud(
            &state.http,
            &cloud,
            &cache_root,
            &machine,
            rt,
            module_id,
            version,
            &no_progress,
            &policy,
        )
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())?;
    }
    registered_at(rt, module_id, version)
}

/// A load that «succeeded» with another version registered did not do what was asked.
fn registered_at(
    rt: &erplora_runtime::Runtime,
    module_id: &str,
    version: &str,
) -> Result<(), String> {
    let registry = rt.registry();
    let running = registry.module_version(module_id);
    if registry.is_installed(module_id) && running == version {
        Ok(())
    } else {
        Err(format!(
            "{module_id}: asked for {version}, registered {running}"
        ))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_interval_defaults_and_has_a_floor() {
        assert_eq!(interval_secs(None), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some("nope")), DEFAULT_INTERVAL_SECS);
        assert_eq!(interval_secs(Some(" 60 ")), 60);
        assert_eq!(interval_secs(Some("1")), MIN_INTERVAL_SECS);
    }
}
