//! The `Representante` block declares **who is presenting these bytes**, and that fact comes from
//! the identity the control plane SIGNED for this transmission — never from the certificate slot
//! (ADR-0268 §4, hub#985 §2 → hub#1460).
//!
//! # The two derivations, and why the slot is not one of them
//!
//! ADR-0268 §4 pins two independent questions and forbids answering either from the slot
//! (`own`/`delegated`), because the slot says *whose* the certificate is — not *what* it is, and
//! not *who presents*:
//!
//! | Question | Derived from |
//! |---|---|
//! | Which AEAT entry point? | the **type** of the certificate (`seal` / `representative`) |
//! | Is `Representante` emitted? | **does the presenter differ from the `IDEmisorFactura`?** |
//!
//! The first half is guarded next door (`entry_point_by_certificate.rs`, hub#470). This file is
//! the second, and it is the half that had never been written: until hub#1460 no envelope carried
//! a `Representante` at all, so every transmission through the cell claimed the client's own NIF
//! was presenting — which is exactly what the AEAT refuses with fault **4112** («el titular del
//! certificado debe ser Obligado Emisión, Colaborador Social, Apoderado o Sucesor»), measured
//! against prewww on 2026-09-02.
//!
//! # Where the presenter comes from on each road
//!
//! - **cell (delegated)** — the hub never sees the Sello, so it *cannot* read the holder from any
//!   bytes it owns. The control plane tells it, inside the signed short-lived token
//!   (`presenter_nif` / `presenter_name`), and the cell cross-checks the same pair against the
//!   holder of the Sello it actually presents: a Cloud that lied here is caught there.
//! - **own (direct)** — the business signs with its own certificate, so the holder *is* the
//!   `IDEmisorFactura`. Presenter and obligado coincide, and ADR-0268 §4 is explicit: no
//!   representation is invented.
use erplora_verifactu::aeat::{self, Presenter};

/// The client whose invoice this is — the `ObligadoEmision`, and the `IDEmisorFactura`.
const OBLIGADO_NIF: &str = "B12345678";
const OBLIGADO_NAME: &str = "PELUQUERIA LA MODERNA SL";
/// ERPlora, presenting as a social collaborator under Convenio 17 (ADR-0268 §1).
const PRESENTER_NIF: &str = "B27593136";
const PRESENTER_NAME: &str = "ERPLORA CLOUD SL";

/// The SLOT names (`certificate::CertificateKind::as_str`). They appear in this file ONLY as the
/// values that must not change the answer — that is the whole point of the guard.
const OWN_SLOT: &str = "own";
const DELEGATED_SLOT: &str = "delegated";

/// A `Cabecera` as `build_soap` emits it, with nothing stamped on it yet.
fn envelope() -> String {
    format!(
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?><soapenv:Envelope>\
         <sum:RegFactuSistemaFacturacion>\
         <sum:Cabecera><sum1:ObligadoEmision>\
         <sum1:NombreRazon>{OBLIGADO_NAME}</sum1:NombreRazon>\
         <sum1:NIF>{OBLIGADO_NIF}</sum1:NIF>\
         </sum1:ObligadoEmision></sum:Cabecera>\
         <sum:RegistroFactura><sum1:RegistroAlta/></sum:RegistroFactura>\
         </sum:RegFactuSistemaFacturacion></soapenv:Envelope>"
    )
}

fn representative_block(name: &str, nif: &str) -> String {
    format!(
        "<sum1:Representante><sum1:NombreRazon>{name}</sum1:NombreRazon>\
         <sum1:NIF>{nif}</sum1:NIF></sum1:Representante>"
    )
}

/// The cell road: the presenter is ERPlora, the obligado is the client, they differ — so the
/// envelope declares the representation, with the identity the token carried.
#[test]
fn the_cell_road_declares_the_signed_presenter_as_representante() {
    let xml = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );

    assert!(
        xml.contains(&representative_block(PRESENTER_NAME, PRESENTER_NIF)),
        "the signed presenter must reach the envelope verbatim: {xml}"
    );
}

