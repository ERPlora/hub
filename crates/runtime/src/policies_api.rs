//! **Las normas del dueño del negocio** — la cara de [`Runtime`] del gate de hub#1701 (ADR-0476).
//!
//! Mismo reparto que los flujos (`flows_api.rs`): aquí solo viven los métodos que la superficie
//! REST llama; las reglas de qué se puede guardar y cómo se evalúa están en [`crate::policies`],
//! que es donde tienen que estar juntas — la puerta de escritura rechaza justo lo que el gate no
//! sabría aplicar.
//!
//! Toda escritura termina reconstruyendo el índice en memoria. No es un detalle de rendimiento: una
//! norma que el dueño acaba de guardar —o de borrar— tiene que estar en vigor en la venta siguiente,
//! y no en el próximo despliegue.
use crate::*;

impl Runtime {
    /// Dónde puede el dueño poner una norma: los puntos de control de los módulos instalados y
    /// activos (hub#1701).
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

    /// Guarda una norma. El registro viaja con ella porque lo que se puede escribir depende del
    /// punto de control que la ofrece: sus `facts` y sus `outcomes` — mismo motivo por el que
    /// `create_flow` lleva el registro.
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

    /// Reconstruye el índice en memoria del que lee el gate, desde las filas de `_policy`.
    ///
    /// Lo llaman el arranque (`ensure_system_tables`) y cada escritura de aquí arriba. **Nada más
    /// tiene que llamarlo**: el índice está indexado por punto de control, así que instalar,
    /// actualizar, pausar o quitar un módulo lo resuelve el Registry al aplicar y no deja el índice
    /// desfasado (ver la nota de [`policies::PolicyIndex`]).
    pub async fn reload_policies(&self) -> Result<()> {
        let by_checkpoint = policies::load_index(self.db.as_ref(), &self.hub_id).await?;
        self.registry.policies.replace(by_checkpoint);
        Ok(())
    }
}
