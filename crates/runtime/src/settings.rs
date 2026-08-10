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

use crate::errors::{DemoLock, Result, RuntimeError};
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
    // LA ZONA HORARIA DEL NEGOCIO (hub#731). `null` = «dedúcela del país», que es el caso normal:
    // el dueño ya contestó dónde está su negocio al darlo de alta, y volver a preguntárselo sería
    // inventarse un ajuste que ya existe. La clave explícita solo hace falta donde el país NO
    // puede contestar — un país con varios husos (US, BR…) — y es lo que hace auditable la
    // deducción. Un nombre IANA (`Europe/Madrid`), nunca un offset: `+02:00` no sabe de DST, y el
    // desfase que se mueve solo dos veces al año es la mitad del problema que esto arregla.
    Setting {
        key: "timezone",
        default: || Value::Null,
        validate: validate_timezone,
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
    // ¿Cada cuánto pregunta el hub QUIÉN está en la caja? (`always` | `per_shift` | `never`,
    // hub#359). Es del NEGOCIO —una afirmación sobre si se identifica a quien vende—, mientras que
    // el modo del dispositivo (hub#357/#358) es de cada terminal; se componen por el lado
    // restrictivo en `crate::pin_policy::effective_session_ttl_secs`.
    //
    // Vive aquí y no en una tabla nueva porque esta puerta ya tiene lo que hace falta: escritura
    // tras **sesión admin** (`PUT /api/settings`), validación por clave y auditoría de quién
    // cambió qué. El default y las grafías los pone `PinPolicy`, no este registro: dos definiciones
    // del valor «que no pregunta» serían dos sitios donde equivocarse.
    Setting {
        key: crate::pin_policy::PIN_POLICY_SETTING,
        default: || json!(crate::pin_policy::PinPolicy::default().as_str()),
        validate: validate_pin_policy,
        parse_stored: |s| json!(s),
    },
    // Minutos de INACTIVIDAD antes de que el shell cierre la sesión y vuelva al pinpad (hub#628).
    // Solo tiene efecto con `pin_policy = always`; quien lo aplica es el CLIENTE (el hub no ve una
    // mano soltar la caja) y el TTL de servidor de `always` queda como red. La UI ofrece paradas
    // (1·5·10·15·30) pero aquí se valida un RANGO: las paradas son presentación.
    Setting {
        key: crate::pin_policy::PIN_INACTIVITY_MINUTES_SETTING,
        default: || json!(crate::pin_policy::DEFAULT_PIN_INACTIVITY_MINUTES),
        validate: validate_pin_inactivity_minutes,
        parse_stored: |s| s.parse::<i64>().map(|n| json!(n)).unwrap_or(Value::Null),
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

/// `timezone`: nombre IANA (`Europe/Madrid`) o vacío/`null` = dedúcela del país (hub#731).
///
/// Se rechaza cualquier cosa que `chrono-tz` no conozca — incluidas las abreviaturas (`CEST`) y los
/// offsets (`+02:00`), que son justo lo que no sirve: no llevan las reglas de cambio de hora.
fn validate_timezone(v: &Value) -> std::result::Result<String, String> {
    match v {
        Value::Null => Ok(String::new()),
        Value::String(s) if s.trim().is_empty() => Ok(String::new()),
        Value::String(s) => {
            let name = s.trim();
            name.parse::<chrono_tz::Tz>()
                .map(|_| name.to_string())
                .map_err(|_| {
                    format!(
                        "zona horaria inválida `{name}`: se espera un nombre IANA \
                         (p. ej. Europe/Madrid), no una abreviatura ni un offset"
                    )
                })
        }
        _ => Err("debe ser un string IANA (p. ej. \"Europe/Madrid\") o null".to_string()),
    }
}

/// La zona que le corresponde a un país (y, cuando hace falta, a su región). Solo se deduce donde
/// la respuesta es **única**: un país con varios husos se queda en UTC hasta que el hub declare el
/// suyo, porque adivinar «la ciudad más grande» sería exactamente el mismo silencio que hub#731
/// denuncia — hacer algo razonable sin decirlo y a la hora que no era.
pub fn zone_for_country(country_code: &str, region_code: &str) -> chrono_tz::Tz {
    use chrono_tz::{Atlantic, Europe, Tz};
    // La región rompe el empate donde el país no puede: Canarias no es Madrid.
    match region_code.trim().to_ascii_uppercase().as_str() {
        "ES-CN" => return Atlantic::Canary,
        "PT-20" => return Atlantic::Azores,
        "PT-30" => return Atlantic::Madeira,
        _ => {}
    }
    match country_code.trim().to_ascii_uppercase().as_str() {
        "ES" => Europe::Madrid,
        "PT" => Europe::Lisbon,
        "AD" => Europe::Andorra,
        "AT" => Europe::Vienna,
        "BE" => Europe::Brussels,
        "BG" => Europe::Sofia,
        "CH" => Europe::Zurich,
        "CZ" => Europe::Prague,
        "DE" => Europe::Berlin,
        "DK" => Europe::Copenhagen,
        "EE" => Europe::Tallinn,
        "FI" => Europe::Helsinki,
        "FR" => Europe::Paris,
        "GB" => Europe::London,
        "GR" => Europe::Athens,
        "HR" => Europe::Zagreb,
        "HU" => Europe::Budapest,
        "IE" => Europe::Dublin,
        "IS" => Atlantic::Reykjavik,
        "IT" => Europe::Rome,
        "LT" => Europe::Vilnius,
        "LU" => Europe::Luxembourg,
        "LV" => Europe::Riga,
        "MT" => Europe::Malta,
        "NL" => Europe::Amsterdam,
        "NO" => Europe::Oslo,
        "PL" => Europe::Warsaw,
        "RO" => Europe::Bucharest,
        "SE" => Europe::Stockholm,
        "SI" => Europe::Ljubljana,
        "SK" => Europe::Bratislava,
        // Un país con varios husos (US, BR, CA, AU, RU…) o uno que no está en la tabla: el hub lo
        // declara con `timezone` y hasta entonces el reloj es UTC, que al menos no miente.
        _ => Tz::UTC,
    }
}

/// La zona horaria del negocio: la clave `timezone` si está declarada y vale, si no la deducida de
/// `country_code`/`region_code` (hub#731). Tolerante como [`country_code_of`]: una fila corrupta o
/// una tabla que aún no existe degradan a la deducción en vez de reventar a las 3 de la mañana.
/// Las tres claves en UNA consulta a propósito: el barrido de flujos pregunta esto **en cada tick**
/// (una vez por segundo), y tres viajes a la base de datos por segundo para leer una zona que casi
/// nunca cambia serían un peaje permanente por una funcionalidad de calendario.
pub async fn timezone_of(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<chrono_tz::Tz> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    // Tolerante como `country_code_of`: si la tabla aún no existe (hub vacío antes de
    // `ensure_system_tables`), se deduce del país por defecto en vez de reventar.
    let rows = match db
        .query(
            "SELECT key, value FROM hub_settings WHERE hub_id = :hub_id \
               AND key IN ('timezone', 'country_code', 'region_code')",
            &p,
        )
        .await
    {
        Ok(res) => res.rows,
        Err(_) => Vec::new(),
    };
    let read = |key: &str| -> String {
        rows.iter()
            .find(|r| r["key"].as_str() == Some(key))
            .and_then(|r| r["value"].as_str())
            .unwrap_or_default()
            .to_string()
    };

    // Lo declarado gana; una fila corrupta degrada a la deducción, no a UTC a secas.
    if let Ok(tz) = read("timezone").parse::<chrono_tz::Tz>() {
        return Ok(tz);
    }
    let country = read("country_code");
    let country = if validate_country(&json!(country)).is_ok() { country } else { "ES".to_string() };
    Ok(zone_for_country(&country, &read("region_code")))
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
/// Valida el dial «pedir PIN» delegando en [`crate::pin_policy::PinPolicy::parse`] — la MISMA
/// puerta cerrada que usa el resto del runtime. Sin `trim` y sin bajar mayúsculas a propósito
/// (aquí sí lo hacen otras claves): el valor que se colaría por una grafía casi-correcta es
/// siempre el laxo, y el laxo de esta clave es el que deja de atribuir las ventas a una persona.
/// Un tipo que no es string tampoco se interpreta: `true`, `0` o `null` no son posiciones del dial.
fn validate_pin_policy(v: &Value) -> std::result::Result<String, String> {
    let s = v
        .as_str()
        .ok_or("debe ser un string: `always`, `per_shift` o `never`")?;
    crate::pin_policy::PinPolicy::parse(s)
        .map(|p| p.as_str().to_string())
        .map_err(|e| e.to_string())
}

/// `pin_inactivity_minutes`: entero 1..=30. Un no-entero (`2.5`, `"five"`, `true`, `null`) no se
/// interpreta: la clave decide cuánto tarda una caja en volver a pedir el PIN, y adivinar aquí es
/// adivinar hacia el lado que deja la sesión abierta.
fn validate_pin_inactivity_minutes(v: &Value) -> std::result::Result<String, String> {
    let n = v
        .as_i64()
        .ok_or("debe ser un entero (minutos de inactividad, 1..=30)")?;
    if (1..=crate::pin_policy::MAX_PIN_INACTIVITY_MINUTES).contains(&n) {
        Ok(n.to_string())
    } else {
        Err(format!(
            "minutos de inactividad inválidos `{n}`: se espera 1..={}",
            crate::pin_policy::MAX_PIN_INACTIVITY_MINUTES
        ))
    }
}

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

/// Las claves de `hub_settings` que SON la identidad fiscal del obligado tributario (ADR-0061).
///
/// Mismos dos nombres que `commands::FISCAL_IDENTITY_PARAMS` — y no es coincidencia: el dispatcher
/// los inyecta como `:business_tax_id`/`:business_legal_name` leyéndolos de AQUÍ, así que la clave
/// y el parámetro son literalmente el mismo dato visto desde los dos lados. `business_address` se
/// queda fuera, igual que allí: no identifica a nadie.
pub(crate) const FISCAL_IDENTITY_SETTINGS: [&str; 2] = ["business_tax_id", "business_legal_name"];

/// La identidad fiscal de un hub de DEMO es de SOLO LECTURA (ADR-0197 §4, hub#376).
///
/// Un hub de demo es anónimo, sin registro y dura una hora: el NIF y la razón social que se
/// tecleen ahí no son de nadie. Dejarlos escribir tiene dos consecuencias concretas, no teóricas:
/// los documentos que emita la demo saldrían a nombre de un negocio real que no ha pedido nada, y
/// `POST /api/business/fiscal-identity` publicaría ese NIF como `BillingProfile` en el SaaS
/// (ADR-0201 decisión 5) — un desconocido escribiendo en la facturación de ERPlora.
///
/// La guarda es al REVÉS de lo que parece: no protege a la demo, protege al negocio cuyo NIF
/// alguien teclearía en ella.
fn enforce_demo_fiscal_identity_lock(
    updates: &serde_json::Map<String, Value>,
    demo_hub: bool,
) -> Result<()> {
    if demo_hub && FISCAL_IDENTITY_SETTINGS.iter().any(|k| updates.contains_key(*k)) {
        return Err(RuntimeError::DemoLocked {
            lock: DemoLock::FiscalIdentity,
        });
    }
    Ok(())
}

/// The tax id a DEMO hub boots with (hub#684).
///
/// All-zero on purpose. It has the shape of a Spanish CIF —letter + 7 digits + a control digit that
/// checks out for `0000000`— so every screen, document and validator downstream treats it as the
/// real thing, and **no company has it**: sequential numbering never issues the zero. A random
/// plausible-looking tax id would eventually be somebody's.
pub const DEMO_BUSINESS_TAX_ID: &str = "B00000000";
/// The legal name a DEMO hub boots with. It says *demo* out loud: it is printed on every ticket the
/// visitor makes, and that ticket has to be readable as an example, not as a real business's.
pub const DEMO_BUSINESS_LEGAL_NAME: &str = "ERPlora Demo SL";
/// The address a DEMO hub boots with. Not part of the fiscal gate (`business_address` is not in
/// [`FISCAL_IDENTITY_SETTINGS`]) and not locked either — it is here so the demo's ticket is a
/// COMPLETE document instead of one with a blank where the address goes.
pub const DEMO_BUSINESS_ADDRESS: &str = "Calle de la Demo 1, 28013 Madrid";

/// `updated_by` of the rows this writes: the core did it, no user did.
const DEMO_IDENTITY_AUTHOR: &str = "system:demo";

/// **A DEMO hub boots with its fiscal identity already filled in** (hub#684).
///
/// The onboarding checklist and the fiscal gate read the SAME two settings
/// (`business_legal_name` ∧ `business_tax_id`), and in a demo both were empty and both had to stay
/// empty: [`enforce_demo_fiscal_identity_lock`] refuses the only door that writes them. The visitor
/// was therefore shown a ⛔ *"you need this in order to invoice"* whose button led to a `409`, and
/// —the expensive half— **their sale went through and the invoice did not**:
/// `invoice.create_from_sale` stamps `:business_tax_id`, so `commands::enforce_fiscal_precondition`
/// rejected it and the document died in the outbox. Money taken, nothing issued.
///
/// The fix is to put the data there, and it has to be *that* rather than any of the shortcuts:
///
/// * **Hiding the item** would make the checklist lie — the gate still refuses, so the first sale
///   would fail with `fiscal_precondition_failed` and no screen would have warned anybody. The
///   invariant of [`crate::setup_status`] («the checklist and the gate must answer identically»)
///   exists for exactly this.
/// * **Exempting the demo from the fiscal precondition** would open a third hole in the one gate
///   that stops a hub selling without registering, to save writing two rows.
///
/// With the rows written, nothing else has to know: the item is done because it IS done, the gate
/// passes because it has what it asks for, and `setup_status` never learns what a demo is.
///
/// ⚠️ **This does not open any of the three closures of ADR-0197 §4.** It is the core writing the
/// demo's own placeholder at boot, not a door: the visitor still cannot CHANGE the identity
/// (`demo_fiscal_identity_locked`), still cannot upload an `own` certificate
/// (`demo_business_certificate_locked`) and is still pinned to `testing`
/// (`demo_fiscal_environment_locked`) — which is what keeps a demo sale away from the real AEAT.
///
/// **Never overwrites.** Only an EMPTY key is filled, so a demo that got an identity another way (a
/// blueprint of its own, a restore) keeps it — a default must not outrank a decision. Returns
/// whether it wrote anything, so the boot can say so once instead of every time.
pub async fn ensure_demo_fiscal_identity(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<bool> {
    let defaults = [
        ("business_tax_id", DEMO_BUSINESS_TAX_ID),
        ("business_legal_name", DEMO_BUSINESS_LEGAL_NAME),
        ("business_address", DEMO_BUSINESS_ADDRESS),
    ];
    let now = now_rfc3339();
    let mut wrote = false;
    for (key, value) in defaults {
        if !stored_value(db, hub_id, key).await?.trim().is_empty() {
            continue;
        }
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("key".into(), json!(key));
        p.insert("value".into(), json!(value));
        p.insert("now".into(), json!(now));
        p.insert("updated_by".into(), json!(DEMO_IDENTITY_AUTHOR));
        db.execute(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
              VALUES (:hub_id, :key, :value, :now, :updated_by) \
              ON CONFLICT (hub_id, key) DO UPDATE SET \
                value = :value, updated_at = :now, updated_by = :updated_by",
            &p,
        )
        .await?;
        wrote = true;
    }
    Ok(wrote)
}

/// El valor **persistido** de una clave (ya normalizado por su `validate`), o `""` si no hay fila.
///
/// Lectura de una sola clave, sin construir el mapa completo de [`get_all`]: la usa el congelado de
/// abajo para comparar con lo que entra.
async fn stored_value(db: &dyn DatabaseAdapter, hub_id: &str, key: &str) -> Result<String> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("key".into(), json!(key));
    let res = db
        .query(
            "SELECT value FROM hub_settings WHERE hub_id = :hub_id AND key = :key",
            &p,
        )
        .await?;
    Ok(res
        .rows
        .first()
        .and_then(|r| r["value"].as_str())
        .unwrap_or_default()
        .to_string())
}

/// **`business_tax_id` deja de ser editable una vez el hub ha EMITIDO** (ADR-0273, hub#554).
///
/// Es la otra mitad de [`crate::fiscal_profile::go_live`], que congela `taxpayer_id` copiándolo de
/// aquí: sin esta puerta, el ancla quedaba sellada en el perfil y el setting del que salió seguía
/// siendo libre.
///
/// La cadena VeriFactu está anclada por `(hub_id, issuer_nif, environment)` (guarda R4, hub#313):
/// el ancla, la secuencia (`next_sequence`) y el `PrimerRegistro` se resuelven por ese NIF. Cambiarlo
/// después de haber emitido **bifurca la cadena en silencio** —arranca una nueva desde 1 y abandona
/// la vieja a mitad— y, para la AEAT, un NIF distinto es **otro obligado tributario**. Y el mismo
/// dato viaja al SaaS como `BillingProfile` (ADR-0201 decisión 5), así que un cambio aquí también
/// reescribe a quién factura ERPlora.
///
/// La puerta se cierra desde `_hub_fiscal_profile.first_record_at` (`""` = nunca), **no** desde el
/// estado: lo que hace irreversible la salida a producción es el registro que salió, no un
/// interruptor. `hub_settings` sigue siendo la fuente única y editable de la identidad de negocio
/// (ADR-0061) — se cierra UNA clave, y solo cuando el daño sería real.
///
/// Dos decisiones que no son de detalle:
///
/// - **Reenviar el MISMO valor no es un cambio.** Ajustes → Negocio manda NIF + razón social +
///   dirección en un único `PUT` (`saveTaxSettings`), así que rechazar el no-op congelaría el
///   formulario entero: un hub que ya emitió no podría volver a corregir su dirección.
/// - **Se compara con el valor ya normalizado**, no con el string crudo: `" b12345678 "` es el
///   mismo obligado tributario que `B12345678`, y tratarlo como un cambio sería un 409 incomprensible.
///
/// `_hub_fiscal_profile.taxpayer_id` es la copia **congelada** con la que la cadena está anclada;
/// esta guarda impide que las dos se separen más. Reconciliar una divergencia ya existente no se
/// hace aquí —cuando divergen, el hub tiene un problema y hay que decirlo, no elegir en silencio—,
/// pero sí se acepta **volver al ancla**: escribir exactamente el `taxpayer_id` con el que la cadena
/// cuelga no es cambiar de obligado tributario, es dejar de divergir. Sin esa salida, un hub que se
/// quedara con el setting vacío (p. ej. al restaurar una copia PROPIA anterior a haberlo puesto) no
/// podría volver a ponerlo **nunca** — y con él vacío la guarda fiscal de ADR-0203 tampoco le deja
/// facturar. Una guarda que deja al negocio sin poder cobrar no es una guarda, es una trampa.
async fn enforce_tax_id_freeze(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    incoming: &str,
) -> Result<()> {
    // Sin perfil no hay nada emitido: `ensure` corre en cada boot y es ESE el sitio donde se anota
    // que algo salió. Tolerante también si la TABLA no se puede leer (un hub a medio bootstrapear,
    // igual que `country_code_of` de arriba): `first_record_at` vive ahí y en ningún otro sitio, así
    // que un perfil ilegible no es «no sé si emitió», es que no consta que emitiera — no se está
    // adivinando, se está usando la única información que existe. Y no regala nada a nadie: para
    // que esa lectura falle hace falta acceso a la BD, y con acceso a la BD se escribe en
    // `hub_settings` directamente sin pasar por esta puerta.
    let profile = match crate::fiscal_profile::load(db, hub_id).await {
        Ok(Some(p)) => p,
        Ok(None) | Err(_) => return Ok(()),
    };
    if profile.first_record_at.is_empty() {
        return Ok(()); // nada ha salido todavía: la identidad sigue siendo del dueño
    }
    let current = stored_value(db, hub_id, "business_tax_id").await?;
    // El ancla es `taxpayer_id`; mientras no esté escrito (lo estampa la salida a producción), el
    // ancla efectiva es lo que el hub tiene puesto.
    let anchor = if profile.taxpayer_id.is_empty() {
        current.clone()
    } else {
        profile.taxpayer_id.clone()
    };
    if incoming == current || incoming == anchor {
        return Ok(());
    }
    Err(RuntimeError::BusinessTaxIdFrozen {
        frozen_to: anchor,
        since: profile.first_record_at,
    })
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
    demo_hub: bool,
) -> Result<Value> {
    // 0) Fiscal identity is READ-ONLY in a demo hub (ADR-0197 §4, hub#376). Before validation and
    //    before the DB, and the whole PUT is refused, not the offending key: settings are already
    //    atomic here, and a partial apply would leave the caller guessing which half landed.
    enforce_demo_fiscal_identity_lock(updates, demo_hub)?;

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

    // 1b) The tax id is FROZEN once this hub emitted its first fiscal record (hub#554). It runs
    //     AFTER validation so the comparison is against the NORMALISED value (`" b1 "` is not a
    //     different taxpayer from `B1`), and only when the batch actually carries the key: every
    //     other settings write — currency, language, the PIN dial — must not pay for a read of the
    //     fiscal profile, nor depend on it being readable.
    if let Some((_, incoming)) = normalized.iter().find(|(k, _)| *k == "business_tax_id") {
        enforce_tax_id_freeze(db, hub_id, incoming).await?;
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
            let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
                .await
                .unwrap();
            assert_eq!(result["theme_palette"], json!(id));
        }

        // Un id que no existe en palettes.css se rechaza (p. ej. el set viejo del Cloud).
        let mut updates = serde_json::Map::new();
        updates.insert("theme_palette".into(), json!("glass"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
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
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .unwrap();
        assert_eq!(result["currency"], json!("USD"));
        assert_eq!(result["language"], json!("en"));
        assert_eq!(result["api_docs_enabled"], json!(true));

        // Persistido: una nueva lectura lo refleja, y un PUT parcial sólo cambia su clave.
        let mut partial = serde_json::Map::new();
        partial.insert("language".into(), json!("es"));
        let result = set_many(&db, "hub-1", &partial, "hub_user:1", false)
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
        let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
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
        let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
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
        set_many(&db, "hub-a", &updates, "x", false).await.unwrap();

        // El hub B no ve los settings del hub A (sigue en sus defaults).
        let b = get_all(&db, "hub-b").await.unwrap();
        assert_eq!(b["currency"], json!("EUR"));
    }

    // ── Identidad fiscal de SOLO LECTURA en un hub de DEMO (ADR-0197 §4 · hub#376) ─────────

    /// 🔴 La guarda, por la puerta que la APLICA: `set_many` es lo que llama
    /// `PUT /api/settings`, no un helper de siembra.
    #[tokio::test]
    async fn a_demo_hub_cannot_write_its_fiscal_identity() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        for key in ["business_tax_id", "business_legal_name"] {
            let mut updates = serde_json::Map::new();
            updates.insert(key.into(), json!("B12345678"));
            let err = set_many(&db, "hub-1", &updates, "hub_user:1", true)
                .await
                .unwrap_err();
            assert!(
                matches!(
                    err,
                    RuntimeError::DemoLocked {
                        lock: DemoLock::FiscalIdentity
                    }
                ),
                "`{key}` must stay read-only in a demo: {err:?}"
            );
            // Y NO se escribió: el rechazo es antes de tocar la BD.
            let all = get_all(&db, "hub-1").await.unwrap();
            assert_eq!(all[key], json!(""), "`{key}` must still be empty");
        }
    }

    /// Colar la identidad dentro de un lote con claves inocentes tampoco cuela — y el lote entero
    /// se rechaza, así que la moneda que iba de acompañante tampoco se aplica.
    #[tokio::test]
    async fn the_lock_survives_being_hidden_in_a_batch() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("USD"));
        updates.insert("business_tax_id".into(), json!("B12345678"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1", true)
            .await
            .unwrap_err();
        assert!(
            matches!(
                err,
                RuntimeError::DemoLocked {
                    lock: DemoLock::FiscalIdentity
                }
            ),
            "got {err:?}"
        );
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"), "the batch is refused whole");
        assert_eq!(all["business_tax_id"], json!(""));
    }

    /// La demo sigue siendo un hub USABLE: todo lo que no es la identidad fiscal se configura
    /// igual (el visitante elige idioma, paleta, moneda…). La bandera no es un modo de solo
    /// lectura, es un cierre de tres cosas concretas.
    #[tokio::test]
    async fn a_demo_hub_configures_everything_else_normally() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("USD"));
        updates.insert("language".into(), json!("en"));
        updates.insert("theme_palette".into(), json!("ocean"));
        updates.insert("business_address".into(), json!("Calle Falsa 123"));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", true)
            .await
            .expect("a demo hub is a hub: only its fiscal identity is frozen");
        assert_eq!(result["currency"], json!("USD"));
        assert_eq!(result["business_address"], json!("Calle Falsa 123"));
    }

    /// 🔴 La otra dirección: un hub REAL escribe su identidad fiscal como siempre. Si la guarda se
    /// escapara a un hub de pago, el negocio no podría configurar el NIF con el que factura.
    #[tokio::test]
    async fn a_real_hub_writes_its_fiscal_identity_as_always() {
        let db = fresh_db().await;
        // Boots the real system tables, not just `hub_settings`: a real hub also has its fiscal
        // profile (v27), which is what the freeze of hub#554 reads on this very path.
        booted(&db, "hub-1").await;
        let mut updates = serde_json::Map::new();
        updates.insert("business_tax_id".into(), json!("B12345678"));
        updates.insert("business_legal_name".into(), json!("Bar Manolo SL"));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .expect("a real hub configures the tax id it invoices with");
        assert_eq!(result["business_tax_id"], json!("B12345678"));
        assert_eq!(result["business_legal_name"], json!("Bar Manolo SL"));
    }

    // ── The tax id stops being editable once the hub has EMITTED (hub#554) ────────────────
    //
    // The VeriFactu chain is anchored by `(hub_id, issuer_nif, environment)` (R4, hub#313). Change
    // the tax id after the first record left and nothing complains: a SECOND chain starts from 1
    // while the first is abandoned half-way. And to the tax authority a different tax id is a
    // different taxpayer — the business would carry on issuing under an identity that may not be
    // its own. So this door, which is the one that writes it, closes for that ONE key, and only
    // once `_hub_fiscal_profile.first_record_at` says something really went out.

    /// Boots the system tables the way `Runtime::ensure_system_tables` does, so these tests run
    /// against the REAL `hub_settings` (v4) and `_hub_fiscal_profile` (v27) instead of a
    /// hand-written copy that can drift away from the migration.
    async fn booted(db: &PgAdapter, hub_id: &str) {
        crate::installer::ensure_hub_module_table(db).await.unwrap();
        crate::identity::ensure_tables(db).await.unwrap();
        crate::system_migrations::apply(db, hub_id).await.unwrap();
    }

    /// Stamps the profile the way going live does: this hub emitted its first fiscal record, under
    /// `taxpayer`, and the chain hangs from it.
    async fn emitted(db: &PgAdapter, hub_id: &str, taxpayer: &str) {
        crate::fiscal_profile::ensure(db, hub_id).await.unwrap();
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("taxpayer_id".into(), json!(taxpayer));
        db.execute(
            "UPDATE _hub_fiscal_profile SET status = 'ACTIVE', environment = 'production', \
               activated_at = '2026-08-08T09:00:00Z', first_record_at = '2026-08-08T10:00:00Z', \
               taxpayer_id = :taxpayer_id WHERE hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
    }

    /// Writes `business_tax_id` through the real door and returns the result.
    async fn write_tax_id(db: &PgAdapter, hub_id: &str, value: &str) -> Result<Value> {
        let mut updates = serde_json::Map::new();
        updates.insert("business_tax_id".into(), json!(value));
        set_many(db, hub_id, &updates, "hub_user:1", false).await
    }

    /// 🔴 With a record already emitted, a DIFFERENT tax id is refused — and nothing moves.
    #[tokio::test]
    async fn a_hub_that_already_emitted_refuses_a_different_tax_id() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        write_tax_id(&db, "hub-1", "B12345678").await.unwrap();
        emitted(&db, "hub-1", "B12345678").await;

        let err = write_tax_id(&db, "hub-1", "B99999999").await.unwrap_err();

        assert_eq!(
            crate::error_registry::error_code_of(&err),
            "business_tax_id_frozen",
            "the refusal needs its own stable code, not a generic one: {err:?}"
        );
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(
            all["business_tax_id"],
            json!("B12345678"),
            "the anchor of the emitted chain must not have moved"
        );
    }

    /// The other half: **before** the first record the identity is still the owner's to fix. A
    /// hub that is setting itself up mistypes its tax id all the time, and the freeze must not
    /// reach that far — nothing is anchored yet.
    #[tokio::test]
    async fn before_the_first_record_the_tax_id_is_still_editable() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        crate::fiscal_profile::ensure(&db, "hub-1").await.unwrap();

        write_tax_id(&db, "hub-1", "B00000000").await.unwrap();
        let result = write_tax_id(&db, "hub-1", "B12345678")
            .await
            .expect("nothing was emitted: the identity is still being set up");
        assert_eq!(result["business_tax_id"], json!("B12345678"));
    }

    /// 🔴 **Re-sending the same tax id is not a change.** Ajustes → Negocio posts the tax id, the
    /// legal name and the address in ONE `PUT` (`saveTaxSettings`), so a freeze that refused the
    /// no-op would freeze the whole form: a hub that already emitted could never correct its
    /// address again. And the comparison is against the NORMALISED value, not the raw string.
    #[tokio::test]
    async fn re_sending_the_same_tax_id_still_saves_the_rest_of_the_form() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        write_tax_id(&db, "hub-1", "B12345678").await.unwrap();
        emitted(&db, "hub-1", "B12345678").await;

        let mut updates = serde_json::Map::new();
        // The same identifier the user is looking at, as the form sends it (spaces, lower case).
        updates.insert("business_tax_id".into(), json!(" b12345678 "));
        updates.insert("business_legal_name".into(), json!("Bar Manolo SL"));
        updates.insert("business_address".into(), json!("Calle Nueva 1"));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .expect("re-posting the same identifier is not a change of taxpayer");

        assert_eq!(result["business_tax_id"], json!("B12345678"));
        assert_eq!(result["business_legal_name"], json!("Bar Manolo SL"));
        assert_eq!(result["business_address"], json!("Calle Nueva 1"));
    }

    /// The first record freezes the IDENTIFIER and nothing else. `business_legal_name` anchors
    /// nothing —the chain does not hang from it— and a business that changes its trade name after
    /// going live has to be able to say so.
    #[tokio::test]
    async fn the_first_record_freezes_the_identifier_and_nothing_else() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        write_tax_id(&db, "hub-1", "B12345678").await.unwrap();
        emitted(&db, "hub-1", "B12345678").await;

        let mut updates = serde_json::Map::new();
        updates.insert("business_legal_name".into(), json!("Bar Manolo SLU"));
        updates.insert("currency".into(), json!("USD"));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .expect("only the identifier is frozen");
        assert_eq!(result["business_legal_name"], json!("Bar Manolo SLU"));
        assert_eq!(result["currency"], json!("USD"));
    }

    /// 🔴 **Volver al ancla se permite — si no, la guarda es una trampa.** A hub whose setting
    /// ended up empty (restoring a PROPIA backup taken before it was filled in) could otherwise
    /// never write it again… and with it empty the fiscal precondition of ADR-0203 refuses to
    /// issue anything. Writing exactly the identifier the chain hangs from is not changing
    /// taxpayer: it is stopping the divergence. A THIRD identifier is still refused.
    #[tokio::test]
    async fn a_hub_can_always_write_back_the_identifier_its_chain_is_anchored_to() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        write_tax_id(&db, "hub-1", "B12345678").await.unwrap();
        emitted(&db, "hub-1", "B12345678").await;
        // The setting is gone; the anchor in the profile is not.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("hub-1"));
        db.execute(
            "DELETE FROM hub_settings WHERE hub_id = :hub_id AND key = 'business_tax_id'",
            &p,
        )
        .await
        .unwrap();

        let result = write_tax_id(&db, "hub-1", "B12345678")
            .await
            .expect("writing back the anchor is not a change of taxpayer");
        assert_eq!(result["business_tax_id"], json!("B12345678"));

        // …and a THIRD identifier is still refused: the way back is to the anchor, not anywhere.
        let err = write_tax_id(&db, "hub-1", "B99999999").await.unwrap_err();
        assert_eq!(
            crate::error_registry::error_code_of(&err),
            "business_tax_id_frozen",
            "{err:?}"
        );
    }

    /// 🔴 **Un hub sin perfil fiscal escribe igual.** El congelado no puede convertirse en un
    /// requisito nuevo para escribir settings: si `_hub_fiscal_profile` no existe todavía (un hub a
    /// medio bootstrapear, o cualquier prueba que levante `hub_settings` a mano), la escritura pasa.
    /// `first_record_at` vive en esa tabla y en ninguna otra, así que un perfil que no se puede leer
    /// no es «no sé si emitió»: es que **no consta** que emitiera.
    #[tokio::test]
    async fn a_hub_with_no_fiscal_profile_yet_writes_its_tax_id() {
        let db = fresh_db().await;
        ensure_table(&db).await; // solo `hub_settings`, como antes de las migraciones de sistema

        let result = write_tax_id(&db, "hub-1", "B12345678")
            .await
            .expect("the freeze must not become a new requirement to write settings");
        assert_eq!(result["business_tax_id"], json!("B12345678"));
    }

    /// 🔴 The refusal takes the WHOLE batch, like every other rejection in this door: hiding the
    /// new tax id among innocent keys must not land half of them.
    #[tokio::test]
    async fn a_frozen_tax_id_refuses_the_whole_batch() {
        let db = fresh_db().await;
        booted(&db, "hub-1").await;
        write_tax_id(&db, "hub-1", "B12345678").await.unwrap();
        emitted(&db, "hub-1", "B12345678").await;

        let mut updates = serde_json::Map::new();
        updates.insert("currency".into(), json!("USD"));
        updates.insert("business_tax_id".into(), json!("B99999999"));
        let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .unwrap_err();
        assert_eq!(
            crate::error_registry::error_code_of(&err),
            "business_tax_id_frozen",
            "{err:?}"
        );

        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["currency"], json!("EUR"), "the batch is refused whole");
        assert_eq!(all["business_tax_id"], json!("B12345678"));
    }

    /// 🔴 Un hub REAL no puede DECLARARSE demo. Ser demo no es un setting: no hay clave que
    /// escribir, así que el intento muere en «clave desconocida». Si lo fuera, cualquier admin
    /// podría apagar sus propias obligaciones fiscales desde Ajustes.
    #[tokio::test]
    async fn being_a_demo_is_not_something_a_hub_can_switch_on() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        for key in ["demo", "is_demo", "demo_hub"] {
            let mut updates = serde_json::Map::new();
            updates.insert(key.into(), json!(true));
            let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
                .await
                .unwrap_err();
            assert!(
                matches!(err, RuntimeError::InvalidPayload { .. }),
                "`{key}` must not be a setting: {err:?}"
            );
        }
        assert!(
            !KNOWN.iter().any(|s| s.key.contains("demo")),
            "the demo marker is the deployment's (HUB_DEMO), never a row anyone can write"
        );
    }

    // ── «Show PIN pad» + idle lock (hub#628) ────────────────────────────────────────────
    //
    // The Settings card became a toggle + an idle range (1 · 5 · 10 · 15 · 30 · until sign-out).
    // The wire keeps the closed `pin_policy` set; the ONE new key is `pin_inactivity_minutes`:
    // how many minutes of inactivity before the shell signs the user out and shows the pinpad.
    // It only matters while `pin_policy = always`; the server-side TTL backstop is unchanged.

    #[tokio::test]
    async fn pin_inactivity_minutes_defaults_to_five() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["pin_inactivity_minutes"], json!(5));
    }

    #[tokio::test]
    async fn pin_inactivity_minutes_accepts_a_minute_count_and_persists_it() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        // The UI offers 1/5/10/15/30, but the door validates a RANGE (1..=30), not the UI's
        // stops: the stops are presentation, and a future numeric input must not need a
        // runtime release.
        for n in [1, 5, 10, 15, 30, 7] {
            let mut updates = serde_json::Map::new();
            updates.insert("pin_inactivity_minutes".into(), json!(n));
            let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
                .await
                .unwrap();
            assert_eq!(result["pin_inactivity_minutes"], json!(n));
        }
    }

    #[tokio::test]
    async fn pin_inactivity_minutes_rejects_what_is_not_a_minute_count() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        for bad in [
            json!(0),
            json!(31),
            json!(-3),
            json!(2.5),
            json!("five"),
            json!(true),
            Value::Null,
        ] {
            let mut updates = serde_json::Map::new();
            updates.insert("pin_inactivity_minutes".into(), bad.clone());
            let err = set_many(&db, "hub-1", &updates, "hub_user:1", false)
                .await
                .unwrap_err();
            assert!(
                matches!(err, RuntimeError::InvalidPayload { .. }),
                "`{bad}` must be refused: {err:?}"
            );
        }
        // And the refusals above are about the VALUE, not an unknown key: a sane write lands.
        let mut updates = serde_json::Map::new();
        updates.insert("pin_inactivity_minutes".into(), json!(10));
        let result = set_many(&db, "hub-1", &updates, "hub_user:1", false)
            .await
            .unwrap();
        assert_eq!(result["pin_inactivity_minutes"], json!(10));
    }

    // ── THE BUSINESS CLOCK (hub#731) ──────────────────────────────────────────────────────────
    //
    // «Cierra la caja a las 21:00» has to be 21:00 in the shop. The zone is NOT a new question
    // asked to the owner: it is derived from the `country_code` they already answered when they
    // set up the hub, and the explicit setting only exists for the countries a country cannot
    // answer for (a country with several zones) — and it is what makes the derivation auditable.

    #[test]
    fn the_zone_comes_from_the_country_the_hub_already_declared() {
        assert_eq!(zone_for_country("ES", ""), chrono_tz::Europe::Madrid);
        assert_eq!(zone_for_country("PT", ""), chrono_tz::Europe::Lisbon);
        assert_eq!(zone_for_country("FR", ""), chrono_tz::Europe::Paris);
        // …and the region breaks the tie where the country cannot: Canarias is NOT Madrid, and a
        // hub in Las Palmas closing the till at 21:00 would otherwise close it at 20:00.
        assert_eq!(zone_for_country("ES", "ES-CN"), chrono_tz::Atlantic::Canary);
        assert_eq!(zone_for_country("PT", "PT-20"), chrono_tz::Atlantic::Azores);
        assert_eq!(zone_for_country("PT", "PT-30"), chrono_tz::Atlantic::Madeira);
    }

    #[test]
    fn a_country_with_several_zones_stays_utc_until_the_hub_says_which_one() {
        // Guessing "the biggest city" for the US or Brazil would be the same silent wrong answer
        // this issue is about. UTC + an explicit setting is the honest one.
        for country in ["US", "BR", "CA", "AU", "RU", "XX"] {
            assert_eq!(zone_for_country(country, ""), chrono_tz::UTC, "{country}");
        }
    }

    #[test]
    fn a_timezone_is_a_real_iana_name_or_it_is_refused() {
        assert_eq!(
            validate_timezone(&json!("Europe/Madrid")),
            Ok("Europe/Madrid".to_string())
        );
        assert_eq!(validate_timezone(&Value::Null), Ok(String::new()));
        assert_eq!(validate_timezone(&json!("")), Ok(String::new()));
        for bad in [json!("Europa/Madrid"), json!("CEST"), json!("+02:00"), json!(2)] {
            assert!(validate_timezone(&bad).is_err(), "{bad}");
        }
    }

    #[tokio::test]
    async fn the_hub_zone_is_derived_unless_it_is_declared() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        // Nothing stored: the default country (`ES`) answers.
        assert_eq!(timezone_of(&db, "hub-1").await.unwrap(), chrono_tz::Europe::Madrid);

        let mut updates = serde_json::Map::new();
        updates.insert("country_code".into(), json!("PT"));
        set_many(&db, "hub-1", &updates, "hub_user:1", false).await.unwrap();
        assert_eq!(timezone_of(&db, "hub-1").await.unwrap(), chrono_tz::Europe::Lisbon);

        // An explicit zone WINS over the derivation — that is the point of having it.
        let mut updates = serde_json::Map::new();
        updates.insert("timezone".into(), json!("Atlantic/Azores"));
        set_many(&db, "hub-1", &updates, "hub_user:1", false).await.unwrap();
        assert_eq!(timezone_of(&db, "hub-1").await.unwrap(), chrono_tz::Atlantic::Azores);

        // …and a garbage row degrades to the derivation instead of exploding at 3 AM.
        db.execute_batch(
            "UPDATE hub_settings SET value = 'Marte/Olympus' \
             WHERE hub_id = 'hub-1' AND key = 'timezone';",
        )
        .await
        .unwrap();
        assert_eq!(timezone_of(&db, "hub-1").await.unwrap(), chrono_tz::Europe::Lisbon);
    }

    // ── The DEMO boots with its fiscal identity ALREADY filled in (hub#684) ───────────────
    //
    // The checklist and the fiscal gate read the SAME two settings, so the only way to clear the
    // demo's ⛔ without making one of them lie is to put the data there for real.

    /// 🔴 A demo hub is handed a fiscal identity at boot, so the gate of ADR-0203 has something to
    /// read and the ⛔ item is genuinely done — not hidden, not faked.
    #[tokio::test]
    async fn a_demo_hub_boots_with_its_fiscal_identity_already_filled_in() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        let seeded = ensure_demo_fiscal_identity(&db, "hub-1").await.unwrap();
        assert!(seeded, "the demo had nothing: the boot fills it in");

        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["business_tax_id"], json!(DEMO_BUSINESS_TAX_ID));
        assert_eq!(all["business_legal_name"], json!(DEMO_BUSINESS_LEGAL_NAME));
        assert_ne!(all["business_address"], json!(""), "a demo ticket carries an address too");
    }

    /// Idempotent, and it never overwrites: re-running the boot is a no-op, and whatever the hub
    /// already had is left exactly as it was.
    #[tokio::test]
    async fn seeding_the_demo_identity_never_overwrites_what_is_already_there() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        assert!(ensure_demo_fiscal_identity(&db, "hub-1").await.unwrap());
        // A second boot writes nothing…
        assert!(!ensure_demo_fiscal_identity(&db, "hub-1").await.unwrap());

        // …and neither does it clobber an identity that got there another way (a blueprint of the
        // hub's own, a restore). Whoever wrote it meant it more than a default does.
        db.execute_batch(
            "UPDATE hub_settings SET value = 'B99999999' \
             WHERE hub_id = 'hub-1' AND key = 'business_tax_id';",
        )
        .await
        .unwrap();
        assert!(!ensure_demo_fiscal_identity(&db, "hub-1").await.unwrap());
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["business_tax_id"], json!("B99999999"));
    }

    /// 🔴 The other direction, and the expensive one: a REAL hub is never handed an identity. A
    /// paying business that found a tax id it never typed would invoice under it — and ADR-0273
    /// freezes it at the first record, so the mistake would be permanent.
    #[tokio::test]
    async fn a_real_hub_is_never_handed_a_fiscal_identity() {
        let db = fresh_db().await;
        ensure_table(&db).await;

        // The seeding function is demo-only by construction: the runtime gates it on `demo_hub`,
        // and that gate is what this asserts — a real hub keeps its empty identity, which is the
        // pending ⛔ its owner has to clear.
        let rt = crate::Runtime::with_hub_id(Box::new(fresh_db().await), "hub-real");
        rt.ensure_system_tables().await.unwrap();
        assert!(!rt.is_demo_hub(), "the default of a runtime is a REAL hub");
        assert!(!rt.ensure_demo_fiscal_identity().await.unwrap());
        let all = get_all(rt.db(), "hub-real").await.unwrap();
        assert_eq!(all["business_tax_id"], json!(""));
        assert_eq!(all["business_legal_name"], json!(""));
        let _ = &db;
    }

    /// …and the demo half of the same door: the runtime DOES seed it when the marker is sealed.
    #[tokio::test]
    async fn the_runtime_seeds_the_identity_only_when_the_demo_marker_is_sealed() {
        let mut rt = crate::Runtime::with_hub_id(Box::new(fresh_db().await), "hub-demo");
        rt.ensure_system_tables().await.unwrap();
        rt.set_demo_hub(true);
        assert!(rt.ensure_demo_fiscal_identity().await.unwrap());
        let all = get_all(rt.db(), "hub-demo").await.unwrap();
        assert_eq!(all["business_tax_id"], json!(DEMO_BUSINESS_TAX_ID));
    }

    #[tokio::test]
    async fn a_corrupt_pin_inactivity_row_degrades_to_the_default() {
        let db = fresh_db().await;
        ensure_table(&db).await;
        db.execute_batch(
            "INSERT INTO hub_settings (hub_id, key, value, updated_at, updated_by) \
             VALUES ('hub-1', 'pin_inactivity_minutes', 'soon', '2026-01-01T00:00:00Z', 'x');",
        )
        .await
        .unwrap();
        let all = get_all(&db, "hub-1").await.unwrap();
        assert_eq!(all["pin_inactivity_minutes"], json!(5), "corrupt row → default");
    }
}
