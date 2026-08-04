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
///
/// ADR-0202 (pending): these hosts are only valid for personal/representative certificates. A
/// **Sello de Entidad** cert — ERPlora's delegated identity — uses a DIFFERENT host pair:
/// `prewww10.aeat.es` / `www10.agenciatributaria.gob.es` (OCA/l10n-spain#4597). Endpoint
/// selection must depend on the certificate kind, not just the environment, or every POST with
/// the delegated cert fails — same failure mode as the invented consult URL (hub#287).
pub fn endpoint(environment: &str) -> &'static str {
    match environment {
        "production" => {
            "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP"
        }
        _ => "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP",
    }
}

/// Endpoint SOAP del **servicio de consulta** VERI*FACTU (`ConsultaFactuSistemaFacturacion`).
///
/// Es el **MISMO** que el de alta. El WSDL oficial (`SistemaFacturacion.wsdl`, servicio
/// `sfVerifactu`) publica la operación de consulta en `VerifactuSOAP`: no tiene URL propia.
///
/// Aquí había una `.../SistemaFacturacion/ConsultaFactuSistemaFacturacion` inventada, con un
/// comentario que pedía verificarla contra el WSDL «antes de producción». Nunca se verificó, y
/// por eso toda consulta —y con ella `recover_from_aeat`, la única recuperación automática de la
/// cadena— devolvía 404 desde siempre (hub#287; el SaaS traía el mismo fallo, saas#1081).
/// Sondeadas ocho rutas con el certificado real contra preproducción: todas 404, y la del alta 200.
pub fn consult_endpoint(environment: &str) -> &'static str {
    endpoint(environment)
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
    v.get(k)
        .and_then(|x| x.as_str())
        .unwrap_or_default()
        .to_string()
}

// ⚠️ Known defect (ADR-0202, design doc §5.5): a missing or malformed amount silently becomes
// 0.00, gets hashed and transmitted. Must become a hard error, not a default.
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

/// Bloque `Destinatarios` (XSD: va tras `DescripcionOperacion` y antes de `Desglose`).
/// La AEAT lo exige para `TipoFactura` F1/F3/R1-R4 (error 1189 si falta); las facturas
/// **simplificadas** (F2) van **sin** destinatario. Se emite solo si el registro trae
/// `recipient_nif` (cliente identificado); si no, devuelve vacío.
fn destinatarios(record: &Json) -> String {
    let nif = s(record, "recipient_nif");
    if nif.is_empty() {
        return String::new();
    }
    let name = {
        let n = s(record, "recipient_name");
        if n.is_empty() {
            nif.clone()
        } else {
            n
        }
    };
    format!(
        "<sum1:Destinatarios><sum1:IDDestinatario>\
         <sum1:NombreRazon>{name}</sum1:NombreRazon>\
         <sum1:NIF>{nif}</sum1:NIF>\
         </sum1:IDDestinatario></sum1:Destinatarios>",
        name = esc(&name),
        nif = esc(&nif),
    )
}

/// Bloque `FacturasSustituidas` (XSD: tras `TipoFactura`, antes de `DescripcionOperacion`).
/// Solo en facturas **F3** (factura completa emitida en SUSTITUCIÓN de una simplificada F2 ya
/// declarada — "el cliente pide factura de un tiquet", ADR-0140): declara la F2 sustituida con su
/// nº+serie, fecha de expedición y NIF del emisor (`IDFacturaARType`, el mismo shape que las
/// rectificadas). Vacío si el registro no trae datos de sustitución (todo lo que no sea F3). No es
/// rectificación: la AEAT no lo trata como tal (el tiquet era correcto), evita el doble cómputo del IVA.
fn facturas_sustituidas(record: &Json) -> String {
    let num = s(record, "substitutes_number");
    if num.is_empty() {
        return String::new();
    }
    let nif = s(record, "substitutes_nif");
    let fecha = format_date(&s(record, "substitutes_date"));
    format!(
        "<sum1:FacturasSustituidas><sum1:IDFacturaSustituida>\
         <sum1:IDEmisorFactura>{nif}</sum1:IDEmisorFactura>\
         <sum1:NumSerieFactura>{num}</sum1:NumSerieFactura>\
         <sum1:FechaExpedicionFactura>{fecha}</sum1:FechaExpedicionFactura>\
         </sum1:IDFacturaSustituida></sum1:FacturasSustituidas>",
        nif = esc(&nif),
        num = esc(&num),
        fecha = esc(&fecha),
    )
}

/// Bloque `SistemaInformatico` (identificación del software, config del hub).
///
/// La identidad del PRODUCTOR del software (ERPlora) es FIJA — la misma para todos los hubs, lo
/// declara la AEAT. Si la config del módulo no la trae (fila vacía/stale), usamos el fallback
/// hardcodeado en vez de emitir un NIF vacío (que la AEAT rechaza con error 1100).
///
/// ADR-0202 (pending): `IndicadorMultiplesOT` is hardcoded to `N` below, but the AEAT developer
/// FAQ requires computing it PER SaaS ACCOUNT — `S` when the account runs more than one
/// facturación, same or different NIF. The hub cannot know that count: it must arrive from the
/// SaaS as a producer fact (heartbeat / fiscal endpoint), together with the producer identity
/// that today only exists as the hardcoded fallback above. `Version` stays declared by this
/// binary (each hub is pinned to its own digest and must declare what actually runs).
fn sistema_informatico(config: &Json, hub_id: &str) -> String {
    // Fallback del productor: identidad legal de ERPlora como fabricante del software.
    const PRODUCER_NAME: &str = "ERPLORA CLOUD SL";
    const PRODUCER_NIF: &str = "B27593136";
    const PRODUCER_ID: &str = "EC";
    const PRODUCER_VERSION: &str = "1.0.0";

    let name = nonempty(s(config, "software_name"), PRODUCER_NAME);
    let nif = nonempty(s(config, "software_nif"), PRODUCER_NIF);
    // IdSistemaInformatico: la AEAT lo limita a 2 caracteres y es un valor FIJO asignado al
    // software ERPlora. No se lee de la BD (que puede tener valores legacy inválidos como
    // "ERPLORA-001" de 11 chars → la AEAT rechaza con error 1100).
    let id = PRODUCER_ID.to_string();
    let version = nonempty(s(config, "software_version"), PRODUCER_VERSION);

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
        name = esc(&name),
        nif = esc(&nif),
        id = esc(&id),
        version = esc(&version),
        hub = esc(hub_id),
    )
}

