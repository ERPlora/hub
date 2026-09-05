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

use erplora_runtime::producer_facts::{DeclarationReference, ProducerFacts, AEAT_FIELDS};
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
    let payload = declaration_payload(Some(&facts()), None, version, HUB_ID, CLOUD);
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
    let other = declaration_payload(Some(&facts()), None, "0.0.1", "other-installation", CLOUD);
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
    let payload = declaration_payload(Some(&facts()), None, "9.9.9", HUB_ID, CLOUD);

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
    let payload = declaration_payload(None, None, "1.0.0", HUB_ID, CLOUD);

    assert_eq!(payload["sistemaInformatico"], Value::Null);
    assert_eq!(payload["version"], json!("1.0.0"));
    assert_eq!(payload["numeroInstalacion"], json!(HUB_ID));
    let serialised = payload.to_string();
    assert!(
        !serialised.contains("ERPLORA CLOUD SL") && !serialised.contains("B27593136"),
        "the manufacturer's identity was invented out of a constant: {serialised}"
    );
}

/// Without a `declaration` reference from the control plane (an older SaaS, a hub that has never
/// reached it, or an archive it could not read) the panel falls back to the ROOT of the public
/// archive on this hub's own control plane, not a hardcoded host: a PRE hub must not send its
/// owner to the production archive, and a self-hosted control plane has no erplora.com at all.
#[test]
fn without_a_declaration_reference_the_panel_falls_back_to_the_archive_root_hub528() {
    let payload = declaration_payload(
        Some(&facts()),
        None,
        "1.0.0",
        HUB_ID,
        "https://pre.erplora.com/",
    );

    assert_eq!(
        payload["declarationUrl"],
        json!("https://pre.erplora.com/legal/declaracion-responsable/"),
        "the trailing slash of the base url must not double up"
    );
}

/// 🔴 hub#1449: the defect this issue is about. While a single declaración responsable was in
/// force, linking the archive root worked by coincidence — the root resolves to whichever one is
/// current. The day a second one is issued, a hub still running the release the first one covers
/// must keep linking THAT text, not the one the root now resolves to (art. 13.3 RRSIF). The panel
/// links the EXACT reference the SaaS names, never a URL this hub composes.
#[test]
fn the_panel_links_the_exact_declaration_the_saas_names_not_the_composed_root_hub1449() {
    let declaration = DeclarationReference {
        version: "v1".to_string(),
        url: "https://erplora.com/legal/declaracion-responsable/v1/".to_string(),
    };

    let payload = declaration_payload(Some(&facts()), Some(&declaration), "1.0.0", HUB_ID, CLOUD);

    assert_eq!(
        payload["declarationUrl"],
        json!("https://erplora.com/legal/declaracion-responsable/v1/"),
        "the panel must serve the reference the SaaS named, not a composed root: {payload}"
    );
}

/// The exact reference wins even on a control plane other than the one hardcoded above: `url`
/// travels verbatim from the SaaS, which already composed it with ITS OWN `cloud_base_url` (a PRE
/// hub gets the PRE reference). The hub must not rewrite it or append anything.
#[test]
fn the_exact_declaration_is_served_as_is_never_rewritten_by_this_hub_hub1449() {
    let declaration = DeclarationReference {
        version: "v2".to_string(),
        url: "https://pre.erplora.com/legal/declaracion-responsable/v2/".to_string(),
    };

    // A different `cloud_base_url` than the one baked into the reference: if the hub composed
    // anything from it while a reference is present, this would catch it.
    let payload = declaration_payload(Some(&facts()), Some(&declaration), "1.0.0", HUB_ID, CLOUD);

    assert_eq!(
        payload["declarationUrl"],
        json!("https://pre.erplora.com/legal/declaracion-responsable/v2/"),
        "the url must ride verbatim, not be recomposed from cloud_base_url: {payload}"
    );
}

