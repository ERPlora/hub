//! La copia PROPIA del hub del `module.zip` de cada módulo instalado (hub#571).
//!
//! Los módulos no van horneados en la imagen: se descargan del marketplace y se descomprimen en
//! `HUB_MODULE_CACHE`, que en Hub Cloud es `/tmp` **sin volumen** (contrato stateless: así el
//! contenedor se reprograma a cualquier worker). El precio era que un crash, un redeploy o un
//! reschedule vaciaba esa caché y la única forma de recuperarla era volver al marketplace — con el
//! SaaS caído, el hub arrancaba **sin un solo módulo**.
//!
//! Aquí vive la copia que sobrevive a eso. **En la base del propio hub**, no en su Object Storage:
//! el hub no tiene credenciales S3 (infra#44), así que su prefijo de Object Storage se lee por el
//! proxy `Hub→Cloud→S3` — o sea, por el SaaS, que es exactamente lo que puede estar caído. Su base
//! es lo único duradero que no es el SaaS y que tampoco ata el contenedor a un nodo.
//!
//! **Lo guardado no se cree a sí mismo.** Junto a los bytes viajan el `sha256` y la firma con la
//! que se verificaron al instalar, porque reponer pasa por la MISMA puerta que una descarga
//! (`erplora-source::ModuleStore::install`): integridad obligatoria (ADR-0015) y firma ed25519
//! según la política del despliegue (ADR-0193/0194). Una caché que se salta la verificación no es
//! una red de seguridad, es una vía de carga de código sin verificar.

use base64::Engine;
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// El `module.zip` de un módulo instalado, con lo que hace falta para volver a verificarlo.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredPackage {
    pub module_id: String,
    pub version: String,
    /// SHA256 hex del zip, tal y como lo dio el marketplace al instalarlo.
    pub sha256: String,
    /// `ModuleSignature` serializada (JSON), o `None` si el artefacto se publicó sin firma.
    pub signature_json: Option<String>,
    /// Los bytes del zip.
    pub zip: Vec<u8>,
}

/// Guarda (o reemplaza) la copia de `module_id` para este hub.
///
/// Una fila por `(hub_id, module_id)`: interesa la versión que corre, no el histórico — guardar
/// versiones viejas sería un almacén de artefactos, y para volver atrás está el marketplace.
pub async fn save(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    module_id: &str,
    version: &str,
    sha256: &str,
    signature_json: Option<&str>,
    zip: &[u8],
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    p.insert("version".into(), json!(version));
    p.insert("sha256".into(), json!(sha256));
    p.insert("signature_json".into(), json!(signature_json));
    p.insert(
        "zip_base64".into(),
        json!(base64::engine::general_purpose::STANDARD.encode(zip)),
    );
    p.insert("stored_at".into(), json!(now_rfc3339()));
    db.execute(
        "INSERT INTO hub_module_package \
         (hub_id, module_id, version, sha256, signature_json, zip_base64, stored_at) \
         VALUES (:hub_id, :module_id, :version, :sha256, :signature_json, :zip_base64, :stored_at) \
         ON CONFLICT (hub_id, module_id) DO UPDATE SET \
           version = EXCLUDED.version, sha256 = EXCLUDED.sha256, \
           signature_json = EXCLUDED.signature_json, zip_base64 = EXCLUDED.zip_base64, \
           stored_at = EXCLUDED.stored_at",
        &p,
    )
    .await?;
    Ok(())
}

/// La copia guardada de `module_id`, o `None` si este hub no tiene ninguna.
pub async fn load(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    module_id: &str,
) -> Result<Option<StoredPackage>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    let rows = db
        .query(
            "SELECT version, sha256, signature_json, zip_base64 FROM hub_module_package \
             WHERE hub_id = :hub_id AND module_id = :module_id",
            &p,
        )
        .await?
        .rows;
    let Some(row) = rows.into_iter().next() else {
        return Ok(None);
    };
    let text = |key: &str| {
        row.get(key)
            .and_then(|v| v.as_str())
            .map(str::to_string)
            .unwrap_or_default()
    };
    let zip = base64::engine::general_purpose::STANDARD
        .decode(text("zip_base64"))
        .map_err(|e| {
            RuntimeError::Storage(format!("paquete local de `{module_id}` ilegible: {e}"))
        })?;
    Ok(Some(StoredPackage {
        module_id: module_id.to_string(),
        version: text("version"),
        sha256: text("sha256"),
        signature_json: row
            .get("signature_json")
            .and_then(|v| v.as_str())
            .map(str::to_string),
        zip,
    }))
}

