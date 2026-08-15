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

/// El registro **encadenado** — es decir, TODOS menos el primero de la vida del sistema.
///
/// `Encadenamiento/RegistroAnterior` repite cuatro nombres que también existen en la secuencia
/// exterior (`IDEmisorFactura`, `NumSerieFactura`, `FechaExpedicionFactura` y sobre todo
/// **`Huella`**, que es el ÚLTIMO elemento de `ORDER_ALTA`). El validador recorría el documento
/// plano, sin noción de anidamiento, así que la `Huella` del registro anterior agotaba el
/// iterador de orden y el `SistemaInformatico` que viene después parecía «fuera de orden».
///
/// Resultado: el gate previo a la transmisión rechazaba **toda factura que no fuera la primera**,
/// antes de tocar la red. Ningún test lo cazó porque todos construían el XML con `prev = None`.
#[test]
fn el_alta_encadenada_pasa_la_validacion() {
    let previo = json!({
        "issuer_nif": "B27593136",
        "invoice_number": "FA/000",
        "invoice_date": "2026-08-01",
        "record_hash": "B".repeat(64),
    });
    let mut rec = alta("F2", "");
    rec["is_first_record"] = json!(0);
    let xml = aeat::build_soap(&rec, &config(), Some(&previo), "hub-1");
    assert!(xml.contains("<sum1:RegistroAnterior>"), "{xml}");

    xsd::validate_registro(&xml)
        .expect("una factura encadenada es el caso NORMAL: debe pasar el gate");
}

