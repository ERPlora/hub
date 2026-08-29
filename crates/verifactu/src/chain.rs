//! Cadena de hash VeriFactu (RD 1007/2023): formatos AEAT + huella SHA-256 + URL del QR.
//!
//! ⚠️ Compliance: los formatos (`format_date` DD-MM-YYYY, `format_amount` 2 decimales con
//! punto, `format_timestamp` ISO-8601 con huso) replican EXACTAMENTE la especificación de
//! la AEAT (detalle técnico de la huella, Orden HAC/1177/2024). Cualquier desviación rompe
//! la validación de la AEAT y la cadena (WASM-TODO.md §1 del módulo `verifactu`).
use sha2::{Digest, Sha256};

/// `FechaExpedicionFactura`: ISO `YYYY-MM-DD` → `DD-MM-YYYY`.
pub fn format_date(iso: &str) -> String {
    let parts: Vec<&str> = iso.split('-').collect();
    if parts.len() == 3 {
        format!("{}-{}-{}", parts[2], parts[1], parts[0])
    } else {
        iso.to_string()
    }
}

/// Importes AEAT: 2 decimales, punto como separador (`{:.2}` redondea half-to-even,
/// como `Decimal.quantize` de la implementación original).
pub fn format_amount(x: f64) -> String {
    format!("{x:.2}")
}

/// `FechaHoraHusoGenRegistro`: ISO-8601 con huso, segundos enteros (sin fracción),
/// p. ej. `2026-06-10T12:34:56+00:00`. Normaliza el `now` RFC3339 que inyecta el host.
pub fn format_timestamp(rfc3339: &str) -> String {
    chrono::DateTime::parse_from_rfc3339(rfc3339)
        .map(|dt| dt.to_rfc3339_opts(chrono::SecondsFormat::Secs, false))
        .unwrap_or_else(|_| rfc3339.to_string())
}

/// Huella SHA-256 de un registro de **alta** (hex mayúsculas).
#[allow(clippy::too_many_arguments)]
pub fn alta_hash(
    issuer_nif: &str,
    invoice_number: &str,
    invoice_date_iso: &str,
    invoice_type: &str,
    tax_amount: f64,
    total_amount: f64,
    previous_hash: &str,
    generation_timestamp: &str,
) -> String {
    let input = format!(
        "IDEmisorFactura={issuer_nif}&NumSerieFactura={invoice_number}\
         &FechaExpedicionFactura={fecha}&TipoFactura={invoice_type}\
         &CuotaTotal={cuota}&ImporteTotal={importe}\
         &Huella={previous_hash}&FechaHoraHusoGenRegistro={generation_timestamp}",
        fecha = format_date(invoice_date_iso),
        cuota = format_amount(tax_amount),
        importe = format_amount(total_amount),
    );
    sha256_upper(&input)
}

/// Huella SHA-256 de un registro de **anulación** (sin TipoFactura/CuotaTotal/ImporteTotal).
///
/// hub#1330: los nombres de campo de la anulación NO son los del alta — la AEAT fija para
/// `RegistroAnulacion/IDFactura` los nombres `IDEmisorFacturaAnulada`/`NumSerieFacturaAnulada`/
/// `FechaExpedicionFacturaAnulada` («Detalle de las especificaciones técnicas para generación
/// de la huella o hash de los registros de facturación», v0.1.2, 27/08/2024, §3.b), ya
/// reflejados en el XML que emite `aeat.rs` (`build_soap`, bloque `RegistroAnulacion`).
pub fn anulacion_hash(
    issuer_nif: &str,
    invoice_number: &str,
    invoice_date_iso: &str,
    previous_hash: &str,
    generation_timestamp: &str,
) -> String {
    let input = format!(
        "IDEmisorFacturaAnulada={issuer_nif}&NumSerieFacturaAnulada={invoice_number}\
         &FechaExpedicionFacturaAnulada={fecha}\
         &Huella={previous_hash}&FechaHoraHusoGenRegistro={generation_timestamp}",
        fecha = format_date(invoice_date_iso),
    );
    sha256_upper(&input)
}

fn sha256_upper(input: &str) -> String {
    let mut hasher = Sha256::new();
    hasher.update(input.as_bytes());
    format!("{:X}", hasher.finalize())
}

/// Una huella VeriFactu válida es **64 caracteres hex** (SHA-256). Se usa al importar/recuperar
/// un hash de otra aplicación o de la AEAT (`recover_manual`) — no aceptar basura como ancla.
pub fn is_valid_hash(s: &str) -> bool {
    s.len() == 64 && s.bytes().all(|b| b.is_ascii_hexdigit())
}

/// Normaliza una huella importada a la forma canónica del módulo (hex en MAYÚSCULAS).
pub fn normalize_hash(s: &str) -> String {
    s.trim().to_ascii_uppercase()
}

/// URL de verificación del QR AEAT (WASM-TODO.md §4). El **host depende del entorno** (igual que el
/// Cloud, `verifactu_qr.py`): `production` → www2.agenciatributaria.gob.es; testing → prewww2.aeat.es.
/// Un QR de pruebas con el host de producción NO validaría. Solo el string; el render lo hace la UI
/// (`ok-qr`, JS puro CSP-safe).
pub fn qr_url(
    issuer_nif: &str,
    invoice_number: &str,
    invoice_date_iso: &str,
    total: f64,
    environment: &str,
) -> String {
    let host = if environment == "production" {
        "https://www2.agenciatributaria.gob.es"
    } else {
        "https://prewww2.aeat.es"
    };
    format!(
        "{host}/wlpl/TIKE-CONT/ValidarQR?nif={}&numserie={}&fecha={}&importe={}",
        url_encode(issuer_nif),
        url_encode(invoice_number),
        url_encode(&format_date(invoice_date_iso)),
        url_encode(&format_amount(total)),
    )
}

/// Percent-encoding mínimo (RFC 3986 unreserved) para los valores de la query del QR.
fn url_encode(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}
