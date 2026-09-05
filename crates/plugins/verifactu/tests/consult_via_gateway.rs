//! Consultar a la AEAT **por la celda** cuando el hub no tiene certificado (hub#1436).
//!
//! La consulta es la única vía por la que el Hub recupera su cadena de lo que la AEAT ya tiene
//! (`recover_from_aeat`, `query_aeat_records` y el auto-rechain de un rechazo de encadenamiento).
//! Hasta hub#1436 esa consulta se hacía SIEMPRE con la identity del core, así que en la vía
//! gateway —la del hub sin certificado, ADR-0320— no podía hacerse: el motor se negaba
//! con «no hay certificado con el que firmar», el auto-rechain se saltaba a propósito y un hub
//! que restaurase un backup se quedaba con la cadena rota y **sin ninguna recuperación**, ni
//! automática ni manual.
//!
//! # La trampa del esquema: la consulta NO lleva `Representante`
//!
//! En el alta, quién presenta viaja como un bloque `Cabecera/Representante` con NIF y razón
//! social (hub#1460). **En la consulta no existe ese bloque.** `CabeceraConsultaSf`
//! (`SuministroInformacion.xsd`) declara la secuencia
//! `IDVersion → (ObligadoEmision | Destinatario) → IndicadorRepresentante?`, y la representación
//! se declara con un **flag**:
//!
//! > `IndicadorRepresentante`: «Flag opcional que tendrá valor S si quien realiza la consulta es
//! > el representante/asesor del obligado tributario. Permite, a quien realiza la consulta,
//! > obtener los registros de facturación en los que figura como representante.»
//!
//! Por eso `aeat::set_representative` —que sí sirve para el alta— **no vale aquí**: estamparía un
//! `<sum1:Representante>` que el esquema de consulta no admite, y la AEAT contestaría 4102
//! después de haber hablado con Hacienda. Y sin el flag, el Sello de ERPlora consultando el
//! `ObligadoEmision` de un cliente es exactamente el caso del fault **4112** («el titular del
//! certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o Sucesor»), medido
//! contra prewww el 2026-09-02: la consulta no devolvería la cadena del cliente.
use erplora_verifactu::aeat::{self, Presenter};

/// El cliente cuya cadena se consulta — el `ObligadoEmision`.
const OBLIGADO_NIF: &str = "B12345678";
const OBLIGADO_NAME: &str = "PELUQUERIA LA MODERNA SL";
/// ERPlora, que presenta con el Sello por la celda (ADR-0268 §1).
const PRESENTER_NIF: &str = "B27593136";
const PRESENTER_NAME: &str = "ERPLORA CLOUD SL";

const INDICATOR: &str = "<sum1:IndicadorRepresentante>S</sum1:IndicadorRepresentante>";

fn presenter() -> Presenter<'static> {
    Presenter {
        nif: PRESENTER_NIF,
        name: PRESENTER_NAME,
    }
}

fn consult(presenter: Option<Presenter<'_>>) -> String {
    aeat::build_consult_soap(OBLIGADO_NIF, OBLIGADO_NAME, "2026", "09", presenter)
        .expect("el sobre de consulta se construye")
}

/// La vía por la celda: presenta ERPlora, el obligado es el cliente, difieren — y el sobre lo
/// declara con el flag que el esquema de consulta sí tiene.
#[test]
fn the_cell_road_declares_the_representative_indicator() {
    let xml = consult(Some(presenter()));
    assert!(
        xml.contains(INDICATOR),
        "sin el flag la AEAT no devuelve la cadena del obligado consultado: {xml}"
    );
}

/// 🔒 La trampa. El bloque `Representante` es del alta; en la consulta es un 4102.
#[test]
fn the_consult_never_carries_a_representante_block() {
    let xml = consult(Some(presenter()));
    assert!(
        !xml.contains("<sum1:Representante>"),
        "CabeceraConsultaSf no declara Representante, solo IndicadorRepresentante: {xml}"
    );
    assert!(
        !xml.contains(PRESENTER_NAME),
        "la identidad del presentador NO viaja en la consulta, solo el flag: {xml}"
    );
}

/// La vía propia: firma el certificado del negocio, el titular ES el obligado y no se inventa
/// representación (ADR-0268 §4) — ni bloque en el alta, ni flag aquí.
#[test]
fn the_direct_road_declares_no_indicator() {
    let xml = consult(None);
    assert!(
        !xml.contains("IndicadorRepresentante"),
        "quien consulta su propia cadena no es representante de nadie: {xml}"
    );
}

/// Un presentador que ES el obligado tampoco levanta el flag: la regla es la MISMA que la del
/// bloque `Representante` del alta (presentador ≠ obligado), y así un hub que algún día
/// presentase por sí mismo a través de la celda no mentiría.
#[test]
fn a_presenter_that_is_the_obligado_declares_no_indicator() {
    let xml = aeat::build_consult_soap(
        OBLIGADO_NIF,
        OBLIGADO_NAME,
        "2026",
        "09",
        Some(Presenter {
            nif: OBLIGADO_NIF,
            name: OBLIGADO_NAME,
        }),
    )
    .expect("el sobre de consulta se construye");
    assert!(!xml.contains("IndicadorRepresentante"), "{xml}");
}

/// `xs:sequence`: el flag va **detrás** de `ObligadoEmision` y **dentro** de la `Cabecera`.
/// Colocarlo en cualquier otro sitio es otro 4102, y el orden no lo comprueba ningún test del
/// alta porque allí el elemento ni existe.
#[test]
fn the_indicator_closes_the_header_after_the_obligado() {
    let xml = consult(Some(presenter()));
    let obligado_end = xml
        .find("</sum1:ObligadoEmision>")
        .expect("el obligado está");
    let indicator = xml.find(INDICATOR).expect("el flag está");
    let header_end = xml.find("</con:Cabecera>").expect("la cabecera cierra");
    assert!(
        obligado_end < indicator && indicator < header_end,
        "IDVersion → ObligadoEmision → IndicadorRepresentante, dentro de Cabecera: {xml}"
    );
}