/// The DOOR, not only the projection: `GET /api/system/declaration` must serve the block the
/// process-wide cache holds — the one the heartbeat installs and `verifactu` reads — plus this
/// binary's version and this hub's own id, AND (hub#1449) the exact declaration reference the same
/// cache holds, never the composed root while one is known. The pure-function tests above cannot
/// see a handler that hands `declaration_payload` a stale copy, a literal or `None`; this one goes
/// through the router, so the value on the wire is compared with the value the engine would put in
/// the XML.
#[tokio::test]
async fn the_route_projects_the_process_wide_producer_facts_hub528() {
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use erplora_db::testutil::fresh_db;
    use erplora_runtime::producer_facts::ProducerFactsCache;
    use erplora_runtime::Runtime;
    use erplora_server::{app, AppState, AuthMode, HubConfig};
    use http_body_util::BodyExt;
    use tower::ServiceExt;

    let db = fresh_db().await;
    let rt = Runtime::new(Box::new(db));
    let config = HubConfig::from_env_with_auth(AuthMode::Dev);
    let hub_id = config.hub_id.clone();
    let cloud_base_url = config.cloud_base_url.clone();
    let router = app(AppState::with_config(rt, config));

    // What the heartbeat would have installed: the same block the XML is built from, and the
    // reference to the declaration that covers this release.
    ProducerFactsCache::global().store(facts());
    let declaration = DeclarationReference {
        version: "v1".to_string(),
        url: "https://erplora.com/legal/declaracion-responsable/v1/".to_string(),
    };
    ProducerFactsCache::global().store_declaration(declaration.clone());

    let response = router
        .oneshot(
            Request::builder()
                .uri("/api/system/declaration")
                .header("x-hub-id", &hub_id)
                .header("x-user-id", "u1")
                .header("x-permissions", "*")
                .body(Body::empty())
                .expect("a well-formed request"),
        )
        .await
        .expect("the router answers");
    assert_eq!(response.status(), StatusCode::OK);
    let bytes = response
        .into_body()
        .collect()
        .await
        .expect("a readable body")
        .to_bytes();
    let served: Value = serde_json::from_slice(&bytes).expect("a JSON body");

    let expected = declaration_payload(
        Some(&facts()),
        Some(&declaration),
        erplora_server::version::HUB_VERSION,
        &hub_id,
        &cloud_base_url,
    );
    assert_eq!(
        served, expected,
        "the route does not serve the process-wide producer facts + declaration + this binary + this hub"
    );
    assert_eq!(
        served["sistemaInformatico"]["NombreRazon"],
        json!("ERPLORA CLOUD SL"),
        "the manufacturer's block did not come from the cache: {served}"
    );
    assert_eq!(
        served["declarationUrl"],
        json!("https://erplora.com/legal/declaracion-responsable/v1/"),
        "the route must serve the exact reference the cache holds, not a composed root: {served}"
    );
}

/// 🔴 hub#1510 (item 4 of hub#1449's DoD): the link alone does not say WHICH text it points at.
/// Art. 13.3 RRSIF lets several declarations coexist — one per range of versions — so an inspector
/// standing in front of the till has to be able to check that the text they are reading is the one
/// that covers this release, without following the URL and comparing folder names. The reference
/// the control plane names already carries that (`v1`, `v2`…); the panel serves it next to the
/// link, at the TOP level: it is a property of the declaration, not one of the nine elements of
/// `SistemaInformatico` that travel inside every record.
#[test]
fn the_panel_names_which_declaration_text_covers_this_release_hub1510() {
    let declaration = DeclarationReference {
        version: "v2".to_string(),
        url: "https://erplora.com/legal/declaracion-responsable/v2/".to_string(),
    };

    let payload = declaration_payload(Some(&facts()), Some(&declaration), "1.0.0", HUB_ID, CLOUD);

    assert_eq!(
        payload["declarationVersion"],
        json!("v2"),
        "the panel must name the declaration the SaaS referenced: {payload}"
    );
    // The version of the BINARY is a different fact and keeps its own key: the release this hub
    // runs, not the text that covers it. Conflating them is what this issue exists to avoid.
    assert_eq!(payload["version"], json!("1.0.0"));
    assert_eq!(
        payload["sistemaInformatico"]["Version"],
        json!("1.0.0"),
        "the declaration version must not leak into the record's block: {payload}"
    );
}

/// Without a reference (an older control plane, a hub that has never reached it) the link falls
/// back to the archive ROOT, and the root has no version to name. The key is then **absent**, not
/// `null` nor an empty string: the panel prints what it was told and stays silent about what it
/// was not, exactly like `sistemaInformatico`. A `""` on the wire would paint an empty label next
/// to the link and read as «this declaration has no version», which is a different claim.
#[test]
fn without_a_reference_the_declaration_version_is_absent_never_empty_hub1510() {
    let payload = declaration_payload(Some(&facts()), None, "1.0.0", HUB_ID, CLOUD);

    assert!(
        payload.get("declarationVersion").is_none(),
        "no reference means no version key at all, not an empty one: {payload}"
    );
    // The link still resolves — the fallback of hub#528 is untouched.
    assert_eq!(
        payload["declarationUrl"],
        json!("https://erplora.com/legal/declaracion-responsable/")
    );
}
