//! El bloque **rectificativo** del `RegistroAlta` — hub#1023.
//!
//! Una devolución en un TPV español no anula la factura: emite una **rectificativa** (R1-R5). El
//! motor sabía declarar la *sustitución* (F3 → `FacturasSustituidas`, ADR-0140) pero no la
//! *rectificación*, así que toda R salía sin `TipoRectificativa` —campo que la AEAT exige en
//! cuanto el `TipoFactura` es R*— y la rechazaban **después** de que el registro hubiera gastado
//! su número de cadena.
//!
//! Tres piezas, en el orden del `xs:sequence` oficial:
//!
//! - `TipoRectificativa` (`S` sustitutiva | `I` incremental/por diferencias),
//! - `FacturasRectificadas/IDFacturaRectificada` (`IDFacturaARType`: NIF + nº+serie + fecha),
//! - `ImporteRectificacion` (`BaseRectificada`/`CuotaRectificada`), que **solo** existe en una `S`.
use erplora_verifactu::{aeat, chain, xsd};
use serde_json::{json, Value};

fn config() -> Value {
    json!({
        "producer_facts": {
            "NombreRazon": "ERPLORA CLOUD SL",
            "NIF": "B27593136",
            "NombreSistemaInformatico": "ERPlora Hub",
            "IdSistemaInformatico": "EC",
            "TipoUsoPosibleSoloVerifactu": "S",
            "TipoUsoPosibleMultiOT": "S",
            "IndicadorMultiplesOT": "N",
        },
    })
}

/// Una rectificativa tal y como nace de una devolución: importes **negativos** (el delta), y el
/// enlace a la factura que rectifica.
fn rectificativa(invoice_type: &str, recipient_nif: &str) -> Value {
    json!({
        "record_type": "alta",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "invoice_number": "RECT/001",
        "invoice_date": "2026-08-20",
        "invoice_type": invoice_type,
        "description": "Devolución de FA/001",
        "base_amount": -10000,
        "tax_rate": 21.0,
        "tax_breakdown": r#"{"21.00":{"base":-10000,"tax":-2100}}"#,
        "tax_amount": -2100,
        "total_amount": -12100,
        "recipient_nif": recipient_nif,
        "recipient_name": if recipient_nif.is_empty() { "" } else { "Cliente SL" },
        "rectifies_number": "FA/001",
        "rectifies_date": "2026-08-02",
        "rectifies_nif": "B27593136",
        "record_hash": "A".repeat(64),
        "is_first_record": 1,
        "generation_timestamp": "2026-08-20T10:00:00+02:00",
    })
}

/// Una venta normal, sin nada que rectificar.
fn alta_normal(invoice_type: &str, recipient_nif: &str) -> Value {
    json!({
        "record_type": "alta",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "invoice_number": "FA/001",
        "invoice_date": "2026-08-02",
        "invoice_type": invoice_type,
        "description": "Venta FA/001",
        "base_amount": 10000,
        "tax_rate": 21.0,
        "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
        "tax_amount": 2100,
        "total_amount": 12100,
        "recipient_nif": recipient_nif,
        "recipient_name": if recipient_nif.is_empty() { "" } else { "Cliente SL" },
        "record_hash": "A".repeat(64),
        "is_first_record": 1,
        "generation_timestamp": "2026-08-02T10:00:00+02:00",
    })
}

fn xml_de(record: &Value) -> String {
    aeat::build_soap(record, &config(), None, "hub-1").expect("el registro se puede declarar")
}

fn set(record: &Value, key: &str, value: Value) -> Value {
    let mut r = record.clone();
    r.as_object_mut().expect("objeto").insert(key.into(), value);
    r
}

// ── Lo que se emite ───────────────────────────────────────────────────────────────────────

/// El caso normal de un TPV: se devuelve un tique, sale una **R5 por diferencias** con el importe
/// en negativo y el enlace a la simplificada que rectifica.
#[test]
fn una_rectificativa_declara_su_tipo_y_la_factura_rectificada() {
    let xml = xml_de(&rectificativa("R5", ""));
    assert!(
        xml.contains("<sum1:TipoRectificativa>I</sum1:TipoRectificativa>"),
        "una R sin ImporteRectificacion declara sus importes por DIFERENCIAS (I): {xml}"
    );
    assert!(
        xml.contains("<sum1:FacturasRectificadas><sum1:IDFacturaRectificada>"),
        "falta el bloque FacturasRectificadas: {xml}"
    );
    assert!(
        xml.contains("<sum1:NumSerieFactura>FA/001</sum1:NumSerieFactura>"),
        "la rectificada se identifica por nº+serie: {xml}"
    );
    assert!(
        xml.contains("<sum1:FechaExpedicionFactura>02-08-2026</sum1:FechaExpedicionFactura>"),
        "la fecha de la rectificada va en formato AEAT DD-MM-YYYY: {xml}"
    );
}

