//! **The one place a flow's URL is parsed** (hub#728 / hub#729 — ADR-0283 §4).
//!
//! Both bugs were the same bug: the kernel judged an URL with a parser written by hand and then
//! handed the *string* to an HTTP client, which parsed it again with the WHATWG parser. Two
//! parsers, two different URLs, and every gate in between defending the wrong one.
//!
//! ```text
//!            what was judged                       what was dialled
//!   http://2130706433:8791/api    «some host name»   http://127.0.0.1:8791/api   ← the hub itself
//!   https://h/anything/../status  «under /anything»  https://h/status            ← not granted
//! ```
//!
//! So there is **one parse**, it happens here, and what comes out is a [`Url`] — an object, not a
//! string. It is the object the allow-list matches, the object the address guard judges and the
//! object handed to `reqwest`. `url` is the same crate and the same version `reqwest` uses
//! internally, so nothing downstream re-parses anything: there is no second URL to disagree with
//! the first.
//!
//! The other half of the invariant is that this normal form is a **fixed point**: parsing the
//! output again is a no-op. That is what makes «the URL judged is the URL dialled» survive
//! somebody adding another hop in the middle later on — the moment a raw string travels again, the
//! second parse moves it and the tests fall over.
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

pub use url::{Host, Url};

/// Parses a rendered URL, or says why the hub will not call it.
///
/// The error is a **reason without the URL in it**: an URL can carry a credential in a query
/// parameter, and every caller already holds the redacted copy it should be naming.
pub fn parse(raw: &str) -> Result<Url, String> {
    let url = Url::parse(raw.trim()).map_err(|e| format!("is not a URL ({e})"))?;
    if !matches!(url.scheme(), "http" | "https") {
        return Err("is not an absolute `http://` or `https://` URL".to_string());
    }
    if url.host().is_none() || url.host_str().unwrap_or_default().is_empty() {
        return Err("names no host".to_string());
    }
    // `user:pass@host` is not accepted anywhere in this kernel: an allow-list that has to reason
    // about credentials in the authority is one that can be fooled
    // (`https://api.example.com@evil.test` reads as the first host and is fetched from the second).
    if !url.username().is_empty() || url.password().is_some() {
        return Err("carries credentials in its authority, which no allow-list can read".to_string());
    }
    Ok(url)
}

/// `scheme://host[:port]`, normalised — the half of an URL that is compared **whole**.
pub fn origin_of(url: &Url) -> &str {
    &url[..url::Position::BeforePath]
}

/// Path + query + fragment, with the dot segments already resolved — the half that is compared by
/// **prefix**. `/anything/../status/418` is `/status/418` here, which is what a server would serve.
pub fn tail_of(url: &Url) -> &str {
    &url[url::Position::BeforePath..]
}

/// The literal address this URL names, or `None` when it names a NAME.
///
/// The distinction is the whole reason the anti-SSRF guard has two halves: a name is resolved by
/// the HTTP client (and judged there, so the addresses approved are the addresses dialled), while
/// a literal never reaches a resolver at all — hyper short-circuits it — and has to be judged
/// here. Every spelling of a literal collapses into this: `2130706433`, `0x7f000001`, `127.1`,
/// `127.0.0.1.` and `[::ffff:7f00:1]` all arrive as `127.0.0.1`, because the WHATWG host parser
/// says so and the HTTP client uses the same one.
pub fn literal_address(url: &Url) -> Option<IpAddr> {
    match url.host()? {
        Host::Ipv4(v4) => Some(IpAddr::V4(v4)),
        Host::Ipv6(v6) => Some(IpAddr::V6(v6)),
        Host::Domain(_) => None,
    }
}

/// Is this address one the hub must never be talked into calling on somebody else's behalf?
///
/// Everything that is not routable on the public internet: loopback, the private ranges, the
/// link-local block that holds every cloud metadata service (`169.254.169.254`), carrier NAT, the
/// reserved space — and the IPv6 spellings of all of them, including an IPv4 address wearing an
/// IPv6 hat (`::ffff:127.0.0.1` is `127.0.0.1`).
pub fn is_internal(ip: &IpAddr) -> bool {
    match ip {
        IpAddr::V4(v4) => is_internal_v4(v4),
        IpAddr::V6(v6) => is_internal_v6(v6),
    }
}

