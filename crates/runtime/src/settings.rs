//! Settings del hub — store key/value de **sistema**, persistido y scoped por `hub_id`.
//!
//! Tabla `hub_settings(hub_id, key, value, updated_at, updated_by)` (PK `(hub_id, key)`, migración
//! de sistema v4). La **validación de claves conocidas vive aquí, en el runtime**, no en la BD: el
//! [`registry`] de claves declara, por cada `key`, su **default** + un **validador** del valor en
//! claro. La tabla solo guarda strings; cada `Setting` sabe parsear/serializar su tipo.
//!
//! Contrato del frontend (lo sirve el server en `GET/PUT /api/settings`):
//!  - `currency`        — string ISO-4217 de 3 letras (p. ej. `"EUR"`). Default `"EUR"`.
//!  - `language`        — locale soportado (`"es"`|`"en"`). Default `"es"`.
//!  - `api_docs_enabled`— bool (gate server-side del OpenAPI interno). Default `false`.
//!
//! **Extensible**: añadir una clave nueva = añadir una entrada a [`KNOWN`] con su `default` + su
//! `validate`, sin tocar la BD ni añadir una migración.
//!
//! - **Lectura** ([`get_all`]): mezcla las filas persistidas con los defaults de TODAS las claves
//!   conocidas, así que el resultado siempre trae el conjunto completo (defensa contra el hub recién
//!   creado sin filas). Una fila con un valor que ya no valida (clave obsoleta / valor corrupto)
//!   degrada al default sin romper la lectura.
//! - **Escritura** ([`set_many`]): valida CADA clave (rechaza claves desconocidas y valores
//!   inválidos ANTES de tocar la BD — atómico a nivel de validación), normaliza el valor (p. ej.
//!   moneda a mayúsculas) y hace upsert. El gate de rol (owner/admin) lo aplica el server.
use std::collections::BTreeMap;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value};

use crate::errors::{Result, RuntimeError};
use crate::registry::now_rfc3339;

/// Una clave de setting conocida: su nombre, el valor por defecto (JSON) y un validador que, dado
/// un valor JSON entrante, devuelve el **string a persistir** (ya normalizado) o un mensaje de error.
struct Setting {
    key: &'static str,
    /// Valor por defecto, en la forma JSON del contrato (string o bool).
    default: fn() -> Value,
    /// Valida + normaliza un valor entrante: `Ok(string a persistir)` o `Err(detalle)`. El string
    /// persistido es lo que [`parse_stored`] reconvierte a JSON al leer.
    validate: fn(&Value) -> std::result::Result<String, String>,
    /// Reconvierte el string persistido en BD a su forma JSON del contrato (inverso de `validate`).
    parse_stored: fn(&str) -> Value,
}

/// Registro de claves conocidas. **Añadir una clave = añadir una entrada aquí** (sin migración).
const KNOWN: &[Setting] = &[
    Setting {
        key: "currency",
        default: || json!("EUR"),
        validate: validate_currency,
        parse_stored: |s| json!(s),
    },
    Setting {
        key: "language",
        default: || json!("es"),
        validate: validate_language,
        parse_stored: |s| json!(s),
    },
    Setting {
        key: "api_docs_enabled",
        default: || json!(false),
        validate: validate_bool,
        parse_stored: |s| json!(s == "true"),
    },
    // Identidad de NEGOCIO (FUENTE ÚNICA, país-agnóstica — ADR-0061): identificador fiscal universal
    // (NIF en ES, SIREN/SIRET en FR, VAT-ID…), razón social y dirección del obligado tributario. La
    // usan invoice (emisor) y los módulos fiscales por país (verifactu, …) + los documentos de venta.
    // Lo específico de cada país (tipos IVA/IGIC, e-factura) NO vive aquí: va en el módulo `taxes` y en
    // los módulos de compliance. Texto libre (vacío hasta que el dueño lo configure en /settings).
    Setting {
        key: "business_tax_id",
        default: || json!(""),
        validate: validate_tax_id,
        parse_stored: |s| json!(s),
    },
    Setting {
        key: "business_legal_name",
        default: || json!(""),
        validate: validate_text,
        parse_stored: |s| json!(s),
    },
    Setting {
        key: "business_address",
        default: || json!(""),
        validate: validate_text,
        parse_stored: |s| json!(s),
    },
];

/// Locales soportados por el hub (espejo del contrato del frontend, ADR-0055).
const SUPPORTED_LOCALES: &[&str] = &["es", "en"];

fn find(key: &str) -> Option<&'static Setting> {
    KNOWN.iter().find(|s| s.key == key)
}

/// `currency`: string ISO-4217 de 3 letras. Se normaliza a MAYÚSCULAS al persistir.
fn validate_currency(v: &Value) -> std::result::Result<String, String> {
    let s = v.as_str().ok_or("debe ser un string ISO-4217 (p. ej. \"EUR\")")?;
    let up = s.trim().to_ascii_uppercase();
    if up.len() == 3 && up.chars().all(|c| c.is_ascii_alphabetic()) {
        Ok(up)
    } else {
        Err(format!("moneda inválida `{s}`: se espera un código ISO-4217 de 3 letras (p. ej. EUR)"))
    }
}

