//! **The in-product declaración responsable serves the SAME facts as the XML** — ERPlora/hub#528.
//!
//! Art. 13.2 RRSIF (RD 1007/2023) makes the responsible declaration appear «por escrito y de modo
//! visible en el propio sistema informático en cada una de sus versiones». The half that lives on
//! erplora.com (the public archive, saas) is not enough: a business inspected by the AEAT has to be
//! able to show it **from its own till**.
//!
//! The trap this file exists for is not the panel, it is the SOURCE. A screen that prints
//! `ERPLORA CLOUD SL / EC / 1.0.0` out of constants looks identical to one that reads the real
//! facts — right up to the day the control plane corrects the manufacturer's block (that is what
//! `ProducerFacts` is for: it already shipped an 11-character `IdSistemaInformatico`) and the till
//! keeps showing the old one while every record leaves declaring the new one. Certifying compliance
//! for a system whose identity does not match the one emitting records is sanctionable.
//!
//! So the assertion is a CROSS-CHECK, not a snapshot: every value the panel serves is looked for
//! inside a real `<sum1:SistemaInformatico>` block built by the fiscal engine
//! (`erplora_verifactu::aeat::build_soap`) from the same producer facts. Change one side only and
//! this test fails.

use erplora_runtime::producer_facts::{ProducerFacts, AEAT_FIELDS};
use erplora_server::settings::declaration_payload;
use erplora_verifactu::aeat;
use serde_json::{json, Value};

const HUB_ID: &str = "6c9e7a52-0f1b-4b2e-9c1d-2f8a5e3d7b10";
const CLOUD: &str = "https://erplora.com";

/// The manufacturer's block exactly as the control plane serves it on the heartbeat
/// (`apps/dashboard/fiscal/services/producer_facts.py`).
fn served_block() -> Value {
    json!({
        "NombreRazon": "ERPLORA CLOUD SL",
        "NIF": "B27593136",
        "NombreSistemaInformatico": "ERPlora Hub",
        "IdSistemaInformatico": "EC",
        "TipoUsoPosibleSoloVerifactu": "S",
        "TipoUsoPosibleMultiOT": "S",
        "IndicadorMultiplesOT": "N",
    })
}

fn facts() -> ProducerFacts {
    ProducerFacts::parse(&served_block()).expect("the served block is valid")
}

/// A cancellation record: the shortest one `build_soap` accepts, and it carries the same
/// `SistemaInformatico` block as an `alta` without dragging amounts into this test.
fn anulacion_record() -> Value {
    json!({
        "record_type": "anulacion",
        "issuer_nif": "B12345674",
        "invoice_number": "FACT-2026-000001",
        "invoice_date": "2026-08-05",
        "generation_timestamp": "2026-08-05T10:00:00+02:00",
        "record_hash": "0".repeat(64),
        "is_first_record": 1,
    })
}

/// The `<sum1:SistemaInformatico>` block of a real envelope, built by the fiscal engine.
fn sistema_informatico_xml() -> String {
    let config = json!({ "producer_facts": served_block() });
    let xml = aeat::build_soap(&anulacion_record(), &config, None, HUB_ID)
        .expect("the record is declarable");
    let start = xml
        .find("<sum1:SistemaInformatico>")
        .expect("the envelope carries the block");
    let end = xml
        .find("</sum1:SistemaInformatico>")
        .expect("the block is closed");
    xml[start..end].to_string()
}