/// Rectificativa **por sustitución**: el registro declara los importes corregidos y, además, la
/// base y la cuota que sustituye (`ImporteRectificacion`).
#[test]
fn una_rectificativa_por_sustitucion_declara_el_importe_rectificado() {
    let mut r = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    r = set(&r, "rectified_base_amount", json!(10000));
    r = set(&r, "rectified_tax_amount", json!(2100));
    let xml = xml_de(&r);
    assert!(
        xml.contains("<sum1:TipoRectificativa>S</sum1:TipoRectificativa>"),
        "el tipo declarado manda: {xml}"
    );
    assert!(
        xml.contains(
            "<sum1:ImporteRectificacion><sum1:BaseRectificada>100.00</sum1:BaseRectificada>\
             <sum1:CuotaRectificada>21.00</sum1:CuotaRectificada></sum1:ImporteRectificacion>"
        ),
        "los importes rectificados van en EUROS con 2 decimales (los céntimos son de la fila): {xml}"
    );
}

/// El recargo de equivalencia rectificado es opcional: solo se declara si viene.
#[test]
fn el_recargo_rectificado_solo_se_declara_si_existe() {
    let mut r = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    r = set(&r, "rectified_base_amount", json!(10000));
    r = set(&r, "rectified_tax_amount", json!(2100));
    assert!(
        !xml_de(&r).contains("CuotaRecargoRectificado"),
        "sin recargo no se emite el elemento"
    );
    let con_recargo = set(&r, "rectified_surcharge_amount", json!(520));
    assert!(
        xml_de(&con_recargo)
            .contains("<sum1:CuotaRecargoRectificado>5.20</sum1:CuotaRecargoRectificado>"),
        "con recargo se emite tras la cuota"
    );
}

/// Una venta no rectifica nada: el bloque **no existe**. Informarlo en una F1/F2 es un rechazo.
#[test]
fn una_factura_normal_no_lleva_bloque_rectificativo() {
    for (tipo, nif) in [("F1", "B12345678"), ("F2", "")] {
        let xml = xml_de(&alta_normal(tipo, nif));
        assert!(
            !xml.contains("TipoRectificativa"),
            "una {tipo} no declara TipoRectificativa: {xml}"
        );
        assert!(
            !xml.contains("FacturasRectificadas"),
            "una {tipo} no declara FacturasRectificadas: {xml}"
        );
        assert!(
            !xml.contains("ImporteRectificacion"),
            "una {tipo} no declara ImporteRectificacion: {xml}"
        );
    }
}

/// Sin datos de la rectificada no se inventa un bloque vacío: `FacturasRectificadas` es opcional
/// en el esquema, `TipoRectificativa` no.
#[test]
fn una_rectificativa_sin_los_datos_de_la_rectificada_declara_igual_su_tipo() {
    let mut r = rectificativa("R5", "");
    for k in ["rectifies_number", "rectifies_date", "rectifies_nif"] {
        r = set(&r, k, json!(""));
    }
    let xml = xml_de(&r);
    assert!(
        xml.contains("<sum1:TipoRectificativa>I</sum1:TipoRectificativa>"),
        "el tipo es obligatorio en toda R: {xml}"
    );
    assert!(
        !xml.contains("FacturasRectificadas"),
        "sin datos, el bloque opcional no se emite vacío: {xml}"
    );
    xsd::validate_registro(&xml).expect("sigue siendo declarable");
}

// ── Lo que NO se emite: no se rellenan huecos fiscales (hub#324) ──────────────────────────

/// Una `S` sin los importes rectificados **no se transmite**. Emitirla con `0,00` declararía a
/// Hacienda que se rectifica una base de cero euros.
#[test]
fn una_sustitutiva_sin_importes_no_se_inventa_un_cero() {
    let r = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    let err = aeat::build_soap(&r, &config(), None, "hub-1")
        .expect_err("una sustitutiva sin base/cuota rectificada no es declarable")
        .to_string();
    assert!(
        err.contains("ImporteRectificacion"),
        "el error nombra el bloque que falta: {err}"
    );
}

/// Un `TipoRectificativa` que no está en la enumeración se para aquí, no en la AEAT.
#[test]
fn un_tipo_rectificativa_desconocido_no_llega_a_la_red() {
    let r = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("X"),
    );
    let err = aeat::build_soap(&r, &config(), None, "hub-1")
        .expect_err("`X` no está en ClaveTipoRectificativaType")
        .to_string();
    assert!(
        err.contains("TipoRectificativa"),
        "el error nombra el campo: {err}"
    );
}

