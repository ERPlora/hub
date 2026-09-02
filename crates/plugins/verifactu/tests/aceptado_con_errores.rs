//! `AceptadoConErrores` — el registro **está registrado en la AEAT**, pero con un error anotado.
//!
//! Las respuestas de este fichero son **capturas reales** de preproducción (2026-08-02,
//! `tests/fixtures/alta_*_2026-08-02.xml`), tomadas con `tests/aeat_live_2007.rs`. Lo que
//! demuestran, y que ningún test mockeado había cazado:
//!
//! 1. Un **2007** («no debe informarse como primer registro») llega como
//!    `EstadoEnvio=ParcialmenteCorrecto` + `EstadoRegistro=AceptadoConErrores` — **no** como
//!    `Incorrecto`. La condición que disparaba `auto_rechain_and_retry` exigía
//!    `classify(...) == "rejected"`, así que la recuperación automática **nunca corría**.
//! 2. Y no debía correr: reenviar ese mismo registro re-anclado devuelve **3000 «Registro de
//!    facturación duplicado»**, con un bloque `RegistroDuplicado` que repite el estado del
//!    original. La AEAT ni lo duplica ni lo sustituye: **lo rechaza**. La consulta posterior
//!    sigue devolviendo UNA sola aparición.
//!
//! De ahí el diseño: un `AceptadoConErrores` es un **aceptado con aviso** — se persiste el código
//! de error de la AEAT para que se vea, y **no se reenvía nunca**.
use erplora_verifactu::aeat;

fn fixture(name: &str) -> String {
    std::fs::read_to_string(format!(
        "{}/tests/fixtures/{name}",
        env!("CARGO_MANIFEST_DIR")
    ))
    .unwrap_or_else(|e| panic!("no se pudo leer la captura {name}: {e}"))
}

// ── 1. El 2007 real ───────────────────────────────────────────────────────────────────────

#[test]
fn el_2007_real_llega_como_aceptado_con_errores_no_como_incorrecto() {
    let resp = aeat::parse_response(&fixture("alta_2007_aceptado_con_errores_2026-08-02.xml"));

    assert_eq!(resp.estado_envio, "ParcialmenteCorrecto");
    assert_eq!(resp.estado_registro, "AceptadoConErrores");
    assert_eq!(resp.codigo_error, "2007");
    assert!(
        resp.descripcion_error.contains("primer registro"),
        "{}",
        resp.descripcion_error
    );
}

/// El veredicto: **aceptado** (la AEAT lo tiene) pero marcado, y con el código a la vista.
#[test]
fn el_2007_se_da_por_aceptado_pero_con_aviso_y_conserva_el_codigo() {
    let resp = aeat::parse_response(&fixture("alta_2007_aceptado_con_errores_2026-08-02.xml"));
    let v = aeat::classify(&resp);

    assert_eq!(v.status, "accepted", "está registrado: NO es un rechazo");
    assert!(
        v.accepted_with_errors,
        "un AceptadoConErrores no es un aceptado limpio"
    );
    // Lo que se persiste tiene que decir 2007, no «AceptadoConErrores/ParcialmenteCorrecto»:
    // si el código se tira, el operador nunca se entera de que la cadena venía mal.
    assert_eq!(v.code, "2007");
    assert!(v.message.contains("primer registro"), "{}", v.message);
}

/// La regresión concreta que este ensayo destapó: reenviar por un 2007.
#[test]
fn un_2007_nunca_se_reenvia() {
    let resp = aeat::parse_response(&fixture("alta_2007_aceptado_con_errores_2026-08-02.xml"));
    let v = aeat::classify(&resp);

    assert!(
        !v.should_retransmit(),
        "reenviar un registro que la AEAT ya tiene devuelve 3000 «Registro duplicado» \
         (verificado contra preproducción el 2026-08-02)"
    );
}

// ── 2. El 3000 que prueba por qué no se reenvía ───────────────────────────────────────────

#[test]
fn el_reenvio_de_un_registro_ya_aceptado_es_un_3000_duplicado() {
    let resp = aeat::parse_response(&fixture("alta_3000_duplicado_tras_rechain_2026-08-02.xml"));
    let v = aeat::classify(&resp);

    assert_eq!(resp.estado_registro, "Incorrecto");
    assert_eq!(v.status, "rejected");
    assert!(!v.accepted_with_errors);
}

/// `RegistroDuplicado` **anida** otro `CodigoErrorRegistro` (el del registro original, 2007).
/// El código que vale es el de fuera —3000—, no el de dentro: confundirlos haría creer que el
/// rechazo es de encadenamiento y dispararía otra recuperación, en bucle.
#[test]
fn el_codigo_del_3000_es_el_de_fuera_no_el_del_bloque_registro_duplicado() {
    let xml = fixture("alta_3000_duplicado_tras_rechain_2026-08-02.xml");
    assert!(
        xml.matches("CodigoErrorRegistro").count() > 2,
        "la captura debe traer el CodigoErrorRegistro anidado del RegistroDuplicado"
    );

    let resp = aeat::parse_response(&xml);
    assert_eq!(resp.codigo_error, "3000", "el de fuera, no el 2007 anidado");
    assert_eq!(resp.descripcion_error, "Registro de facturación duplicado.");
}

/// Y un 3000 **no** es un fallo de encadenamiento: no debe re-anclar nada.
#[test]
fn un_3000_duplicado_no_cuenta_como_rechazo_de_encadenamiento() {
    let resp = aeat::parse_response(&fixture("alta_3000_duplicado_tras_rechain_2026-08-02.xml"));

    assert!(
        !aeat::is_chaining_rejection(&resp.codigo_error, &resp.descripcion_error),
        "re-anclar por un duplicado movería la cadena fiscal por un fallo que no es de eslabón"
    );
}

// ── 3. El aceptado limpio sigue siendo limpio ─────────────────────────────────────────────

#[test]
fn un_correcto_sigue_siendo_un_aceptado_sin_aviso() {
    let resp = aeat::AeatResponse {
        estado_envio: "Correcto".into(),
        estado_registro: "Correcto".into(),
        csv: "A-W9R5GU6C5RRW8C".into(),
        codigo_error: String::new(),
        descripcion_error: String::new(),
    };
    let v = aeat::classify(&resp);

    assert_eq!(v.status, "accepted");
    assert!(!v.accepted_with_errors);
    assert!(!v.should_retransmit());
}