/// La anulación encadenada tiene el mismo choque de nombres (`ORDER_ANULACION` también acaba en
/// `Huella`), y además su `IDFactura` usa los nombres con sufijo `Anulada`.
#[test]
fn la_anulacion_encadenada_pasa_la_validacion() {
    let previo = json!({
        "issuer_nif": "B27593136",
        "invoice_number": "FA/000",
        "invoice_date": "2026-08-01",
        "record_hash": "B".repeat(64),
    });
    let mut rec = alta("F1", "B12345678");
    rec["record_type"] = json!("anulacion");
    rec["is_first_record"] = json!(0);
    let xml = aeat::build_soap(&rec, &config(), Some(&previo), "hub-1");
    assert!(xml.contains("<sum1:RegistroAnterior>"), "{xml}");

    xsd::validate_registro(&xml).expect("una anulación encadenada también debe pasar el gate");
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

// ── DetalleDesglose: las reglas que el XSD NO atrapa (hub#292) ────────────────────────────
//
// Un desglose mal CALIFICADO valida contra el esquema igual de bien que uno correcto: los tipos
// del XSD admiten cualquier combinación de `CalificacionOperacion` con `TipoImpositivo` y
// `CuotaRepercutida`. Lo que rechaza la AEAT son las **validaciones** (documento «Validaciones ·
// Sistemas Informáticos de Facturación y Sistemas VERI*FACTU» v1.2.2), y por eso van en código.

/// Sustituye el bloque `Desglose` del XML por uno construido a mano, para poder probar detalles
/// que el módulo nunca generaría (y que otro caller sí podría construir).
fn con_desglose(detalle: &str) -> String {
    con_desglose_de("F2", "", detalle)
}

/// Same, choosing the invoice type and recipient: §15.8 only bites on `F2`, so its tests need an
/// `F1` counterexample built the same way.
fn con_desglose_de(tipo: &str, nif: &str, detalle: &str) -> String {
    let xml = xml_de(&alta(tipo, nif));
    let ini = xml.find("<sum1:Desglose>").expect("Desglose");
    let fin = xml.find("</sum1:Desglose>").expect("cierre") + "</sum1:Desglose>".len();
    format!(
        "{}<sum1:Desglose>{detalle}</sum1:Desglose>{}",
        &xml[..ini],
        &xml[fin..]
    )
}

const DETALLE_OK: &str = "<sum1:DetalleDesglose>\
     <sum1:Impuesto>01</sum1:Impuesto>\
     <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
     <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
     <sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>\
     <sum1:BaseImponibleOimporteNoSujeto>100.00</sum1:BaseImponibleOimporteNoSujeto>\
     <sum1:CuotaRepercutida>21.00</sum1:CuotaRepercutida>\
     </sum1:DetalleDesglose>";

#[test]
fn un_detalle_bien_calificado_pasa() {
    xsd::validate_registro(&con_desglose(DETALLE_OK)).expect("venta nacional al 21 %");
}

/// **Error 1237.** Es la regla que más caro sale descubrir tarde, porque el XSD la deja pasar.
#[test]
fn el_1237_no_deja_informar_tipo_ni_cuota_con_n2() {
    let malo = DETALLE_OK.replace(
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
        "<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>",
    );
    let err = xsd::validate_registro(&con_desglose(&malo)).expect_err("N2 con tipo y cuota");
    let msg = err.to_string();
    assert!(msg.contains("1237"), "el código de la AEAT, para buscarlo: {msg}");
    assert!(msg.contains("TipoImpositivo") || msg.contains("CuotaRepercutida"), "{msg}");
}

/// El régimen 17 (OSS) **no** es una excepción al 1237 desde la revisión v1.0.6 (25/04/2025) del
/// documento de validaciones. Este test es el que impide reintroducir el mapeo del SaaS.
#[test]
fn el_regimen_17_tampoco_deja_informar_tipo_con_n2() {
    let malo = DETALLE_OK
        .replace(
            "<sum1:ClaveRegimen>01</sum1:ClaveRegimen>",
            "<sum1:ClaveRegimen>17</sum1:ClaveRegimen>",
        )
        .replace(
            "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
            "<sum1:CalificacionOperacion>N2</sum1:CalificacionOperacion>",
        );
    let err = xsd::validate_registro(&con_desglose(&malo)).expect_err("17 no salva del 1237");
    assert!(err.to_string().contains("1237"), "{err}");
}

/// **§15.5.** Con `OperacionExenta` no se informan tipo, cuota ni recargo.
#[test]
fn una_exenta_no_puede_llevar_tipo_ni_cuota() {
    let malo = DETALLE_OK.replace(
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
        "<sum1:OperacionExenta>E1</sum1:OperacionExenta>",
    );
    let err = xsd::validate_registro(&con_desglose(&malo)).expect_err("exenta con tipo");
    assert!(err.to_string().contains("OperacionExenta"), "{err}");
}

/// El `<choice>` del XSD: ni los dos, ni ninguno.
#[test]
fn calificacion_y_exenta_son_excluyentes() {
    let ambos = DETALLE_OK.replace(
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
         <sum1:OperacionExenta>E1</sum1:OperacionExenta>",
    );
    assert!(xsd::validate_registro(&con_desglose(&ambos)).is_err(), "los dos a la vez");

    let ninguno = DETALLE_OK.replace(
        "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
        "",
    );
    assert!(xsd::validate_registro(&con_desglose(&ninguno)).is_err(), "ninguno de los dos");
}

/// **§15.4.** `S2` exige `TipoImpositivo = 0` y `CuotaRepercutida = 0` **presentes**: es el caso
/// que se comporta al revés que N1/N2, y confundirlos es un rechazo.
#[test]
fn la_s2_exige_ceros_explicitos() {
    let sin_ceros = "<sum1:DetalleDesglose>\
         <sum1:Impuesto>01</sum1:Impuesto>\
         <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
         <sum1:CalificacionOperacion>S2</sum1:CalificacionOperacion>\
         <sum1:BaseImponibleOimporteNoSujeto>100.00</sum1:BaseImponibleOimporteNoSujeto>\
         </sum1:DetalleDesglose>";
    let err = xsd::validate_registro(&con_desglose(sin_ceros)).expect_err("S2 sin ceros");
    assert!(err.to_string().contains("S2"), "{err}");

    let con_ceros = DETALLE_OK
        .replace(
            "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
            "<sum1:CalificacionOperacion>S2</sum1:CalificacionOperacion>",
        )
        .replace("21.00</sum1:TipoImpositivo>", "0.00</sum1:TipoImpositivo>")
        .replace("21.00</sum1:CuotaRepercutida>", "0.00</sum1:CuotaRepercutida>");
    xsd::validate_registro(&con_desglose(&con_ceros)).expect("S2 con ceros explícitos");
}

/// **§15.6.6.** `ClaveRegimen 08` obliga a `N2`.
#[test]
fn el_regimen_08_exige_n2() {
    let malo = DETALLE_OK.replace(
        "<sum1:ClaveRegimen>01</sum1:ClaveRegimen>",
        "<sum1:ClaveRegimen>08</sum1:ClaveRegimen>",
    );
    let err = xsd::validate_registro(&con_desglose(&malo)).expect_err("08 con S1");
    assert!(err.to_string().contains("08"), "{err}");
}

/// **§15.1.** Con IVA y `S1`, la AEAT solo admite `0; 2; 4; 5; 7,5; 10; 21`. Ahí es donde
/// aterrizaba el recargo de equivalencia cuando salía como una línea con `TipoImpositivo 5,20`.
#[test]
fn un_tipo_que_no_es_de_iva_no_sale_a_la_red() {
    let malo = DETALLE_OK.replace("21.00</sum1:TipoImpositivo>", "5.20</sum1:TipoImpositivo>");
    let err = xsd::validate_registro(&con_desglose(&malo)).expect_err("5,20 % no es tipo de IVA");
    assert!(err.to_string().contains("TipoImpositivo"), "{err}");
}

/// …y ese mismo 5,20 % **sí** es válido como recargo de equivalencia dentro de la línea del 21 %.
#[test]
fn el_recargo_de_equivalencia_es_valido_dentro_de_la_linea_del_iva() {
    let bueno = DETALLE_OK.replace(
        "</sum1:DetalleDesglose>",
        "<sum1:TipoRecargoEquivalencia>5.20</sum1:TipoRecargoEquivalencia>\
         <sum1:CuotaRecargoEquivalencia>5.20</sum1:CuotaRecargoEquivalencia>\
         </sum1:DetalleDesglose>",
    );
    xsd::validate_registro(&con_desglose(&bueno)).expect("recargo en la línea del IVA");
}

/// El tipo de IGIC (7 %) NO está en la lista de tipos de IVA — y con `Impuesto 03` no tiene por
/// qué estarlo. Confundir el ámbito de §15.1 haría imposible facturar en Canarias.
#[test]
fn un_tipo_de_igic_es_valido_con_impuesto_03() {
    let canario = DETALLE_OK
        .replace(
            "<sum1:Impuesto>01</sum1:Impuesto>",
            "<sum1:Impuesto>03</sum1:Impuesto>",
        )
        .replace("21.00</sum1:TipoImpositivo>", "7.00</sum1:TipoImpositivo>")
        .replace("21.00</sum1:CuotaRepercutida>", "7.00</sum1:CuotaRepercutida>");
    xsd::validate_registro(&con_desglose(&canario)).expect("IGIC al 7 %");
}

/// Enumeraciones: `Impuesto`, `CalificacionOperacion` y `OperacionExenta` son listas cerradas.
#[test]
fn las_enumeraciones_del_detalle_son_cerradas() {
    for (de, a) in [
        ("<sum1:Impuesto>01</sum1:Impuesto>", "<sum1:Impuesto>04</sum1:Impuesto>"),
        (
            "<sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>",
            "<sum1:CalificacionOperacion>S3</sum1:CalificacionOperacion>",
        ),
    ] {
        let malo = DETALLE_OK.replace(de, a);
        assert!(
            xsd::validate_registro(&con_desglose(&malo)).is_err(),
            "debería rechazar `{a}`"
        );
    }
}

/// `E7`/`E8` son exenciones **de IGIC**: con IVA no existen (§15.5).
#[test]
fn las_exenciones_e7_e8_son_solo_de_igic() {
    let exenta = |impuesto: &str, causa: &str| {
        format!(
            "<sum1:DetalleDesglose>\
             <sum1:Impuesto>{impuesto}</sum1:Impuesto>\
             <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
             <sum1:OperacionExenta>{causa}</sum1:OperacionExenta>\
             <sum1:BaseImponibleOimporteNoSujeto>100.00</sum1:BaseImponibleOimporteNoSujeto>\
             </sum1:DetalleDesglose>"
        )
    };
    xsd::validate_registro(&con_desglose(&exenta("03", "E7"))).expect("E7 con IGIC");
    assert!(
        xsd::validate_registro(&con_desglose(&exenta("01", "E7"))).is_err(),
        "E7 no existe con IVA"
    );
    xsd::validate_registro(&con_desglose(&exenta("01", "E1"))).expect("E1 con IVA");
}

/// El XSD limita `DetalleDesglose` a `maxOccurs="12"`, y un `Desglose` sin ningún detalle no es
/// un desglose.
#[test]
fn el_desglose_lleva_entre_uno_y_doce_detalles() {
    assert!(xsd::validate_registro(&con_desglose("")).is_err(), "sin detalle");
    let trece = DETALLE_OK.repeat(13);
    let err = xsd::validate_registro(&con_desglose(&trece)).expect_err("13 detalles");
    assert!(err.to_string().contains("12"), "{err}");
}

/// El orden dentro del `DetalleType` también es `xs:sequence`.
#[test]
fn el_orden_dentro_del_detalle_es_parte_del_esquema() {
    let desordenado = "<sum1:DetalleDesglose>\
         <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
         <sum1:Impuesto>01</sum1:Impuesto>\
         <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
         <sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>\
         <sum1:BaseImponibleOimporteNoSujeto>100.00</sum1:BaseImponibleOimporteNoSujeto>\
         <sum1:CuotaRepercutida>21.00</sum1:CuotaRepercutida>\
         </sum1:DetalleDesglose>";
    let err = xsd::validate_registro(&con_desglose(desordenado)).expect_err("orden alterado");
    assert!(err.to_string().contains("orden"), "{err}");
}

/// Las enumeraciones del validador tampoco pueden separarse del XSD oficial: si la AEAT añade un
/// código (como `E7`/`E8` o la clave de régimen `21`, que faltaban en la copia que teníamos
/// vendorizada), este test es el que se entera.
#[test]
fn las_enumeraciones_del_detalle_salen_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    for (tipo, esperado) in [
        ("ImpuestoType", xsd::IMPUESTO),
        ("CalificacionOperacionType", xsd::CALIFICACION),
        ("OperacionExentaType", xsd::OPERACION_EXENTA),
        ("IdOperacionesTrascendenciaTributariaType", xsd::CLAVE_REGIMEN),
    ] {
        let del_esquema = xsd::enumeration_of(xsd_src, tipo)
            .unwrap_or_else(|| panic!("{tipo} no está en el XSD vendorizado"));
        assert_eq!(
            del_esquema, esperado,
            "la enumeración de {tipo} no coincide con el XSD oficial"
        );
    }
}