// ── La huella no se toca ──────────────────────────────────────────────────────────────────

/// El bloque rectificativo **no entra en la huella** (`alta_hash` solo encadena NIF, nº, fecha,
/// tipo, cuota, total, huella anterior y timestamp). Si entrara, añadirlo rompería la cadena de
/// todos los registros ya emitidos.
#[test]
fn el_bloque_rectificativo_no_cambia_la_huella() {
    let r = rectificativa("R5", "");
    let huella = |v: &Value| {
        chain::alta_hash(
            v["issuer_nif"].as_str().unwrap(),
            v["invoice_number"].as_str().unwrap(),
            v["invoice_date"].as_str().unwrap(),
            v["invoice_type"].as_str().unwrap(),
            v["tax_amount"].as_f64().unwrap() / 100.0,
            v["total_amount"].as_f64().unwrap() / 100.0,
            "",
            v["generation_timestamp"].as_str().unwrap(),
        )
    };
    let mut sin = r.clone();
    for k in ["rectifies_number", "rectifies_date", "rectifies_nif"] {
        sin = set(&sin, k, json!(""));
    }
    assert_eq!(
        huella(&r),
        huella(&sin),
        "los campos rectificativos no son parte de la huella AEAT"
    );
}

// ── El validador: lo que la AEAT castiga ──────────────────────────────────────────────────

/// El XML que genera el motor para una rectificativa pasa la validación previa.
#[test]
fn la_rectificativa_que_genera_el_modulo_pasa_la_validacion() {
    xsd::validate_registro(&xml_de(&rectificativa("R5", ""))).expect("R5 de un tique");
    xsd::validate_registro(&xml_de(&rectificativa("R1", "B12345678")))
        .expect("R1 con destinatario");
    let mut s = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    s = set(&s, "rectified_base_amount", json!(10000));
    s = set(&s, "rectified_tax_amount", json!(2100));
    xsd::validate_registro(&xml_de(&s)).expect("R1 por sustitución");
}

/// Sustituye o inserta un elemento en el XML ya construido, para probar sobres que el motor no
/// generaría pero que otro caller sí podría construir.
fn quitar(xml: &str, tag: &str) -> String {
    let abre = format!("<sum1:{tag}>");
    let cierra = format!("</sum1:{tag}>");
    let i = xml.find(&abre).expect("el elemento está");
    let j = xml.find(&cierra).expect("cierre") + cierra.len();
    format!("{}{}", &xml[..i], &xml[j..])
}

fn insertar_antes(xml: &str, marcador: &str, elemento: &str) -> String {
    let i = xml.find(marcador).expect("marcador");
    format!("{}{elemento}{}", &xml[..i], &xml[i..])
}

/// **El defecto de hub#1023**: una R sin `TipoRectificativa` la rechaza la AEAT, y para entonces
/// el registro ya ha gastado su número de cadena. Se para antes de la red.
#[test]
fn una_rectificativa_sin_tipo_no_llega_a_la_aeat() {
    let xml = quitar(&xml_de(&rectificativa("R5", "")), "TipoRectificativa");
    let err = xsd::validate_registro(&xml).expect_err("una R sin TipoRectificativa no es válida");
    assert!(
        err.to_string().contains("TipoRectificativa"),
        "el error nombra el campo que falta: {err}"
    );
}

/// `TipoRectificativa` solo existe en una rectificativa: informarlo en una F1 es un rechazo.
#[test]
fn el_tipo_rectificativa_solo_existe_en_una_rectificativa() {
    let xml = insertar_antes(
        &xml_de(&alta_normal("F1", "B12345678")),
        "<sum1:DescripcionOperacion>",
        "<sum1:TipoRectificativa>I</sum1:TipoRectificativa>",
    );
    let err = xsd::validate_registro(&xml).expect_err("una F1 no rectifica nada");
    assert!(
        err.to_string().contains("TipoRectificativa"),
        "el error nombra el campo sobrante: {err}"
    );
}

/// `FacturasRectificadas`, igual: solo en una R.
#[test]
fn las_facturas_rectificadas_solo_existen_en_una_rectificativa() {
    let xml = insertar_antes(
        &xml_de(&alta_normal("F1", "B12345678")),
        "<sum1:DescripcionOperacion>",
        "<sum1:FacturasRectificadas><sum1:IDFacturaRectificada>\
         <sum1:IDEmisorFactura>B27593136</sum1:IDEmisorFactura>\
         <sum1:NumSerieFactura>FA/000</sum1:NumSerieFactura>\
         <sum1:FechaExpedicionFactura>01-08-2026</sum1:FechaExpedicionFactura>\
         </sum1:IDFacturaRectificada></sum1:FacturasRectificadas>",
    );
    let err = xsd::validate_registro(&xml).expect_err("una F1 no rectifica nada");
    assert!(
        err.to_string().contains("FacturasRectificadas"),
        "el error nombra el bloque sobrante: {err}"
    );
}

