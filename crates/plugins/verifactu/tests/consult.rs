//! Consulta de registros a la AEAT (`ConsultaFactuSistemaFacturacion`) — hub#287.
//!
//! La consulta es la única vía por la que el Hub puede **recuperar** su cadena de lo que la
//! AEAT ya tiene. Nunca funcionó, por tres fallos encadenados que el SaaS destapó primero
//! (saas#1078 / #1081 / #1083) y que el Hub arrastra idénticos:
//!
//! 1. **La URL estaba inventada.** El WSDL oficial (`SistemaFacturacion.wsdl`, servicio
//!    `sfVerifactu`) publica la operación de consulta en el **MISMO** endpoint que el alta
//!    (`VerifactuSOAP`); no tiene ruta propia. Ocho rutas sondeadas con certificado real
//!    contra preproducción: todas 404, y la del alta 200.
//! 2. **El envelope.** `ConsultaLR.xsd` **importa** `SuministroInformacion.xsd`, así que el
//!    documento lleva DOS namespaces y cada elemento va en el del esquema donde se DECLARA.
//!    Además `ObligadoEmisionConsultaType` exige `NombreRazon` **además** del NIF.
//! 3. **El ancla.** La AEAT devuelve los registros del **más NUEVO al más viejo**; coger uno
//!    por posición acierta por casualidad. El orden lo da `FechaHoraHusoGenRegistro`, que
//!    forma parte de la propia huella.
//!
//! Y un cuarto, silencioso: un **SOAP Fault** se leía como «0 registros», que es la peor
//! lectura posible cuando lo que se intenta es recuperar la cadena.
use erplora_verifactu::{aeat, VerifactuError};

/// Respuesta **REAL** de la AEAT de preproducción, capturada tal cual con el certificado de
/// ERPlora el 2026-08-01 (`tests/aeat_live.rs`). No es una respuesta inventada, y la diferencia
/// importa: el fixture que se escribió a mano *antes* de capturarla era más simple que la real y
/// dejaba pasar un fallo (ver `el_numero_de_factura_no_lo_pisa_el_registro_anterior`).
///
/// Lo que la respuesta real tiene y un mock razonable no anticipa:
///
/// - `Encadenamiento/RegistroAnterior` repite `IDEmisorFactura`, `NumSerieFactura`,
///   `FechaExpedicionFactura` y `Huella` — **del registro ANTERIOR**, dentro del bloque del
///   registro actual.
/// - `Destinatarios` repite `NombreRazon`/`NIF`, y `DatosPresentacion` repite NIF y timestamps.
/// - `EstadoRegistro` es a la vez **contenedor y hoja** (`<EstadoRegistro><EstadoRegistro>`).
/// - No trae `CSV` en ningún registro.
const REAL_RESPONSE: &str = include_str!("fixtures/consulta_preproduccion_2026-08-01.xml");

const SOAP_FAULT: &str = r#"<?xml version="1.0" encoding="UTF-8"?>
<env:Envelope xmlns:env="http://schemas.xmlsoap.org/soap/envelope/"><env:Body><env:Fault>
<faultcode>env:Client</faultcode>
<faultstring>Codigo[4102].El XML no cumple el esquema. Falta informar campo obligatorio.: IDVersion</faultstring>
</env:Fault></env:Body></env:Envelope>"#;

// ── 1. El endpoint ────────────────────────────────────────────────────────────────────────

/// The consult operation is published on the SAME endpoint as the alta. The path
/// `.../SistemaFacturacion/ConsultaFactuSistemaFacturacion` does not exist: 404 (saas#1081).
///
/// Both axes since hub#320 — the entry point also depends on the certificate that signs, and a
/// delegated hub has to be able to recover its chain through its own door
/// (`entry_point_by_certificate.rs`).
#[test]
fn the_consult_uses_the_same_endpoint_as_the_alta() {
    for env in ["testing", "production"] {
        for kind in ["own", "delegated"] {
            assert_eq!(
                aeat::consult_endpoint(env, kind),
                aeat::endpoint(env, kind),
                "the WSDL publishes ConsultaFactuSistemaFacturacion on VerifactuSOAP ({env}, {kind})"
            );
        }
    }
}

#[test]
fn the_consult_endpoint_no_longer_carries_the_invented_path() {
    for env in ["testing", "production"] {
        for kind in ["own", "delegated"] {
            assert!(
                !aeat::consult_endpoint(env, kind).contains("ConsultaFactu"),
                "that path does not exist at the AEAT: 404 verified with a real certificate"
            );
        }
    }
}

// ── 2. El envelope ────────────────────────────────────────────────────────────────────────

fn envelope() -> String {
    aeat::build_consult_soap("B27593136", "ERPLORA CLOUD SL", "2026", "08", None).expect("envelope")
}

#[test]
fn el_envelope_declara_los_dos_namespaces() {
    let xml = envelope();
    assert!(xml.contains("ConsultaLR.xsd"), "{xml}");
    assert!(xml.contains("SuministroInformacion.xsd"), "{xml}");
}

