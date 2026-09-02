//! Access to the fiscal gateway CELL, as a host capability (hub#1432, hub#985 §1).
//!
//! The engine that transmits (a native plugin today, the module's WASM tomorrow) must never hold
//! a cloud credential: `certificate_refetch.rs` spelled the rule out and this module follows it.
//! What the engine gets is a [`GatewayAccess`] — URL, short-lived Bearer, mTLS identity and the
//! CA root — through `NativeHost::fiscal_gateway_access`. Who actually OBTAINS those four things
//! is a [`GatewayBroker`] the server installs at boot (`HubGatewayBroker`): it holds the machine
//! token, calls the control plane, caches the 300-second Bearer and reads the identity from
//! [`crate::gateway_identity`].
//!
//! Why a broker and not a plain cached value (the `producer_facts` shape): the token expires in
//! 300 s while the heartbeat beats every 60 s — refreshing it on the beat would burn the
//! control-plane quota (60/h) for tokens nobody uses. The broker fetches ON DEMAND, when a
//! transmission actually needs one.

use std::sync::{Arc, OnceLock, RwLock};

use crate::errors::Result;

/// Everything one transmission through the cell needs. Opaque to the engine: it carries no
/// machine token and does not say how any of it was obtained.
#[derive(Clone)]
pub struct GatewayAccess {
    /// The cell's base URL, as the control plane answered it (`gateway_url`). ONE for every hub,
    /// behind the private LB — the hub reads no env for this (saas#1794). The transmission path
    /// is appended by the ENGINE: the core never names it (the hub#1407 guard is why).
    pub url: String,
    /// The short-lived Bearer. NEVER in a log line — the manual `Debug` below is the guard.
    pub token: String,
    /// The hub's mTLS client identity (key born on the hub, `gateway_identity.rs`).
    pub identity: reqwest::Identity,
    /// PEM of the internal CA that anchors the cell's SERVER certificate.
    pub ca_pem: Vec<u8>,
}

impl std::fmt::Debug for GatewayAccess {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The token is a bearer credential and the identity wraps a private key: neither has any
        // business in a Debug dump. The URL alone is enough to recognise the value in a log.
        f.debug_struct("GatewayAccess")
            .field("url", &self.url)
            .field("token", &"[redacted]")
            .field("ca_pem_bytes", &self.ca_pem.len())
            .finish_non_exhaustive()
    }
}

/// Who can actually get an access. Implemented by the server (`HubGatewayBroker`), faked in
/// tests; the default host has none installed and answers `None` — a hub that cannot reach the
/// gateway keeps queueing, it never panics.
#[async_trait::async_trait]
pub trait GatewayBroker: Send + Sync {
    /// `Ok(None)` = the route is not available (no identity enrolled, no machine credential, or
    /// the hub was told to go direct). `Err` = it should be available and something broke — the
    /// caller surfaces it on the record.
    async fn access(&self, hub_id: &str) -> Result<Option<GatewayAccess>>;

    /// The cell answered 401 with the Bearer in flight: drop the cache so the next
    /// [`access`](Self::access) fetches a fresh one.
    async fn invalidate_token(&self) {}
}

/// The process-global slot the server installs its broker into (the `ProducerFactsCache` shape:
/// composition root writes, `DbHost` reads). Re-installable so tests can plant fakes.
pub struct GatewayBrokerCell {
    broker: RwLock<Option<Arc<dyn GatewayBroker>>>,
}

impl GatewayBrokerCell {
    fn new() -> Self {
        Self {
            broker: RwLock::new(None),
        }
    }

    pub fn global() -> &'static GatewayBrokerCell {
        static CELL: OnceLock<GatewayBrokerCell> = OnceLock::new();
        CELL.get_or_init(GatewayBrokerCell::new)
    }

    pub fn install(&self, broker: Arc<dyn GatewayBroker>) {
        if let Ok(mut slot) = self.broker.write() {
            *slot = Some(broker);
        }
    }

    /// `None` until the server installs one — the state of every test host and of a runtime
    /// embedded without a control plane.
    pub fn current(&self) -> Option<Arc<dyn GatewayBroker>> {
        self.broker.read().ok().and_then(|slot| slot.clone())
    }

    /// Removes the installed broker (tests: leave the global as you found it).
    pub fn clear(&self) {
        if let Ok(mut slot) = self.broker.write() {
            *slot = None;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    struct NoBroker;
    #[async_trait::async_trait]
    impl GatewayBroker for NoBroker {
        async fn access(&self, _hub_id: &str) -> Result<Option<GatewayAccess>> {
            Ok(None)
        }
    }

    /// The Debug of an access must never print the Bearer: it is the one shape of this value
    /// that could end up in a log line by accident.
    #[test]
    fn the_debug_of_an_access_redacts_the_bearer() {
        let identity = {
            // Any valid identity does; reuse the runtime's own test material shape (a throwaway
            // EC key + self-signed cert built with openssl, like gateway_identity's tests).
            let group =
                openssl::ec::EcGroup::from_curve_name(openssl::nid::Nid::X9_62_PRIME256V1).unwrap();
            let ec = openssl::ec::EcKey::generate(&group).unwrap();
            let pkey = openssl::pkey::PKey::from_ec_key(ec).unwrap();
            let mut name = openssl::x509::X509NameBuilder::new().unwrap();
            name.append_entry_by_nid(openssl::nid::Nid::COMMONNAME, "debug-test").unwrap();
            let name = name.build();
            let mut cert = openssl::x509::X509::builder().unwrap();
            cert.set_version(2).unwrap();
            cert.set_subject_name(&name).unwrap();
            cert.set_issuer_name(&name).unwrap();
            cert.set_pubkey(&pkey).unwrap();
            cert.set_not_before(&openssl::asn1::Asn1Time::days_from_now(0).unwrap()).unwrap();
            cert.set_not_after(&openssl::asn1::Asn1Time::days_from_now(1).unwrap()).unwrap();
            cert.sign(&pkey, openssl::hash::MessageDigest::sha256()).unwrap();
            let bundle = format!(
                "{}\n{}",
                String::from_utf8(pkey.private_key_to_pem_pkcs8().unwrap()).unwrap(),
                String::from_utf8(cert.build().to_pem().unwrap()).unwrap(),
            );
            reqwest::Identity::from_pem(bundle.as_bytes()).unwrap()
        };
        let access = GatewayAccess {
            url: "https://cell.internal.example".to_owned(),
            token: "SUPER-SECRET-BEARER".to_owned(),
            identity,
            ca_pem: b"ca".to_vec(),
        };

        let printed = format!("{access:?}");

        assert!(!printed.contains("SUPER-SECRET-BEARER"), "{printed}");
        assert!(printed.contains("[redacted]"));
        assert!(printed.contains("https://cell.internal.example"));
    }

    /// The global cell starts empty, takes a broker, and can be cleared back.
    #[test]
    fn the_global_cell_installs_and_clears() {
        let cell = GatewayBrokerCell::new();
        assert!(cell.current().is_none());
        cell.install(Arc::new(NoBroker));
        assert!(cell.current().is_some());
        cell.clear();
        assert!(cell.current().is_none());
    }
}