/// `language`: locale soportado (`es`|`en`). Se normaliza a minúsculas al persistir.
fn validate_language(v: &Value) -> std::result::Result<String, String> {
    let s = v.as_str().ok_or("debe ser un string de locale (p. ej. \"es\")")?;
    let lo = s.trim().to_ascii_lowercase();
    if SUPPORTED_LOCALES.contains(&lo.as_str()) {
        Ok(lo)
    } else {
        Err(format!(
            "idioma no soportado `{s}`: soportados {}",
            SUPPORTED_LOCALES.join(", ")
        ))
    }
}

/// Texto libre (razón social, dirección…). Acepta cualquier string (incl. vacío); recorta extremos.
/// Tope defensivo de 500 chars para no almacenar payloads enormes.
fn validate_text(v: &Value) -> std::result::Result<String, String> {
    let s = v.as_str().ok_or("debe ser un string")?;
    let t = s.trim();
    if t.chars().count() > 500 {
        return Err("texto demasiado largo (máx. 500 caracteres)".into());
    }
    Ok(t.to_string())
}

/// Identificador fiscal del negocio (universal): texto libre normalizado a MAYÚSCULAS sin espacios
/// (puede estar vacío). Vale para NIF/CIF (ES), SIREN/SIRET (FR), VAT-ID… La validación estricta del
/// formato la hace cada módulo fiscal de país al transmitir; aquí solo normalizamos.
fn validate_tax_id(v: &Value) -> std::result::Result<String, String> {
    let s = v.as_str().ok_or("debe ser un string")?;
    let up = s.trim().to_ascii_uppercase().replace(char::is_whitespace, "");
    if up.chars().count() > 20 {
        return Err("identificador fiscal demasiado largo".into());
    }
    Ok(up)
}

/// Boolean. Acepta solo un JSON `true`/`false`; se persiste como `"true"`/`"false"`.
fn validate_bool(v: &Value) -> std::result::Result<String, String> {
    match v.as_bool() {
        Some(b) => Ok(if b { "true".into() } else { "false".into() }),
        None => Err("debe ser un booleano (true/false)".into()),
    }
}

/// Lee TODOS los settings conocidos de `hub_id`: las filas persistidas mezcladas sobre los defaults
/// (claves sin fila → su default). Una fila cuya clave ya no es conocida se ignora; una fila cuyo
/// valor ya no valida degrada al default (lectura nunca rompe). Devuelve un objeto JSON
/// `{ currency, language, api_docs_enabled, … }` con el conjunto completo.
pub async fn get_all(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Value> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query("SELECT key, value FROM hub_settings WHERE hub_id = :hub_id", &p)
        .await?;

    // Mapa key→string persistido para una búsqueda rápida.
    let stored: BTreeMap<String, String> = res
        .rows
        .iter()
        .filter_map(|r| {
            let k = r["key"].as_str()?.to_string();
            let v = r["value"].as_str()?.to_string();
            Some((k, v))
        })
        .collect();

    let mut out = serde_json::Map::new();
    for s in KNOWN {
        let value = match stored.get(s.key) {
            // Hay fila: reconviértela a JSON; si su string ya no valida, degrada al default.
            Some(raw) => {
                let parsed = (s.parse_stored)(raw);
                if (s.validate)(&parsed).is_ok() {
                    parsed
                } else {
                    (s.default)()
                }
            }
            None => (s.default)(),
        };
        out.insert(s.key.to_string(), value);
    }
    Ok(Value::Object(out))
}