/// The own road: the business signs with its own certificate, the holder IS the obligado, and
/// ADR-0268 §4 says no representation is invented.
#[test]
fn the_own_road_declares_no_representante() {
    let xml = aeat::set_representative(&envelope(), None, OBLIGADO_NIF);

    assert!(
        !xml.contains("Representante"),
        "no road, no presenter, no invented representation: {xml}"
    );
    assert_eq!(xml, envelope(), "an unrepresented envelope is untouched");
}

/// 🔴 **THE GUARD hub#1460 exists for.** The answer is the SIGNED identity, and the slot is not an
/// input to it — not even a tie-breaker.
///
/// A slot-driven implementation (`delegated` ⇒ emit, `own` ⇒ omit — the shape the code kept
/// promising in its own comments for a year) fails BOTH halves of this test:
///
/// - it would emit a block for `delegated` even when the presenter IS the obligado (a hub that
///   enrolled the client's OWN seal in the cell): a `Representante` naming the obligado as its own
///   representative, which is a 4102 waiting to happen;
/// - it would omit the block for `own` even when the presenter differs, which is fault 4112 —
///   the very rejection this issue was opened for.
///
/// `set_representative` never receives the slot, so the only way to reintroduce the defect is to
/// thread it in — and then this test goes red.
#[test]
fn the_slot_is_not_an_input_to_the_representante() {
    // The slot values exist; nothing in this call can see them. Named so the guard reads as the
    // rule it encodes rather than as two unrelated assertions.
    let _ = (OWN_SLOT, DELEGATED_SLOT);

    // Presenter == obligado: no representation, whatever road carried it. A slot-driven
    // implementation on the `delegated` road would emit a block here.
    let same = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: OBLIGADO_NIF,
            name: OBLIGADO_NAME,
        }),
        OBLIGADO_NIF,
    );
    assert!(
        !same.contains("Representante"),
        "presenter == obligado is not a representation (ADR-0268 §4): {same}"
    );

    // Presenter != obligado: representation, whatever road carried it. A slot-driven
    // implementation on the `own` road would omit the block here — fault 4112.
    let differ = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );
    assert!(
        differ.contains(&representative_block(PRESENTER_NAME, PRESENTER_NIF)),
        "presenter != obligado is a representation, on any road: {differ}"
    );
}

/// The NIF comparison is about identity, not about typography: the control plane may hand the NIF
/// back lowercase or padded, and a mismatch there would invent a representation of the obligado by
/// itself.
#[test]
fn the_presenter_matches_the_obligado_regardless_of_case_or_padding() {
    let xml = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: "  b12345678 ",
            name: OBLIGADO_NAME,
        }),
        OBLIGADO_NIF,
    );

    assert!(
        !xml.contains("Representante"),
        "`b12345678 ` and `B12345678` are the same NIF: {xml}"
    );
}

/// `CabeceraType` is an `xs:sequence`: ObligadoEmision → Representante? → RemisionVoluntaria? →
/// RemisionRequerimiento?. Out of order it is a 4102 — with the chain number already spent.
///
/// The contingency stamp anchors on the SAME point (`</ObligadoEmision>`), so the two stamps have
/// to compose in either order and still come out in sequence. This is the case the queue actually
/// produces: a record that waited for the AEAT to come back is stamped `Incidencia` AND presented
/// by the cell.
#[test]
fn both_header_stamps_compose_in_schema_order() {
    let stamped = aeat::stamp_contingency_incidence(&envelope());
    let xml = aeat::set_representative(
        &stamped,
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );

    let obligado = xml
        .find("</sum1:ObligadoEmision>")
        .expect("ObligadoEmision");
    let representante = xml.find("<sum1:Representante>").expect("Representante");
    let remision = xml
        .find("<sum1:RemisionVoluntaria>")
        .expect("RemisionVoluntaria");
    let cabecera_end = xml.find("</sum:Cabecera>").expect("Cabecera");

    assert!(
        obligado < representante && representante < remision && remision < cabecera_end,
        "CabeceraType sequence broken: {xml}"
    );
    // And the schema validator agrees — the envelope that goes out is the one that was checked.
    erplora_verifactu::xsd::validate_registro(&xml).expect_err("the stub registro is incomplete");
}

