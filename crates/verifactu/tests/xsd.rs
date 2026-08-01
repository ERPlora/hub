//! Validación del XML **antes** de transmitir a la AEAT — hub#287, punto 6.
//!
//! La cadena fiscal es inmutable: cuando la AEAT contesta `Codigo[4102]. El XML no cumple el
//! esquema`, el registro **ya ha gastado su número**. Validar después de enviar no sirve de nada;
//! hay que hacerlo antes de tocar la red.
//!
//! Y hay que hacerlo **en producción**. En el SaaS la validación existía pero su dependencia
//! (`xmlschema`) estaba en el grupo *dev*: la imagen desplegada no la instalaba y el código
//! degradaba, por diseño, a «se transmite sin validar». La protección funcionaba en los tests y
//! era inerte donde importa (saas#1083). Aquí el validador es código del propio crate, sin
//! dependencias opcionales ni `#[cfg(feature)]`: si compila el binario, compila la validación.
//!
//! No es un motor XSD completo (ver `src/xsd.rs`): comprueba lo que la AEAT castiga de verdad
//! —obligatorios presentes, orden de la secuencia, y los formatos/enumeraciones de los campos que
//! este módulo emite—, y un test de este fichero contrasta esa tabla contra el **XSD oficial**
//! vendorizado en `schemas/aeat/`, para que no se separe del esquema en silencio.
use erplora_verifactu::{aeat, xsd};
use serde_json::{json, Value};

fn config() -> Value {
    json!({
        "software_name": "ERPLORA CLOUD SL",
        "software_nif": "B27593136",
        "software_version": "1.0.0",
    })
}

/// Registro de alta COMPLETO, del que sale un XML que la AEAT acepta.
fn alta(invoice_type: &str, recipient_nif: &str) -> Value {
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
    aeat::build_soap(record, &config(), None, "hub-1")
}

// ── El XML que el módulo genera es válido ─────────────────────────────────────────────────

#[test]
fn el_alta_que_genera_el_modulo_pasa_la_validacion() {
    xsd::validate_registro(&xml_de(&alta("F2", ""))).expect("una F2 completa es válida");
    xsd::validate_registro(&xml_de(&alta("F1", "B12345678"))).expect("una F1 con destinatario");
}

#[test]
fn la_anulacion_que_genera_el_modulo_pasa_la_validacion() {
    let mut rec = alta("F1", "B12345678");
    rec["record_type"] = json!("anulacion");
    xsd::validate_registro(&xml_de(&rec)).expect("anulación válida");
}

// ── Obligatorios ausentes ─────────────────────────────────────────────────────────────────

/// `DescripcionOperacion` es `minOccurs="1"`: la AEAT lo rechaza con 1100. Ya se le puso un
/// fallback en `ingest_invoice`, pero el gate tiene que estar en el límite de la red.
#[test]
fn un_obligatorio_vacio_no_llega_a_la_aeat() {
    let mut rec = alta("F2", "");
    rec["description"] = json!("");
    let err = xsd::validate_registro(&xml_de(&rec)).expect_err("descripción vacía");
    assert!(err.to_string().contains("DescripcionOperacion"), "{err}");
}

#[test]
fn un_obligatorio_ausente_se_nombra_en_el_error() {
    // El sobre se recorta a mano: falta `ImporteTotal`, que es minOccurs=1.
    let xml = xml_de(&alta("F2", ""));
    let recortado = xml.replace("<sum1:ImporteTotal>121.00</sum1:ImporteTotal>", "");
    let err = xsd::validate_registro(&recortado).expect_err("falta ImporteTotal");
    assert!(err.to_string().contains("ImporteTotal"), "{err}");
}

/// La cabecera del sobre: `ObligadoEmision` exige NombreRazon **y** NIF.
#[test]
fn la_cabecera_exige_el_obligado_completo() {
    let mut rec = alta("F2", "");
    rec["issuer_nif"] = json!("");
    let err = xsd::validate_registro(&xml_de(&rec)).expect_err("sin NIF del obligado");
    assert!(err.to_string().contains("NIF"), "{err}");
}

// ── Orden de la secuencia ─────────────────────────────────────────────────────────────────

