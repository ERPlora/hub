//! hub#1742 — the beat has to NAME the running binary the way the SaaS reads it, and the number
//! it names has to be the one the AEAT record declares.
//!
//! Art. 13.3 of the RRSIF (RD 1007/2023) asks for one *declaración responsable* per version of
//! the system, and there are two published: a hub still running the older binary must be linked
//! the older text, because the newer one describes a composition it does not have installed. Only
//! the hub knows which binary is alive — `Hub.deployed_image` is the spec written at deploy time,
//! not the container that is answering — so the beat is where that number has to travel.
//!
//! **The beat already carried it, under a name nobody was reading.** hub#515 put it on the wire as
//! `hub_version`; the endpoint that picks the declaration reads `core_version` and nothing on the
//! SaaS ever reads `hub_version` from this body. The number was emitted and dropped, and every hub
//! got the declaration in force whatever it was running. Renaming it — rather than adding a second
//! field with the same value — is the point: two spellings of one number is exactly the drift the
//! second test below exists to forbid.

use erplora_server::daily_usage::{DailyUsageHeartbeat, PendingObligationFields};
use erplora_server::version::HUB_VERSION;
use serde_json::{json, Value};

/// A beat carrying nothing but the version, built the way `collect_daily_usage` builds it.
fn beat() -> DailyUsageHeartbeat {
    DailyUsageHeartbeat {
        orders_today: None,
        last_sale_at: None,
        terminals: None,
        last_user_activity_at: None,
        core_version: HUB_VERSION.to_string(),
        pending: PendingObligationFields::default(),
        cpu_pct: None,
        memory_used_mb: None,
        memory_limit_mb: None,
        memory_peak_mb: None,
        transmission_route: None,
    }
}

fn wire() -> Value {
    serde_json::to_value(beat()).expect("the beat has to serialize")
}

/// The producer's half of `SistemaInformatico`, as the control plane serves it — without it there
/// is no envelope to compare against.
fn config() -> Value {
    json!({
        "producer_facts": {
            "NombreRazon": "ERPLORA CLOUD SL",
            "NIF": "B27593136",
            "NombreSistemaInformatico": "ERPlora Hub",
            "IdSistemaInformatico": "EC",
            "TipoUsoPosibleSoloVerifactu": "S",
            "TipoUsoPosibleMultiOT": "S",
            "IndicadorMultiplesOT": "N",
        },
    })
}

fn alta() -> Value {
    json!({
        "record_type": "alta",
        "issuer_nif": "B27593136",
        "issuer_name": "ERPLORA CLOUD SL",
        "invoice_number": "FA/001",
        "invoice_date": "2026-08-02",
        "invoice_type": "F2",
        "description": "Venta FA/001",
        "base_amount": 10000,
        "tax_rate": 21.0,
        "tax_breakdown": r#"{"21.00":{"base":10000,"tax":2100}}"#,
        "tax_amount": 2100,
        "total_amount": 12100,
        "recipient_nif": "",
        "recipient_name": "",
        "record_hash": "A".repeat(64),
        "is_first_record": 1,
        "generation_timestamp": "2026-08-02T10:00:00+02:00",
    })
}

/// `<sum1:Version>` as the record actually declares it — the single occurrence, or the test fails
/// rather than picking one.
fn version_in_the_record() -> String {
    let xml = erplora_verifactu::aeat::build_soap(&alta(), &config(), None, "hub-1")
        .expect("an alta with producer facts is declarable");
    assert_eq!(
        xml.matches("<sum1:Version>").count(),
        1,
        "one record declares one version: {xml}"
    );
    let rest = xml
        .split_once("<sum1:Version>")
        .expect("the envelope carries SistemaInformatico/Version")
        .1;
    rest.split_once("</sum1:Version>")
        .expect("the element closes")
        .0
        .to_string()
}

/// The name is the contract: `POST /api/v1/hub/device/heartbeat/` picks the covering declaration
/// from `core_version`, and reads nothing else. A number under any other key is a number the
/// control plane never sees.
#[test]
fn the_beat_names_the_version_the_way_the_saas_reads_it() {
    let wire = wire();

    assert_eq!(
        wire["core_version"], HUB_VERSION,
        "the beat has to carry the running binary under the key the SaaS reads: {wire}"
    );
    assert!(
        wire.get("hub_version").is_none(),
        "one number, one spelling — a second key is a number that will drift: {wire}"
    );
}

/// It travels WITHOUT the `v`: the prefix is for a panel, and the SaaS compares this against
/// `covers_from` without stripping anything.
#[test]
fn the_version_on_the_wire_has_no_v_prefix() {
    let wire = wire();

    assert!(
        !wire["core_version"]
            .as_str()
            .expect("the version is a string")
            .starts_with('v'),
        "the `v` is for reading a panel, not for something the Cloud will compare: {wire}"
    );
}

/// 🔴 The one the issue is really about: the number the hub REPORTS and the number it DECLARES to
/// the AEAT are the same number.
///
/// If they separate, the hub emits `SistemaInformatico/Version` = X in every record and asks the
/// control plane for the declaration covering Y — so it links the text of a product it is not
/// running, which is the art. 13.3 failure this whole change exists to close.
#[test]
fn the_number_on_the_wire_is_the_one_the_aeat_record_declares() {
    let reported = wire()["core_version"]
        .as_str()
        .expect("the version is a string")
        .to_string();

    assert_eq!(
        reported,
        version_in_the_record(),
        "the version reported on the beat and the one declared in the record are one number"
    );
}