/// Every value the panel shows is the value the AEAT receives — field by field, no exceptions.
#[test]
fn the_declaration_panel_serves_the_same_facts_as_the_xml_hub528() {
    let version = erplora_server::version::HUB_VERSION;
    let payload = declaration_payload(Some(&facts()), version, HUB_ID, CLOUD);
    let block = payload["sistemaInformatico"]
        .as_object()
        .expect("the panel serves the SistemaInformatico block");
    let xml = sistema_informatico_xml();

    // The nine elements the XML carries: the seven the control plane owns plus the two this hub
    // declares about itself (ADR-0202 §5.1). Anything missing here is a fact an inspector asked
    // for and the till could not show.
    let expected: Vec<&str> = AEAT_FIELDS
        .iter()
        .copied()
        .chain(["Version", "NumeroInstalacion"])
        .collect();
    assert_eq!(
        block.len(),
        expected.len(),
        "the panel must serve exactly the nine elements of SistemaInformatico, got {block:?}"
    );

    for field in expected {
        let shown = block
            .get(field)
            .and_then(Value::as_str)
            .unwrap_or_else(|| panic!("the panel does not serve `{field}`: {block:?}"));
        assert!(
            !shown.trim().is_empty(),
            "the panel serves an empty `{field}`"
        );
        assert!(
            xml.contains(&format!("<sum1:{field}>{shown}</sum1:{field}>")),
            "the panel shows `{field}` = {shown:?}, which is NOT what the XML declares: {xml}"
        );
    }

    // Negative control — the loop above is only worth something if it can FAIL. Two of the nine
    // elements are the ones this hub owns, and both happen to equal today's literals (`1.0.0`, and a
    // `hub_id` somebody could paste): a panel built out of constants would sail through the loop
    // by coincidence, on this build, and start lying on the next release. So the same call is
    // made with a different installation and a different release, and the values MUST follow.
    let other = declaration_payload(Some(&facts()), "0.0.1", "other-installation", CLOUD);
    assert_eq!(
        other["sistemaInformatico"]["Version"],
        json!("0.0.1"),
        "`Version` does not follow the running binary — it is a constant"
    );
    assert_eq!(
        other["sistemaInformatico"]["NumeroInstalacion"],
        json!("other-installation"),
        "`NumeroInstalacion` does not follow this installation — it is a constant"
    );
}

/// `Version` is the binary this hub is running and `NumeroInstalacion` is its own `hub_id`. They
/// are the two halves art. 13.2 calls «cada una de sus versiones» and art. 13.4 «datos
/// identificativos» — and the two the fleet cannot share, because hubs are pinned to different
/// digests.
#[test]
fn the_installed_version_and_this_installation_are_this_hubs_own_facts_hub528() {
    let payload = declaration_payload(Some(&facts()), "9.9.9", HUB_ID, CLOUD);

    assert_eq!(payload["version"], json!("9.9.9"), "`version`: {payload}");
    assert_eq!(
        payload["numeroInstalacion"],
        json!(HUB_ID),
        "`numeroInstalacion`: {payload}"
    );
    assert_eq!(
        payload["sistemaInformatico"]["Version"],
        json!("9.9.9"),
        "`Version` is not the version this hub is running: {payload}"
    );
    assert_eq!(
        payload["sistemaInformatico"]["NumeroInstalacion"],
        json!(HUB_ID),
        "`NumeroInstalacion` is not this installation: {payload}"
    );
}

/// Nobody has told this hub who its manufacturer is yet (a hub that has never reached the control
/// plane). There are no defaults for a legal declaration — the engine refuses to build the
/// envelope — so the panel refuses to invent the block too, and still shows the two facts this hub
/// owns. A screen that filled the gap with constants is the defect this issue is about.
#[test]
fn without_the_producer_facts_the_panel_invents_nothing_hub528() {
    let payload = declaration_payload(None, "1.0.0", HUB_ID, CLOUD);

    assert_eq!(payload["sistemaInformatico"], Value::Null);
    assert_eq!(payload["version"], json!("1.0.0"));
    assert_eq!(payload["numeroInstalacion"], json!(HUB_ID));
    let serialised = payload.to_string();
    assert!(
        !serialised.contains("ERPLORA CLOUD SL") && !serialised.contains("B27593136"),
        "the manufacturer's identity was invented out of a constant: {serialised}"
    );
}

/// The signed text is served by the control plane this hub belongs to, not by a hardcoded host: a
/// PRE hub must not send its owner to the production archive, and a self-hosted control plane has
/// no erplora.com at all.
#[test]
fn the_signed_declaration_is_linked_on_this_hubs_control_plane_hub528() {
    let payload = declaration_payload(Some(&facts()), "1.0.0", HUB_ID, "https://pre.erplora.com/");

    assert_eq!(
        payload["declarationUrl"],
        json!("https://pre.erplora.com/legal/declaracion-responsable/"),
        "the trailing slash of the base url must not double up"
    );
}