/// El fallo exacto que devolvía la AEAT: `Falta informar campo obligatorio.: IDVersion`.
/// El campo estaba, pero en el namespace del envoltorio en vez del del esquema que lo declara.
#[test]
fn los_campos_de_dentro_van_en_suministroinformacion() {
    let xml = envelope();
    assert!(
        xml.contains("<sum1:IDVersion>1.0</sum1:IDVersion>"),
        "{xml}"
    );
    assert!(xml.contains("<sum1:NIF>B27593136</sum1:NIF>"), "{xml}");
    assert!(
        xml.contains("<sum1:NombreRazon>ERPLORA CLOUD SL</sum1:NombreRazon>"),
        "{xml}"
    );
    assert!(
        xml.contains("<sum1:Ejercicio>2026</sum1:Ejercicio>"),
        "{xml}"
    );
    assert!(xml.contains("<sum1:Periodo>08</sum1:Periodo>"), "{xml}");
}

#[test]
fn el_envoltorio_va_en_consultalr() {
    let xml = envelope();
    for tag in [
        "ConsultaFactuSistemaFacturacion",
        "Cabecera",
        "FiltroConsulta",
        "PeriodoImputacion",
    ] {
        assert!(
            xml.contains(&format!("<con:{tag}>")),
            "{tag} no va en ConsultaLR: {xml}"
        );
    }
}

/// `ObligadoEmisionConsultaType` exige `NombreRazon` además del NIF. Mandarlo incompleto solo
/// produce otro 4102 DESPUÉS de haber hablado con Hacienda: mejor negarse antes.
#[test]
fn sin_razon_social_del_obligado_no_se_construye_el_envelope() {
    assert!(aeat::build_consult_soap("B27593136", "", "2026", "08", None).is_err());
    assert!(aeat::build_consult_soap("B27593136", "   ", "2026", "08", None).is_err());
}

#[test]
fn sin_nif_del_obligado_no_se_construye_el_envelope() {
    assert!(aeat::build_consult_soap("", "ERPLORA CLOUD SL", "2026", "08", None).is_err());
}

// NOTA — aquí vivía `sin_periodo_no_se_emite_el_elemento_vacio`, que afirmaba que sin periodo
// «el filtro es solo el ejercicio» y daba por buena la construcción del sobre. Era objetivamente
// falso, y lo demostró el servicio real (2026-08-02, ADR-0189): ese sobre recibe
// `Codigo[4102].El XML no cumple el esquema. Falta informar campo obligatorio.: Periodo`.
// El contrato correcto —el sobre no se construye— lo cubre
// `el_sobre_de_consulta_sin_periodo_no_se_construye`, al final de este fichero.

// ── 3. El parser, sobre la respuesta REAL ─────────────────────────────────────────────────

#[test]
fn lee_todos_los_registros_de_la_respuesta_real() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");
    assert_eq!(recs.len(), 4, "{recs:?}");
}

/// El `RegistroAnterior` del propio bloque necesita nº, fecha y huella — no solo la huella. En la
/// respuesta real esos campos viven en bloques distintos (`IDFactura` /
/// `DatosRegistroFacturacion`), así que alinearlos por posición no vale: hay que agruparlos POR
/// REGISTRO.
#[test]
fn extrae_lo_que_la_cadena_necesita_de_cada_registro() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");

    assert_eq!(recs[0].invoice_number, "PRU-20260801-0004");
    assert_eq!(recs[0].invoice_date, "01-08-2026");
    assert_eq!(recs[0].issuer_nif, "B27593136");
    assert_eq!(
        recs[0].record_hash,
        "3056799E8B154276ED2F71108D8570168FD8FE345428C5270459C90AEFBF3696"
    );
    assert_eq!(recs[0].estado, "Correcto");
}

/// **El fallo que solo destapó la respuesta real.** Dentro del bloque de CADA registro, la AEAT
/// mete un `Encadenamiento/RegistroAnterior` con el `NumSerieFactura`, la `FechaExpedicionFactura`
/// y la `Huella` **del registro anterior**. Un parser que vaya leyendo etiquetas por nombre se
/// queda con esos, no con los del registro que está leyendo.
///
/// Concretamente: el primer registro es `PRU-20260801-0004` y su `RegistroAnterior` es
/// `PRU-20260801-0003`. Antes de este arreglo el ancla salía con el número del anterior — es
/// decir, la recuperación anclaba señalando a la factura equivocada.
///
/// Ningún mock escrito a mano tenía esto: hizo falta la captura contra preproducción.
#[test]
fn el_numero_de_factura_no_lo_pisa_el_registro_anterior() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");

    assert_eq!(
        recs[0].invoice_number, "PRU-20260801-0004",
        "es el número del registro, no el de su RegistroAnterior (PRU-20260801-0003)"
    );
    assert_eq!(
        recs[0].record_hash, "3056799E8B154276ED2F71108D8570168FD8FE345428C5270459C90AEFBF3696",
        "es la huella PROPIA, no la del RegistroAnterior (81050190…)"
    );
    // El segundo registro sí es el 0003, y su huella es la que el primero declara como anterior.
    assert_eq!(recs[1].invoice_number, "PRU-20260801-0003");
    assert_eq!(
        recs[1].record_hash,
        "81050190F9B2057B3E83C8A09F7C1B05FA99DF52D4859EEF96C57031DFD7AA8F"
    );
}

