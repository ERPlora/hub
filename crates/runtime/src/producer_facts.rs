//! The **manufacturer's half of `SistemaInformatico`**, as the control plane serves it
//! (ADR-0202 §5.1 — hub#323, the hub side of saas#1128).
//!
//! Every VeriFactu record carries a `SistemaInformatico` block, and it mixes two kinds of fact
//! that have different owners:
//!
//! | | Who declares it | Why |
//! |---|---|---|
//! | `Version` | **the hub** | Its own binary. The fleet is pinned to different digests, so each hub must declare the one IT is running — a central number would be a lie on most of them. |
//! | `NumeroInstalacion` | **the hub** | Its own `hub_id` (ADR-0202 §4.2). |
//! | `NombreRazon` · `NIF` · `NombreSistemaInformatico` · `IdSistemaInformatico` | **the SaaS** | The manufacturer's identity: a fact about ERPlora, identical for the whole fleet, and correctable in one place instead of by rebuilding every hub. |
//! | `TipoUsoPosibleSoloVerifactu` · `TipoUsoPosibleMultiOT` | **the SaaS** | Product capabilities declared by the manufacturer; they must agree with the Declaración Responsable. |
//! | `IndicadorMultiplesOT` | **the SaaS** | The AEAT computes it **per user of the SaaS SIF** — over how many facturaciones that account has created. A hub can only see itself. |
//!
//! This module holds the second group. It arrives inline on the heartbeat response (~80 bytes,
//! public, so it rides the beat instead of being announced by a version number) and lands in a
//! process-wide cache that the `verifactu` engine reads — the same shape and the same reason as
//! [`crate::certificate_refetch`]: the layer that talks to the control plane is not the layer
//! that needs the fact, and nothing below the host knows the Cloud exists.
//!
//! **The AEAT element names travel LITERALLY**, in Spanish, because VeriFactu imposes them. A
//! snake_case transliteration would invent a second spelling of a legal contract and force a
//! translation table on both ends.

use std::sync::{OnceLock, RwLock};

use serde_json::{json, Value as Json};

/// The seven `SistemaInformatico` fields the control plane owns, already validated.
///
/// Constructing one is the validation: [`ProducerFacts::parse`] is the only way in, so a block
/// that would be rejected by the AEAT never reaches an envelope. That matters more here than
/// almost anywhere else in the hub — these fields are identical for the whole fleet, so a bad one
/// is **error 1100 on every record of every hub**, and the crate already carries the scar of that
/// accident (a legacy 11-character `IdSistemaInformatico`).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProducerFacts {
    /// `NombreRazon` — the legal name of the MANUFACTURER, not of the product and not of the
    /// business using the hub.
    pub nombre_razon: String,
    /// `NIF` — the manufacturer's tax id. Exactly 9 characters (`NIFType`).
    pub nif: String,
    /// `NombreSistemaInformatico` — the name of the PRODUCT. A different fact from `NombreRazon`,
    /// and the engine used to emit the same string in both.
    pub nombre_sistema_informatico: String,
    /// `IdSistemaInformatico` — the 2-position code the manufacturer assigns to its product.
    pub id_sistema_informatico: String,
    /// `TipoUsoPosibleSoloVerifactu` — `S`/`N`.
    pub tipo_uso_posible_solo_verifactu: String,
    /// `TipoUsoPosibleMultiOT` — `S`/`N`.
    pub tipo_uso_posible_multi_ot: String,
    /// `IndicadorMultiplesOT` — `S`/`N`. **Not a hub fact**: it is computed per account, over the
    /// facturaciones its owner has created, and it was hardcoded to `N` before hub#323.
    pub indicador_multiples_ot: String,
}

/// The keys of the block, exactly as the AEAT names the elements and as the SaaS serves them.
pub const AEAT_FIELDS: [&str; 7] = [
    "NombreRazon",
    "NIF",
    "NombreSistemaInformatico",
    "IdSistemaInformatico",
    "TipoUsoPosibleSoloVerifactu",
    "TipoUsoPosibleMultiOT",
    "IndicadorMultiplesOT",
];