/// Devuelve `val` si no está vacío, si no `fallback`.
fn nonempty(val: String, fallback: &str) -> String {
    if val.is_empty() {
        fallback.to_string()
    } else {
        val
    }
}
// ── Desglose: el TIPO y la CALIFICACIÓN ───────────────────────────────────────────────────
//
// Una `DetalleDesglose` tiene DOS ejes y hay que acertar los dos:
//
//   * el **tipo** — cuánto se repercute. Antes se emitía una sola línea con el tipo *efectivo*
//     (`cuota/base`): un ticket con una caña al 21 % y una tapa al 10 % declaraba un 17,33 % que no
//     existe en el sistema fiscal español. Resuelto: una línea por tipo real.
//   * la **calificación** — qué impuesto es, bajo qué régimen, y si la operación está sujeta,
//     exenta o no sujeta. Iba literal (`01`/`01`/`S1`), que describe solo la venta nacional sujeta
//     y no exenta: un hub canario declaraba IGIC como si fuera IVA, un servicio sanitario exento
//     salía como «sujeto al 0 %», el recargo de equivalencia salía como un tipo inventado del
//     5,20 %, y una venta intracomunitaria repercutía IVA español (hub#292).
//
// El `tax_breakdown` que escribe `invoice` es el contrato entre los dos módulos, y su FORMA
// distingue las dos generaciones — las facturas ya emitidas están encadenadas en la huella y no se
// pueden reinterpretar:
//
//   * **objeto** (viejo) `{"21.00":{"base":1000,"tax":210}}` — clave = tipo. Todo se declara como
//     venta nacional sujeta y no exenta, que es lo que aquellas facturas efectivamente eran.
//   * **array** (nuevo) — una entrada por **clave fiscal completa**:
//     ```json
//     {"tax":"vat|igic|ipsi|other", "regime":"01", "class":"subject|subject_reverse|exempt|
//       not_subject|not_subject_location", "exempt_reason":"E1", "rate":21.00,
//       "base":1000, "quota":210, "surcharge_rate":5.20, "surcharge_quota":52}
//     ```
//     `regime` y `exempt_reason` son códigos de la jurisdicción y viajan **opacos** (para España,
//     `ClaveRegimen` de L8A/L8B y `OperacionExenta` de L10): `taxes` los guarda, `invoice` los
//     copia y aquí se emiten tal cual. El vocabulario de `tax`/`class` es el mismo que el del
//     VeriFactu del SaaS (ADR-0183) para que los dos se expliquen igual, pero el código NO se
//     comparte: son emisores, cadenas y certificados distintos a propósito (ADR-0049).
//
// Los importes vienen en CÉNTIMOS (ADR-0007) y la AEAT exige euros con 2 decimales → `/100.0` en el
// límite. Los signos se conservan (las rectificativas llevan base y cuota negativas).

/// `Impuesto` (L1 del diseño de registro). Lo que no se reconozca es IVA, que es el default
/// explícito de la AEAT («o no se cumplimenta, considerándose 01 - IVA»).
fn impuesto_code(kind: &str) -> &'static str {
    match kind.trim().to_ascii_lowercase().as_str() {
        "igic" | "03" => "03",
        "ipsi" | "02" => "02",
        "other" | "otros" | "05" => "05",
        _ => "01",
    }
}

/// Una línea del desglose ya resuelta a códigos de la AEAT. `base`/`quota`/`surcharge_quota` en
/// céntimos; `rate`/`surcharge_rate` en tanto por ciento.
struct Detalle {
    impuesto: &'static str,
    regimen: String,
    /// `S1|S2|N1|N2`, o vacío cuando la línea va por `OperacionExenta` (el XSD es un `<choice>`).
    calificacion: &'static str,
    /// `E1…E8`, o vacío si la línea lleva `CalificacionOperacion`.
    exenta: String,
    rate: f64,
    base: f64,
    quota: f64,
    surcharge_rate: f64,
    surcharge_quota: f64,
    has_surcharge: bool,
}

impl Detalle {
    /// Línea del formato viejo (y del fallback sin desglose): venta nacional, régimen general,
    /// sujeta y no exenta.
    fn nacional(rate: f64, base: f64, quota: f64) -> Self {
        Detalle {
            impuesto: "01",
            regimen: "01".to_string(),
            calificacion: "S1",
            exenta: String::new(),
            rate,
            base,
            quota,
            surcharge_rate: 0.0,
            surcharge_quota: 0.0,
            has_surcharge: false,
        }
    }

    /// ¿Se pueden informar tipo, cuota y recargo en esta línea?
    ///
    /// - **Exenta** — no (§15.5: con `OperacionExenta` no se informan `TipoImpositivo`,
    ///   `CuotaRepercutida`, `TipoRecargoEquivalencia` ni `CuotaRecargoEquivalencia`).
    /// - **N1/N2** — no. Es el **error 1237**, y hay que resistir la tentación de la excepción por
    ///   `ClaveRegimen 17`: la revisión **v1.0.6 (25/04/2025)** del documento de validaciones la
    ///   **eliminó** («eliminando las referencias a la clave de régimen 17 en la clasificación
    ///   operación N1/N2»), y §15.7 lo remata sin excepciones — «CuotaRepercutida solo podrá ser
    ///   distinta de cero si CalificacionOperacion es S1». Formalmente 1237 solo acota el IVA, pero
    ///   §15.7 no distingue impuesto, así que la regla se aplica igual con IGIC/IPSI.
    /// - **S1/S2** — sí. Ojo con S2: no es «omitir», es informar **ceros explícitos** (§15.4).
    fn con_importes(&self) -> bool {
        self.exenta.is_empty() && !matches!(self.calificacion, "N1" | "N2")
    }

    fn render(&self) -> String {
        // Orden fijado por el `xs:sequence` de `DetalleType` en SuministroInformacion.xsd.
        let mut out = format!(
            "<sum1:DetalleDesglose>\
             <sum1:Impuesto>{imp}</sum1:Impuesto>",
            imp = self.impuesto,
        );
        if !self.regimen.is_empty() {
            out.push_str(&format!(
                "<sum1:ClaveRegimen>{}</sum1:ClaveRegimen>",
                esc(&self.regimen)
            ));
        }
        // `<choice>`: uno de los dos, nunca los dos.
        if self.exenta.is_empty() {
            out.push_str(&format!(
                "<sum1:CalificacionOperacion>{}</sum1:CalificacionOperacion>",
                self.calificacion
            ));
        } else {
            out.push_str(&format!(
                "<sum1:OperacionExenta>{}</sum1:OperacionExenta>",
                esc(&self.exenta)
            ));
        }
        let con_importes = self.con_importes();
        if con_importes {
            out.push_str(&format!(
                "<sum1:TipoImpositivo>{}</sum1:TipoImpositivo>",
                format_amount(self.rate)
            ));
        }
        // El único elemento obligatorio del detalle. En una operación no sujeta o exenta no es «la
        // base de un impuesto que no hay»: es el IMPORTE de la operación (el nombre del campo lo
        // dice, `BaseImponible` **O** `importeNoSujeto`), y el productor lo manda ya así.
        out.push_str(&format!(
            "<sum1:BaseImponibleOimporteNoSujeto>{}</sum1:BaseImponibleOimporteNoSujeto>",
            format_amount(self.base / 100.0)
        ));
        if con_importes {
            out.push_str(&format!(
                "<sum1:CuotaRepercutida>{}</sum1:CuotaRepercutida>",
                format_amount(self.quota / 100.0)
            ));
            // Recargo de equivalencia: NO es otro tipo impositivo, son dos campos MÁS dentro de la
            // misma línea del IVA. Emitirlo como una `DetalleDesglose` aparte manda un
            // `TipoImpositivo` de 5,20 %, que no está en la lista de tipos que admite la AEAT
            // (§15.1: 0; 2; 4; 5; 7,5; 10; 21) — rechazo garantizado.
            //
            // La restricción de tener que usar `ClaveRegimen 18` para informarlo **ya no existe**:
            // v1.0.7 (26/05/2025) la eliminó y v1.1.2 (15/07/2025) borró la sección entera. Los
            // listados de errores de terceros que la repiten (1279/1280) están desfasados.
            if self.has_surcharge {
                out.push_str(&format!(
                    "<sum1:TipoRecargoEquivalencia>{}</sum1:TipoRecargoEquivalencia>\
                     <sum1:CuotaRecargoEquivalencia>{}</sum1:CuotaRecargoEquivalencia>",
                    format_amount(self.surcharge_rate),
                    format_amount(self.surcharge_quota / 100.0),
                ));
            }
        }
        out.push_str("</sum1:DetalleDesglose>");
        out
    }
}

/// El XSD limita `DetalleDesglose` a `maxOccurs="12"`. Pasarse es un rechazo por esquema (4102),
/// y el registro ya habría gastado su número.
const MAX_DETALLES: usize = 12;

