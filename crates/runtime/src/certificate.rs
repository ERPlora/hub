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

use crate::errors::{Result, RuntimeError};
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

// ── Firma/identidad MEDIADA por el host (ADR-0079) ────────────────────────────
// El core posee el certificado y hace TODA la cripto PKCS#12 (OpenSSL) en UN solo sitio. Los
// módulos (verifactu, futuro B2B…) solo PIDEN la operación (`NativeHost::certificate_*`); la clave
// privada NUNCA cruza al módulo (no ve los bytes del `.p12`). Reutilizable por cualquier esquema
// fiscal/firma. El módulo solo necesita la capability `certificate` concedida.

/// Lee los bytes del PKCS#12 del negocio desde `_hub_certificate` (base64 → DER) + contraseña.
/// `None` si el hub no tiene certificado cargado.
async fn load_pkcs12(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<(Vec<u8>, String)>> {
    use base64::Engine as _;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT pkcs12_b64, password FROM _hub_certificate WHERE hub_id = :hub_id LIMIT 1",
            &p,
        )
        .await?;
    let Some(row) = res.rows.into_iter().next() else {
        return Ok(None);
    };
    let b64 = row.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("");
    if b64.is_empty() {
        return Ok(None);
    }
    let password = row.get("password").and_then(|v| v.as_str()).unwrap_or("").to_string();
    let der = base64::engine::general_purpose::STANDARD
        .decode(b64.trim())
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 base64 inválido en _hub_certificate: {e}")))?;
    Ok(Some((der, password)))
}