/// La clave de ORDEN de la cadena: entra en el cálculo de la propia huella.
#[test]
fn captura_la_marca_temporal_de_generacion() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");
    assert_eq!(recs[0].generated_at, "2026-08-01T18:38:11Z");
    assert_eq!(recs[3].generated_at, "2026-08-01T15:28:04Z");
}

/// En la respuesta real `EstadoRegistro` es a la vez **contenedor y hoja**
/// (`<EstadoRegistro><TimestampUltimaModificacion/><EstadoRegistro>Correcto</EstadoRegistro></…>`):
/// quedarse con el contenedor —que no tiene texto— deja el registro sin estado.
#[test]
fn el_estado_sale_de_la_hoja_no_del_contenedor() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");
    assert_eq!(recs[0].estado, "Correcto");
    assert_eq!(
        recs[3].estado, "AceptadoConErrores",
        "el registro que la AEAT aceptó CON el error 2007"
    );
}

/// Devolver `[]` ante un fallo lo hace indistinguible de «la AEAT no tiene nada que
/// recuperar», que es justo la lectura que rompe la recuperación.
#[test]
fn un_soap_fault_es_un_error_no_cero_registros() {
    let err = aeat::parse_consult_response(SOAP_FAULT).expect_err("un Fault no son 0 registros");
    let msg = err.to_string();
    assert!(
        msg.contains("4102"),
        "el mensaje de la AEAT debe llegar entero: {msg}"
    );
}

// ── 4. El ancla ───────────────────────────────────────────────────────────────────────────

/// La AEAT devuelve del MÁS NUEVO al más viejo. Coger uno por posición acierta por casualidad;
/// el criterio es `FechaHoraHusoGenRegistro`, que forma parte de la huella.
#[test]
fn el_ancla_es_el_mas_reciente_no_el_primero_de_la_lista() {
    let recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");
    let latest = aeat::pick_latest_record(&recs).expect("hay ancla");
    assert_eq!(latest.invoice_number, "PRU-20260801-0004");
}

/// El mismo contenido en orden inverso debe dar el MISMO ancla: si dependiera de la posición,
/// este test y el anterior no podrían pasar a la vez.
#[test]
fn el_ancla_no_depende_del_orden_en_que_lleguen() {
    let mut recs = aeat::parse_consult_response(REAL_RESPONSE).expect("respuesta válida");
    recs.reverse();
    let latest = aeat::pick_latest_record(&recs).expect("hay ancla");
    assert_eq!(latest.invoice_number, "PRU-20260801-0004");
}

/// Un registro sin huella no sirve como ancla: la huella ES el eslabón.
#[test]
fn los_registros_sin_huella_no_sirven_de_ancla() {
    let sin_huella = vec![aeat::ConsultRecord {
        invoice_number: "X".into(),
        ..Default::default()
    }];
    assert!(aeat::pick_latest_record(&sin_huella).is_none());
}

/// Sin marca temporal no se puede ordenar, pero no puede reventar: se prefiere el fechado.
#[test]
fn sobrevive_a_un_registro_sin_marca_temporal() {
    let recs = vec![
        aeat::ConsultRecord {
            invoice_number: "A".into(),
            record_hash: "1".into(),
            ..Default::default()
        },
        aeat::ConsultRecord {
            invoice_number: "B".into(),
            record_hash: "2".into(),
            generated_at: "2026-08-01T10:00:00Z".into(),
            ..Default::default()
        },
    ];
    assert_eq!(aeat::pick_latest_record(&recs).unwrap().invoice_number, "B");
}

/// `Periodo` **no es opcional**. Se emitía el filtro solo con `Ejercicio` cuando el periodo
/// llegaba vacío, dando por hecho que eso consultaba el año entero. La AEAT de preproducción
/// responde (verificado el 2026-08-02, ADR-0189):
///
/// ```text
/// Codigo[4102].El XML no cumple el esquema. Falta informar campo obligatorio.: Periodo
/// ```
///
/// Un sobre así se rechaza DESPUÉS de haber hablado con Hacienda, así que se corta antes.
#[test]
fn el_sobre_de_consulta_sin_periodo_no_se_construye() {
    let err = aeat::build_consult_soap("B27593136", "ERPLORA CLOUD SL", "2026", "", None)
        .expect_err("sin Periodo la AEAT responde 4102: no se manda");
    assert!(
        matches!(&err, VerifactuError::MissingField(field) if *field == "Periodo"),
        "the error names the field by code, not by prose: {err}"
    );
}

#[test]
fn el_sobre_de_consulta_con_periodo_lo_incluye() {
    let xml = aeat::build_consult_soap("B27593136", "ERPLORA CLOUD SL", "2026", "08", None)
        .expect("con periodo se construye");
    assert!(xml.contains("<sum1:Periodo>08</sum1:Periodo>"), "{xml}");
    assert!(
        xml.contains("<sum1:Ejercicio>2026</sum1:Ejercicio>"),
        "{xml}"
    );
}
