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
    // IDENTIDAD FISCAL DEL HUB (ADR-0085): vive aquí, en el core, NO en el módulo `taxes`.
    //
    // Es lo que le permite al servidor resolver el IVA de una venta contra el catálogo: una regla
    // fiscal es `(country_code, region_code, tax_category_key) → rate_pct`, así que sin el país del
    // hub el runtime no puede casar ninguna regla… y el handler cae al fallback, que es la pista
    // del cliente. O sea: **sin esto, el navegador decide el IVA que se declara a la AEAT**.
    Setting {
        key: "country_code",
        default: || json!("ES"),
        validate: validate_country,
        parse_stored: |s| json!(s),
    },
    // Región/comunidad (`ES-MD`, `ES-CN`…). `null` = todo el país (el caso normal). Existe porque
    // hay regímenes con tipos propios (Canarias/IGIC, Ceuta y Melilla/IPSI).
    Setting {
        key: "region_code",
        default: || Value::Null,
        validate: validate_region,
        parse_stored: |s| if s.is_empty() { Value::Null } else { json!(s) },
    },
    // Los decimales de la moneda. `null` = «resuélvelos del registro ISO-4217» (el caso normal);
    // un número = el hub los declara a mano, para una moneda que el registro no conoce.
    Setting {
        key: "currency_decimals",
        default: || Value::Null,
        validate: validate_currency_decimals,
        parse_stored: |s| s.parse::<i64>().map(|n| json!(n)).unwrap_or(Value::Null),
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
    // ALLOWLIST DE DESTINATARIOS de `host.notify` (hub#240). Lista (coma / salto de línea) de
    // emails y teléfonos E.164 a los que el hub autoriza enviar recordatorios. Vacía por defecto:
    // el destinatario de una notificación ya NO puede venir libre en el payload de un módulo —
    // tiene que resolverse desde datos del hub (esta lista o un usuario del hub).
    Setting {
        key: crate::host_notify::ALLOWED_RECIPIENTS_SETTING,
        default: || json!(""),
        validate: validate_recipient_list,
        parse_stored: |s| json!(s),
    },
    // Paleta de tema DEFAULT del hub (ADR-0138): valor de `data-ok-palette` (OutfitKit
    // palettes.css, compartido con Cloud). 'erplora' = marca por defecto (sin atributo).
    // El override POR USUARIO no vive aquí: está en `hub_user_pref`, aislado por hub + usuario.
    Setting {
        key: "theme_palette",
        default: || json!("erplora"),
        validate: validate_theme_palette,
        parse_stored: |s| json!(s),
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
///
/// **No es una lista blanca**: cualquier código bien formado vale, aunque el registro de monedas no
/// lo conozca. Lo que el registro aporta son los **decimales** de las monedas que sí conoce; para el
/// resto, el hub los declara a mano en `currency_decimals`.
fn validate_currency(v: &Value) -> std::result::Result<String, String> {
    let s = v
        .as_str()
        .ok_or("debe ser un string ISO-4217 (p. ej. \"EUR\")")?;
    erplora_guest_sdk::currency::normalize_code(s).ok_or_else(|| {
        format!("moneda inválida `{s}`: se espera un código ISO-4217 de 3 letras (p. ej. EUR)")
    })
}

/// `country_code`: ISO-3166-1 alpha-2 (`ES`, `FR`, `PT`…). Se normaliza a MAYÚSCULAS.
///
/// Es la mitad de la clave con la que se resuelve el impuesto (`country + region + categoría` →
/// `rate_pct`, ADR-0085). Sin él, ninguna regla fiscal casa.
fn validate_country(v: &Value) -> std::result::Result<String, String> {
    let s = v
        .as_str()
        .ok_or("debe ser un string ISO-3166 de 2 letras (p. ej. \"ES\")")?;
    let up = s.trim().to_ascii_uppercase();
    if up.len() == 2 && up.chars().all(|c| c.is_ascii_alphabetic()) {
        Ok(up)
    } else {
        Err(format!(
            "país inválido `{s}`: se espera ISO-3166-1 alpha-2 (p. ej. ES)"
        ))
    }
}

/// `region_code`: subdivisión ISO-3166-2 (`ES-MD`, `ES-CN`…) o vacío/`null` = todo el país.
///
/// Existe porque hay regímenes con tipos propios (Canarias/IGIC, Ceuta y Melilla/IPSI): una regla
/// con región gana a la del país (ADR-0085).
fn validate_region(v: &Value) -> std::result::Result<String, String> {
    match v {
        Value::Null => Ok(String::new()),
        Value::String(s) if s.trim().is_empty() => Ok(String::new()),
        Value::String(s) => {
            let up = s.trim().to_ascii_uppercase();
            // `XX-YYY`: país + subdivisión.
            let ok = up.len() >= 4
                && up.len() <= 6
                && up.as_bytes()[2] == b'-'
                && up[..2].chars().all(|c| c.is_ascii_alphabetic())
                && up[3..].chars().all(|c| c.is_ascii_alphanumeric());
            if ok {
                Ok(up)
            } else {
                Err(format!(
                    "región inválida `{s}`: se espera ISO-3166-2 (p. ej. ES-CN) o vacío"
                ))
            }
        }
        _ => Err("debe ser un string ISO-3166-2 (p. ej. \"ES-CN\") o null".to_string()),
    }
}

/// `currency_decimals`: cuántos decimales tiene la moneda del hub.
///
/// **Solo hace falta si la moneda NO está en el registro** (ISO-4217 conoce EUR=2, JPY=0, KWD=3…).
/// Es la vía para que un hub con una moneda rara funcione igual: la declara y ya.
///
/// El rango es 0..=4 porque es el de ISO-4217 — y **0 no es un error**: el yen no tiene céntimos, su
/// unidad mínima es el propio yen. Precisamente por eso el `/100` clavado en la capa de dinero era un
/// bug: en un hub en yenes habría mostrado y cobrado **100 veces mal**.
fn validate_currency_decimals(v: &Value) -> std::result::Result<String, String> {
    let n = v
        .as_i64()
        .ok_or("debe ser un entero (los decimales de la moneda: EUR 2, JPY 0, KWD 3)")?;
    if (0..=4).contains(&n) {
        Ok(n.to_string())
    } else {
        Err(format!(
            "decimales inválidos `{n}`: ISO-4217 va de 0 (JPY) a 4"
        ))
    }
}

/// Los decimales de una moneda, **sin** override del hub: lo que diga el registro, y si no la
/// conoce, el default explícito. Nunca un 2 clavado «porque sí».
pub fn decimals_of(currency: &str) -> u32 {
    erplora_guest_sdk::currency::decimals_for(currency)
        .unwrap_or(erplora_guest_sdk::currency::DEFAULT_DECIMALS)
}

/// `language`: locale soportado (`es`|`en`). Se normaliza a minúsculas al persistir.
fn validate_language(v: &Value) -> std::result::Result<String, String> {
    let s = v
        .as_str()
        .ok_or("debe ser un string de locale (p. ej. \"es\")")?;
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
    let up = s
        .trim()
        .to_ascii_uppercase()
        .replace(char::is_whitespace, "");
    if up.chars().count() > 20 {
        return Err("identificador fiscal demasiado largo".into());
    }
    Ok(up)
}

/// Paletas de tema válidas (espejo 1:1 de `@erplora/outfitkit/palettes.css` + el default).
const THEME_PALETTES: &[&str] = &[
    "erplora",
    "terracotta",
    "corporate",
    "minimal",
    "forest",
    "ocean",
    "violet",
];

/// `theme_palette`: una de las paletas de OutfitKit. Se normaliza a minúsculas al persistir.
fn validate_theme_palette(v: &Value) -> std::result::Result<String, String> {
    let s = v
        .as_str()
        .ok_or("debe ser un string (id de paleta, p. ej. \"ocean\")")?;
    let lo = s.trim().to_ascii_lowercase();
    if THEME_PALETTES.contains(&lo.as_str()) {
        Ok(lo)
    } else {
        Err(format!(
            "paleta desconocida `{s}`: válidas {}",
            THEME_PALETTES.join(", ")
        ))
    }
}

/// Boolean. Acepta solo un JSON `true`/`false`; se persiste como `"true"`/`"false"`.
fn validate_bool(v: &Value) -> std::result::Result<String, String> {
    match v.as_bool() {
        Some(b) => Ok(if b { "true".into() } else { "false".into() }),
        None => Err("debe ser un booleano (true/false)".into()),
    }
}

/// Allowlist de destinatarios de `host.notify`: string separado por comas/saltos de línea o array
/// de strings. Se normaliza a `"a@b.com,+34600000000"`. Rechaza entradas con caracteres de control
/// (esta lista acaba en un `to` de email/SMS: un `\r\n` sería inyección de cabeceras).
fn validate_recipient_list(v: &Value) -> std::result::Result<String, String> {
    let raw: Vec<String> = match v {
        Value::String(s) => s
            .split(|c: char| c == ',' || c == ';' || c == '\n' || c == '\r')
            .map(|s| s.trim().to_string())
            .collect(),
        Value::Array(items) => items
            .iter()
            .map(|i| {
                i.as_str()
                    .map(|s| s.trim().to_string())
                    .ok_or_else(|| "cada destinatario debe ser un string".to_string())
            })
            .collect::<std::result::Result<Vec<_>, _>>()?,
        Value::Null => vec![],
        _ => return Err("debe ser una lista de destinatarios (string o array)".into()),
    };
    let mut out = Vec::new();
    for entry in raw.into_iter().filter(|s| !s.is_empty()) {
        if entry.chars().any(|c| c.is_control()) || entry.len() > 254 {
            return Err(format!("destinatario inválido: `{entry}`"));
        }
        out.push(entry);
    }
    Ok(out.join(","))
}

/// Lee TODOS los settings conocidos de `hub_id`: las filas persistidas mezcladas sobre los defaults
/// (claves sin fila → su default). Una fila cuya clave ya no es conocida se ignora; una fila cuyo
/// valor ya no valida degrada al default (lectura nunca rompe). Devuelve un objeto JSON
/// `{ currency, language, api_docs_enabled, … }` con el conjunto completo.
pub async fn get_all(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Value> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT key, value FROM hub_settings WHERE hub_id = :hub_id",
            &p,
        )
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

/// Resuelve SOLO el `country_code` de `hub_id` (identidad fiscal del hub, ADR-0085): la fila
/// persistida si valida, si no su default (`"ES"`). Es la lectura barata (una sola clave) que usa
/// el instalador para decidir si aplica el seed suplementario de IVA España (hub#107) al instalar
/// `taxes`: sin traer todo el mapa de settings. Tolerante — si la tabla aún no existe (un hub
/// vacío antes de `ensure_system_tables`), degrada al default.
pub async fn country_code_of(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<String> {
    let setting = find("country_code").expect("country_code es un setting conocido");
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    // Tolerante: si la tabla/consulta aún no existe (hub vacío antes de ensure_system_tables) o no
    // hay fila, degrada al default (igual que get_all hace con `None`). Una fila corrupta también.
    let stored = match db
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = 'country_code'",
            &p,
        )
        .await
    {
        Ok(res) => res
            .rows
            .first()
            .and_then(|r| r["value"].as_str())
            .map(|s| s.to_string()),
        Err(_) => None,
    };
    let value = match stored {
        Some(raw) => {
            let parsed = (setting.parse_stored)(&raw);
            if (setting.validate)(&parsed).is_ok() {
                parsed
            } else {
                (setting.default)()
            }
        }
        None => (setting.default)(),
    };
    Ok(value.as_str().unwrap_or("ES").to_string())
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
    use erplora_db::{testutil::fresh_db, PgAdapter};

    // ── La MONEDA y sus DECIMALES (ADR-0123 §7) ─────────────────────────────────────────
    //
    // El dinero se guarda en UNIDADES MÍNIMAS, y cuántas tiene una unidad mayor depende de la
    // MONEDA: EUR 2, JPY **0**, KWD **3**. Un hub en yenes con la escala clavada en 2 mostraría y
    // cobraría **100 veces mal**. Y la app es gratuita: la usará quien quiera, no solo la eurozona.

    #[test]
    fn los_decimales_salen_del_registro_de_monedas_no_de_un_2_fijo() {
        assert_eq!(validate_currency_decimals(&json!(0)), Ok("0".to_string()));
        assert_eq!(validate_currency_decimals(&json!(3)), Ok("3".to_string()));
    }

    #[test]
    fn una_moneda_que_el_registro_NO_conoce_se_puede_declarar_a_mano() {
        // «Si la moneda no existe en el hub, se debería poder añadir a mano.» El registro sabe de
        // las comunes; para el resto, el hub declara sus decimales y funciona igual.
        assert_eq!(validate_currency(&json!("xpf")), Ok("XPF".to_string()));
        assert_eq!(validate_currency_decimals(&json!(0)), Ok("0".to_string()));
    }

    #[test]
    fn los_decimales_no_pueden_ser_cualquier_cosa() {
        // ISO-4217 no pasa de 4. Un 8 sería un hub cuya unidad mínima no cabe en la cabeza de nadie.
        assert!(validate_currency_decimals(&json!(5)).is_err());
        assert!(validate_currency_decimals(&json!(-1)).is_err());
        assert!(validate_currency_decimals(&json!("dos")).is_err());
    }

    #[test]
    fn sin_declararlos_se_resuelven_desde_la_moneda() {
        // El default NO es un 2 fijo: es «lo que diga el registro para la moneda del hub».
        assert_eq!(decimals_of("EUR"), 2);
        assert_eq!(decimals_of("JPY"), 0, "en yenes NO se divide entre 100");
        assert_eq!(decimals_of("KWD"), 3);
        // Y una moneda desconocida cae en el default explícito (2), que el hub puede sobreescribir.
        assert_eq!(decimals_of("ZZZ"), 2);
    }

    /// Crea la tabla `hub_settings` a mano (en prod la crea la migración de sistema v4).
    async fn ensure_table(db: &PgAdapter) {
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
        let db = fresh_db().await;
        ensure_table(&db).await;
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"));
        assert_eq!(all["language"], json!("es"));
        assert_eq!(all["api_docs_enabled"], json!(false));
    }

    // ── PALETA DE TEMA global del hub (ADR-0138, ERPlora/pm#15) ────────────────────────
    //
    // `theme_palette` es la paleta DEFAULT del hub (data-ok-palette de OutfitKit palettes.css,
    // compartida con Cloud). El override vive en `hub_user_pref`; esta clave es lo que ve quien no
    // ha elegido nada.

    #[tokio::test]
    async fn theme_palette_default_es_la_marca_erplora() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["theme_palette"], json!("erplora"));
    }

    #[tokio::test]
    async fn theme_palette_acepta_las_paletas_de_outfitkit_y_rechaza_el_resto() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        // Las 6 paletas de palettes.css + 'erplora' (default) son válidas.
        for id in [
            "erplora",
            "terracotta",
            "corporate",
            "minimal",
            "forest",
            "ocean",
            "violet",
        ] {
            let mut updates = serde_json::Map::new();
            updates.insert("theme_palette".into(), json!(id));
            let result = set_many(&db, "hub-1", &updates, "hub_user:1")
                .await
                .unwrap();
            assert_eq!(result["theme_palette"], json!(id));
        }

        // Un id que no existe en palettes.css se rechaza (p. ej. el set viejo del Cloud).
        let mut updates = serde_json::Map::new();
        updates.insert("theme_palette".into(), json!("glass"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "err = {err:?}"
        );
    }

    #[tokio::test]
    async fn set_many_persists_and_normalizes() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("usd")); // se normaliza a USD
        updates.insert("language".into(), json!("en"));
        updates.insert("api_docs_enabled".into(), json!(true));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1")
            .await
            .unwrap();
        assert_eq!(result["currency"], json!("USD"));
        assert_eq!(result["language"], json!("en"));
        assert_eq!(result["api_docs_enabled"], json!(true));

        // Persistido: una nueva lectura lo refleja, y un PUT parcial sólo cambia su clave.
        let mut partial = serde_json::Map::new();
        partial.insert("language".into(), json!("es"));
        let result = set_many(&db, "hub-1", &partial, "hub_user:1")
            .await
            .unwrap();
        assert_eq!(result["language"], json!("es"));
        assert_eq!(
            result["currency"],
            json!("USD"),
            "la moneda previa se conserva"
        );
        assert_eq!(result["api_docs_enabled"], json!(true));
    }

    #[tokio::test]
    async fn set_many_rejects_unknown_key() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("not_a_setting".into(), json!("x"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "err = {err:?}"
        );
    }

    #[tokio::test]
    async fn set_many_rejects_invalid_value_atomically() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        // Lote con una clave válida (currency) y una inválida (language=fr): se rechaza TODO; ni
        // siquiera la válida se persiste (validación atómica).
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("GBP"));
        updates.insert("language".into(), json!("fr")); // no soportado
        let err = set_many(&db, "hub-1", &updates, "hub_user:1")
            .await
            .unwrap_err();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "err = {err:?}"
        );

        // La moneda NO se aplicó (sigue el default) porque el lote completo se rechazó.
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"));
    }

    #[tokio::test]
    async fn get_all_degrades_corrupt_row_to_default() {
        let db = fresh_db().await;
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
        let db = fresh_db().await;
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("USD"));
        set_many(&db, "hub-a", &updates, "x").await.unwrap();

        // El hub B no ve los settings del hub A (sigue en sus defaults).
        let b = get_all(&db, "hub-b").await.unwrap();
        assert_eq!(b["currency"], json!("EUR"));
    }
}