/// Y el orden del detalle sale del `xs:sequence` de `DetalleType`, no de una lista a mano.
#[test]
fn el_orden_del_detalle_sale_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    let del_esquema = xsd::sequence_of(xsd_src, "DetalleType").expect("DetalleType");
    // El `<choice>` no es un `<element>` del sequence, así que el scraper no lo ve: la tabla del
    // validador lo intercala. Quitándolo, tiene que coincidir literalmente.
    let sin_choice: Vec<&str> = xsd::ORDER_DETALLE
        .iter()
        .copied()
        .filter(|e| *e != "CalificacionOperacion" && *e != "OperacionExenta")
        .collect();
    assert_eq!(del_esquema, sin_choice);
}

// ── §15.8: the 3,000 EUR ceiling of a simplified invoice (hub#297) ────────────────────────
//
// «Cuando TipoFactura sea "F2", se validará que Ʃ (BaseImponibleOimporteNoSujeto +
// CuotaRepercutida) de todas las líneas de detalle no sea superior a 3.000,00 euros. Se admitirá
// un error de +10,00 euros.» — Validaciones AEAT v1.2.2, §15.8.
//
// Unlike the 400 EUR ceiling of the simplified invoice (ADR-0184), which is the merchant's
// obligation and is deliberately NOT enforced, this one is a **certain rejection** by the
// service — and a rejection arrives with the chain number already spent.