/// Traduce una entrada del array a códigos de la AEAT.
fn detalle_de_entrada(e: &Json) -> Detalle {
    let impuesto = impuesto_code(&s(e, "tax"));
    // §15.6: `ClaveRegimen` es obligatoria con IVA e IGIC, y el régimen general es `01`.
    let regimen = {
        let r = s(e, "regime");
        if r.trim().is_empty() {
            "01".to_string()
        } else {
            r.trim().to_string()
        }
    };
    let class = s(e, "class");
    let class = if class.trim().is_empty() {
        "subject".to_string()
    } else {
        class.trim().to_ascii_lowercase()
    };
    let mut calificacion = match class.as_str() {
        "subject_reverse" => "S2",
        "not_subject" => "N1",
        "not_subject_location" => "N2",
        "exempt" => "",
        _ => "S1",
    };
    let exenta = if class == "exempt" {
        let causa = s(e, "exempt_reason");
        if causa.trim().is_empty() {
            // El `<choice>` obliga a poner uno de los dos: sin causa declarada, «exenta por
            // otros» es exactamente lo que la AEAT tiene para este hueco.
            "E6".to_string()
        } else {
            causa.trim().to_ascii_uppercase()
        }
    } else {
        String::new()
    };
    // §15.6.6: con `ClaveRegimen 08` (la operación se localiza en Canarias/Ceuta/Melilla y por eso
    // NO lleva el impuesto del emisor) la calificación tiene que ser `N2`, siempre. Igual con la
    // clave `20` de IGIC (operaciones sujetas al IPSI, §15.6.10). Se corrige aquí en vez de
    // confiar en que el productor acierte: un desglose mal calificado valida contra el XSD.
    if calificacion != "" && (regimen == "08" || (impuesto == "03" && regimen == "20")) {
        calificacion = "N2";
    }
    Detalle {
        impuesto,
        regimen,
        calificacion,
        exenta,
        rate: f(e, "rate"),
        base: f(e, "base"),
        quota: f(e, "quota"),
        surcharge_rate: f(e, "surcharge_rate"),
        surcharge_quota: f(e, "surcharge_quota"),
        has_surcharge: e.get("surcharge_rate").is_some() || e.get("surcharge_quota").is_some(),
    }
}

fn desglose(record: &Json) -> String {
    let mut lines: Vec<Detalle> = Vec::new();

    match serde_json::from_str::<Json>(&s(record, "tax_breakdown")) {
        // Formato nuevo: una entrada por clave fiscal completa.
        Ok(Json::Array(entries)) => {
            for e in &entries {
                if e.is_object() {
                    lines.push(detalle_de_entrada(e));
                }
            }
        }
        // Formato viejo: clave = tipo, todo venta nacional sujeta y no exenta.
        Ok(Json::Object(map)) => {
            for (rate, amounts) in map {
                if let Ok(rate) = rate.trim().parse::<f64>() {
                    lines.push(Detalle::nacional(
                        rate,
                        f(&amounts, "base"),
                        f(&amounts, "tax"),
                    ));
                }
            }
        }
        _ => {}
    }
    if lines.is_empty() {
        // Facturas anteriores al campo (`'{}'`), o un desglose ilegible: el tipo efectivo de una
        // factura de tipo único ES su tipo real, y `Desglose` no puede quedarse sin detalle.
        lines.push(Detalle::nacional(
            f(record, "tax_rate"),
            f(record, "base_amount"),
            f(record, "tax_amount"),
        ));
    }
    // Orden estable: el XML no puede depender del orden de las claves de un objeto JSON ni de cómo
    // el productor construyera el array. Dentro de la misma clave fiscal, tipo descendente.
    lines.sort_by(|a, b| {
        a.impuesto
            .cmp(b.impuesto)
            .then_with(|| a.regimen.cmp(&b.regimen))
            .then_with(|| a.exenta.cmp(&b.exenta))
            .then_with(|| a.calificacion.cmp(b.calificacion))
            .then_with(|| b.rate.partial_cmp(&a.rate).unwrap_or(std::cmp::Ordering::Equal))
    });
    lines.truncate(MAX_DETALLES);

    lines.iter().map(Detalle::render).collect()
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
             {sustituidas}\
             <sum1:DescripcionOperacion>{desc}</sum1:DescripcionOperacion>\
             {destinatarios}\
             <sum1:Desglose>{desglose}</sum1:Desglose>\
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
            sustituidas = facturas_sustituidas(record),
            desc = esc(&s(record, "description")),
            destinatarios = destinatarios(record),
            // Una línea de desglose por tipo REAL de la factura (ver `desglose`). Los importes están
            // en CÉNTIMOS (INTEGER, ADR-0007) y la AEAT exige euros con 2 decimales → /100.0 aquí.
            desglose = desglose(record),
            cuota = format_amount(f(record, "tax_amount") / 100.0),
            total = format_amount(f(record, "total_amount") / 100.0),
            chain = encadenamiento(record, prev),
            sistema = sistema_informatico(config, hub_id),
            ts = esc(&gen_ts),
            hash = esc(&s(record, "record_hash")),
        )
    };

    // ADR-0202 (pending): the Cabecera below carries only ObligadoEmision. Two optional XSD
    // blocks are still never emitted — `RemisionVoluntaria/Incidencia=S` (flags a send coming
    // out of the contingency queue; it is per ENVELOPE, so a future batch must not mix flagged
    // and unflagged records) and `Representante` (required when transmitting with ERPlora's
    // delegated certificate on behalf of the taxpayer).
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

// La identidad mTLS y la caducidad del certificado se obtienen ahora del **core** vía
// `NativeHost::certificate_identity`/`certificate_expiry` (ADR-0079): el `.p12` y toda la cripto
// PKCS#12 (OpenSSL) viven en `erplora-runtime::certificate`, no en este módulo. verifactu solo PIDE.

/// Respuesta AEAT parseada (subconjunto que persiste el módulo).
#[derive(Debug, Default)]
pub struct AeatResponse {
    pub estado_envio: String,
    pub estado_registro: String,
    pub csv: String,
    pub codigo_error: String,
    pub descripcion_error: String,
}

/// Veredicto sobre una respuesta de la AEAT: qué se persiste y si hay algo más que hacer.
#[derive(Debug, PartialEq, Eq)]
pub struct Verdict {
    /// Estado que se guarda en el registro: `accepted` | `rejected` | `error`.
    pub status: &'static str,
    /// `AceptadoConErrores`: la AEAT **registró** el documento, pero le anotó un error.
    /// Es un aceptado **con aviso**, no un aceptado limpio y tampoco un rechazo.
    pub accepted_with_errors: bool,
    /// Código a persistir. En un aceptado con errores es el código de la AEAT (p. ej. `2007`),
    /// no la etiqueta de estado: si se tira, el operador nunca ve que la cadena venía mal.
    pub code: String,
    pub message: String,
}

impl Verdict {
    /// ¿Hay que volver a enviar este registro?
    ///
    /// **Nunca** para un aceptado (con o sin errores). Verificado contra preproducción el
    /// 2026-08-02: reenviar re-anclado un registro que la AEAT ya tenía devuelve **3000
    /// «Registro de facturación duplicado»** —con un bloque `RegistroDuplicado` que repite el
    /// estado del original— y la consulta posterior sigue mostrando UNA sola aparición: la AEAT
    /// ni duplica ni sustituye, rechaza. Ver `tests/aceptado_con_errores.rs`.
    pub fn should_retransmit(&self) -> bool {
        self.status != "accepted"
    }
}

