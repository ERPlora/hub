//! **Calling MY cloud, with MY machine credential** — a host primitive, not a use-case door
//! (hub#1459).
//!
//! A first-party engine sometimes needs something only the control plane knows. It must never
//! hold the machine credential to get it (`X-Hub-Token` is a runtime secret, ADR-0003), and the
//! core must not learn what the engine is asking for — a `fiscal_gateway_access` method names its
//! caller's use case and drags regime knowledge into the base (hub#1407).
//!
//! So the host is a **decorator**: the engine picks the METHOD, the PATH and the BODY; the host
//! puts the DESTINATION and the CREDENTIAL. That split is the whole security property and the
//! only thing this primitive constrains — the destination is the hub's own cloud
//! (`HUB_CLOUD_API_URL`), because a credential handed to a destination the caller chooses is a
//! credential leaked. It is NOT a URL allowlist: with mTLS (where no key travels) the engine
//! keeps choosing its own destination, as `verifactu` already does.
//!
//! Who actually makes the call is a [`CloudCaller`] the server installs at boot (the
//! `ProducerFactsCache` shape: composition root writes, `DbHost` reads).

use std::sync::{Arc, OnceLock, RwLock};

use crate::errors::{Result, RuntimeError};

/// The verbs an engine may ask for. A closed set on purpose: this primitive exists to lend a
/// credential, not to be a general-purpose HTTP client bolted onto the host.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CloudMethod {
    Get,
    Post,
}

impl CloudMethod {
    pub fn as_str(self) -> &'static str {
        match self {
            CloudMethod::Get => "GET",
            CloudMethod::Post => "POST",
        }
    }
}

/// One call, as the engine describes it. No host, no scheme, no headers: those are the host's.
#[derive(Debug, Clone)]
pub struct CloudRequest {
    pub method: CloudMethod,
    /// Absolute path on the hub's own cloud, `/api/…`. Validated by [`check_path`].
    pub path: String,
    /// JSON body, `None` for a bodyless call.
    pub body: Option<String>,
}

/// What the cloud answered. `status` is the whole verdict; the body is data for the engine.
#[derive(Clone)]
pub struct CloudResponse {
    pub status: u16,
    pub body: String,
}

impl std::fmt::Debug for CloudResponse {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // The body of a control-plane answer routinely carries a bearer (the gateway token is one)
        // and, on a proxy mishap, so can the body of a non-2xx. Neither has any business in a log
        // line: the status is what a reader needs. Same lesson as `fiscal_certificate.rs`.
        f.debug_struct("CloudResponse")
            .field("status", &self.status)
            .field("body", &"[redacted]")
            .field("body_bytes", &self.body.len())
            .finish()
    }
}

/// Stable refusal code for a path that would leave the hub's own cloud (ABI shape of hub#139:
/// callers program against the code, never the prose).
pub const PATH_NOT_MINE: &str = "cloud_call.path_not_mine";

/// **The one thing this primitive constrains.** The engine chooses the path; the host makes sure
/// that path stays on the hub's own cloud, because what rides on it is the machine credential.
///
/// Refused: anything with a scheme (`https://…`), a protocol-relative host (`//evil.example/…`),
/// a `..` segment that could climb out of `/api/`, and anything not rooted at `/api/`.
pub fn check_path(path: &str) -> Result<()> {
    let rooted = path.starts_with("/api/");
    let climbs = path.split('/').any(|segment| segment == "..");
    let switches_host = path.starts_with("//") || path.contains("://");
    // A backslash or a control character in a URL is how a request line gets split; neither has
    // any business in an API path, so they are refused rather than escaped.
    let malformed = path
        .chars()
        .any(|c| c == '\\' || c.is_whitespace() || c.is_control());
    if !rooted || climbs || switches_host || malformed {
        return Err(refused(path));
    }
    Ok(())
}