impl ProducerFacts {
    /// Reads the block the control plane serves. `None` when anything about it is wrong.
    ///
    /// **A partial block is not half-usable, it is unusable**: `SistemaInformatico` has no
    /// optional children, so the choice is a complete block or no block. Rejecting it here means
    /// the hub keeps whatever it already had rather than starting to emit a broken identity on
    /// every invoice.
    pub fn parse(block: &Json) -> Option<Self> {
        let field = |key: &str| -> Option<String> {
            let value = block.get(key)?.as_str()?.trim();
            (!value.is_empty()).then(|| value.to_string())
        };
        let si_no = |key: &str| -> Option<String> {
            let value = field(key)?;
            matches!(value.as_str(), "S" | "N").then_some(value)
        };
        let bounded = |key: &str, max: usize| -> Option<String> {
            let value = field(key)?;
            (value.chars().count() <= max).then_some(value)
        };

        let nif = field("NIF")?;
        // `NIFType` is `length = 9`, not `maxLength`. A NIF of any other size is error 1100 for
        // the whole fleet, and it is cheaper to refuse the block than to find out from the AEAT.
        if nif.chars().count() != 9 {
            return None;
        }

        Some(ProducerFacts {
            nombre_razon: bounded("NombreRazon", 120)?,
            nif,
            nombre_sistema_informatico: bounded("NombreSistemaInformatico", 30)?,
            id_sistema_informatico: bounded("IdSistemaInformatico", 2)?,
            tipo_uso_posible_solo_verifactu: si_no("TipoUsoPosibleSoloVerifactu")?,
            tipo_uso_posible_multi_ot: si_no("TipoUsoPosibleMultiOT")?,
            indicador_multiples_ot: si_no("IndicadorMultiplesOT")?,
        })
    }

    /// The block back in the shape it arrived in — the AEAT-literal keys.
    ///
    /// This is how the facts cross into a native module: through the module's config, next to the
    /// certificate markers, so the engine reads one object and never learns that a control plane
    /// exists.
    pub fn to_json(&self) -> Json {
        json!({
            "NombreRazon": self.nombre_razon,
            "NIF": self.nif,
            "NombreSistemaInformatico": self.nombre_sistema_informatico,
            "IdSistemaInformatico": self.id_sistema_informatico,
            "TipoUsoPosibleSoloVerifactu": self.tipo_uso_posible_solo_verifactu,
            "TipoUsoPosibleMultiOT": self.tipo_uso_posible_multi_ot,
            "IndicadorMultiplesOT": self.indicador_multiples_ot,
        })
    }
}

/// Which text on the public archive covers the version this hub is running (hub#1449,
/// ERPlora/saas#1724 — art. 13.3 RRSIF).
///
/// The archive is versioned **by declaration** (`v1`, `v2`…), not by release number, so the root
/// of the archive only resolves to the version an inspector needs while a single declaration is
/// in force. The day a second one is issued, a hub still running the version the first one covers
/// must keep linking THAT one — and only the control plane knows which declaration that is,
/// because the mapping «release → declaration that covers it» is recorded on the archive, not in
/// this crate.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DeclarationReference {
    /// Which declaration this is (`v1`, `v2`…) — the folder name on the archive, shown next to
    /// the link so an inspector can check it against the text without following the URL.
    pub version: String,
    /// Where the signed text lives, on the control plane this hub belongs to.
    pub url: String,
}

impl DeclarationReference {
    /// Reads `{"version": …, "url": …}`, exactly as `declaration_reference()` serves it
    /// (`apps/dashboard/fiscal/services/declaracion_responsable.py`). `None` when either half is
    /// missing: a reference that names a text without saying where it lives is not something the
    /// panel can link, and the caller falls back to the root of the public archive.
    pub fn parse(block: &Json) -> Option<Self> {
        let field = |key: &str| -> Option<String> {
            let value = block.get(key)?.as_str()?.trim();
            (!value.is_empty()).then(|| value.to_string())
        };
        Some(Self {
            version: field("version")?,
            url: field("url")?,
        })
    }
}

/// What this process last heard from the control plane about the manufacturer, and which
/// declaration covers the version it is running.
///
/// One per process in production ([`ProducerFactsCache::global`]); constructible so tests own
/// theirs instead of racing over a static. The two facts travel together on purpose: they arrive
/// on the same heartbeat and the same cycle (hub#1449), so a second cache that could fall behind
/// this one would let the panel link a declaration for an identity the hub no longer holds.
#[derive(Debug, Default)]
pub struct ProducerFactsCache {
    facts: RwLock<Option<ProducerFacts>>,
    declaration: RwLock<Option<DeclarationReference>>,
}