/// Clasifica la respuesta de la AEAT.
///
/// `AceptadoConErrores` cuenta como **aceptado**: el registro está en la AEAT y reenviarlo sería
/// un duplicado. Lo que cambia respecto a un `Correcto` es que se conserva el código de error
/// para que el evento lo cuente (`accepted_with_errors`).
pub fn classify(resp: &AeatResponse) -> Verdict {
    let status = match resp.estado_registro.as_str() {
        "Correcto" | "AceptadoConErrores" => "accepted",
        "Incorrecto" => "rejected",
        _ if resp.estado_envio == "Correcto" => "accepted",
        _ => "error",
    };
    let accepted_with_errors = status == "accepted" && !resp.codigo_error.trim().is_empty();

    if status == "accepted" && !accepted_with_errors {
        Verdict {
            status,
            accepted_with_errors,
            code: resp.estado_registro.clone(),
            message: resp.estado_envio.clone(),
        }
    } else {
        Verdict {
            status,
            accepted_with_errors,
            code: resp.codigo_error.clone(),
            message: resp.descripcion_error.clone(),
        }
    }
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

/// Códigos de la AEAT que indican que el rechazo es **de encadenamiento**: el registro está bien
/// formado, pero cuelga del eslabón equivocado.
///
/// `2007` es el que aparece tras **restaurar un backup**: la cadena local retrocede, la AEAT
/// conserva los registros posteriores y el siguiente envío se anuncia como primero cuando no lo
/// es — *«No debe informarse como primer registro, existen facturas emitidas con el obligado
/// emisión y el sistema informático actual»*.
const CHAINING_ERROR_CODES: [&str; 1] = ["2007"];

/// Marcas en la **descripción** del error que delatan un problema de encadenamiento cuando el
/// código no está en la lista. La tabla de códigos de la AEAT es más amplia de lo que se ha
/// podido verificar contra el servicio real, así que el texto es la red de seguridad.
const CHAINING_ERROR_HINTS: [&str; 4] = [
    "encadenamiento",
    "registro anterior",
    "primer registro",
    "último registro",
];

/// ¿El rechazo de la AEAT es de **encadenamiento** (y por tanto recuperable re-anclando)?
///
/// Importa que sea estrecho: re-anclar mueve la cadena fiscal. Hacerlo por un NIF mal escrito
/// (1100) o por un `Destinatarios` que falta (1189) sería mucho peor que el fallo original, así
/// que todo lo que no delate un problema de eslabón se trata como un rechazo normal.
pub fn is_chaining_rejection(code: &str, description: &str) -> bool {
    if CHAINING_ERROR_CODES.contains(&code.trim()) {
        return true;
    }
    let d = description.to_lowercase();
    CHAINING_ERROR_HINTS.iter().any(|h| d.contains(h))
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

// ── Consulta de registros a la AEAT (ConsultaFactuSistemaFacturacion) ─────────────────────

/// Un registro tal como lo devuelve el servicio de **consulta** de la AEAT.
/// `invoice_date` llega en formato AEAT (`DD-MM-YYYY`); el caller lo normaliza a ISO.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct ConsultRecord {
    pub issuer_nif: String,
    pub invoice_number: String,
    pub invoice_date: String,
    pub record_hash: String,
    pub csv: String,
    pub estado: String,
    /// `FechaHoraHusoGenRegistro` — marca temporal de generación del registro. Es la clave de
    /// **orden** de la cadena (entra en el cálculo de la propia huella), y la única forma fiable
    /// de saber cuál es el último: la AEAT devuelve los registros del más NUEVO al más viejo.
    pub generated_at: String,
}
/// Construye el sobre SOAP de **consulta** para un emisor y periodo (`ejercicio` = año YYYY,
/// `periodo` = mes MM; vacío = todo el ejercicio).
///
/// **Dos namespaces, no uno.** `ConsultaLR.xsd` **importa** `SuministroInformacion.xsd`, así que
/// el documento lleva los dos —igual que el XML de alta (`sum:`/`sum1:`)— y cada elemento va en
/// el del esquema donde se **declara**: el envoltorio (`ConsultaFactuSistemaFacturacion`,
/// `Cabecera`, `FiltroConsulta`, `PeriodoImputacion`) en ConsultaLR; los campos de dentro
/// (`IDVersion`, `ObligadoEmision`, `Ejercicio`, `Periodo`) en SuministroInformacion. Con uno
/// solo la AEAT responde `Codigo[4102] … Falta informar campo obligatorio.: IDVersion` — el
/// campo está, pero en el namespace equivocado (saas#1083).
///
/// `ObligadoEmisionConsultaType` exige **`NombreRazon` además del NIF**: sin él no se construye
/// el sobre. Mandarlo incompleto solo produce otro 4102 DESPUÉS de haber hablado con Hacienda.
pub fn build_consult_soap(
    issuer_nif: &str,
    issuer_name: &str,
    ejercicio: &str,
    periodo: &str,
) -> Result<String, VerifactuError> {
    if issuer_nif.trim().is_empty() {
        return Err(VerifactuError::Payload(
            "falta el NIF del obligado a emisión para consultar a la AEAT".into(),
        ));
    }
    if issuer_name.trim().is_empty() {
        return Err(VerifactuError::Payload(
            "falta la razón social del obligado a emisión (la exige ObligadoEmisionConsultaType)"
                .into(),
        ));
    }
    // `Periodo` es OBLIGATORIO. Antes se omitía cuando llegaba vacío, dando por hecho que un
    // filtro sin mes consultaba el ejercicio entero. No existe tal filtro: la AEAT responde
    // `Codigo[4102].El XML no cumple el esquema. Falta informar campo obligatorio.: Periodo`
    // (verificado contra preproducción el 2026-08-02, ADR-0189). Se corta aquí porque el 4102
    // llega DESPUÉS de haber hablado con Hacienda.
    if periodo.trim().is_empty() {
        return Err(VerifactuError::Payload(
            "falta el Periodo (mes MM) de la consulta: la AEAT lo exige y sin él responde 4102; \
             no existe el filtro «todo el ejercicio»"
                .into(),
        ));
    }
    let periodo_xml = format!("<sum1:Periodo>{}</sum1:Periodo>", esc(periodo));
    Ok(format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\
         <soapenv:Envelope xmlns:soapenv=\"http://schemas.xmlsoap.org/soap/envelope/\" \
         xmlns:con=\"https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/ConsultaLR.xsd\" \
         xmlns:sum1=\"https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/tike/cont/ws/SuministroInformacion.xsd\">\
         <soapenv:Header/><soapenv:Body>\
         <con:ConsultaFactuSistemaFacturacion>\
         <con:Cabecera>\
         <sum1:IDVersion>1.0</sum1:IDVersion>\
         <sum1:ObligadoEmision>\
         <sum1:NombreRazon>{name}</sum1:NombreRazon>\
         <sum1:NIF>{nif}</sum1:NIF>\
         </sum1:ObligadoEmision>\
         </con:Cabecera>\
         <con:FiltroConsulta>\
         <con:PeriodoImputacion>\
         <sum1:Ejercicio>{ejercicio}</sum1:Ejercicio>{periodo_xml}\
         </con:PeriodoImputacion>\
         </con:FiltroConsulta>\
         </con:ConsultaFactuSistemaFacturacion>\
         </soapenv:Body></soapenv:Envelope>",
        name = esc(issuer_name),
        nif = esc(issuer_nif),
        ejercicio = esc(ejercicio),
    ))
}

