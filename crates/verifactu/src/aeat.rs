//! Transmisión a la AEAT (VERI*FACTU): construcción del XML SOAP
//! `RegFactuSistemaFacturacion`, identidad cliente desde el certificado **PKCS#12** y
//! POST con **TLS mutua** al endpoint según `config.environment`.
//!
//! Nota de cumplimiento: en modalidad **VERI*FACTU** (la que implementa este módulo,
//! `mode='verifactu'`) los registros **no** llevan firma XAdES — la autenticación es el
//! certificado en el canal TLS (la firma electrónica del registro solo se exige en la
//! modalidad "NO VERI*FACTU"). Por eso "firma PKCS#12" == identidad cliente TLS.
use serde_json::Value as Json;

use crate::chain::{format_amount, format_date};
use crate::VerifactuError;

/// Endpoint SOAP del sistema de facturación VERI*FACTU por entorno.
/// `testing` (prewww1.aeat.es) es el **default** del módulo (config.environment).
pub fn endpoint(environment: &str) -> &'static str {
    match environment {
        "production" => {
            "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        }
        _ => "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    }
}

/// Escapa texto para XML.
fn esc(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&apos;")
}

fn s(v: &Json, k: &str) -> String {
    v.get(k).and_then(|x| x.as_str()).unwrap_or_default().to_string()
}

fn f(v: &Json, k: &str) -> f64 {
    match v.get(k) {
        Some(Json::Number(n)) => n.as_f64().unwrap_or(0.0),
        Some(Json::String(t)) => t.trim().parse().unwrap_or(0.0),
        _ => 0.0,
    }
}

/// Bloque `Encadenamiento`: primer registro o referencia al registro anterior.
fn encadenamiento(record: &Json, prev: Option<&Json>) -> String {
    let is_first = record
        .get("is_first_record")
        .map(|v| v.as_i64().unwrap_or(0) != 0 || v.as_bool().unwrap_or(false))
        .unwrap_or(false);
    match (is_first, prev) {
        (true, _) | (false, None) => {
            "<sum1:Encadenamiento><sum1:PrimerRegistro>S</sum1:PrimerRegistro></sum1:Encadenamiento>"
                .to_string()
        }
        (false, Some(p)) => format!(
            "<sum1:Encadenamiento><sum1:RegistroAnterior>\
             <sum1:IDEmisorFactura>{}</sum1:IDEmisorFactura>\
             <sum1:NumSerieFactura>{}</sum1:NumSerieFactura>\
             <sum1:FechaExpedicionFactura>{}</sum1:FechaExpedicionFactura>\
             <sum1:Huella>{}</sum1:Huella>\
             </sum1:RegistroAnterior></sum1:Encadenamiento>",
            esc(&s(p, "issuer_nif")),
            esc(&s(p, "invoice_number")),
            esc(&format_date(&s(p, "invoice_date"))),
            esc(&s(p, "record_hash")),
        ),
    }
}

/// Bloque `SistemaInformatico` (identificación del software, config del hub).
fn sistema_informatico(config: &Json, hub_id: &str) -> String {
    format!(
        "<sum1:SistemaInformatico>\
         <sum1:NombreRazon>{name}</sum1:NombreRazon>\
         <sum1:NIF>{nif}</sum1:NIF>\
         <sum1:NombreSistemaInformatico>{name}</sum1:NombreSistemaInformatico>\
         <sum1:IdSistemaInformatico>{id}</sum1:IdSistemaInformatico>\
         <sum1:Version>{version}</sum1:Version>\
         <sum1:NumeroInstalacion>{hub}</sum1:NumeroInstalacion>\
         <sum1:TipoUsoPosibleSoloVerifactu>S</sum1:TipoUsoPosibleSoloVerifactu>\
         <sum1:TipoUsoPosibleMultiOT>S</sum1:TipoUsoPosibleMultiOT>\
         <sum1:IndicadorMultiplesOT>N</sum1:IndicadorMultiplesOT>\
         </sum1:SistemaInformatico>",
        name = esc(&s(config, "software_name")),
        nif = esc(&s(config, "software_nif")),
        id = esc(&s(config, "software_id")),
        version = esc(&s(config, "software_version")),
        hub = esc(hub_id),
    )
}

/// Construye el sobre SOAP `RegFactuSistemaFacturacion` para un registro (alta/anulación).
/// `prev` = registro anterior de la cadena (para `Encadenamiento`), si lo hay.
pub fn build_soap(record: &Json, config: &Json, prev: Option<&Json>, hub_id: &str) -> String {
    let record_type = s(record, "record_type");
    let gen_ts = s(record, "generation_timestamp");
    let registro = if record_type == "anulacion" {
        format!(
            "<sum1:RegistroAnulacion><sum1:IDVersion>1.0</sum1:IDVersion>\
             <sum1:IDFactura>\
             <sum1:IDEmisorFacturaAnulada>{nif}</sum1:IDEmisorFacturaAnulada>\
             <sum1:NumSerieFacturaAnulada>{num}</sum1:NumSerieFacturaAnulada>\
             <sum1:FechaExpedicionFacturaAnulada>{fecha}</sum1:FechaExpedicionFacturaAnulada>\
             </sum1:IDFactura>\
             {chain}{sistema}\
             <sum1:FechaHoraHusoGenRegistro>{ts}</sum1:FechaHoraHusoGenRegistro>\
             <sum1:TipoHuella>01</sum1:TipoHuella>\
             <sum1:Huella>{hash}</sum1:Huella>\
             </sum1:RegistroAnulacion>",
            nif = esc(&s(record, "issuer_nif")),
            num = esc(&s(record, "invoice_number")),
            fecha = esc(&format_date(&s(record, "invoice_date"))),
            chain = encadenamiento(record, prev),
            sistema = sistema_informatico(config, hub_id),
            ts = esc(&gen_ts),
            hash = esc(&s(record, "record_hash")),
        )
    } else {
        format!(
            "<sum1:RegistroAlta><sum1:IDVersion>1.0</sum1:IDVersion>\
             <sum1:IDFactura>\
             <sum1:IDEmisorFactura>{nif}</sum1:IDEmisorFactura>\
             <sum1:NumSerieFactura>{num}</sum1:NumSerieFactura>\
             <sum1:FechaExpedicionFactura>{fecha}</sum1:FechaExpedicionFactura>\
             </sum1:IDFactura>\
             <sum1:NombreRazonEmisor>{issuer_name}</sum1:NombreRazonEmisor>\
             <sum1:TipoFactura>{tipo}</sum1:TipoFactura>\
             <sum1:DescripcionOperacion>{desc}</sum1:DescripcionOperacion>\
             <sum1:Desglose><sum1:DetalleDesglose>\
             <sum1:Impuesto>01</sum1:Impuesto>\
             <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
             <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
             <sum1:TipoImpositivo>{tax_rate}</sum1:TipoImpositivo>\
             <sum1:BaseImponibleOimporteNoSujeto>{base}</sum1:BaseImponibleOimporteNoSujeto>\
             <sum1:CuotaRepercutida>{cuota}</sum1:CuotaRepercutida>\
             </sum1:DetalleDesglose></sum1:Desglose>\
             <sum1:CuotaTotal>{cuota}</sum1:CuotaTotal>\
             <sum1:ImporteTotal>{total}</sum1:ImporteTotal>\
             {chain}{sistema}\
             <sum1:FechaHoraHusoGenRegistro>{ts}</sum1:FechaHoraHusoGenRegistro>\
             <sum1:TipoHuella>01</sum1:TipoHuella>\
             <sum1:Huella>{hash}</sum1:Huella>\
             </sum1:RegistroAlta>",
            nif = esc(&s(record, "issuer_nif")),
            num = esc(&s(record, "invoice_number")),
            fecha = esc(&format_date(&s(record, "invoice_date"))),
            issuer_name = esc(&s(record, "issuer_name")),
            tipo = esc(&s(record, "invoice_type")),
            desc = esc(&s(record, "description")),
            // tax_rate es % (REAL) → se formatea tal cual. Los importes están en CÉNTIMOS
            // (INTEGER, ADR-0007) y la AEAT exige euros con 2 decimales → /100.0 en el límite.
            tax_rate = format_amount(f(record, "tax_rate")),
            base = format_amount(f(record, "base_amount") / 100.0),
            cuota = format_amount(f(record, "tax_amount") / 100.0),
            total = format_amount(f(record, "total_amount") / 100.0),
            chain = encadenamiento(record, prev),
            sistema = sistema_informatico(config, hub_id),
            ts = esc(&gen_ts),
            hash = esc(&s(record, "record_hash")),
        )
    };

    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
         <soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" \
         xmlns:sum=\"https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroLR.xsd\" \
         xmlns:sum1=\"https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd\">\
         <soapenv:Header/><soapenv:Body>\
         <sum:RegFactuSistemaFacturacion>\
         <sum:Cabecera><sum1:ObligadoEmision>\
         <sum1:NombreRazon>{obligado}</sum1:NombreRazon>\
         <sum1:NIF>{nif}</sum1:NIF>\
         </sum1:ObligadoEmision></sum:Cabecera>\
         <sum:RegistroFactura>{registro}</sum:RegistroFactura>\
         </sum:RegFactuSistemaFacturacion>\
         </soapenv:Body></soapenv:Envelope>",
        obligado = esc(&s(record, "issuer_name")),
        nif = esc(&s(record, "issuer_nif")),
        registro = registro,
    )
}

