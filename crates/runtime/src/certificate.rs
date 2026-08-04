//! Certificado fiscal del NEGOCIO en el core (ADR-0079).
//!
//! El PKCS#12 del negocio (identidad fiscal: VeriFactu y futuros B2B) es un **recurso del HUB**,
//! subido en Ajustes → Negocio (junto al NIF y el nombre), NO en un módulo. Vive en la tabla de
//! sistema `_hub_certificate` (migración v6), singleton por hub. Un módulo solo lo USA si tiene la
//! capability `certificate` concedida (el gate del dispatcher la exige antes del handler nativo, y
//! verifactu lo lee del core vía `host.read`); la clave nunca cruza al sandbox WASM.
//!
//! `pkcs12_b64`/`password` se cifran at-rest ([`crate::secret_box`], ERPlora/hub#114) con una
//! master key que vive FUERA de la BD (`HUB_SECRETS_KEY`, env) — quien lea `_hub_certificate`
//! directamente ya no puede firmar en nombre del negocio. **Sin la master key, [`set`] falla
//! (fail-closed): nunca se guarda un certificado nuevo en claro.** Filas legacy (subidas antes de
//! este fix, sin el prefijo `v1:`) se siguen LEYENDO igual (compat hacia atrás); se re-cifran de
//! forma perezosa la próxima vez que alguien vuelva a subir el certificado (no hay migración de
//! arranque — ver `secret_box.rs` para el porqué).
//!
//! ADR-0202 (pending): this table grows a second slot — `kind = 'own' | 'delegated'`. `own` is
//! the business cert uploaded here (unchanged; ADR-0079/0081 stay in force). `delegated` is
//! ERPlora's Sello de Entidad, distributed and rotated by the SaaS control plane (pull on boot,
//! on heartbeat version mismatch, and on any TLS failure against the AEAT). Selection rule:
//! `own` wins ONLY if uploaded — a fallback, never a user-facing option.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value};

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;
use crate::secret_box::{self, SecretsKey};

fn certificate_error(context: &str, err: secret_box::SecretBoxError) -> RuntimeError {
    RuntimeError::Certificate(format!("{context}: {err}"))
}

/// Master key para cifrar/descifrar `_hub_certificate` (ADR-0016, ERPlora/hub#114). Separado en
/// su propia función para que el mensaje de error de [`set`] (fail-closed) sea específico del
/// certificado fiscal, no genérico de `secret_box`.
fn load_master_key() -> Result<Option<SecretsKey>> {
    secret_box::master_key_from_env().map_err(|e| {
        certificate_error(
            &format!("{} inválida", secret_box::MASTER_KEY_ENV),
            e,
        )
    })
}

/// Sube/reemplaza el certificado del negocio (upsert). `by` = `hub_user:<id>` admin.
///
/// **Fail-closed:** sin `HUB_SECRETS_KEY` definida, falla — NUNCA se persiste un `.p12`/password
/// nuevo en claro ni se genera una clave y se guarda en la misma BD (eso no protegería nada). El
/// Hub es Postgres-only/cloud-only desde ADR-0154 (no hay distinción Local/Cloud que relajar esta
/// política para un subconjunto de despliegues).
pub async fn set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    pkcs12_b64: &str,
    password: &str,
    by: &str,
) -> Result<()> {
    let key = load_master_key()?.ok_or_else(|| {
        RuntimeError::Certificate(format!(
            "cifrado de secretos no configurado: define {} antes de subir un certificado nuevo \
             (ADR-0016, ERPlora/hub#114) — nunca se guarda un .p12/contraseña en claro",
            secret_box::MASTER_KEY_ENV
        ))
    })?;
    let pkcs12_b64_enc = secret_box::encrypt(&key, pkcs12_b64)
        .map_err(|e| certificate_error("cifrando el .p12", e))?;
    let password_enc =
        secret_box::encrypt(&key, password).map_err(|e| certificate_error("cifrando la contraseña", e))?;

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("pkcs12_b64".into(), json!(pkcs12_b64_enc));
    p.insert("password".into(), json!(password_enc));
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
///
/// Descifra ambas columnas ([`crate::secret_box`]); las filas legacy (en claro, sin prefijo `v1:`)
/// se leen igual que siempre, sin exigir master key. Las filas YA cifradas sí la exigen — si falta
/// o no coincide, el error es explícito (nunca un pánico ni un `.p12` corrupto silencioso).
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
    let b64_stored = row.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("");
    if b64_stored.is_empty() {
        return Ok(None);
    }
    let password_stored = row.get("password").and_then(|v| v.as_str()).unwrap_or("");

    let key = load_master_key()?;
    let b64 = secret_box::decrypt_or_legacy(key.as_ref(), b64_stored)
        .map_err(|e| certificate_error("descifrando el .p12 de _hub_certificate", e))?;
    let password = secret_box::decrypt_or_legacy(key.as_ref(), password_stored)
        .map_err(|e| certificate_error("descifrando la contraseña de _hub_certificate", e))?;

    let der = base64::engine::general_purpose::STANDARD
        .decode(b64.trim())
        .map_err(|e| RuntimeError::Certificate(format!("PKCS#12 base64 inválido en _hub_certificate: {e}")))?;
    Ok(Some((der, password)))
}