/// One 21 % VAT line with the given base and tax amount, as the AEAT formats them.
fn linea_iva(base: &str, cuota: &str) -> String {
    format!(
        "<sum1:DetalleDesglose>\
         <sum1:Impuesto>01</sum1:Impuesto>\
         <sum1:ClaveRegimen>01</sum1:ClaveRegimen>\
         <sum1:CalificacionOperacion>S1</sum1:CalificacionOperacion>\
         <sum1:TipoImpositivo>21.00</sum1:TipoImpositivo>\
         <sum1:BaseImponibleOimporteNoSujeto>{base}</sum1:BaseImponibleOimporteNoSujeto>\
         <sum1:CuotaRepercutida>{cuota}</sum1:CuotaRepercutida>\
         </sum1:DetalleDesglose>"
    )
}

/// Inserts an element as a DIRECT child of `RegistroAlta`, right before `marcador` (which must be
/// a direct child too, so the new element lands at the depth the validator reads).
fn con_elemento_antes_de(xml: &str, marcador: &str, elemento: &str) -> String {
    let out = xml.replacen(marcador, &format!("{elemento}{marcador}"), 1);
    assert_ne!(out, *xml, "el marcador `{marcador}` no está en el sobre");
    out
}

/// The case that pays for this rule: a 3.630 € simplified ticket. Today it reaches the AEAT, gets
/// rejected, and the invoice number is already burnt.
#[test]
fn una_f2_por_encima_de_3000_no_llega_a_la_aeat() {
    let xml = con_desglose(&linea_iva("3000.00", "630.00"));
    let err = xsd::validate_registro(&xml).expect_err("una F2 de 3.630 € es un rechazo seguro");
    let msg = err.to_string();
    assert!(msg.contains("15.8"), "la referencia, para buscarla: {msg}");
    assert!(msg.contains("F2"), "{msg}");
    assert!(msg.contains("3.000") || msg.contains("3000"), "{msg}");
}

