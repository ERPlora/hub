//! Hub settings and module capabilities — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// Lee TODOS los settings conocidos del hub del despliegue: filas persistidas mezcladas sobre
    /// los defaults de las claves conocidas (objeto JSON completo). Lectura barata sin gate de rol;
    /// el server la expone a cualquier sesión de usuario válida.
    pub async fn get_settings(&self) -> Result<Json> {
        settings::get_all(self.db.as_ref(), &self.hub_id).await
    }

    /// El nombre IANA de la zona horaria del negocio, ya **resuelta** (hub#731): la declarada en
    /// `timezone` o, lo normal, la deducida de `country_code`/`region_code`. `get_settings`
    /// devuelve la clave cruda (`null` mientras se deduzca) porque tiene que poder volver por un
    /// `PUT`; esto es lo que la UI necesita para decir a qué hora local va a correr un flujo.
    pub async fn timezone_name(&self) -> Result<String> {
        Ok(settings::timezone_of(self.db.as_ref(), &self.hub_id)
            .await?
            .name()
            .to_string())
    }

    /// Aplica un mapa parcial de settings (valida cada clave conocida; rechaza desconocidas o
    /// valores inválidos antes de tocar la BD) y devuelve el objeto completo actualizado. El gate
    /// de rol (owner/admin) lo aplica el server. `updated_by` audita quién hizo el cambio.
    pub async fn set_settings(
        &self,
        updates: &serde_json::Map<String, Json>,
        updated_by: &str,
    ) -> Result<Json> {
        settings::set_many(
            self.db.as_ref(),
            &self.hub_id,
            updates,
            updated_by,
            self.registry.demo_hub,
        )
        .await
    }

    /// Capabilities DECLARADAS por un módulo con su estado de grant (ADR-0079). Para
    /// `GET /api/modules/:id/capabilities`. Lista vacía = el módulo no pide permisos.
    pub async fn module_capabilities(&self, module_id: &str) -> Result<Vec<(String, bool)>> {
        capabilities::list_for_module(self.db.as_ref(), &self.registry, &self.hub_id, module_id)
            .await
    }

    /// **Gate de UNA capability** para un módulo (ADR-0079, default-deny): tiene que estar
    /// DECLARADA en su `module.json` **y** CONCEDIDA por el dueño. Es [`capabilities::require`]
    /// con el `db`/`registry`/`hub_id` de este runtime ya puestos.
    ///
    /// La usa el server donde el host ejerce el primitivo. Hoy: la puerta del kernel de flujos
    /// (`/api/hub/flows*`, hub#714), que **suma** este gate al de sesión admin — nunca lo
    /// sustituye.
    pub async fn require_module_capability(
        &self,
        module_id: &str,
        kind: manifest::CapabilityKind,
    ) -> Result<()> {
        capabilities::require(
            self.db.as_ref(),
            &self.registry,
            module_id,
            &self.hub_id,
            kind,
        )
        .await
    }

    /// Concede/revoca una capability de un módulo (ADR-0079). `by` = `hub_user:<id>` admin.
    pub async fn set_module_capability(
        &self,
        module_id: &str,
        capability: &str,
        granted: bool,
        by: &str,
    ) -> Result<()> {
        capabilities::set_grant(
            self.db.as_ref(),
            &self.registry,
            &self.hub_id,
            module_id,
            capability,
            granted,
            by,
        )
        .await
    }
}