/// `ImporteRectificacion` **solo** se informa si la rectificativa es por sustitución.
#[test]
fn el_importe_rectificado_solo_existe_en_una_sustitutiva() {
    let xml = insertar_antes(
        &xml_de(&rectificativa("R5", "")),
        "<sum1:DescripcionOperacion>",
        "<sum1:ImporteRectificacion><sum1:BaseRectificada>100.00</sum1:BaseRectificada>\
         <sum1:CuotaRectificada>21.00</sum1:CuotaRectificada></sum1:ImporteRectificacion>",
    );
    let err = xsd::validate_registro(&xml).expect_err("una I no lleva importe rectificado");
    assert!(
        err.to_string().contains("ImporteRectificacion"),
        "el error nombra el bloque: {err}"
    );
}

/// …y una sustitutiva sin él tampoco sale.
#[test]
fn una_sustitutiva_sin_importe_rectificado_no_llega_a_la_aeat() {
    let mut s = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    s = set(&s, "rectified_base_amount", json!(10000));
    s = set(&s, "rectified_tax_amount", json!(2100));
    let xml = quitar(&xml_de(&s), "ImporteRectificacion");
    let err = xsd::validate_registro(&xml).expect_err("una S exige el importe rectificado");
    assert!(
        err.to_string().contains("ImporteRectificacion"),
        "el error nombra el bloque que falta: {err}"
    );
}

/// El `TipoRectificativa` del XML tiene que estar en la enumeración del esquema.
#[test]
fn el_tipo_rectificativa_del_xml_esta_en_la_enumeracion() {
    let xml = xml_de(&rectificativa("R5", "")).replace(
        "<sum1:TipoRectificativa>I</sum1:TipoRectificativa>",
        "<sum1:TipoRectificativa>X</sum1:TipoRectificativa>",
    );
    let err = xsd::validate_registro(&xml).expect_err("`X` no está en la enumeración");
    assert!(
        err.to_string().contains("TipoRectificativa"),
        "el error nombra el campo: {err}"
    );
}

// ── El contrato del esquema ───────────────────────────────────────────────────────────────

/// El orden que emite el motor es el del `xs:sequence` oficial: `TipoFactura` →
/// `TipoRectificativa` → `FacturasRectificadas` → `FacturasSustituidas` → `ImporteRectificacion`
/// → `DescripcionOperacion`.
#[test]
fn el_bloque_rectificativo_va_donde_dice_el_esquema() {
    let mut s = set(
        &rectificativa("R1", "B12345678"),
        "rectification_type",
        json!("S"),
    );
    s = set(&s, "rectified_base_amount", json!(10000));
    s = set(&s, "rectified_tax_amount", json!(2100));
    let xml = xml_de(&s);
    let pos = |t: &str| {
        xml.find(&format!("<sum1:{t}>"))
            .unwrap_or_else(|| panic!("falta {t}"))
    };
    assert!(pos("TipoFactura") < pos("TipoRectificativa"));
    assert!(pos("TipoRectificativa") < pos("FacturasRectificadas"));
    assert!(pos("FacturasRectificadas") < pos("ImporteRectificacion"));
    assert!(pos("ImporteRectificacion") < pos("DescripcionOperacion"));
}

/// La enumeración que aplica el validador sale del **XSD oficial** vendorizado, no de una lista
/// escrita a mano: el día que la AEAT publique otra versión, este test es el que se entera.
#[test]
fn la_enumeracion_rectificativa_sale_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    let del_esquema = xsd::enumeration_of(xsd_src, "ClaveTipoRectificativaType")
        .expect("ClaveTipoRectificativaType no está en el XSD vendorizado");
    assert_eq!(
        del_esquema,
        xsd::TIPO_RECTIFICATIVA,
        "la enumeración del validador no coincide con el XSD oficial"
    );
}

/// …y el orden del `ImporteRectificacion` también.
#[test]
fn el_orden_del_importe_rectificado_sale_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    let del_esquema = xsd::sequence_of(xsd_src, "DesgloseRectificacionType")
        .expect("DesgloseRectificacionType no está en el XSD vendorizado");
    assert_eq!(
        del_esquema,
        vec![
            "BaseRectificada".to_string(),
            "CuotaRectificada".to_string(),
            "CuotaRecargoRectificado".to_string(),
        ],
        "el desglose de la rectificación no coincide con el XSD oficial"
    );
}