fn is_internal_v4(ip: &Ipv4Addr) -> bool {
    let [a, b, ..] = ip.octets();
    ip.is_private()
        || ip.is_loopback()
        || ip.is_link_local()
        || ip.is_unspecified()
        || ip.is_broadcast()
        || ip.is_documentation()
        || ip.is_multicast()
        || (a == 100 && (64..128).contains(&b))   // 100.64/10  carrier-grade NAT
        || (a == 192 && b == 0)                   // 192.0.0/24 IETF protocol assignments
        || (a == 198 && (18..20).contains(&b))    // 198.18/15  benchmarking
        || a >= 240 // 240/4      reserved, and 255.255.255.255 with it
}

fn is_internal_v6(ip: &Ipv6Addr) -> bool {
    if ip.is_loopback() || ip.is_unspecified() || ip.is_multicast() {
        return true;
    }
    let s = ip.segments();
    if (s[0] & 0xfe00) == 0xfc00 || (s[0] & 0xffc0) == 0xfe80 {
        return true; // fc00::/7 unique-local · fe80::/10 link-local
    }
    // The same address in another notation is the same address. `to_ipv4` also covers the
    // deprecated `::a.b.c.d` compat form, which some stacks still route.
    if let Some(v4) = ip.to_ipv4_mapped().or_else(|| ip.to_ipv4()) {
        return is_internal_v4(&v4);
    }
    if s[0] == 0x0064 && s[1] == 0xff9b {
        // 64:ff9b::/96 — NAT64 wraps a v4 address in the last two groups.
        let v4 = Ipv4Addr::new(
            (s[6] >> 8) as u8,
            (s[6] & 0xff) as u8,
            (s[7] >> 8) as u8,
            (s[7] & 0xff) as u8,
        );
        return is_internal_v4(&v4);
    }
    false
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_address_that_is_not_the_public_internet_is_internal() {
        for blocked in [
            "127.0.0.1",
            "127.1.2.3",
            "0.0.0.0",
            "10.0.0.5",
            "172.16.0.1",
            "172.31.255.254",
            "192.168.1.1",
            // The one that matters most: every cloud's metadata service.
            "169.254.169.254",
            "100.64.0.1",     // carrier-grade NAT
            "192.0.0.1",      // IETF protocol assignments
            "198.18.0.1",     // benchmarking
            "240.0.0.1",      // reserved
            "255.255.255.255",
            "224.0.0.1",      // multicast
            "::1",
            "::",
            "fe80::1",        // link-local
            "fc00::1",        // unique-local
            "fd12:3456::1",
            "::ffff:127.0.0.1",   // v4 wearing a v6 hat
            "::ffff:169.254.169.254",
            "::169.254.169.254",  // the deprecated compat form
            "64:ff9b::7f00:1",    // NAT64 of 127.0.0.1
            "ff02::1",            // multicast
        ] {
            assert!(
                is_internal(&blocked.parse().unwrap()),
                "`{blocked}` must never be reachable from a flow"
            );
        }

        for public in [
            "1.1.1.1",
            "8.8.8.8",
            "93.184.216.34",
            "172.32.0.1",  // just outside 172.16/12
            "100.128.0.1", // just outside 100.64/10
            "198.20.0.1",  // just outside 198.18/15
            "9.9.9.9",
            "2606:4700:4700::1111",
        ] {
            assert!(
                !is_internal(&public.parse().unwrap()),
                "`{public}` is the public internet and a granted flow may call it"
            );
        }
    }

    /// hub#728 — the corpus a QA walked a live hub through. Not one of these is «a host name»:
    /// they are all the loopback or the cloud metadata service, and the parser the HTTP client
    /// uses has always known it.
    #[test]
    fn every_notation_of_an_internal_literal_arrives_as_that_literal() {
        for (raw, address) in [
            ("http://2130706433:8791/api/hub/context", "127.0.0.1"),
            ("http://0x7f000001/x", "127.0.0.1"),
            ("http://017700000001/x", "127.0.0.1"),
            ("http://127.1/x", "127.0.0.1"),
            ("http://127.0.0.1./x", "127.0.0.1"),
            ("http://0/x", "0.0.0.0"),
            ("http://2852039166/latest/meta-data/", "169.254.169.254"),
            ("http://0xa9fea9fe/latest/", "169.254.169.254"),
            ("http://3232235777/x", "192.168.1.1"),
            ("http://167772161/x", "10.0.0.1"),
            ("http://[::ffff:169.254.169.254]/x", "::ffff:169.254.169.254"),
            ("http://[::ffff:a9fe:a9fe]/x", "::ffff:169.254.169.254"),
            ("http://[64:ff9b::a9fe:a9fe]/x", "64:ff9b::a9fe:a9fe"),
            ("http://[0:0:0:0:0:0:0:1]/x", "::1"),
        ] {
            let url = parse(raw).unwrap_or_else(|e| panic!("`{raw}`: {e}"));
            let found = literal_address(&url).unwrap_or_else(|| panic!("`{raw}` names a literal"));
            assert_eq!(found, address.parse::<IpAddr>().unwrap(), "{raw}");
            assert!(is_internal(&found), "{raw}");
        }

        // A NAME is not a literal: it is the resolver's question, and it is asked there so that the
        // addresses approved are the addresses dialled (the DNS-rebinding half of hub#662).
        for name in ["http://localhost/x", "https://api.example.com/v1", "http://localtest.me/x"] {
            assert!(literal_address(&parse(name).unwrap()).is_none(), "{name}");
        }
    }

    /// hub#729 — the path is resolved before anybody compares it, in every spelling WHATWG treats
    /// as a dot segment.
    #[test]
    fn the_path_is_the_one_a_server_would_serve() {
        for raw in [
            "https://httpbin.org/anything/../status/418",
            r"https://httpbin.org/anything\..\..\status\418",
            "https://httpbin.org/anything/%2e%2e/status/418",
            "https://httpbin.org/anything/./../status/418",
        ] {
            assert_eq!(tail_of(&parse(raw).unwrap()), "/status/418", "{raw}");
        }
        // …and `%2f` is NOT a separator, so it does not become one.
        assert_eq!(
            tail_of(&parse("https://httpbin.org/anything/..%2fstatus/418").unwrap()),
            "/anything/..%2fstatus/418"
        );
        // The origin is the whole authority, normalised — a default port and a shouted host are
        // the same origin, not two.
        assert_eq!(
            origin_of(&parse("https://API.EXAMPLE.COM:443/v1").unwrap()),
            "https://api.example.com"
        );
        // Query and fragment travel with the path, because a grant may name them.
        assert_eq!(
            tail_of(&parse("https://h.test/v1/send?to=+34600111222#f").unwrap()),
            "/v1/send?to=+34600111222#f"
        );
    }

    /// The property everything else leans on: this normal form does not move if it is parsed
    /// again — which is exactly what happens when a string is handed to an HTTP client.
    #[test]
    fn the_normal_form_is_a_fixed_point_of_the_parser() {
        for raw in [
            "http://2130706433:8791/api/hub/context",
            "https://httpbin.org/anything/../status/418",
            "https://API.EXAMPLE.COM:443/v1/send?to=1#f",
            "http://[::ffff:127.0.0.1]/x",
            "https://api.example.com/v1/a b",
            "http://例え.テスト/x",
        ] {
            let once = parse(raw).unwrap();
            let twice = parse(once.as_str()).unwrap();
            assert_eq!(once, twice, "`{raw}` moved on the second parse");
            assert_eq!(once.as_str(), twice.as_str(), "{raw}");
        }
    }

    #[test]
    fn what_the_hub_refuses_to_call_at_all() {
        for raw in [
            "file:///etc/passwd",
            "ftp://example.com/x",
            "gopher://x/",
            "/x",
            "//evil.test/x",
            "",
            "not a url",
            // The authority trick: this is fetched from `evil.test`, not from `api.example.com`.
            "https://api.example.com@evil.test/x",
            "https://user:pass@api.example.com/x",
        ] {
            assert!(parse(raw).is_err(), "`{raw}` must never be called");
        }
    }
}