/// The threshold is 3.000 € **plus the +10 € margin the AEAT admits**: 3.010,00 € passes and
/// 3.010,01 € does not. Getting this off by one cent either lets a rejection through or blocks a
/// legitimate sale.
#[test]
fn el_limite_de_la_f2_esta_en_3010_exactos_e_inclusive() {
    // 2.487,60 × 21 % = 522,40 → 3.010,00 exactos.
    xsd::validate_registro(&con_desglose(&linea_iva("2487.60", "522.40")))
        .expect("3.010,00 € es el último importe admitido (3.000 + los 10 € de tolerancia)");

    let err = xsd::validate_registro(&con_desglose(&linea_iva("2487.61", "522.40")))
        .expect_err("3.010,01 € ya se pasa");
    assert!(err.to_string().contains("15.8"), "{err}");
}

/// The tolerance is not decorative: between 3.000 € and 3.010 € the AEAT admits the record, so
/// the validator must not block it.
#[test]
fn una_f2_de_3005_pasa_por_la_tolerancia_de_10_euros() {
    // 2.483,47 × 21 % = 521,53 → 3.005,00.
    xsd::validate_registro(&con_desglose(&linea_iva("2483.47", "521.53")))
        .expect("3.005 € entra por la tolerancia de +10 € (§15.8)");
}

