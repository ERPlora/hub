//! **The business owner's rules** — the [`Runtime`] face of the hub#1701 gate (ADR-0476).
//!
//! Same split as the flows (`flows_api.rs`): only the methods the REST surface calls live here; the
//! rules about what may be stored and how it is evaluated live in [`crate::policies`], which is
//! where they have to be together — the write door refuses exactly what the gate would not know how
//! to apply.
//!
//! Every write ends by rebuilding the in-memory index. That is not a performance detail: a rule the
//! owner has just saved — or deleted — has to be in force on the next sale, not on the next deploy.
use crate::*;

impl Runtime {
    /// Where the owner may put a rule: the checkpoints of the installed and active modules
    /// (hub#1701).
    pub fn policy_checkpoints(&self) -> Vec<policies::PolicyCheckpoint> {
        self.registry
            .policy_checkpoints()
            .into_iter()
            .cloned()
            .collect()
    }

    pub async fn list_policies(&self) -> Result<Vec<policies::Policy>> {
        policies::list(self.db.as_ref(), &self.hub_id).await
    }

    pub async fn get_policy(&self, id: &str) -> Result<policies::Policy> {
        policies::get(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Stores a rule. The registry travels with it because what may be written depends on the
    /// checkpoint that offers it: its `facts` and its `outcomes` — the same reason `create_flow`
    /// carries the registry.
    pub async fn create_policy(&self, new: &policies::NewPolicy, by: &str) -> Result<policies::Policy> {
        let saved =
            policies::create(self.db.as_ref(), &self.hub_id, &self.registry, new, by).await?;
        self.reload_policies().await?;
        Ok(saved)
    }

    pub async fn update_policy(
        &self,
        id: &str,
        new: &policies::NewPolicy,
        by: &str,
    ) -> Result<policies::Policy> {
        let saved =
            policies::update(self.db.as_ref(), &self.hub_id, id, &self.registry, new, by).await?;
        self.reload_policies().await?;
        Ok(saved)
    }

    pub async fn delete_policy(&self, id: &str, by: &str) -> Result<()> {
        policies::delete(self.db.as_ref(), &self.hub_id, id, by).await?;
        self.reload_policies().await
    }

    /// Rebuilds the in-memory index the gate reads from, out of the `_policy` rows.
    ///
    /// Called by boot (`ensure_system_tables`) and by every write above. **Nothing else has to call
    /// it**: the index is keyed by checkpoint, so installing, updating, pausing or removing a module
    /// is resolved by the Registry at apply time and does not leave the index stale (see the note on
    /// [`policies::PolicyIndex`]).
    pub async fn reload_policies(&self) -> Result<()> {
        let by_checkpoint = policies::load_index(self.db.as_ref(), &self.hub_id).await?;
        self.registry.policies.replace(by_checkpoint);
        Ok(())
    }
}