/// Olvida la copia de `module_id` — lo llama `installer::uninstall`.
///
/// Sin esto, un módulo que el dueño quitó volvería solo en el primer arranque sin red: la fila de
/// `hub_module` se va, pero el paquete seguiría ahí ofreciéndose.
pub async fn forget(db: &dyn DatabaseAdapter, hub_id: &str, module_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("module_id".into(), json!(module_id));
    db.execute(
        "DELETE FROM hub_module_package WHERE hub_id = :hub_id AND module_id = :module_id",
        &p,
    )
    .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::fresh_db;

    /// Esquema de sistema completo, en el mismo orden que el arranque: baseline v0 (`hub_module` +
    /// identidad, que las migraciones ALTERan) y después el catálogo versionado.
    async fn db_with_schema() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-a").await.unwrap();
        db
    }

    /// Round-trip: lo que se guarda vuelve byte a byte, con su sha y su firma.
    #[tokio::test]
    async fn a_saved_package_comes_back_exactly_as_it_went_in() {
        let db = db_with_schema().await;
        let zip = vec![0u8, 1, 2, 250, 255];
        save(
            &db,
            "hub-a",
            "notes",
            "1.0.0",
            "deadbeef",
            Some(r#"{"key_id":"mk"}"#),
            &zip,
        )
        .await
        .unwrap();

        let stored = load(&db, "hub-a", "notes")
            .await
            .unwrap()
            .expect("guardado");
        assert_eq!(stored.version, "1.0.0");
        assert_eq!(stored.sha256, "deadbeef");
        assert_eq!(stored.signature_json.as_deref(), Some(r#"{"key_id":"mk"}"#));
        assert_eq!(stored.zip, zip);
    }

    /// Actualizar reemplaza la copia: quien repone tras un reinicio debe encontrar la versión que
    /// corre, no la de ayer.
    #[tokio::test]
    async fn saving_again_replaces_the_copy_instead_of_piling_up() {
        let db = db_with_schema().await;
        save(&db, "hub-a", "notes", "1.0.0", "aaa", None, b"old")
            .await
            .unwrap();
        save(&db, "hub-a", "notes", "2.0.0", "bbb", None, b"new")
            .await
            .unwrap();

        let stored = load(&db, "hub-a", "notes").await.unwrap().unwrap();
        assert_eq!(stored.version, "2.0.0");
        assert_eq!(stored.zip, b"new");
    }

    /// La copia es de UN hub. En una base compartida (hubs pre-ADR-0201) el vecino no la ve.
    #[tokio::test]
    async fn a_package_belongs_to_one_hub_and_the_neighbour_never_sees_it() {
        let db = db_with_schema().await;
        save(&db, "hub-a", "notes", "1.0.0", "aaa", None, b"mine")
            .await
            .unwrap();

        assert!(load(&db, "hub-b", "notes").await.unwrap().is_none());
        assert!(load(&db, "hub-a", "notes").await.unwrap().is_some());
    }

    /// Olvidar es idempotente y solo se lleva lo suyo.
    #[tokio::test]
    async fn forgetting_removes_only_that_module_and_can_be_repeated() {
        let db = db_with_schema().await;
        save(&db, "hub-a", "notes", "1.0.0", "aaa", None, b"n")
            .await
            .unwrap();
        save(&db, "hub-a", "tasks", "1.0.0", "bbb", None, b"t")
            .await
            .unwrap();

        forget(&db, "hub-a", "notes").await.unwrap();
        forget(&db, "hub-a", "notes").await.unwrap();

        assert!(load(&db, "hub-a", "notes").await.unwrap().is_none());
        assert!(load(&db, "hub-a", "tasks").await.unwrap().is_some());
    }
}