/// Identidad TLS-cliente (mTLS) del negocio, para que un módulo con la capability `certificate`
/// transmita a Hacienda **sin ver el `.p12`**. Error si no hay certificado o no parsea.
pub async fn identity(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<reqwest::Identity> {
    let (der, password) = load_pkcs12(db, hub_id).await?.ok_or_else(|| {
        RuntimeError::Certificate("no hay certificado del negocio cargado (Ajustes → Negocio)".into())
    })?;
    identity_from_der(&der, &password)
}

/// Caducidad (notAfter) del certificado del negocio como ISO `YYYY-MM-DD`. `Ok(None)` si no hay
/// certificado o la fecha no se puede interpretar.
pub async fn expiry(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<String>> {
    match load_pkcs12(db, hub_id).await? {
        Some((der, password)) => expiry_from_der(&der, &password),
        None => Ok(None),
    }
}

/// Parsea el PKCS#12 **en memoria con OpenSSL** (acepta los `.p12` BER reales de FNMT/Windows que un
/// parser DER estricto rechaza) y lo entrega a **rustls** como PEM (clave + certificado + cadena).
/// A diferencia de `native-tls`, OpenSSL no importa la clave al Llavero del SO (sin diálogos macOS).
/// `pub` para `certificate_*_from` (cert provisto en memoria, p.ej. validar uno recién subido) — la
/// cripto sigue viviendo SOLO aquí, en el core. (OpenSSL → solo non-Android; ver stub abajo.)
#[cfg(not(target_os = "android"))]
pub fn identity_from_der(der: &[u8], password: &str) -> Result<reqwest::Identity> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    let key = parsed
        .pkey
        .ok_or_else(|| RuntimeError::Certificate("el PKCS#12 no contiene clave privada".into()))?;
    let cert = parsed
        .cert
        .ok_or_else(|| RuntimeError::Certificate("el PKCS#12 no contiene certificado".into()))?;
    let mut pem = key
        .private_key_to_pem_pkcs8()
        .map_err(|e| RuntimeError::Certificate(format!("clave privada: {e}")))?;
    pem.extend_from_slice(
        &cert.to_pem().map_err(|e| RuntimeError::Certificate(format!("certificado: {e}")))?,
    );
    // Cadena intermedia (si el `.p12` la incluye) — la AEAT valida hasta la raíz FNMT.
    if let Some(chain) = parsed.ca {
        for c in chain {
            if let Ok(b) = c.to_pem() {
                pem.extend_from_slice(&b);
            }
        }
    }
    reqwest::Identity::from_pem(&pem)
        .map_err(|e| RuntimeError::Certificate(format!("identidad TLS inválida: {e}")))
}

/// Stub Android: sin OpenSSL no se puede parsear el `.p12` (ver `Cargo.toml`). El shell Android no
/// hace transmisión fiscal todavía; la firma vive en Hub Cloud/Local.
#[cfg(target_os = "android")]
pub fn identity_from_der(_der: &[u8], _password: &str) -> Result<reqwest::Identity> {
    Err(RuntimeError::Certificate(
        "firma con certificado fiscal no disponible en Android (sin OpenSSL)".into(),
    ))
}

/// Caducidad (notAfter) de un PKCS#12 en DER como ISO `YYYY-MM-DD`. `pub` para `certificate_*_from`.
#[cfg(not(target_os = "android"))]
pub fn expiry_from_der(der: &[u8], password: &str) -> Result<Option<String>> {
    ensure_legacy_provider();
    let pkcs12 = openssl::pkcs12::Pkcs12::from_der(der)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let parsed = pkcs12
        .parse2(password)
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 (¿contraseña incorrecta?): {e}")))?;
    match parsed.cert {
        // El Display de Asn1Time es "MMM DD HH:MM:SS YYYY GMT" (p.ej. "Jun 10 00:00:00 2028 GMT").
        Some(cert) => Ok(asn1_time_to_iso(&cert.not_after().to_string())),
        None => Ok(None),
    }
}

/// Stub Android: sin OpenSSL no se puede leer la caducidad del `.p12` (ver `Cargo.toml`).
#[cfg(target_os = "android")]
pub fn expiry_from_der(_der: &[u8], _password: &str) -> Result<Option<String>> {
    Ok(None)
}

/// Carga (una sola vez) el proveedor **`legacy`** de OpenSSL 3 junto al `default`, para descifrar
/// PKCS#12 con PBE antiguos (RC2-40-CBC, 3DES) de certificados reales (FNMT, exportados de Windows).
/// OpenSSL 3 los movió fuera del proveedor por defecto; sin esto fallan con `RC2-40-CBC : unsupported`.
#[cfg(not(target_os = "android"))]
fn ensure_legacy_provider() {
    use std::sync::OnceLock;
    static LEGACY: OnceLock<Option<openssl::provider::Provider>> = OnceLock::new();
    LEGACY.get_or_init(|| openssl::provider::Provider::try_load(None, "legacy", true).ok());
}

/// "Jun 10 00:00:00 2028 GMT" → "2028-06-10". `None` si el formato no casa.
#[cfg(not(target_os = "android"))]
fn asn1_time_to_iso(s: &str) -> Option<String> {
    let parts: Vec<&str> = s.split_whitespace().collect();
    if parts.len() < 4 {
        return None;
    }
    let month = match parts[0] {
        "Jan" => "01", "Feb" => "02", "Mar" => "03", "Apr" => "04",
        "May" => "05", "Jun" => "06", "Jul" => "07", "Aug" => "08",
        "Sep" => "09", "Oct" => "10", "Nov" => "11", "Dec" => "12",
        _ => return None,
    };
    let day = parts[1];
    let day = if day.len() == 1 { format!("0{day}") } else { day.to_string() };
    Some(format!("{}-{}-{}", parts[3], month, day))
}

#[cfg(all(test, not(target_os = "android")))]
mod asn1_tests {
    use super::asn1_time_to_iso;
    #[test]
    fn parses_openssl_asn1_time() {
        assert_eq!(asn1_time_to_iso("Jun 10 00:00:00 2028 GMT").as_deref(), Some("2028-06-10"));
        assert_eq!(asn1_time_to_iso("Mar 3 23:59:59 2027 GMT").as_deref(), Some("2027-03-03"));
        assert_eq!(asn1_time_to_iso("garbage").as_deref(), None);
    }
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