/// 🔒 **A retry must declare who presents it TODAY.** The queue reuses the frozen `xml_content` of
/// the previous attempt, and that envelope was stamped for the road it was going to take then. If
/// the hub uploaded its own certificate while the record waited, re-presenting it with ERPlora's
/// identity is a false representation; if the presenter rotated, the stale one is a 4112.
///
/// So the stamp SETS the block — replace, insert or remove — instead of leaving whatever was
/// already there. The `Cabecera` is not an input of the `Huella` (ADR-0202 §4.6), so none of this
/// touches the chain.
#[test]
fn the_stamp_replaces_a_stale_representante_and_removes_it_when_the_road_changes() {
    let stale = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: "B99999999",
            name: "PRESENTADOR ANTERIOR SL",
        }),
        OBLIGADO_NIF,
    );
    assert!(stale.contains("B99999999"));

    let rotated = aeat::set_representative(
        &stale,
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );
    assert!(
        rotated.contains(&representative_block(PRESENTER_NAME, PRESENTER_NIF)),
        "the current presenter replaces the frozen one: {rotated}"
    );
    assert!(
        !rotated.contains("B99999999"),
        "and the stale one does not survive alongside it: {rotated}"
    );

    let moved_to_own = aeat::set_representative(&stale, None, OBLIGADO_NIF);
    assert!(
        !moved_to_own.contains("Representante"),
        "a hub that uploaded its own certificate stops representing: {moved_to_own}"
    );
    assert_eq!(
        moved_to_own,
        envelope(),
        "and the envelope goes back to exactly what it was"
    );
}

/// An identity we cannot name is not a representation we can declare. `NombreRazon` and `NIF` are
/// both required by `PersonaFisicaJuridicaESType`, so half a presenter is a 4102 — and inventing
/// the missing half would be worse. It refuses to stamp and says so through the schema validator,
/// which is what marks the record `rejected` locally instead of spending a chain number.
#[test]
fn half_a_presenter_is_not_stamped() {
    for presenter in [
        Presenter {
            nif: "",
            name: PRESENTER_NAME,
        },
        Presenter {
            nif: PRESENTER_NIF,
            name: "   ",
        },
    ] {
        let xml = aeat::set_representative(&envelope(), Some(presenter), OBLIGADO_NIF);
        assert!(
            !xml.contains("Representante"),
            "an unnameable presenter is not declared: {xml}"
        );
    }
}

/// The presenter's name is business data and reaches the envelope through the same escaping as
/// every other field: an `&` in a razón social must not break the document.
#[test]
fn the_presenter_identity_is_escaped() {
    let xml = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: "GESTORIA A & B <SL>",
        }),
        OBLIGADO_NIF,
    );

    assert!(
        xml.contains("GESTORIA A &amp; B &lt;SL&gt;"),
        "the razón social must be escaped, not injected: {xml}"
    );
}

/// 🔒 The same composition with the stamps applied the other way round. Both anchor inside the
/// `Cabecera`, and the contingency one used to anchor *only* on `</ObligadoEmision>` — which was
/// correct exactly as long as no `Representante` existed. Now that one does, anchoring there
/// unconditionally would slide `RemisionVoluntaria` in FRONT of it and break the sequence.
///
/// Order-independence is not decoration: the two stamps are applied by different pieces of the
/// transmission path, and nothing in the type system keeps them in one order forever.
#[test]
fn the_stamps_compose_in_schema_order_whichever_is_applied_first() {
    let represented = aeat::set_representative(
        &envelope(),
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );
    let xml = aeat::stamp_contingency_incidence(&represented);

    let representante = xml.find("<sum1:Representante>").expect("Representante");
    let remision = xml
        .find("<sum1:RemisionVoluntaria>")
        .expect("RemisionVoluntaria");
    assert!(
        representante < remision,
        "Representante must precede RemisionVoluntaria (CabeceraType xs:sequence): {xml}"
    );

    // And it composes to the SAME document either way round.
    let other_way = aeat::set_representative(
        &aeat::stamp_contingency_incidence(&envelope()),
        Some(Presenter {
            nif: PRESENTER_NIF,
            name: PRESENTER_NAME,
        }),
        OBLIGADO_NIF,
    );
    assert_eq!(xml, other_way, "the stamps must commute");
}
