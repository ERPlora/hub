//! The AEAT entry point depends on **what the certificate IS**, not on which slot it came from
//! (ADR-0202 §2.1, hub#320 → hub#470).
//!
//! The AEAT segregates the VERI\*FACTU service by the TYPE of certificate that identifies the
//! caller in the TLS handshake — the same split it has had for SII since 2017:
//!
//! - a **holder/representative** certificate (a natural person inside the `.p12`) enters through
//!   `www1` / `prewww1`;
//! - an **entity seal** (*Sello de Entidad*, not tied to any person's DNI) enters through
//!   `www10` / `prewww10` (confirmed in [OCA/l10n-spain#4597]).
//!
//! # Why this file changed shape (hub#470)
//!
//! hub#320 keyed the entry point on the **slot** (`own` → holder, `delegated` → seal). The slot
//! says *whose* the certificate is, not *what* it is: `delegated` means «the control plane handed
//! it down», and that it holds a Sello de Entidad was a premise of ADR-0202 that never travelled
//! across the border. It was not a theoretical gap — the `.p12` ERPlora invoices with today is a
//! **representative** certificate (`…_R_…`), and uploading it to the control plane would have sent
//! every delegated hub in the fleet to `www10`, where all of them would have been rejected, one
//! record at a time and with nothing to warn anybody.
//!
//! So the axis is now the TYPE
//! (`erplora_runtime::certificate::CertificateType::as_str` — `"seal"` / `"representative"`),
//! derived from the container the hub actually holds and cross-checked against what the control
//! plane declared. The slot keeps its own job (which certificate signs, and the `Representante`
//! block of hub#321); it just no longer decides the URL.
//!
//! There are **two axes and they multiply**, which is why they are pinned here together rather
//! than one test per axis: getting the type right while losing the environment is not a smaller
//! bug, it is a worse one — a rejection is noisy and recoverable, a real invoice accepted into
//! preproduction (or a test invoice accepted into production) is neither.
//!
//! [OCA/l10n-spain#4597]: https://github.com/OCA/l10n-spain/discussions/4597
use erplora_verifactu::aeat;

/// The type names are the core's (`certificate::CertificateType::as_str`) and travel to the engine
/// inside `certificate_type` of the config, put there by `read_config` (hub#470).
const REPRESENTATIVE: &str = "representative";
const SEAL: &str = "seal";

/// The SLOT names (`certificate::CertificateKind::as_str`). They are NOT valid values of this axis
/// — that is exactly the confusion hub#470 removes — so they appear here only as the unknown values
/// they now are.
const OWN_SLOT: &str = "own";
const DELEGATED_SLOT: &str = "delegated";

const PREPRODUCTION_HOLDER: &str =
    "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PREPRODUCTION_SEAL: &str =
    "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PRODUCTION_HOLDER: &str =
    "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PRODUCTION_SEAL: &str =
    "https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";

/// **An entity seal transmits through the seal entry point** — the rule hub#320 introduced, now
/// keyed on what the certificate is instead of on where it came from.
#[test]
fn an_entity_seal_transmits_through_the_seal_entry_point() {
    assert_eq!(aeat::endpoint("testing", SEAL), PREPRODUCTION_SEAL);
    assert_eq!(aeat::endpoint("production", SEAL), PRODUCTION_SEAL);
}

/// The other half of the same rule: a representative certificate — which is what every hub in the
/// field signs with today — must keep going exactly where it went before. A regression here is the
/// whole deployed fleet at once.
#[test]
fn a_representative_certificate_keeps_the_holder_entry_point() {
    assert_eq!(aeat::endpoint("testing", REPRESENTATIVE), PREPRODUCTION_HOLDER);
    assert_eq!(aeat::endpoint("production", REPRESENTATIVE), PRODUCTION_HOLDER);
}

/// 🔴 **The bug hub#470 closes.** `delegated` describes the PROVENANCE of the certificate, and
/// routing on it sent ERPlora's own representative `.p12` — the one it invoices with today — to the
/// seal's door for the entire delegated fleet.
///
/// The slot name is now simply not a value of this axis, so it lands on the safe default like any
/// other unknown string. What decides is the type the core derived from the container itself.
#[test]
fn the_slot_a_certificate_came_from_no_longer_decides_the_entry_point() {
    for slot in [OWN_SLOT, DELEGATED_SLOT] {
        assert_eq!(
            aeat::endpoint("testing", slot),
            PREPRODUCTION_HOLDER,
            "the slot name {slot:?} must not be read as a certificate type"
        );
        assert_eq!(
            aeat::endpoint("production", slot),
            PRODUCTION_HOLDER,
            "the slot name {slot:?} must not be read as a certificate type"
        );
    }
}