/// Un evento del documento. Hacen falta los CIERRES, y no solo los nombres: la respuesta de
/// consulta **anida bloques que repiten las mismas etiquetas**, así que sin saber dónde acaba
/// `Encadenamiento` no hay forma de distinguir la huella del registro de la de su anterior.
enum XmlEvent<'a> {
    Open(&'a str, &'a str),
    /// El cierre solo aporta la **profundidad**: qué etiqueta cerró da igual, porque el bloque
    /// que se está saltando se identifica por el nivel al que se abrió.
    Close,
}

/// Recorre el documento emitiendo aperturas y cierres en orden. Ignora el prefijo de namespace
/// (las respuestas AEAT usan prefijos variables: `tik:`, `tikLRRC:`, …), la declaración XML y los
/// comentarios; las auto-cerradas (`<x/>`) emiten apertura y cierre. Sin dependencia XML completa,
/// en la línea de `xml_text`.
fn xml_events(body: &str) -> Vec<XmlEvent<'_>> {
    let bytes = body.as_bytes();
    let mut out = Vec::new();
    let mut i = 0;
    while let Some(rel) = body[i..].find('<') {
        let lt = i + rel;
        match bytes.get(lt + 1) {
            None => break,
            // `<!-- … -->` comentario / DOCTYPE.
            Some(&b'!') => {
                i = match body[lt..].find("-->") {
                    Some(j) => lt + j + 3,
                    None => body[lt..].find('>').map(|j| lt + j + 1).unwrap_or(lt + 1),
                };
                continue;
            }
            // `<?xml …?>` declaración.
            Some(&b'?') => {
                i = body[lt..].find('>').map(|j| lt + j + 1).unwrap_or(lt + 1);
                continue;
            }
            // `</…>` cierre.
            Some(&b'/') => {
                let after = &body[lt + 2..];
                let Some(gt) = after.find('>') else { break };
                out.push(XmlEvent::Close);
                i = lt + 2 + gt;
                continue;
            }
            _ => {}
        }
        let after = &body[lt + 1..];
        let Some(gt) = after.find('>') else { break };
        let name_end = after[..gt].find(['/', ' ', '\t', '\n', '\r']).unwrap_or(gt);
        let raw_name = &after[..name_end];
        let local = raw_name.rsplit(':').next().unwrap_or(raw_name);
        let self_closing = after[..gt].ends_with('/');
        let text = if self_closing {
            ""
        } else {
            let val_start = lt + 1 + gt + 1;
            match body[val_start..].find('<') {
                Some(j) => body[val_start..val_start + j].trim(),
                None => "",
            }
        };
        if !local.is_empty() {
            out.push(XmlEvent::Open(local, text));
            if self_closing {
                out.push(XmlEvent::Close);
            }
        }
        i = lt + 1 + gt;
    }
    out
}

/// Nombre local del elemento que abre CADA registro en la respuesta de consulta. La AEAT
/// devuelve `RegistroRespuestaConsultaFactuSistemaFacturacion`; `RegistroFactura` se acepta por
/// tolerancia con respuestas del servicio de alta.
const RECORD_BOUNDARY: [&str; 2] = [
    "RegistroRespuestaConsultaFactuSistemaFacturacion",
    "RegistroFactura",
];

/// Bloques del registro cuyo contenido NO describe al propio registro y hay que **saltarse
/// entero**. El decisivo es `Encadenamiento`: dentro lleva un `RegistroAnterior` con el
/// `NumSerieFactura`, la `FechaExpedicionFactura` y la `Huella` **del registro ANTERIOR** — las
/// mismas etiquetas que las del registro que se está leyendo. Un parser que vaya por nombre se
/// queda con las del anterior y el ancla acaba señalando a la factura equivocada.
///
/// Los otros tres repiten identificadores por el mismo motivo (`Destinatarios` trae NIF del
/// cliente, `DatosPresentacion` el del presentador, `Desglose` los importes por tipo).
const NESTED_BLOCKS: [&str; 4] = [
    "Encadenamiento",
    "Destinatarios",
    "DatosPresentacion",
    "Desglose",
];

/// Parsea la respuesta de consulta agrupando **por registro**.
///
/// Antes alineaba los campos **por posición** (todos los `NumSerieFactura`, todos los `Huella`, y
/// luego se emparejaban por índice). Contra la respuesta real eso no se sostiene ni un renglón: el
/// nº y la fecha viven dentro de `IDFactura`, la huella dentro de `DatosRegistroFacturacion`,
/// `EstadoRegistro` es a la vez contenedor y hoja, el `CSV` no viene, y —lo que de verdad lo
/// rompe— cada registro incluye un `Encadenamiento/RegistroAnterior` con las mismas etiquetas
/// referidas al registro anterior (ver [`NESTED_BLOCKS`]).
///
/// Un **SOAP Fault** se devuelve como error, no como lista vacía: leerlo como «0 registros» lo
/// hace indistinguible de «la AEAT no tiene nada que recuperar», que es justo la lectura que
/// rompe la recuperación de la cadena (saas#1083).
pub fn parse_consult_response(body: &str) -> Result<Vec<ConsultRecord>, VerifactuError> {
    let events = xml_events(body);

    for ev in &events {
        if let XmlEvent::Open("faultstring", text) = ev {
            return Err(VerifactuError::Consult(format!(
                "la AEAT rechazó la consulta: {text}"
            )));
        }
    }

    let mut records: Vec<ConsultRecord> = Vec::new();
    let mut current = ConsultRecord::default();
    let mut started = false;
    let mut depth: i32 = 0;
    // Profundidad a la que se abrió el bloque anidado que se está saltando, si lo hay.
    let mut skipping_from: Option<i32> = None;

    for ev in events {
        match ev {
            XmlEvent::Close => {
                if skipping_from == Some(depth) {
                    skipping_from = None;
                }
                depth -= 1;
            }
            XmlEvent::Open(tag, text) => {
                depth += 1;
                if skipping_from.is_none() && NESTED_BLOCKS.contains(&tag) {
                    skipping_from = Some(depth);
                }
                if skipping_from.is_some() {
                    continue;
                }
                if RECORD_BOUNDARY.contains(&tag) {
                    if started && current != ConsultRecord::default() {
                        records.push(std::mem::take(&mut current));
                    }
                    current = ConsultRecord::default();
                    started = true;
                    continue;
                }
                match tag {
                    "IDEmisorFactura" => current.issuer_nif = text.to_string(),
                    "NumSerieFactura" => current.invoice_number = text.to_string(),
                    "FechaExpedicionFactura" => current.invoice_date = text.to_string(),
                    "Huella" => current.record_hash = text.to_string(),
                    "CSV" => current.csv = text.to_string(),
                    // `EstadoRegistro` es contenedor Y hoja: el contenedor no tiene texto propio,
                    // así que solo cuenta cuando trae valor.
                    "EstadoRegistro" | "EstadoRegistroFactura" if !text.is_empty() => {
                        current.estado = text.to_string()
                    }
                    "FechaHoraHusoGenRegistro" => current.generated_at = text.to_string(),
                    _ => {}
                }
            }
        }
    }
    if started && current != ConsultRecord::default() {
        records.push(current);
    }
    Ok(records)
}