/// §15.8 adds up **every** detail line. Checking line by line would let a two-line ticket through.
#[test]
fn el_limite_de_la_f2_suma_todas_las_lineas() {
    let una = linea_iva("1500.00", "315.00"); // 1.815 € — por sí sola, muy por debajo
    xsd::validate_registro(&con_desglose(&una)).expect("una sola línea de 1.815 € es válida");

    let dos = format!("{una}{una}"); // 3.630 €
    let err = xsd::validate_registro(&con_desglose(&dos)).expect_err("dos líneas suman 3.630 €");
    assert!(err.to_string().contains("15.8"), "{err}");
}

/// The rule is scoped to `F2`. A complete invoice has no ceiling — blocking one would stop the
/// normal way of billing above 3.000 €, which is exactly what the operator has to do instead.
#[test]
fn el_limite_de_3000_no_aplica_a_una_factura_completa() {
    let xml = con_desglose_de("F1", "B12345678", &linea_iva("3000.00", "630.00"));
    xsd::validate_registro(&xml).expect("una F1 de 3.630 € es perfectamente válida");
}

/// First exception of §15.8: a billing agreement (`NumRegistroAcuerdoFacturacion`). The module
/// does not emit it today, but the rule has to know about it or it will block a legitimate sale
/// the day it does.
#[test]
fn el_acuerdo_de_facturacion_exime_del_limite_de_la_f2() {
    let base = con_desglose(&linea_iva("3000.00", "630.00"));
    assert!(
        xsd::validate_registro(&base).is_err(),
        "sin acuerdo, se rechaza"
    );

    let con_acuerdo = con_elemento_antes_de(
        &base,
        "<sum1:TipoHuella>",
        "<sum1:NumRegistroAcuerdoFacturacion>ACU-001</sum1:NumRegistroAcuerdoFacturacion>",
    );
    xsd::validate_registro(&con_acuerdo).expect("con acuerdo de facturación §15.8 no aplica");
}

/// Second exception: `FacturaSinIdentifDestinatarioArt61d = "S"`. Only `"S"` exempts — an `"N"`
/// (the other value of the enumeration) is a normal F2 and keeps the ceiling.
#[test]
fn el_articulo_61d_exime_del_limite_de_la_f2_solo_con_s() {
    let base = con_desglose(&linea_iva("3000.00", "630.00"));
    let art61d = |v: &str| {
        con_elemento_antes_de(
            &base,
            "<sum1:Desglose>",
            &format!(
                "<sum1:FacturaSinIdentifDestinatarioArt61d>{v}\
                 </sum1:FacturaSinIdentifDestinatarioArt61d>"
            ),
        )
    };
    xsd::validate_registro(&art61d("S")).expect("con art. 61.d = S, §15.8 no aplica");
    assert!(
        xsd::validate_registro(&art61d("N")).is_err(),
        "`N` no es una excepción: sigue siendo una F2 con su techo"
    );
}

/// The two exceptions are named after the **official XSD**, not after the prose of the validations
/// document (which writes `Articulo61d` while the schema says `Art61d`). A typo here would make
/// the exception silently unreachable.
#[test]
fn los_nombres_de_las_excepciones_del_15_8_salen_del_xsd_oficial() {
    let xsd_src = include_str!("../schemas/aeat/SuministroInformacion.xsd");
    let del_esquema = xsd::sequence_of(xsd_src, "RegistroFacturacionAltaType").expect("secuencia");
    for nombre in xsd::F2_LIMIT_EXEMPTIONS {
        assert!(
            del_esquema.iter().any(|e| e == nombre),
            "`{nombre}` no está en el xs:sequence oficial: {del_esquema:?}"
        );
    }
}