impl ProducerFactsCache {
    pub fn new() -> Self {
        Self::default()
    }

    /// The process-wide cache: what the heartbeat fills and what `verifactu` reads.
    pub fn global() -> &'static ProducerFactsCache {
        static CACHE: OnceLock<ProducerFactsCache> = OnceLock::new();
        CACHE.get_or_init(ProducerFactsCache::new)
    }

    /// Installs what the control plane just said.
    pub fn store(&self, facts: ProducerFacts) {
        if let Ok(mut slot) = self.facts.write() {
            *slot = Some(facts);
        }
    }

    /// The current facts, or `None` when this hub has never been told them.
    ///
    /// `None` is **not** «use the defaults»: there are no defaults for a legal declaration. The
    /// caller refuses to build the envelope, which leaves the record in the contingency queue
    /// until the next beat — a minute at most, and the hub could not have transmitted anyway
    /// without ever reaching the Cloud.
    pub fn current(&self) -> Option<ProducerFacts> {
        self.facts.read().ok().and_then(|slot| slot.clone())
    }

    /// Installs which declaration the control plane says covers this hub's running version.
    pub fn store_declaration(&self, declaration: DeclarationReference) {
        if let Ok(mut slot) = self.declaration.write() {
            *slot = Some(declaration);
        }
    }

    /// The declaration reference last announced, or `None` when this hub has never been told one
    /// — an older control plane, a hub that has not spoken to it yet, or an archive the control
    /// plane could not read. `None` is «no news», never an error: the caller falls back to the
    /// root of the public archive, which already resolves to the declaration in force.
    pub fn current_declaration(&self) -> Option<DeclarationReference> {
        self.declaration.read().ok().and_then(|slot| slot.clone())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The block exactly as `apps/dashboard/fiscal/services/producer_facts.py` serves it.
    fn served_block() -> Json {
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

    #[test]
    fn the_block_the_saas_serves_is_read_field_by_field() {
        let facts = ProducerFacts::parse(&served_block()).expect("the served block is valid");

        assert_eq!(facts.nombre_razon, "ERPLORA CLOUD SL");
        assert_eq!(facts.nif, "B27593136");
        assert_eq!(facts.nombre_sistema_informatico, "ERPlora Hub");
        assert_eq!(facts.id_sistema_informatico, "EC");
        assert_eq!(facts.indicador_multiples_ot, "N");
    }

    /// The manufacturer (`NombreRazon`) and the product (`NombreSistemaInformatico`) are two
    /// different facts. The engine used to emit one string in both slots.
    #[test]
    fn the_manufacturer_and_the_product_are_not_the_same_name() {
        let facts = ProducerFacts::parse(&served_block()).unwrap();

        assert_ne!(facts.nombre_razon, facts.nombre_sistema_informatico);
    }

    /// A round trip has to come back with the same keys: they are the XML element names, and a
    /// second spelling of them is a rejection nobody would see coming.
    #[test]
    fn the_keys_survive_the_round_trip_literally() {
        let facts = ProducerFacts::parse(&served_block()).unwrap();

        let json = facts.to_json();
        for field in AEAT_FIELDS {
            assert!(json.get(field).is_some(), "missing `{field}` in {json}");
        }
        assert_eq!(ProducerFacts::parse(&json), Some(facts));
    }

    /// Missing anything at all: `SistemaInformatico` has no optional children, so half a block is
    /// no block. Keeping the previous one beats emitting a broken identity on every invoice.
    #[test]
    fn a_partial_block_is_refused_whole() {
        for field in AEAT_FIELDS {
            let mut block = served_block();
            block.as_object_mut().unwrap().remove(field);

            assert_eq!(
                ProducerFacts::parse(&block),
                None,
                "a block without `{field}` must not be installed"
            );
        }
    }

    /// 🔴 The accident the crate already carries a comment about: `IdSistemaInformatico` is
    /// `TextMax2Type`, and a legacy 11-character value was rejected with error 1100. These facts
    /// are fleet-wide, so one bad character is every record of every hub.
    #[test]
    fn an_over_long_product_code_is_refused() {
        let mut block = served_block();
        block["IdSistemaInformatico"] = json!("ERPLORA-001");

        assert_eq!(ProducerFacts::parse(&block), None);
    }

    /// `NIFType` is `length = 9`, not `maxLength`.
    #[test]
    fn a_nif_that_is_not_nine_characters_is_refused() {
        for wrong in ["B2759313", "B275931366"] {
            let mut block = served_block();
            block["NIF"] = json!(wrong);

            assert_eq!(ProducerFacts::parse(&block), None, "{wrong}");
        }
    }

    /// `SiNoType` is a closed list. `true`, `"si"` or `"Y"` are not values the AEAT knows, and
    /// silently reading them as one of the two would be declaring something nobody said.
    #[test]
    fn the_indicator_only_accepts_s_or_n() {
        for wrong in [json!("Y"), json!("si"), json!(true), json!("")] {
            let mut block = served_block();
            block["IndicadorMultiplesOT"] = wrong.clone();

            assert_eq!(ProducerFacts::parse(&block), None, "{wrong}");
        }
    }

    /// Nothing to say yet is `None`, and `None` is not a set of defaults: there are none for a
    /// legal declaration.
    #[test]
    fn a_cache_nobody_has_filled_answers_nothing() {
        assert_eq!(ProducerFactsCache::new().current(), None);
    }

    /// The last thing the control plane said is what the next invoice declares — that is the
    /// whole point of serving these from the SaaS instead of compiling them in.
    #[test]
    fn the_cache_keeps_the_latest_answer() {
        let cache = ProducerFactsCache::new();
        cache.store(ProducerFacts::parse(&served_block()).unwrap());

        let mut second = served_block();
        second["IndicadorMultiplesOT"] = json!("S");
        cache.store(ProducerFacts::parse(&second).unwrap());

        assert_eq!(cache.current().unwrap().indicador_multiples_ot, "S");
    }

    /// The block exactly as `declaration_reference()` serves it (saas#1724): which text covers
    /// the version this hub is running, and where it lives on the archive.
    fn declaration_block() -> Json {
        json!({
            "version": "v1",
            "url": "https://erplora.com/legal/declaracion-responsable/v1/",
        })
    }

    #[test]
    fn the_declaration_reference_is_read_field_by_field() {
        let declaration =
            DeclarationReference::parse(&declaration_block()).expect("the served block is valid");

        assert_eq!(declaration.version, "v1");
        assert_eq!(
            declaration.url,
            "https://erplora.com/legal/declaracion-responsable/v1/"
        );
    }

    /// `version` and `url` are both required: a reference that names a text without saying where
    /// it lives (or the reverse) is not a fact the panel can link.
    #[test]
    fn a_declaration_reference_missing_either_field_is_refused() {
        for field in ["version", "url"] {
            let mut block = declaration_block();
            block.as_object_mut().unwrap().remove(field);

            assert_eq!(
                DeclarationReference::parse(&block),
                None,
                "a reference without `{field}` must not be installed"
            );
        }
    }

    /// Nothing heard yet is `None` — and `None` is what makes the caller fall back to the root of
    /// the public archive instead of linking a made-up version.
    #[test]
    fn a_cache_nobody_has_told_the_declaration_answers_nothing() {
        assert_eq!(ProducerFactsCache::new().current_declaration(), None);
    }

    /// hub#1449: when the AEAT publishes a second declaration, the reference the panel links has
    /// to follow the latest heartbeat, exactly like the manufacturer's facts already do.
    #[test]
    fn the_cache_keeps_the_latest_declaration() {
        let cache = ProducerFactsCache::new();
        cache.store_declaration(DeclarationReference::parse(&declaration_block()).unwrap());

        let mut second = declaration_block();
        second["version"] = json!("v2");
        second["url"] = json!("https://erplora.com/legal/declaracion-responsable/v2/");
        cache.store_declaration(DeclarationReference::parse(&second).unwrap());

        assert_eq!(cache.current_declaration().unwrap().version, "v2");
        assert_eq!(
            cache.current_declaration().unwrap().url,
            "https://erplora.com/legal/declaracion-responsable/v2/"
        );
    }
}