/// Identidad TLS cliente desde un contenedor PKCS#12: parsea clave + cadena de
/// certificados (Rust puro, `p12-keystore`) y la entrega a rustls como PEM.
pub fn identity_from_pkcs12(der: &[u8], password: &str) -> Result<reqwest::Identity, VerifactuError> {
    use base64::Engine as _;
    let store = p12_keystore::KeyStore::from_pkcs12(der, password)
        .map_err(|e| VerifactuError::Certificate(format!("PKCS#12 inválido: {e}")))?;
    let (_alias, chain) = store
        .private_key_chain()
        .ok_or_else(|| VerifactuError::Certificate("el PKCS#12 no contiene clave privada".into()))?;

    let b64 = |data: &[u8]| -> String {
        let raw = base64::engine::general_purpose::STANDARD.encode(data);
        raw.as_bytes()
            .chunks(64)
            .map(|c| std::str::from_utf8(c).unwrap_or_default())
            .collect::<Vec<_>>()
            .join("\n")
    };

    let mut pem = format!(
        "-----BEGIN PRIVATE KEY-----\n{}\n-----END PRIVATE KEY-----\n",
        b64(chain.key())
    );
    for cert in chain.chain() {
        pem.push_str(&format!(
            "-----BEGIN CERTIFICATE-----\n{}\n-----END CERTIFICATE-----\n",
            b64(cert.as_der())
        ));
    }
    reqwest::Identity::from_pem(pem.as_bytes())
        .map_err(|e| VerifactuError::Certificate(format!("identidad TLS inválida: {e}")))
}