/// Aplica un mapa parcial de settings para `hub_id` (upsert por clave) tras **validar cada clave**:
///  - una clave **desconocida** → `InvalidPayload` (no se persiste nada),
///  - un valor **inválido** para su clave → `InvalidPayload` (no se persiste nada),
/// de modo que un PUT con una sola clave mala se rechaza por completo (validación atómica). El
/// `updated_by` audita quién hizo el cambio (un `hub_user:<id>` admin). Devuelve el objeto completo
/// actualizado (vía [`get_all`]).
pub async fn set_many(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    updates: &serde_json::Map<String, Value>,
    updated_by: &str,
) -> Result<Value> {
    // 1) Validación de TODO el lote antes de tocar la BD (rechazo total si algo no cuadra).
    let mut normalized: Vec<(&'static str, String)> = Vec::with_capacity(updates.len());
    for (key, value) in updates {
        let Some(setting) = find(key) else {
            return Err(RuntimeError::InvalidPayload {
                name: "settings".into(),
                detail: format!("clave de setting desconocida `{key}`"),
            });
        };
        match (setting.validate)(value) {
            Ok(persist) => normalized.push((setting.key, persist)),
            Err(detail) => {
                return Err(RuntimeError::InvalidPayload {
                    name: format!("settings.{key}"),
                    detail,
                })
            }
        }
    }

    // 2) Upsert por clave (mismo SQL en SQLite y Postgres: ON CONFLICT sobre la PK compuesta).
    let now = now_rfc3339();
    for (key, value) in &normalized {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("key".into(), json!(key));
        p.insert("value".into(), json!(value));
        p.insert("now".into(), json!(now));
        p.insert("updated_by".into(), json!(updated_by));
        db.execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
              VALUES (:hub_id, :key, :value, :now, :updated_by) \
              ON CONFLICT (hub_id, key) DO UPDATE SET \
                value = :value, updated_at = :now, updated_by = :updated_by",
            &p,
        )
        .await?;
    }

    get_all(db, hub_id).await
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::SqliteAdapter;

    /// Crea la tabla `hub_settings` a mano (en prod la crea la migración de sistema v4).
    async fn ensure_table(db: &SqliteAdapter) {
        db.execute_batch(
            "CREATE TABLE hub_settings (\
              hub_id TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, \
              updated_at TEXT NOT NULL, updated_by TEXT NOT NULL DEFAULT '', \
              PRIMARY KEY (hub_id, key));",
        )
        .await
        .unwrap();
    }

    #[test]
    fn validators_accept_and_reject() {
        // currency: 3 letras → normaliza a mayúsculas; otra cosa → error.
        assert_eq!(validate_currency(&json!("usd")).unwrap(), "USD");
        assert_eq!(validate_currency(&json!("EUR")).unwrap(), "EUR");
        assert!(validate_currency(&json!("EU")).is_err());
        assert!(validate_currency(&json!("EUROS")).is_err());
        assert!(validate_currency(&json!("E1R")).is_err());
        assert!(validate_currency(&json!(5)).is_err());

        // language: solo soportados, normaliza a minúsculas.
        assert_eq!(validate_language(&json!("ES")).unwrap(), "es");
        assert_eq!(validate_language(&json!("en")).unwrap(), "en");
        assert!(validate_language(&json!("fr")).is_err());
        assert!(validate_language(&json!(true)).is_err());

        // bool: solo true/false JSON.
        assert_eq!(validate_bool(&json!(true)).unwrap(), "true");
        assert_eq!(validate_bool(&json!(false)).unwrap(), "false");
        assert!(validate_bool(&json!("true")).is_err());
        assert!(validate_bool(&json!(1)).is_err());
    }

    #[tokio::test]
    async fn get_all_returns_defaults_on_empty_hub() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"));
        assert_eq!(all["language"], json!("es"));
        assert_eq!(all["api_docs_enabled"], json!(false));
    }

    #[tokio::test]
    async fn set_many_persists_and_normalizes() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;

        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("usd")); // se normaliza a USD
        updates.insert("language".into(), json!("en"));
        updates.insert("api_docs_enabled".into(), json!(true));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1").await.unwrap();
        assert_eq!(result["currency"], json!("USD"));
        assert_eq!(result["language"], json!("en"));
        assert_eq!(result["api_docs_enabled"], json!(true));

        // Persistido: una nueva lectura lo refleja, y un PUT parcial sólo cambia su clave.
        let mut partial = serde_json::Map::new();
        partial.insert("language".into(), json!("es"));
        let result = set_many(&db, "hub-1", &partial, "hub_user:1").await.unwrap();
        assert_eq!(result["language"], json!("es"));
        assert_eq!(result["currency"], json!("USD"), "la moneda previa se conserva");
        assert_eq!(result["api_docs_enabled"], json!(true));
    }

    #[tokio::test]
    async fn set_many_rejects_unknown_key() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("not_a_setting".into(), json!("x"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1").await.unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidPayload { .. }), "err = {err:?}");
    }

    #[tokio::test]
    async fn set_many_rejects_invalid_value_atomically() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;

        // Lote con una clave válida (currency) y una inválida (language=fr): se rechaza TODO; ni
        // siquiera la válida se persiste (validación atómica).
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("GBP"));
        updates.insert("language".into(), json!("fr")); // no soportado
        let err = set_many(&db, "hub-1", &updates, "hub_user:1").await.unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidPayload { .. }), "err = {err:?}");

        // La moneda NO se aplicó (sigue el default) porque el lote completo se rechazó.
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"));
    }

    #[tokio::test]
    async fn get_all_degrades_corrupt_row_to_default() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;
        // Inserta una fila con un valor que ya no valida (currency = "ZZZZ").
        db.execute_batch(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES ('hub-1', 'currency', 'ZZZZ', '2026-01-01T00:00:00Z', 'x');",
        )
        .await
        .unwrap();
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"), "fila corrupta → default");
    }

    #[tokio::test]
    async fn settings_are_hub_scoped() {
        let db = SqliteAdapter::open_in_memory().await.unwrap();
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("USD"));
        set_many(&db, "hub-a", &updates, "x").await.unwrap();

        // El hub B no ve los settings del hub A (sigue en sus defaults).
        let b = get_all(&db, "hub-b").await.unwrap();
        assert_eq!(b["currency"], json!("EUR"));
    }
}