/// Los tipos de la AEAT son `xs:sequence`: el orden es parte del esquema, no una preferencia.
#[test]
fn el_orden_de_la_secuencia_es_parte_del_esquema() {
    let xml = xml_de(&alta("F2", ""));
    // Intercambia CuotaTotal e ImporteTotal.
    let desordenado = xml.replace(
        "<sum1:CuotaTotal>21.00</sum1:CuotaTotal><sum1:ImporteTotal>121.00</sum1:ImporteTotal>",
        "<sum1:ImporteTotal>121.00</sum1:ImporteTotal><sum1:CuotaTotal>21.00</sum1:CuotaTotal>",
    );
    assert_ne!(desordenado, xml, "el reemplazo debe haber aplicado");
    let err = xsd::validate_registro(&desordenado).expect_err("orden alterado");
    assert!(err.to_string().contains("orden"), "{err}");
}

// ── Reglas de negocio que la AEAT castiga con código propio ───────────────────────────────

/// Error **1189**: una F1 sin `Destinatarios`. Es el que se comía la numeración antes de
/// `resolve_invoice_type`; aquí queda la última red por si alguien construye el registro a mano.
#[test]
fn una_f1_sin_destinatarios_no_sale_a_la_red() {
    let err = xsd::validate_registro(&xml_de(&alta("F1", ""))).expect_err("F1 sin destinatario");
    let msg = err.to_string();
    assert!(msg.contains("Destinatarios"), "{msg}");
    assert!(
        msg.contains("1189"),
        "el error de la AEAT, para poder buscarlo: {msg}"
    );
}

#[test]
fn una_f2_sin_destinatarios_es_correcta() {
    xsd::validate_registro(&xml_de(&alta("F2", "")))
        .expect("la simplificada no lleva destinatario");
}

/// `IdSistemaInformatico` está limitado a 2 caracteres; con más, la AEAT responde 1100.
#[test]
fn el_id_del_sistema_informatico_no_puede_pasar_de_dos_caracteres() {
    let xml = xml_de(&alta("F2", "")).replace(
        "<sum1:IdSistemaInformatico>EC</sum1:IdSistemaInformatico>",
        "<sum1:IdSistemaInformatico>ERPLORA-001</sum1:IdSistemaInformatico>",
    );
    let err = xsd::validate_registro(&xml).expect_err("id demasiado largo");
    assert!(err.to_string().contains("IdSistemaInformatico"), "{err}");
}

#[test]
fn el_tipo_de_factura_debe_estar_en_la_enumeracion() {
    let xml = xml_de(&alta("F2", "")).replace(
        "<sum1:TipoFactura>F2</sum1:TipoFactura>",
        "<sum1:TipoFactura>XX</sum1:TipoFactura>",
    );
    let err = xsd::validate_registro(&xml).expect_err("tipo inventado");
    assert!(err.to_string().contains("TipoFactura"), "{err}");
}

/// La huella es SHA-256 en hexadecimal: 64 caracteres. `TipoHuella` solo admite `01`.
#[test]
fn la_huella_debe_ser_sha256_hexadecimal() {
    let xml = xml_de(&alta("F2", "")).replace(&"A".repeat(64), "no-es-una-huella");
    let err = xsd::validate_registro(&xml).expect_err("huella inválida");
    assert!(err.to_string().contains("Huella"), "{err}");
}

// ── La tabla del validador NO puede separarse del XSD oficial ─────────────────────────────

/// Contrasta los obligatorios que exige el validador contra el **XSD oficial** vendorizado en
/// `schemas/aeat/`. Sin esto, la tabla es una lista escrita a mano que envejece en silencio: el
/// día que la AEAT publique una versión nueva del esquema, este test es el que se entera.
#[test]
fn los_obligatorios_del_validador_salen_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");

    for (tipo, esperado) in [
        ("RegistroFacturacionAltaType", xsd::REQUIRED_ALTA),
        ("RegistroFacturacionAnulacionType", xsd::REQUIRED_ANULACION),
    ] {
        let del_esquema = xsd::required_elements_of(xsd_src, tipo)
            .unwrap_or_else(|| panic!("{tipo} no está en el XSD vendorizado"));
        assert_eq!(
            del_esquema, esperado,
            "los obligatorios de {tipo} no coinciden con el XSD oficial"
        );
    }
}

/// El orden que aplica el validador es el del `xs:sequence` del XSD, no uno elegido a mano.
#[test]
fn el_orden_del_validador_sale_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    let del_esquema = xsd::sequence_of(xsd_src, "RegistroFacturacionAltaType").expect("secuencia");

    // Los que el módulo emite, en el orden en que los emite, deben ser una SUBSECUENCIA del
    // orden del esquema.
    let emitidos = xsd::ORDER_ALTA;
    let mut it = del_esquema.iter();
    for e in emitidos {
        assert!(
            it.any(|x| x == e),
            "`{e}` no aparece (o aparece fuera de orden) en el xs:sequence oficial"
        );
    }
}
