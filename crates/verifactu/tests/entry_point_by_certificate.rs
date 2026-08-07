//! The AEAT entry point depends on the CERTIFICATE, not only on the environment
//! (ADR-0202 §2.1, hub#320).
//!
//! The AEAT segregates the VERI\*FACTU service by the kind of certificate that identifies the
//! caller in the TLS handshake — the same split it has had for SII since 2017:
//!
//! - a **holder/representative** certificate (a NIF inside the `.p12`) enters through
//!   `www1` / `prewww1`;
//! - an **entity seal** (*Sello de Entidad*, not tied to any person's DNI) enters through
//!   `www10` / `prewww10` (confirmed in [OCA/l10n-spain#4597]).
//!
//! ERPlora's `delegated` slot IS that seal: it signs for every hub under a power of attorney
//! (ADR-0202 §2, procedure ZP01). So the certificate the core selects
//! (`own` → the business's, `delegated` → ERPlora's) drags the URL with it, and until hub#320 it
//! did not: `endpoint()` only looked at the environment, so a hub whose only certificate was the
//! delegated one POSTed its seal to the holder's entry point and the AEAT rejected **every**
//! record. A rejection is not a link in the chain (ADR-0189), so each one had to be corrected by
//! hand afterwards.
//!
//! There are **two axes and they multiply**, which is why they are pinned here together rather
//! than one test per axis: getting the kind right while losing the environment is not a smaller
//! bug, it is a worse one — a rejection is noisy and recoverable, a real invoice accepted into
//! preproduction (or a test invoice accepted into production) is neither.
//!
//! [OCA/l10n-spain#4597]: https://github.com/OCA/l10n-spain/discussions/4597
use erplora_verifactu::aeat;

/// The slot names are the core's (`certificate::CertificateKind::as_str`) and travel to the engine
/// inside `certificate_kind` of the config, put there by `read_config` (hub#319).
const OWN: &str = "own";
const DELEGATED: &str = "delegated";

const PREPRODUCTION_HOLDER: &str =
    "https://prewww1.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PREPRODUCTION_SEAL: &str =
    "https://prewww10.aeat.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PRODUCTION_HOLDER: &str =
    "https://www1.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";
const PRODUCTION_SEAL: &str =
    "https://www10.agenciatributaria.gob.es/wlpl/TIKE-CONT/ws/SistemaFacturacion/VerifactuSOAP";

/// 🔴 **The bug hub#320 closes.** With ERPlora's delegated certificate the POST has to go to the
/// seal entry point; before this, it went to the holder's and every record came back rejected.
#[test]
fn the_delegated_certificate_transmits_through_the_seal_entry_point() {
    assert_eq!(aeat::endpoint("testing", DELEGATED), PREPRODUCTION_SEAL);
    assert_eq!(aeat::endpoint("production", DELEGATED), PRODUCTION_SEAL);
}

/// The other half of the same rule: a business signing with ITS OWN certificate must keep going
/// exactly where it went before hub#320. This is the whole deployed fleet, so a regression here is
/// every hub at once.
#[test]
fn the_businesss_own_certificate_keeps_the_holder_entry_point() {
    assert_eq!(aeat::endpoint("testing", OWN), PREPRODUCTION_HOLDER);
    assert_eq!(aeat::endpoint("production", OWN), PRODUCTION_HOLDER);
}

/// **The two axes never get multiplied wrong.** Four combinations, four different URLs, and no
/// preproduction host inside a production URL or the other way round.
#[test]
fn the_environment_and_the_certificate_are_independent_axes() {
    let matrix = [
        ("testing", OWN, PREPRODUCTION_HOLDER),
        ("testing", DELEGATED, PREPRODUCTION_SEAL),
        ("production", OWN, PRODUCTION_HOLDER),
        ("production", DELEGATED, PRODUCTION_SEAL),
    ];
    for (environment, kind, expected) in matrix {
        let url = aeat::endpoint(environment, kind);
        assert_eq!(url, expected, "({environment}, {kind})");
        let is_production = environment == "production";
        assert_eq!(
            url.contains("agenciatributaria.gob.es"),
            is_production,
            "the environment axis leaked: ({environment}, {kind}) → {url}"
        );
        assert_eq!(
            url.contains("prewww"),
            !is_production,
            "the environment axis leaked: ({environment}, {kind}) → {url}"
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
        for kind in [OWN, DELEGATED] {
            let url = aeat::endpoint(environment, kind);
            assert!(
                url.starts_with("https://") && url.ends_with(PATH),
                "({environment}, {kind}) → {url}"
            );
        }
    }
}

/// 🔒 **An unknown certificate kind goes to the holder's entry point, not the seal's.** The engine
/// refuses to transmit without a certificate at all (`build_identity`), so this only covers a slot
/// this build does not know about. Sending an unknown certificate to `www10` and sending it to
/// `www1` both end in a rejection — but `www1` is what every certificate in the field is today, so
/// the unknown value degrades into the behaviour that was there before hub#320 instead of routing
/// the whole fleet somewhere new.
#[test]
fn an_unknown_certificate_kind_falls_back_to_the_holder_entry_point() {
    for kind in ["", "  ", "DELEGATED", "delegated ", "sello", "own", "future-slot"] {
        assert_eq!(
            aeat::endpoint("testing", kind),
            PREPRODUCTION_HOLDER,
            "unknown kind {kind:?} must not be routed to the seal entry point"
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
        assert_eq!(aeat::endpoint(environment, OWN), PREPRODUCTION_HOLDER, "{environment:?}");
        assert_eq!(
            aeat::endpoint(environment, DELEGATED),
            PREPRODUCTION_SEAL,
            "{environment:?}"
        );
    }
}

/// The consult operation is published on the SAME entry point as the alta (hub#287) — and that
/// stays true on **both** axes, so a delegated hub can also recover its chain.
#[test]
fn the_consult_shares_the_entry_point_with_the_alta_for_every_certificate() {
    for environment in ["testing", "production"] {
        for kind in [OWN, DELEGATED] {
            assert_eq!(
                aeat::consult_endpoint(environment, kind),
                aeat::endpoint(environment, kind),
                "({environment}, {kind})"
            );
        }
    }
}