/// Who actually makes the call. Implemented by the server (`HubCloudCaller`), faked in tests; the
/// default host has none installed and answers `None`.
#[async_trait::async_trait]
pub trait CloudCaller: Send + Sync {
    /// `Ok(None)` = this hub cannot call its cloud at all (no caller installed, or no machine
    /// credential). `Err` = the call was attempted and broke. `Ok(Some(_))` = the cloud answered,
    /// whatever the status — a 404 or a 409 is an ANSWER and the engine decides what it means.
    async fn call(&self, request: CloudRequest) -> Result<Option<CloudResponse>>;
}

/// The process-global slot the server installs its caller into. Re-installable so tests can plant
/// fakes.
pub struct CloudCallerCell {
    caller: RwLock<Option<Arc<dyn CloudCaller>>>,
}

impl CloudCallerCell {
    fn new() -> Self {
        Self {
            caller: RwLock::new(None),
        }
    }

    pub fn global() -> &'static CloudCallerCell {
        static CELL: OnceLock<CloudCallerCell> = OnceLock::new();
        CELL.get_or_init(CloudCallerCell::new)
    }

    pub fn install(&self, caller: Arc<dyn CloudCaller>) {
        if let Ok(mut slot) = self.caller.write() {
            *slot = Some(caller);
        }
    }

    /// `None` until the server installs one — the state of every test host and of a runtime
    /// embedded without a control plane.
    pub fn current(&self) -> Option<Arc<dyn CloudCaller>> {
        self.caller.read().ok().and_then(|slot| slot.clone())
    }

    /// Removes the installed caller (tests: leave the global as you found it).
    pub fn clear(&self) {
        if let Ok(mut slot) = self.caller.write() {
            *slot = None;
        }
    }
}

fn refused(path: &str) -> RuntimeError {
    RuntimeError::Native(format!(
        "{PATH_NOT_MINE}: `{path}` no es una ruta de la nube de este hub"
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    struct NoCaller;
    #[async_trait::async_trait]
    impl CloudCaller for NoCaller {
        async fn call(&self, _request: CloudRequest) -> Result<Option<CloudResponse>> {
            Ok(None)
        }
    }

    /// 🔒 The security property of the whole primitive: the credential goes to MY cloud and
    /// nowhere else. Every shape that could redirect it is refused, with the stable code.
    #[test]
    fn a_path_that_leaves_my_cloud_is_refused() {
        for path in [
            "https://evil.example/api/v1/steal/",
            "http://evil.example/api/",
            "//evil.example/api/v1/steal/",
            "/api/v1/../../../steal/",
            "/api/../etc/passwd",
            "/not-the-api/",
            "api/v1/hub/device/",
            "",
        ] {
            let error = check_path(path)
                .err()
                .unwrap_or_else(|| panic!("`{path}` must not be reachable with the machine token"));
            assert!(
                error.to_string().contains(PATH_NOT_MINE),
                "`{path}`: {error}"
            );
        }
    }

    /// The positive control (regla de cero regresiones): a check that refuses everything guards
    /// nothing. The paths the runtime really calls must pass.
    #[test]
    fn the_paths_of_this_hubs_own_cloud_pass() {
        for path in [
            "/api/v1/hub/device/fiscal/gateway-token/",
            "/api/v1/hub/device/heartbeat/",
            "/api/v1/hub/device/entitlement/",
        ] {
            check_path(path).unwrap_or_else(|e| panic!("`{path}` should pass: {e}"));
        }
    }

    /// The body of a control-plane answer carries bearers. Its `Debug` must not.
    #[test]
    fn the_debug_of_a_response_redacts_the_body() {
        let response = CloudResponse {
            status: 200,
            body: r#"{"token":"SUPER-SECRET-BEARER"}"#.to_owned(),
        };

        let printed = format!("{response:?}");

        assert!(!printed.contains("SUPER-SECRET-BEARER"), "{printed}");
        assert!(printed.contains("[redacted]"));
        assert!(printed.contains("200"));
    }

    /// The global cell starts empty, takes a caller, and can be cleared back.
    #[test]
    fn the_global_cell_installs_and_clears() {
        let cell = CloudCallerCell::new();
        assert!(cell.current().is_none());
        cell.install(Arc::new(NoCaller));
        assert!(cell.current().is_some());
        cell.clear();
        assert!(cell.current().is_none());
    }
}