/// Respuesta AEAT parseada (subconjunto que persiste el módulo).
#[derive(Debug, Default)]
pub struct AeatResponse {
    pub estado_envio: String,
    pub estado_registro: String,
    pub csv: String,
    pub codigo_error: String,
    pub descripcion_error: String,
}

/// Extrae `<*:tag>texto</...>` por búsqueda de sufijo de nombre (las respuestas AEAT van
/// namespaced con prefijos variables; evitamos una dependencia XML completa).
fn xml_text(body: &str, tag: &str) -> String {
    for open in [format!(":{tag}>"), format!("<{tag}>")] {
        if let Some(i) = body.find(&open) {
            let rest = &body[i + open.len()..];
            if let Some(j) = rest.find('<') {
                return rest[..j].trim().to_string();
            }
        }
    }
    String::new()
}

/// Parsea la respuesta SOAP de la AEAT (`RespuestaRegFactuSistemaFacturacion`).
pub fn parse_response(body: &str) -> AeatResponse {
    AeatResponse {
        estado_envio: xml_text(body, "EstadoEnvio"),
        estado_registro: xml_text(body, "EstadoRegistro"),
        csv: xml_text(body, "CSV"),
        codigo_error: xml_text(body, "CodigoErrorRegistro"),
        descripcion_error: xml_text(body, "DescripcionErrorRegistro"),
    }
}

/// POST TLS-mutua del sobre SOAP al endpoint AEAT. Devuelve el cuerpo de la respuesta
/// (estado HTTP 2xx) o un [`VerifactuError::Transmission`].
pub async fn post_soap(
    endpoint_url: &str,
    identity: reqwest::Identity,
    xml: &str,
) -> Result<String, VerifactuError> {
    let client = reqwest::Client::builder()
        .identity(identity)
        .timeout(std::time::Duration::from_secs(30))
        .build()
        .map_err(|e| VerifactuError::Transmission(format!("cliente TLS: {e}")))?;
    let resp = client
        .post(endpoint_url)
        .header("Content-Type", "text/xml;charset=UTF-8")
        .header("SOAPAction", "")
        .body(xml.to_string())
        .send()
        .await
        .map_err(|e| VerifactuError::Transmission(format!("conexión AEAT: {e}")))?;
    let status = resp.status();
    let body = resp
        .text()
        .await
        .map_err(|e| VerifactuError::Transmission(format!("respuesta AEAT: {e}")))?;
    if !status.is_success() {
        return Err(VerifactuError::Transmission(format!(
            "AEAT HTTP {status}: {}",
            body.chars().take(300).collect::<String>()
        )));
    }
    Ok(body)
}
