//! Certificado fiscal del NEGOCIO en el core (ADR-0079).
//!
//! El PKCS#12 del negocio (identidad fiscal: VeriFactu y futuros B2B) es un **recurso del HUB**,
//! subido en Ajustes → Negocio (junto al NIF y el nombre), NO en un módulo. Vive en la tabla de
//! sistema `_hub_certificate` (migración v6), singleton por hub. Un módulo solo lo USA si tiene la
//! capability `certificate` concedida (el gate del dispatcher la exige antes del handler nativo, y
//! verifactu lo lee del core vía `host.read`); la clave nunca cruza al sandbox WASM.
//!
//! `password` se guarda en claro **de momento** (mismo estado que verifactu hoy; el cifrado at-rest
//! de secretos es decisión pendiente — ADR-0016).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value};

use crate::errors::Result;
use crate::registry::now_rfc3339;

/// Sube/reemplaza el certificado del negocio (upsert). `by` = `hub_user:<id>` admin.
pub async fn set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pkcs12_b64: &str,
    password: &str,
    by: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("pkcs12_b64".into(), json!(pkcs12_b64));
    p.insert("password".into(), json!(password));
    p.insert("uploaded_at".into(), json!(now_rfc3339()));
    p.insert("uploaded_by".into(), json!(by));
    db.execute(
        "INSERT INTO _hub_certificate (hub_id, pkcs12_b64, password, uploaded_at, uploaded_by) \
         VALUES (:hub_id, :pkcs12_b64, :password, :uploaded_at, :uploaded_by) \
         ON CONFLICT (hub_id) DO UPDATE SET \
           pkcs12_b64 = excluded.pkcs12_b64, password = excluded.password, \
           uploaded_at = excluded.uploaded_at, uploaded_by = excluded.uploaded_by",
        &p,
    )
    .await?;
    Ok(())
}

/// Estado del certificado (NO devuelve los bytes ni la contraseña): `{ present, uploaded_at, uploaded_by }`.
pub async fn status(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Value> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT uploaded_at, uploaded_by FROM _hub_certificate WHERE hub_id = :hub_id LIMIT 1",
            &p,
        )
        .await?;
    match res.rows.into_iter().next() {
        Some(r) => Ok(json!({
            "present": true,
            "uploaded_at": r.get("uploaded_at").cloned().unwrap_or(Value::Null),
            "uploaded_by": r.get("uploaded_by").cloned().unwrap_or(Value::Null),
        })),
        None => Ok(json!({ "present": false })),
    }
}

/// Elimina el certificado del negocio.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    db.execute("DELETE FROM _hub_certificate WHERE hub_id = :hub_id", &p)
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

    async fn db_ready() -> SqliteAdapter {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test").await.unwrap();
        db
    }

    #[tokio::test]
    async fn set_status_delete_roundtrip() {
        let db = db_ready().await;
        // Ausente.
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
        // Subir.
        set(&db, "hub-test", "QkFTRTY0", "secret", "hub_user:admin").await.unwrap();
        let st = status(&db, "hub-test").await.unwrap();
        assert_eq!(st["present"], json!(true));
        assert_eq!(st["uploaded_by"], json!("hub_user:admin"));
        // status NO expone bytes ni password.
        assert!(st.get("pkcs12_b64").is_none() && st.get("password").is_none());
        // Reemplazar (upsert, no duplica).
        set(&db, "hub-test", "TkVX", "p2", "hub_user:admin").await.unwrap();
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(true));
        // Borrar.
        delete(&db, "hub-test").await.unwrap();
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
    }
}