/// El registro **más reciente** de los que devuelve la AEAT, o `None`.
///
/// **No vale coger uno por posición.** La AEAT los devuelve del más NUEVO al más viejo, así que
/// `records[0]` acierta por casualidad y `records[-1]` da justo el más antiguo. Anclar en el
/// equivocado hace que la siguiente factura se encadene desde un eslabón que no es el último y
/// Hacienda la rechace: la recuperación rompería exactamente lo que viene a arreglar (saas#1083).
///
/// El orden lo da `FechaHoraHusoGenRegistro`, la marca temporal de generación del registro, que
/// **forma parte de la propia huella** — es el criterio de orden de la cadena, no una heurística.
/// Los que no traen huella no sirven de ancla (la huella ES el eslabón) y se descartan. En empate
/// gana el que llegó antes, que en el orden de la AEAT es el más nuevo.
pub fn pick_latest_record(records: &[ConsultRecord]) -> Option<&ConsultRecord> {
    let mut best: Option<&ConsultRecord> = None;
    for r in records.iter().filter(|r| !r.record_hash.is_empty()) {
        match best {
            Some(b) if r.generated_at <= b.generated_at => {}
            _ => best = Some(r),
        }
    }
    best
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

#[cfg(test)]
mod desglose_tests {
    use super::*;
    use serde_json::json;

    /// Un registro de alta mínimo. `base`/`tax` en CÉNTIMOS (ADR-0007); `tax_breakdown` es el JSON
    /// que escribe el módulo `invoice` (`{"21.00":{"base":…,"tax":…}, …}`, también en céntimos).
    fn alta(tax_breakdown: &str, base_cents: f64, tax_cents: f64, tax_rate: f64) -> Json {
        json!({
            "record_type": "alta",
            "issuer_nif": "B12345678",
            "issuer_name": "Bar Paco SL",
            "invoice_number": "F2026/1",
            "invoice_date": "2026-07-09",
            "invoice_type": "F2",
            "description": "Ticket",
            "base_amount": base_cents,
            "tax_amount": tax_cents,
            "total_amount": base_cents + tax_cents,
            "tax_rate": tax_rate,
            "tax_breakdown": tax_breakdown,
            "record_hash": "ABC123",
            "generation_timestamp": "2026-07-09T10:00:00+02:00",
        })
    }

    fn xml_de(record: &Json) -> String {
        build_soap(record, &json!({}), None, "hub-1")
    }

    /// EL caso del negocio: una caña (21%) y una tapa (10%) en el mismo ticket. Antes se declaraba
    /// a la AEAT un ÚNICO `TipoImpositivo` con el tipo EFECTIVO (17,33%), que no existe en España.
    #[test]
    fn un_ticket_de_bar_declara_sus_dos_tipos_reales_no_uno_inventado() {
        let tb = r#"{"21.00":{"base":1000,"tax":210},"10.00":{"base":500,"tax":50}}"#;
        let xml = xml_de(&alta(tb, 1500.0, 260.0, 17.33));

        assert_eq!(
            xml.matches("<sum1:DetalleDesglose>").count(),
            2,
            "una línea por tipo"
        );
        assert!(xml.contains("<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>"));
        assert!(xml.contains("<sum1:TipoImpositivo>10.00</sum1:TipoImpositivo>"));
        assert!(
            !xml.contains("<sum1:TipoImpositivo>17.33</sum1:TipoImpositivo>"),
            "el tipo efectivo no es un tipo español y no puede viajar a Hacienda"
        );

        // Base y cuota POR LÍNEA, en euros (los céntimos se dividen en el límite AEAT).
        assert!(xml.contains(
            "<sum1:BaseImponibleOimporteNoSujeto>10.00</sum1:BaseImponibleOimporteNoSujeto>"
        ));
        assert!(xml.contains("<sum1:CuotaRepercutida>2.10</sum1:CuotaRepercutida>"));
        assert!(xml.contains(
            "<sum1:BaseImponibleOimporteNoSujeto>5.00</sum1:BaseImponibleOimporteNoSujeto>"
        ));
        assert!(xml.contains("<sum1:CuotaRepercutida>0.50</sum1:CuotaRepercutida>"));

        // Los totales NO cambian: son los que alimentan la huella (CuotaTotal + ImporteTotal), así
        // que la cadena de registros ya emitidos sigue siendo válida.
        assert!(xml.contains("<sum1:CuotaTotal>2.60</sum1:CuotaTotal>"));
        assert!(xml.contains("<sum1:ImporteTotal>17.60</sum1:ImporteTotal>"));
    }

    #[test]
    fn el_orden_de_las_lineas_no_depende_del_json() {
        let tb = r#"{"10.00":{"base":500,"tax":50},"21.00":{"base":1000,"tax":210}}"#;
        let xml = xml_de(&alta(tb, 1500.0, 260.0, 17.33));
        let pos21 = xml.find("<sum1:TipoImpositivo>21.00").expect("21%");
        let pos10 = xml.find("<sum1:TipoImpositivo>10.00").expect("10%");
        assert!(pos21 < pos10, "tipo descendente, estable entre ejecuciones");
    }

    #[test]
    fn una_factura_de_tipo_unico_sigue_emitiendo_una_sola_linea() {
        let tb = r#"{"10.00":{"base":1100,"tax":110}}"#;
        let xml = xml_de(&alta(tb, 1100.0, 110.0, 10.0));
        assert_eq!(xml.matches("<sum1:DetalleDesglose>").count(), 1);
        assert!(xml.contains("<sum1:TipoImpositivo>10.00</sum1:TipoImpositivo>"));
    }

    /// Facturas viejas guardadas con `'{}'`: sin desglose no hay nada que descomponer, y el tipo
    /// efectivo de una factura de tipo único ES su tipo real. Se conserva ese comportamiento.
    #[test]
    fn una_factura_antigua_sin_desglose_cae_al_tipo_efectivo() {
        let xml = xml_de(&alta("{}", 1000.0, 100.0, 10.0));
        assert_eq!(xml.matches("<sum1:DetalleDesglose>").count(), 1);
        assert!(xml.contains("<sum1:TipoImpositivo>10.00</sum1:TipoImpositivo>"));
    }

    /// Rectificativa: base y cuota negativas. Los signos se conservan línea a línea.
    #[test]
    fn una_rectificativa_conserva_los_signos_por_linea() {
        let tb = r#"{"21.00":{"base":-1000,"tax":-210}}"#;
        let xml = xml_de(&alta(tb, -1000.0, -210.0, 21.0));
        assert!(xml.contains("<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>"));
        assert!(xml.contains(
            "<sum1:BaseImponibleOimporteNoSujeto>-10.00</sum1:BaseImponibleOimporteNoSujeto>"
        ));
        assert!(xml.contains("<sum1:CuotaRepercutida>-2.10</sum1:CuotaRepercutida>"));
    }

    // ── La CALIFICACIÓN (hub#292) ────────────────────────────────────────────────────────
    //
    // El eje del TIPO ya estaba resuelto (arriba). Este bloque cubre el otro eje: qué IMPUESTO
    // es, bajo qué RÉGIMEN y con qué CALIFICACIÓN se declara cada línea. Antes los tres iban
    // literales (`01`/`01`/`S1`) y describían solo la venta nacional sujeta y no exenta.
    //
    // El `tax_breakdown` nuevo es un ARRAY (una entrada por clave fiscal completa); el viejo era
    // un objeto por tipo. La forma los distingue, así que las facturas ya encadenadas siguen
    // generando su XML sin tocar nada.

    /// Cuenta las apariciones de un elemento (por nombre local con prefijo `sum1:`).
    fn count(xml: &str, tag: &str) -> usize {
        xml.matches(&format!("<sum1:{tag}>")).count()
    }

    /// Un hub en CANARIAS no cobra IVA: cobra IGIC. Declararlo con `Impuesto 01` es declarar un
    /// impuesto que ese hub no repercute, con un tipo (7 %) que ni siquiera existe en la lista de
    /// tipos de IVA que admite la AEAT (§15.1: 0; 2; 4; 5; 7,5; 10; 21).
    ///
    /// Verificado contra las validaciones oficiales v1.2.2 §15.6: con `Impuesto 03` la
    /// `ClaveRegimen` sale de la lista **L8B**, y el régimen general sigue siendo `01`. NO es `08`
    /// — en L8B, `08` significa «operaciones sujetas al IPSI / IVA», es decir, los OTROS impuestos.
    #[test]
    fn un_hub_canario_declara_igic_no_iva() {
        let tb = r#"[{"tax":"igic","regime":"01","class":"subject","rate":7.00,
                      "base":10000,"quota":700}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 700.0, 7.0));
        assert!(xml.contains("<sum1:Impuesto>03</sum1:Impuesto>"), "{xml}");
        assert!(xml.contains("<sum1:ClaveRegimen>01</sum1:ClaveRegimen>"));
        assert!(xml.contains("<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>"));
        assert!(xml.contains("<sum1:TipoImpositivo>7.00</sum1:TipoImpositivo>"));
        assert!(xml.contains("<sum1:CuotaRepercutida>7.00</sum1:CuotaRepercutida>"));
    }

    /// Ceuta y Melilla: IPSI, `Impuesto 02`.
    #[test]
    fn un_hub_de_ceuta_declara_ipsi() {
        let tb = r#"[{"tax":"ipsi","regime":"01","class":"subject","rate":4.00,
                      "base":10000,"quota":400}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 400.0, 4.0));
        assert!(xml.contains("<sum1:Impuesto>02</sum1:Impuesto>"), "{xml}");
    }

    /// Un servicio EXENTO (sanitario, formación — reales en el vertical de estética) NO es «sujeto
    /// y no exento al 0 %»: exige `OperacionExenta`, que en el XSD es una ALTERNATIVA a
    /// `CalificacionOperacion` (`<choice>`), no un tipo del 0 %.
    ///
    /// §15.5: con `OperacionExenta` no se pueden informar `TipoImpositivo`, `CuotaRepercutida`,
    /// `TipoRecargoEquivalencia` ni `CuotaRecargoEquivalencia`.
    #[test]
    fn un_servicio_exento_va_por_operacion_exenta_sin_tipo_ni_cuota() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"exempt","exempt_reason":"E1",
                      "rate":0.00,"base":5000,"quota":0}]"#;
        let xml = xml_de(&alta(tb, 5000.0, 0.0, 0.0));
        assert!(xml.contains("<sum1:OperacionExenta>E1</sum1:OperacionExenta>"), "{xml}");
        assert_eq!(count(&xml, "CalificacionOperacion"), 0, "el XSD es un <choice>: uno u otro");
        assert_eq!(count(&xml, "TipoImpositivo"), 0, "§15.5: exenta no lleva tipo");
        assert_eq!(count(&xml, "CuotaRepercutida"), 0, "§15.5: exenta no lleva cuota");
        // El importe de la operación sigue viajando: es el único obligatorio del detalle.
        assert!(xml.contains(
            "<sum1:BaseImponibleOimporteNoSujeto>50.00</sum1:BaseImponibleOimporteNoSujeto>"
        ));
    }

    /// Venta a empresa de otro estado miembro: no sujeta por reglas de localización (art.
    /// 69.Uno.1º LIVA) → **N2**, y la cuota la autoliquida el cliente. NO es S2 (que es la
    /// inversión en operaciones *sujetas en España*, art. 84.Uno.2º).
    ///
    /// **Error 1237**: con N1/N2 e Impuesto IVA no se puede informar `TipoImpositivo` ni
    /// `CuotaRepercutida`. El XSD NO cubre esta regla — un XML mal calificado valida igual.
    #[test]
    fn una_venta_intracomunitaria_b2b_es_n2_y_no_lleva_tipo_ni_cuota() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"not_subject_location",
                      "rate":0.00,"base":100000,"quota":0}]"#;
        let xml = xml_de(&alta(tb, 100000.0, 0.0, 0.0));
        assert!(xml.contains("<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>"), "{xml}");
        assert_eq!(count(&xml, "TipoImpositivo"), 0, "error 1237");
        assert_eq!(count(&xml, "CuotaRepercutida"), 0, "error 1237");
    }

    /// La excepción de `ClaveRegimen 17` (OSS) al error 1237 **ya no existe**: la revisión v1.0.6
    /// (25/04/2025) del documento de validaciones eliminó «las referencias a la clave de régimen 17
    /// en la clasificación operación N1/N2». §15.7 lo remata sin excepción alguna: «CuotaRepercutida
    /// solo podrá ser distinta de cero (positivo o negativo) si CalificacionOperacion es S1».
    ///
    /// El VeriFactu del SaaS (ADR-0183) todavía mapea `oss → ("17","N2", con tipo y cuota)`. Este
    /// test es el que impide que ese mapeo se copie aquí.
    #[test]
    fn el_regimen_17_no_es_excepcion_al_1237() {
        let tb = r#"[{"tax":"vat","regime":"17","class":"not_subject_location",
                      "rate":19.00,"base":10000,"quota":1900}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 1900.0, 19.0));
        assert!(xml.contains("<sum1:ClaveRegimen>17</sum1:ClaveRegimen>"), "{xml}");
        assert_eq!(count(&xml, "TipoImpositivo"), 0, "1237 sin excepción de régimen 17");
        assert_eq!(count(&xml, "CuotaRepercutida"), 0, "1237 sin excepción de régimen 17");
    }

    /// `ClaveRegimen 08` (operación localizada en Canarias/Ceuta/Melilla, declarada por un emisor
    /// peninsular) obliga a `N2` (§15.6.6) — y por tanto arrastra el 1237.
    #[test]
    fn el_regimen_08_fuerza_n2() {
        let tb = r#"[{"tax":"vat","regime":"08","class":"subject","rate":21.00,
                      "base":10000,"quota":2100}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 2100.0, 21.0));
        assert!(xml.contains("<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>"), "{xml}");
        assert_eq!(count(&xml, "TipoImpositivo"), 0);
    }

    /// El RECARGO DE EQUIVALENCIA no es otro tipo impositivo: son dos campos MÁS dentro de la
    /// MISMA línea del IVA. Hoy `taxes` lo modela como una fila componente y el desglose le daba su
    /// propia clave, así que salía una `DetalleDesglose` con `TipoImpositivo 5.20` — que no es un
    /// tipo de IVA válido (§15.1) y hace que la AEAT rechace el registro.
    #[test]
    fn el_recargo_de_equivalencia_va_en_la_linea_del_iva_no_en_otra() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,
                      "base":10000,"quota":2100,"surcharge_rate":5.20,"surcharge_quota":520}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 2620.0, 21.0));
        assert_eq!(count(&xml, "DetalleDesglose"), 1, "una sola línea, no dos: {xml}");
        assert!(xml.contains("<sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>"));
        assert!(xml.contains("<sum1:TipoRecargoEquivalencia>5.20</sum1:TipoRecargoEquivalencia>"));
        assert!(xml.contains("<sum1:CuotaRecargoEquivalencia>5.20</sum1:CuotaRecargoEquivalencia>"));
        assert!(
            !xml.contains("<sum1:TipoImpositivo>5.20</sum1:TipoImpositivo>"),
            "5,20 % no es un tipo de IVA: la AEAT solo admite 0; 2; 4; 5; 7,5; 10; 21"
        );
    }

    /// Inversión del sujeto pasivo en operación SUJETA en España (art. 84.Uno.2º) → `S2`. §15.4
    /// exige `TipoImpositivo = 0` y `CuotaRepercutida = 0` **presentes** — no omitidos, que es lo
    /// contrario de lo que pide N1/N2.
    #[test]
    fn la_inversion_sujeta_en_espana_es_s2_con_tipo_y_cuota_a_cero_explicitos() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"subject_reverse",
                      "rate":0.00,"base":50000,"quota":0}]"#;
        let xml = xml_de(&alta(tb, 50000.0, 0.0, 0.0));
        assert!(xml.contains("<sum1:CalificacionOperacion>S2</sum1:CalificacionOperacion>"), "{xml}");
        assert!(xml.contains("<sum1:TipoImpositivo>0.00</sum1:TipoImpositivo>"), "§15.4: 0 explícito");
        assert!(xml.contains("<sum1:CuotaRepercutida>0.00</sum1:CuotaRepercutida>"), "§15.4: 0 explícito");
    }

    /// El caso que junta los dos ejes: la peluquería que en el mismo ticket vende un corte (21 %) y
    /// un tratamiento sanitario exento. Dos líneas, cada una con SU calificación.
    #[test]
    fn un_ticket_mixto_sujeto_mas_exento_declara_las_dos_calificaciones() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,
                      "base":2000,"quota":420},
                     {"tax":"vat","regime":"01","class":"exempt","exempt_reason":"E1",
                      "rate":0.00,"base":4000,"quota":0}]"#;
        let xml = xml_de(&alta(tb, 6000.0, 420.0, 7.0));
        assert_eq!(count(&xml, "DetalleDesglose"), 2, "{xml}");
        assert_eq!(count(&xml, "CalificacionOperacion"), 1, "solo la sujeta lleva calificación");
        assert_eq!(count(&xml, "OperacionExenta"), 1);
        assert_eq!(count(&xml, "TipoImpositivo"), 1, "la exenta no lleva tipo");
    }

    /// El `<choice>` del XSD es `CalificacionOperacion` **o** `OperacionExenta`, y el
    /// `xs:sequence` de `DetalleType` fija el orden: Impuesto → ClaveRegimen → (choice) →
    /// TipoImpositivo → BaseImponibleOimporteNoSujeto → CuotaRepercutida →
    /// TipoRecargoEquivalencia → CuotaRecargoEquivalencia.
    #[test]
    fn el_detalle_respeta_el_orden_del_xs_sequence() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"subject","rate":21.00,
                      "base":10000,"quota":2100,"surcharge_rate":5.20,"surcharge_quota":520}]"#;
        let xml = xml_de(&alta(tb, 10000.0, 2620.0, 21.0));
        let at = |t: &str| xml.find(&format!("<sum1:{t}>")).unwrap_or_else(|| panic!("falta {t}"));
        assert!(at("Impuesto") < at("ClaveRegimen"));
        assert!(at("ClaveRegimen") < at("CalificacionOperacion"));
        assert!(at("CalificacionOperacion") < at("TipoImpositivo"));
        assert!(at("TipoImpositivo") < at("BaseImponibleOimporteNoSujeto"));
        assert!(at("BaseImponibleOimporteNoSujeto") < at("CuotaRepercutida"));
        assert!(at("CuotaRepercutida") < at("TipoRecargoEquivalencia"));
        assert!(at("TipoRecargoEquivalencia") < at("CuotaRecargoEquivalencia"));
    }

    /// El XSD limita `DetalleDesglose` a `maxOccurs="12"`. Más de 12 claves fiscales distintas no
    /// caben, y mandarlas es un rechazo seguro por esquema.
    #[test]
    fn el_desglose_no_pasa_de_doce_lineas() {
        let entradas: Vec<String> = (1..=15)
            .map(|i| {
                format!(
                    r#"{{"tax":"vat","regime":"{i:02}","class":"subject","rate":21.00,
                        "base":100,"quota":21}}"#
                )
            })
            .collect();
        let tb = format!("[{}]", entradas.join(","));
        let xml = xml_de(&alta(&tb, 1500.0, 315.0, 21.0));
        assert_eq!(count(&xml, "DetalleDesglose"), 12, "maxOccurs=12 en el XSD");
    }

    /// COMPATIBILIDAD: una factura ya emitida con el formato viejo (objeto por tipo) sigue
    /// produciendo EXACTAMENTE el XML de antes. Está encadenada en la huella: no se puede
    /// reinterpretar.
    #[test]
    fn el_formato_viejo_sigue_declarandose_como_venta_nacional_sujeta() {
        let tb = r#"{"21.00":{"base":1000,"tax":210},"10.00":{"base":500,"tax":50}}"#;
        let xml = xml_de(&alta(tb, 1500.0, 260.0, 17.33));
        assert_eq!(count(&xml, "DetalleDesglose"), 2);
        assert_eq!(count(&xml, "Impuesto"), 2);
        assert!(xml.contains("<sum1:Impuesto>01</sum1:Impuesto>"));
        assert!(xml.contains("<sum1:ClaveRegimen>01</sum1:ClaveRegimen>"));
        assert_eq!(count(&xml, "CalificacionOperacion"), 2);
        assert!(xml.contains("<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>"));
        assert_eq!(count(&xml, "OperacionExenta"), 0);
    }

    /// El orden del array tampoco puede depender de cómo lo escribiera el productor.
    #[test]
    fn el_orden_de_las_lineas_del_array_es_estable() {
        let tb = r#"[{"tax":"vat","regime":"01","class":"subject","rate":10.00,"base":500,"quota":50},
                     {"tax":"vat","regime":"01","class":"subject","rate":21.00,"base":1000,"quota":210}]"#;
        let xml = xml_de(&alta(tb, 1500.0, 260.0, 17.33));
        let pos21 = xml.find("<sum1:TipoImpositivo>21.00").expect("21%");
        let pos10 = xml.find("<sum1:TipoImpositivo>10.00").expect("10%");
        assert!(pos21 < pos10, "tipo descendente dentro de la misma clave fiscal");
    }

    /// Un array vacío o basura no puede dejar el `Desglose` sin ninguna línea: el elemento es
    /// obligatorio y sin detalle el registro se rechaza. Cae al tipo efectivo, como el `'{}'`.
    #[test]
    fn un_desglose_vacio_cae_al_tipo_efectivo() {
        let xml = xml_de(&alta("[]", 1000.0, 100.0, 10.0));
        assert_eq!(count(&xml, "DetalleDesglose"), 1);
        assert!(xml.contains("<sum1:TipoImpositivo>10.00</sum1:TipoImpositivo>"));
        assert!(xml.contains("<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>"));
    }

    /// Defaults del contrato: sin `tax` es IVA, sin `regime` es régimen general, sin `class` es
    /// sujeta y no exenta. Es lo que hace que un productor que solo sepa de tipos siga funcionando.
    #[test]
    fn los_defaults_del_contrato_son_iva_regimen_general_y_sujeta() {
        let tb = r#"[{"rate":21.00,"base":1000,"quota":210}]"#;
        let xml = xml_de(&alta(tb, 1000.0, 210.0, 21.0));
        assert!(xml.contains("<sum1:Impuesto>01</sum1:Impuesto>"), "{xml}");
        assert!(xml.contains("<sum1:ClaveRegimen>01</sum1:ClaveRegimen>"));
        assert!(xml.contains("<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>"));
    }

    /// Una exenta sin causa declarada no puede quedarse sin `OperacionExenta` (el `<choice>` exige
    /// uno de los dos): cae a `E6` — «exenta por otros» — que es lo que la AEAT tiene para eso.
    #[test]
    fn una_exenta_sin_causa_cae_a_e6() {
        let tb = r#"[{"tax":"vat","class":"exempt","rate":0.00,"base":1000,"quota":0}]"#;
        let xml = xml_de(&alta(tb, 1000.0, 0.0, 0.0));
        assert!(xml.contains("<sum1:OperacionExenta>E6</sum1:OperacionExenta>"), "{xml}");
    }
}