/// **The two axes never get multiplied wrong.** Four combinations, four different URLs, and no
/// preproduction host inside a production URL or the other way round.
#[test]
fn the_environment_and_the_certificate_are_independent_axes() {
    let matrix = [
        ("testing", REPRESENTATIVE, PREPRODUCTION_HOLDER),
        ("testing", SEAL, PREPRODUCTION_SEAL),
        ("production", REPRESENTATIVE, PRODUCTION_HOLDER),
        ("production", SEAL, PRODUCTION_SEAL),
    ];
    for (environment, certificate_type, expected) in matrix {
        let url = aeat::endpoint(environment, certificate_type);
        assert_eq!(url, expected, "({environment}, {certificate_type})");
        let is_production = environment == "production";
        assert_eq!(
            url.contains("agenciatributaria.gob.es"),
            is_production,
            "the environment axis leaked: ({environment}, {certificate_type}) → {url}"
        );
        assert_eq!(
            url.contains("prewww"),
            !is_production,
            "the environment axis leaked: ({environment}, {certificate_type}) → {url}"
        );
    }
    // Distinct: a match arm collapsed into another is a silent misrouting, not a compile error.
    let urls = [
        PREPRODUCTION_HOLDER,
        PREPRODUCTION_SEAL,
        PRODUCTION_HOLDER,
        PRODUCTION_SEAL,
    ];
    for (i, a) in urls.iter().enumerate() {
        for b in urls.iter().skip(i + 1) {
            assert_ne!(a, b, "two cells of the matrix answer the same URL");
        }
    }
}

/// **Only the host changes.** The path is chosen by the AEAT and is the same on all four entry
/// points; a typo on one branch only would 404 exactly one quadrant of the fleet.
#[test]
fn the_four_entry_points_differ_only_in_the_host() {
    const PATH: &str = "/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
    for environment in ["testing", "production"] {
        for certificate_type in [REPRESENTATIVE, SEAL] {
            let url = aeat::endpoint(environment, certificate_type);
            assert!(
                url.starts_with("https://") && url.ends_with(PATH),
                "({environment}, {certificate_type}) → {url}"
            );
        }
    }
}

/// 🔒 **Only a certificate positively known to be a seal reaches the seal's door.** Everything else
/// — an empty value, a slot name, a spelling this build does not know, a container the core could
/// not classify — degrades to the holder's entry point.
///
/// That asymmetry is the whole safety argument of hub#470: identifying a seal takes evidence
/// (an eIDAS `QcType` eSeal statement, or the control plane saying so), while the ABSENCE of
/// evidence must never open the seal's door. Both mistakes end in a rejection, but `www1` is where
/// every certificate in the field already goes, so the unknown value degrades into today's
/// behaviour instead of routing hubs somewhere new.
#[test]
fn an_unknown_certificate_type_falls_back_to_the_holder_entry_point() {
    for value in [
        "",
        "  ",
        "SEAL",
        "seal ",
        "sello",
        "sello_de_entidad",
        "delegated",
        "own",
        "future-type",
    ] {
        assert_eq!(
            aeat::endpoint("testing", value),
            PREPRODUCTION_HOLDER,
            "unknown certificate type {value:?} must not be routed to the seal entry point"
        );
    }
}

/// 🔒 **The certificate axis must not open a door into production.** `environment` defaults to
/// preproduction for anything that is not literally `production` — an empty config, a typo, a value
/// from a newer module version. A real invoice accepted by the real AEAT because a config string
/// was misspelled cannot be taken back (ADR-0189: a remitted record is never re-sent).
#[test]
fn an_unknown_environment_stays_in_preproduction_for_both_certificates() {
    for environment in ["", "testing", "Production", "production ", "prod", "sandbox"] {
        assert_eq!(
            aeat::endpoint(environment, REPRESENTATIVE),
            PREPRODUCTION_HOLDER,
            "{environment:?}"
        );
        assert_eq!(
            aeat::endpoint(environment, SEAL),
            PREPRODUCTION_SEAL,
            "{environment:?}"
        );
    }
}

/// The consult operation is published on the SAME entry point as the alta (hub#287) — and that
/// stays true on **both** axes, so a hub signing with a seal can also recover its chain.
#[test]
fn the_consult_shares_the_entry_point_with_the_alta_for_every_certificate() {
    for environment in ["testing", "production"] {
        for certificate_type in [REPRESENTATIVE, SEAL, "", "delegated"] {
            assert_eq!(
                aeat::consult_endpoint(environment, certificate_type),
                aeat::endpoint(environment, certificate_type),
                "({environment}, {certificate_type})"
            );
        }
    }
}