/// Bytes DER del PKCS#12 del negocio, **descifrados** — SIN la contraseña. Para flujos que solo
/// necesitan el binario del certificado, no firmar con él (p.ej. el export de blueprint,
/// `crates/server/src/export_import.rs`, decisión (d): "la contraseña NO viaja"). `None` si el hub
/// no tiene certificado. Antes de ERPlora/hub#114 estos flujos leían `pkcs12_b64` crudo de la BD
/// (era el propio base64 en claro); con el cifrado at-rest deben pasar por aquí.
pub async fn der_bytes(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Option<Vec<u8>>> {
    Ok(load_pkcs12(db, hub_id).await?.map(|(der, _password)| der))
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
    use crate::secret_box::test_support::{env_lock, test_key_b64, EnvVarGuard};
    use erplora_db::{testutil::fresh_db, PgAdapter};

    async fn db_ready() -> PgAdapter {
        let db = fresh_db().await;
        crate::installer::ensure_hub_module_table(&db).await.unwrap();
        // hub_session baseline (v0): la migración v8 (device_id, ADR-0154) lo ALTERa.
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "hub-test").await.unwrap();
        db
    }

    /// Lee la fila cruda de `_hub_certificate` tal y como está en la BD (sin pasar por
    /// `load_pkcs12`/descifrado) — lo que vería alguien con acceso directo a la BD.
    async fn raw_row(db: &dyn DatabaseAdapter, hub_id: &str) -> (String, String) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        let res = db
            .query("SELECT pkcs12_b64, password FROM _hub_certificate WHERE hub_id = :hub_id LIMIT 1", &p)
            .await
            .unwrap();
        let row = res.rows.into_iter().next().expect("fila esperada");
        (
            row.get("pkcs12_b64").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            row.get("password").and_then(|v| v.as_str()).unwrap_or("").to_string(),
        )
    }

    #[tokio::test]
    async fn set_status_delete_roundtrip() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(1));
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

    // ── ERPlora/hub#114: cifrado at-rest de `_hub_certificate` ─────────────────────────────────

    #[tokio::test]
    async fn set_encrypts_pkcs12_and_password_at_rest() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(2));
        let db = db_ready().await;

        set(&db, "hub-test", "TVVZLVNFQ1JFVE8tUEtDUzEy", "s3cr3t-p12-password", "hub_user:admin")
            .await
            .unwrap();

        let (pkcs12_raw, password_raw) = raw_row(&db, "hub-test").await;
        // La fila cruda NUNCA debe contener el password ni el .p12 en claro.
        assert_ne!(pkcs12_raw, "TVVZLVNFQ1JFVE8tUEtDUzEy");
        assert_ne!(password_raw, "s3cr3t-p12-password");
        assert!(!pkcs12_raw.contains("TVVZLVNFQ1JFVE8tUEtDUzEy"));
        assert!(!password_raw.contains("s3cr3t-p12-password"));
        // Formato versionado (`secret_box::PREFIX`).
        assert!(pkcs12_raw.starts_with("v1:"));
        assert!(password_raw.starts_with("v1:"));
    }

    #[tokio::test]
    async fn set_then_load_pkcs12_roundtrip_returns_originals() {
        use base64::Engine as _;
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(3));
        let db = db_ready().await;

        let original_b64 = "TVVZLVNFQ1JFVE8tUEtDUzEy"; // base64("MUY-SECRETO-PKCS12")
        set(&db, "hub-test", original_b64, "mi-contraseña-real", "hub_user:admin").await.unwrap();

        let (der, password) = load_pkcs12(&db, "hub-test").await.unwrap().expect("certificado presente");
        assert_eq!(der, base64::engine::general_purpose::STANDARD.decode(original_b64).unwrap());
        assert_eq!(password, "mi-contraseña-real");
    }

    #[tokio::test]
    async fn der_bytes_decrypts_without_leaking_password() {
        // Regresión: `crates/server/src/export_import.rs` (export de blueprint, decisión (d) "la
        // contraseña no viaja") leía antes el base64 crudo de la columna. Con cifrado at-rest debe
        // pasar por aquí para no exportar el ciphertext como si fuera el `.p12`.
        use base64::Engine as _;
        let _lock = env_lock();
        let _guard = EnvVarGuard::set(&test_key_b64(6));
        let db = db_ready().await;

        let original_b64 = "TVVZLVNFQ1JFVE8tUEtDUzEy";
        set(&db, "hub-test", original_b64, "no-debe-viajar", "hub_user:admin").await.unwrap();

        let der = der_bytes(&db, "hub-test").await.unwrap().expect("certificado presente");
        assert_eq!(der, base64::engine::general_purpose::STANDARD.decode(original_b64).unwrap());
    }

    #[tokio::test]
    async fn load_pkcs12_reads_legacy_plaintext_row_without_key() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        let db = db_ready().await;

        // Fila legacy: escrita ANTES de este fix, directamente en claro (bypassa `set`, que ahora
        // exige la master key). Reproduce el estado real de las instalaciones ya existentes.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-test"));
        p.insert("pkcs12_b64".into(), json!("TEVHQUNZLVBMQUlOVEVYVA=="));
        p.insert("password".into(), json!("legacy-plaintext-password"));
        p.insert("uploaded_at".into(), json!(now_rfc3339()));
        p.insert("uploaded_by".into(), json!("hub_user:admin"));
        db.execute(
            "INSERT INTO _hub_certificate (hub_id, pkcs12_b64, password, uploaded_at, uploaded_by) \
             VALUES (:hub_id, :pkcs12_b64, :password, :uploaded_at, :uploaded_by)",
            &p,
        )
        .await
        .unwrap();

        // Sin HUB_SECRETS_KEY, la fila legacy se sigue leyendo igual (compat hacia atrás).
        use base64::Engine as _;
        let (der, password) = load_pkcs12(&db, "hub-test").await.unwrap().expect("certificado presente");
        assert_eq!(
            der,
            base64::engine::general_purpose::STANDARD.decode("TEVHQUNZLVBMQUlOVEVYVA==").unwrap()
        );
        assert_eq!(password, "legacy-plaintext-password");
    }

    #[tokio::test]
    async fn set_without_master_key_fails_fail_closed() {
        let _lock = env_lock();
        let _guard = EnvVarGuard::unset();
        let db = db_ready().await;

        let err = set(&db, "hub-test", "cGtjczEy", "password", "hub_user:admin").await.unwrap_err();
        let msg = err.to_string();
        assert!(msg.contains("HUB_SECRETS_KEY"), "mensaje de error poco claro: {msg}");
        // No debe haber guardado nada.
        assert_eq!(status(&db, "hub-test").await.unwrap()["present"], json!(false));
    }

    #[tokio::test]
    async fn load_pkcs12_wrong_key_fails_clearly_not_panics() {
        let _lock = env_lock();
        let db = {
            let _guard = EnvVarGuard::set(&test_key_b64(4));
            let db = db_ready().await;
            set(&db, "hub-test", "cGtjczEy", "password", "hub_user:admin").await.unwrap();
            db
        };

        // Misma fila, master key DISTINTA: debe fallar con un error claro, no un pánico.
        let _guard = EnvVarGuard::set(&test_key_b64(5));
        let err = load_pkcs12(&db, "hub-test").await.unwrap_err();
        assert!(matches!(err, RuntimeError::Certificate(_)));
    }
}
