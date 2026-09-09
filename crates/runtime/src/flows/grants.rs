//! **What a flow is allowed to do** (`_flow_grants`, ADR-0283 D2).
//!
//! A flow does not borrow anybody's role. The alternatives were both considered and both
//! discarded in the ADR: inheriting the creator's permissions breaks the day that employee is
//! deleted (and quietly changes what the flow may do every time somebody is promoted), and a `*`
//! wildcard is no containment at all. What is left is the same shape as module capabilities
//! (ADR-0079) — **default-deny by absence**: a row exists and is alive, or the answer is no.
//!
//! Three properties are the reason this is a table and not a field on the flow:
//!
//! 1. **Fresh at every step.** The gate reads this on each command a run executes, so revoking a
//!    grant while a run is in flight stops the run at its NEXT step. Not the current one — that
//!    one is already inside a transaction — which is the honest guarantee and the one this file's
//!    tests pin.
//! 2. **Revocation is auditable.** A revoked grant is soft-deleted with `revoked_by`, so "who
//!    could do what, and until when" survives. The unique index is partial for exactly this
//!    reason (see the v32 migration).
//! 3. **No elevation.** A grant opens the gate for the command it names and nothing else. It does
//!    not add a permission to a session, and a flow runs as [`crate::registry::Principal::Machine`],
//!    which can never be offered the manager's PIN (hub#361).
use std::collections::{HashMap, HashSet};

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def;
use crate::flows::net::{self, Url};
use crate::host_notify::{Channel, FLOW_GRANT_PREFIX};
use crate::registry::{new_id, now_rfc3339, Registry};

pub const ERR_GRANT_DENIED: &str = "flow.grant_denied";
pub const ERR_UNKNOWN_GRANT_KIND: &str = "flow.unknown_grant_kind";
pub const ERR_GRANT_KIND_NOT_AVAILABLE: &str = "flow.grant_kind_not_available";
pub const ERR_INVALID_HTTP_PATTERN: &str = "flow.invalid_http_pattern";
/// hub#821 — a `notify` grant that names a channel this hub cannot send on, or no channel at all.
pub const ERR_INVALID_NOTIFY_GRANT: &str = "flow.invalid_notify_grant";
/// hub#821 — a `recipient_query` grant that is not `<query>#<field>`.
pub const ERR_INVALID_RECIPIENT_GRANT: &str = "flow.invalid_recipient_grant";
/// hub#824 — a command a flow can never invoke, named where a flow names commands.
pub const ERR_INTERNAL_COMMAND: &str = "flow.internal_command";
/// hub#1623 — the command IS granted, but the grant PINS part of its payload and this call
/// contradicts the pin. A separate code from [`ERR_GRANT_DENIED`] on purpose: «this flow may not
/// cancel appointments» and «this flow may only cancel them as the customer» are different
/// sentences on the grants screen, and the second one is the one that tells an owner their
/// containment worked.
pub const ERR_GRANT_PAYLOAD_DENIED: &str = "flow.grant_payload_denied";
/// hub#1623 — a `payload` pin that cannot be stored: one on a kind that carries no payload, or one
/// that is not an object. Refused rather than stored as a restriction nothing can enforce, the same
/// rule [`GrantKind::is_available`] enforces for the kinds.
pub const ERR_INVALID_GRANT_PAYLOAD: &str = "flow.invalid_grant_payload";

/// The five kinds of ADR-0283 §2. The vocabulary is frozen here; what grows is which of them can
/// be CREATED, because a grant for something the kernel cannot do yet would tell an owner that
/// their flow may call an URL or message a customer when it cannot.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum GrantKind {
    Command,
    /// A read the flow may perform. Creatable since hub#665: it is the third filter over the tools
    /// an agent step offers the model ("assembled ∩ declared by the step ∩ granted"), and without
    /// it that intersection would have nothing behind it for reads.
    Query,
    /// hub#821 — **one channel** a `notify` step may leave by (`email`, `whatsapp`). Separate from
    /// [`GrantKind::RecipientQuery`] on purpose: "may this flow spend WhatsApp messages" and "whose
    /// address may it reach" are two questions an owner answers separately, and a flow that may
    /// email its customers must not gain their phone the day somebody adds a second channel.
    Notify,
    /// hub#662 — one URL pattern, `https://host/path*`, matched against the URL the step really
    /// built (see [`Authority::allows_http`]).
    Http,
    /// hub#821 — `<query>#<field>`: the ONE field of the ONE read a `notify` step may take a
    /// recipient from. Customers live in a module's table, so this is the only way a flow ever
    /// reaches one — never an address out of the event payload.
    RecipientQuery,
}

impl GrantKind {
    pub fn as_str(self) -> &'static str {
        match self {
            GrantKind::Command => "command",
            GrantKind::Query => "query",
            GrantKind::Notify => "notify",
            GrantKind::Http => "http",
            GrantKind::RecipientQuery => "recipient_query",
        }
    }
    pub fn parse(s: &str) -> Option<Self> {
        Some(match s {
            "command" => GrantKind::Command,
            "query" => GrantKind::Query,
            "notify" => GrantKind::Notify,
            "http" => GrantKind::Http,
            "recipient_query" => GrantKind::RecipientQuery,
            _ => return None,
        })
    }
    /// Can this kind be created today? The list grew one issue at a time — `http` with hub#662,
    /// `query` with hub#665, and `notify`/`recipient_query` with hub#821 — because a grant for
    /// something the kernel cannot do would tell an owner their flow may message a customer when
    /// it cannot. With hub#821 the five of ADR-0283 §2 are all real.
    pub fn is_available(self) -> bool {
        true
    }
    pub const ALL: &'static [GrantKind] = &[
        GrantKind::Command,
        GrantKind::Query,
        GrantKind::Notify,
        GrantKind::Http,
        GrantKind::RecipientQuery,
    ];
}

/// One live grant, as the REST layer shows it.
#[derive(Debug, Clone, serde::Serialize)]
pub struct Grant {
    pub id: String,
    pub kind: String,
    pub value: String,
    /// hub#1623 — the payload fields this grant FIXES, `{}` when it fixes none. It is part of what
    /// the grant says, so it travels with it: a screen that showed «may cancel appointments» for a
    /// grant that really says «may cancel appointments as the customer» would describe a wider
    /// permission than the one that was given.
    pub payload: Json,
    pub granted_by: String,
    pub created_at: String,
}

/// One grant **as it is asked for** — the pair, plus the payload a `command` grant pins.
///
/// hub#1623: until this existed the unit of authorisation was the command NAME, so «may cancel
/// appointments» and «may cancel appointments as the customer» were the same grant. They are not.
/// A flow whose payload is written by a model reading a stranger's message needs the second one,
/// because the first one hands that stranger every argument the command takes.
///
/// The pin is an **allow-list of fixed values**, not a list of forbidden fields, and that choice is
/// the same one the rest of this file makes everywhere: a forbidden-field list authorises every
/// field nobody thought of, so the day a module adds an argument the grant silently widens. A fixed
/// value covers exactly what it says and nothing else, and it reads on the screen as the sentence
/// the owner meant.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GrantSpec {
    pub kind: GrantKind,
    pub value: String,
    /// Top-level payload fields this grant fixes. Empty = fixes nothing, which is every grant that
    /// existed before hub#1623 and every grant of a kind that carries no payload.
    pub payload: Params,
}

impl GrantSpec {
    /// A grant that pins nothing — the shape every kind other than `command` has, and the default
    /// for a `command` too.
    pub fn pair(kind: GrantKind, value: impl Into<String>) -> Self {
        Self {
            kind,
            value: value.into(),
            payload: Params::new(),
        }
    }

    /// A `command` grant that fixes part of the payload (hub#1623).
    pub fn pinned(command: impl Into<String>, payload: Params) -> Self {
        Self {
            kind: GrantKind::Command,
            value: command.into(),
            payload,
        }
    }

    /// A `query` grant that fixes part of its parameters (hub#1662) — «read the appointments **of
    /// this customer**», not «read the appointments».
    pub fn pinned_query(query: impl Into<String>, params: Params) -> Self {
        Self {
            kind: GrantKind::Query,
            value: query.into(),
            payload: params,
        }
    }
}

/// The kinds whose grant is ever handed values to judge, and therefore the only ones a pin can
/// restrict: a `command`'s payload (hub#1623) and a `query`'s parameters (hub#1662). A pin on any
/// other kind is refused rather than stored, the rule [`GrantKind::is_available`] applies to the
/// kinds themselves — never put a restriction on the screen that nothing applies.
impl GrantKind {
    pub fn can_pin(self) -> bool {
        matches!(self, GrantKind::Command | GrantKind::Query)
    }
}

/// The roots a pin may reference (hub#1662). The run scope the executor builds is
/// `{ input, steps }` and nothing else, so these two are all of it.
///
/// `secret.…` is absent on purpose and it is not an oversight: a gate that answered «granted» only
/// when a value equalled a secret would be an **oracle** — a model that can retry has a way to read
/// the secret one guess at a time. `event.…` is absent because the run scope does not carry it, so
/// such a pin could only ever deny: a permission that authorises nothing, which is exactly what
/// this file refuses to store.
const PIN_ROOTS: [&str; 2] = ["input", "steps"];

/// The live grants of one flow, read once. Everything the gate and the context need comes from
/// this snapshot, so a step asks the database once and then answers consistently for that step.
#[derive(Debug, Clone, Default)]
pub struct Authority {
    granted: HashSet<(GrantKind, String)>,
    /// hub#1623, widened by hub#1662 — the grant → the values it FIXES. Keyed by the whole pair and
    /// not by the name, because `command` and `query` are two vocabularies: a read and a write that
    /// happened to share a name must not be able to inherit each other's restriction. A pair absent
    /// from here pins nothing; it is NOT «denied», which is what `granted` answers.
    pins: HashMap<(GrantKind, String), Params>,
}

impl Authority {
    /// May this flow run this command RIGHT NOW? Default-deny: an unknown flow, a flow with no
    /// grants and a flow whose grant was revoked a second ago all answer the same.
    pub fn allows_command(&self, command: &str) -> bool {
        self.granted
            .contains(&(GrantKind::Command, command.to_string()))
    }

    /// The payload fields this flow's grant for `command` FIXES (hub#1623), or `None` when the
    /// grant pins nothing.
    ///
    /// Separate from [`Authority::allows_command`] deliberately: the pin narrows a grant that
    /// EXISTS, so a caller that forgets to ask this gets a command that is granted and unpinned —
    /// the pre-hub#1623 answer — and never a command that is denied. Which is why the enforcement
    /// does not live here but in [`check_command_grant`], the one door the dispatcher goes through.
    pub fn command_pin(&self, command: &str) -> Option<&Params> {
        self.pin(GrantKind::Command, command)
    }

    /// The parameters this flow's grant for `query` FIXES (hub#1662), or `None` when it pins none.
    ///
    /// Same separation as [`Authority::command_pin`], and for the same reason: the pin narrows a
    /// grant that EXISTS, so a caller that forgets to ask gets the pre-hub#1662 answer — granted and
    /// unpinned — and never a read that is denied. The enforcement lives in [`check_query_grant`],
    /// the one door `Runtime::execute_flow_query` and `execute_flow_query_page` both go through.
    pub fn query_pin(&self, query: &str) -> Option<&Params> {
        self.pin(GrantKind::Query, query)
    }

    fn pin(&self, kind: GrantKind, value: &str) -> Option<&Params> {
        self.pins
            .get(&(kind, value.to_string()))
            .filter(|p| !p.is_empty())
    }

    /// May this flow run this query RIGHT NOW? Same default-deny, same freshness. A read is not
    /// harmless just because it writes nothing: an agent step's whole job is to put what it reads
    /// in front of a model, and a hub's tables hold its customers.
    pub fn allows_query(&self, query: &str) -> bool {
        self.granted
            .contains(&(GrantKind::Query, query.to_string()))
    }

    /// The permissions a run carries in its [`crate::registry::RequestContext`]: **only** the
    /// `permission` of the commands this flow was granted.
    ///
    /// It is NOT what opens the gate — that is [`Authority::allows_command`], which names the
    /// COMMAND, not a permission, so being granted `crm.note.add` never opens its neighbour just
    /// because they share a permission. What this list is for is everything downstream that still
    /// asks a context what it may do: a handler's preloaded `reads`, a nested command resolved
    /// through `validate_operation`.
    ///
    /// The original design (ADR-0283 §2) justified this union with the CASCADES — «so that a flow
    /// creating a sale does not have its invoice listener die in dead-letter». That reason was a
    /// **bug**, not a requirement, and it is gone: since ADR-0288 (hub#686) a listener runs with
    /// the authority of its OWN module instead of the reconstructed permissions of whoever emitted
    /// the event. So a flow's context no longer has to carry other modules' listeners on its back;
    /// it carries exactly what it was granted, which is what the decision wanted all along.
    pub fn permissions(&self, registry: &Registry) -> HashSet<String> {
        self.granted
            .iter()
            .filter_map(|(kind, name)| match kind {
                GrantKind::Command => registry.get_command(name).map(|c| c.def.permission.clone()),
                // The granted READS have to be here too, or a query with a live grant would pass
                // the flow's gate and then be refused by the permission check inside
                // `queries::execute`: the grant would open one door and the next one would be shut.
                GrantKind::Query => registry.get_query(name).map(|q| q.def.permission.clone()),
                // Same reason for the read behind a `recipient_query` (hub#821): the `notify` step
                // runs it through the very same `queries::execute`. It does NOT make that query a
                // tool an `ai` step may call — that is [`Authority::allows_query`], and it stays
                // false here: the grant authorises taking ONE field out of the row to address a
                // message, not handing the row to a model.
                GrantKind::RecipientQuery => split_recipient(name)
                    .and_then(|(query, _)| registry.get_query(query))
                    .map(|q| q.def.permission.clone()),
                _ => None,
            })
            .filter(|p| !p.is_empty() && p != "*")
            .collect()
    }

    /// May this flow call this URL RIGHT NOW? (hub#662)
    ///
    /// The caller passes the URL **as it will really be requested** — templates rendered, secrets
    /// substituted, and **already parsed** ([`flows::net::parse`](crate::flows::net::parse)).
    /// Matching the un-templated form would authorise `https://api.example.com/{{input.path}}` and
    /// then call whatever the event carried; matching the un-parsed form was hub#729 — the string
    /// `…/anything/../status/418` starts with `/anything`, and the request goes to `/status/418`.
    ///
    /// It takes a [`Url`] and not a `&str` on purpose: a caller cannot reach this gate without
    /// having produced the very object the request will be built from.
    pub fn allows_http(&self, url: &Url) -> bool {
        self.granted
            .iter()
            .filter(|(kind, _)| *kind == GrantKind::Http)
            .any(|(_, pattern)| url_matches(pattern, url))
    }

    /// May this flow send by this channel RIGHT NOW? (hub#821)
    ///
    /// Per channel and not per "may notify", because the channels do not cost the same: a WhatsApp
    /// message is metered and billed through Meta, an email is not. An owner who allows the
    /// reminder by email has not agreed to pay for it by WhatsApp.
    pub fn allows_notify(&self, channel: Channel) -> bool {
        self.granted
            .contains(&(GrantKind::Notify, channel.as_str().to_string()))
    }

    /// May this flow take a recipient from THIS field of THIS query RIGHT NOW? (hub#821)
    ///
    /// The pair is compared whole. A grant over `crm.customer.get#phone` is not a grant over the
    /// same customer's email, nor over the phone in a query that returns the whole address book:
    /// what a recipient grant contains is one column of one declared read, and everything else is
    /// the same default answer as always.
    pub fn allows_recipient(&self, query: &str, field: &str) -> bool {
        self.granted
            .contains(&(GrantKind::RecipientQuery, recipient_value(query, field)))
    }

    pub fn is_empty(&self) -> bool {
        self.granted.is_empty()
    }
}

/// One `http` grant, taken apart with **the same parser that will take apart the URL it judges**
/// ([`net::parse`]). That identity is the fix for hub#729: before it, the pattern was split by
/// hand and compared against raw text, so `…/anything/../status/418` «started with» `/anything`
/// and was fetched from `/status/418`.
struct HttpPattern {
    /// `scheme://host[:port]`, normalised — compared **whole**.
    origin: String,
    /// Path + query + fragment, with dot segments resolved — compared by **prefix**.
    prefix: String,
    /// Was there a trailing `*`?
    wildcard: bool,
}

impl HttpPattern {
    /// `None` when the pattern is not «one scheme, one host, one path prefix». The reasons are
    /// spelled out one by one in [`check_http_pattern`], which is what an admin reads; here an
    /// unusable pattern simply covers nothing, so a row that somehow got stored is default-deny
    /// rather than a wildcard.
    fn parse(pattern: &str) -> Option<Self> {
        let (head, wildcard) = match pattern.strip_suffix('*') {
            Some(head) => (head, true),
            None => (pattern, false),
        };
        // A grant must name a path: `https://host` on its own reads like containment of the host
        // and would silently become «the root document», which is not what anybody means.
        if !head.split_once("//")?.1.contains(['/', '?', '#']) {
            return None;
        }
        let url = net::parse(head).ok()?;
        Some(Self {
            origin: net::origin_of(&url).to_string(),
            prefix: net::tail_of(&url).to_string(),
            wildcard,
        })
    }

    /// The pattern as it will really be matched. When this is not what was typed, the grant does
    /// not read as what it covers — see [`check_http_pattern`].
    fn canonical(&self) -> String {
        format!(
            "{}{}{}",
            self.origin,
            self.prefix,
            if self.wildcard { "*" } else { "" }
        )
    }

    /// **The origin is compared whole and the path only by prefix.** That asymmetry is the whole
    /// security of the allow-list: a plain `starts_with` over the entire URL would let
    /// `https://api.example.com.evil.test/…` through a grant for `https://api.example.com/…`,
    /// which is the oldest allow-list escape there is.
    ///
    /// A trailing `*` extends the match to anything below the prefix; without it the path must be
    /// exactly the one granted. `*` anywhere else is not a wildcard — it is a literal, because
    /// `https://*.example.com` reads like containment and is not (nothing stops
    /// `a.b.evil.example.com` from being somebody else's server).
    fn covers(&self, url: &Url) -> bool {
        if self.origin != net::origin_of(url) {
            return false;
        }
        let tail = net::tail_of(url);
        if self.wildcard {
            tail.starts_with(&self.prefix)
        } else {
            tail == self.prefix
        }
    }
}

/// Does `url` fall under `pattern`? Both sides normalised, by construction.
fn url_matches(pattern: &str, url: &Url) -> bool {
    HttpPattern::parse(pattern).is_some_and(|p| p.covers(url))
}

/// Refuses a pattern that is not «one scheme, one host, one path prefix» — the only shape the
/// matcher can enforce. Everything else (`*`, `https://*`, a bare host) reads as containment on the
/// grants screen while covering more than the owner believes, and a grant nobody can read
/// correctly is worse than no grant at all.
///
/// hub#728 added the last of the refusals, and it is the same invariant as everywhere else in this
/// file: **the pattern has to be written the way it will be matched.** `http://2130706433/api*` IS
/// `http://127.0.0.1/api*` and `http://2852039166/latest*` IS the cloud metadata service; a
/// pattern spelled like that authorises something nobody reading the grants screen would recognise.
/// It is refused with its canonical form in the message, so an admin who really wants it writes it
/// down in the notation everybody can read — and then the ADDRESS guard, not the allow-list, is
/// what refuses to dial it. Those stay two separate questions on purpose: an admin may grant a LAN
/// address by mistake, and the answer is still no at call time.
fn check_http_pattern(pattern: &str) -> Result<()> {
    let refuse = |why: String| {
        Err(RuntimeError::Domain {
            code: ERR_INVALID_HTTP_PATTERN.to_string(),
            message: format!(
                "`{pattern}` is not a usable http grant: {why}. The shape is \
                 `https://host/path` or `https://host/path*`."
            ),
        })
    };
    let head = pattern.strip_suffix('*').unwrap_or(pattern);
    let url = match net::parse(head) {
        Ok(url) => url,
        Err(why) => return refuse(why),
    };
    if url.host_str().unwrap_or_default().contains('*') {
        return refuse("the host cannot contain a wildcard".to_string());
    }
    let Some(parsed) = HttpPattern::parse(pattern) else {
        return refuse(
            "it must name a path (use `/*` to mean the whole host, deliberately)".to_string(),
        );
    };
    if parsed.prefix.contains('*') {
        return refuse("`*` is only a wildcard at the very end".to_string());
    }
    let canonical = parsed.canonical();
    if canonical != pattern {
        return refuse(format!(
            "it is not written the way it will be matched — it means `{canonical}`, and a grant \
             has to read as what it covers"
        ));
    }
    Ok(())
}

/// `<query>#<field>` taken apart, or `None` when it is not that shape.
fn split_recipient(value: &str) -> Option<(&str, &str)> {
    let (query, field) = value.split_once('#')?;
    if query.is_empty() || field.is_empty() || field.contains('#') {
        return None;
    }
    Some((query, field))
}

/// How a `recipient_query` grant is written down. One function so the value that is STORED, the
/// value that is MATCHED and the value shown on the grants screen cannot drift apart.
pub fn recipient_value(query: &str, field: &str) -> String {
    format!("{query}#{field}")
}

/// Refuses a `notify` grant that does not name one channel this hub can actually send on.
///
/// `sms` is refused by name: ADR-0012 lists it, and neither the SaaS proxy nor the hub has a
/// transport for it. A grant for it would read as permission on the screen and turn into eight
/// retries and a dead-letter the first night the flow ran.
fn check_notify_channel(value: &str) -> Result<()> {
    let refuse = |why: String| {
        Err(RuntimeError::Domain {
            code: ERR_INVALID_NOTIFY_GRANT.to_string(),
            message: format!("`{value}` is not a usable notify grant: {why}."),
        })
    };
    match Channel::parse(value.trim()) {
        Some(channel) if channel.is_deliverable() => Ok(()),
        Some(channel) => refuse(format!(
            "this hub has no transport for `{}` — the SaaS proxies email and whatsapp, and the hub \
             holds no provider credential of its own",
            channel.as_str()
        )),
        None => refuse(format!(
            "a notify grant names ONE channel, one of {}",
            Channel::DELIVERABLE
                .iter()
                .map(|c| c.as_str())
                .collect::<Vec<_>>()
                .join(", ")
        )),
    }
}

/// **Refuses a command that `Origin::Automation` can never invoke** (hub#824).
///
/// An internal command (`_` on the last segment, or `internal: true` — [`CommandDef::is_internal`])
/// is barred to automation exactly as it is to an external caller: it is the half of a module that
/// exists so the public command decides when it runs (flows.md §2, and the gate in
/// `commands::execute_at`). Before this, only that gate asked — three seconds too late, with the run
/// already `failed` and the grants screen still saying «granted».
///
/// **An unknown command is NOT this function's business.** It answers one question, and each door
/// decides what «not in the registry» means for it: a GRANT refuses it (a grant naming nothing reads
/// as authorisation), while a DOCUMENT may legitimately name a module that is not installed yet —
/// a blueprint lands its flows and its modules in whatever order.
///
/// One function on purpose: the grants door and the save door must refuse the same names with the
/// same code, or one of them becomes the lenient one.
pub fn refuse_internal_command(registry: &Registry, command: &str) -> Result<()> {
    match registry.get_command(command) {
        Some(cmd) if cmd.def.is_internal(command) => Err(RuntimeError::Domain {
            code: ERR_INTERNAL_COMMAND.to_string(),
            message: format!(
                "`{command}` is an INTERNAL command: only the runtime itself invokes it, so an \
                 automation could never run it. Refused here rather than accepted and denied at \
                 execution — a permission nobody enforces reads as one that was granted. Name the \
                 public command that orchestrates it instead."
            ),
        }),
        _ => Ok(()),
    }
}

/// Refuses a `recipient_query` grant that is not «one field of one declared read».
///
/// The query has to exist, for the same reason a `command` grant's does: a grant naming nothing
/// reads as authorisation on the screen. And the field has to be a plain column name — a path like
/// `customer.phone` would look like it walks into the row and does not (the recipient is taken from
/// the row's own column), so it is refused instead of silently resolving to nothing at 3 AM.
fn check_recipient_pattern(registry: &Registry, value: &str) -> Result<()> {
    let refuse = |why: String| {
        Err(RuntimeError::Domain {
            code: ERR_INVALID_RECIPIENT_GRANT.to_string(),
            message: format!(
                "`{value}` is not a usable recipient grant: {why}. The shape is `<query>#<field>` \
                 (e.g. `crm.customer.get#phone`)."
            ),
        })
    };
    let Some((query, field)) = split_recipient(value) else {
        return refuse("it must name a query and a field, separated by `#`".to_string());
    };
    if registry.get_query(query).is_none() {
        return Err(RuntimeError::QueryNotFound(query.to_string()));
    }
    if !field.chars().all(|c| c.is_ascii_alphanumeric() || c == '_')
        || field.chars().next().is_some_and(|c| c.is_ascii_digit())
    {
        return refuse(format!(
            "`{field}` is not a column name; the recipient is ONE column of the row the query \
             returns"
        ));
    }
    Ok(())
}

/// Is this a value a pin may FIX? (hub#1662)
///
/// A pin holds a literal or a **reference to this run** — `input.…`, `steps.…`. Everything else is
/// refused at save rather than stored, the rule this whole function follows: never keep a
/// restriction nothing can enforce, because on the screen it reads as containment.
///
/// - `secret.…` would make the gate an **oracle**: «granted» exactly when a value equals the
///   secret, and a caller that can retry reads it one guess at a time.
/// - `event.…` names something the run scope does not carry ([`run_scope`] builds `{input, steps}`),
///   so it could only ever deny — a permission that authorises nothing.
/// - `{{…}}` prose is refused because a pin is a VALUE, not a sentence: rendering it would flatten
///   a number to a string and, worse, an unresolved template renders EMPTY, so the pin would
///   quietly stop matching anything and the containment would read as working while it denied
///   everything.
fn check_pin_value(kind: &GrantKind, name: &str, field: &str, written: &Json) -> Result<()> {
    let refuse = |why: String| -> Result<()> {
        Err(RuntimeError::Domain {
            code: ERR_INVALID_GRANT_PAYLOAD.to_string(),
            message: format!(
                "the `{}` grant for `{name}` fixes `{field}` to something it cannot be: {why}",
                kind.as_str()
            ),
        })
    };
    let Some(text) = written.as_str() else {
        return Ok(()); // a number, a bool, a structure: a literal, compared as it stands
    };
    if text.contains("{{") {
        return refuse(
            "a pin is a value, not text with templates in it; name the path on its own \
             (`steps.<step>.<field>`) so its type survives"
                .to_string(),
        );
    }
    if def::is_path(text) && !PIN_ROOTS.contains(&text.split('.').next().unwrap_or_default()) {
        return refuse(format!(
            "`{text}` is not something this run carries; a pin may name {} and nothing else",
            PIN_ROOTS
                .iter()
                .map(|r| format!("`{r}.…`"))
                .collect::<Vec<_>>()
                .join(" or ")
        ));
    }
    Ok(())
}

/// Reads the live grants of a flow. One query, and the caller decides what to ask of the result.
pub async fn authority(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Authority> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    let res = db
        .query(
            // `id` travels because of what happens when a row cannot be read: the report has to
            // name the row an owner must revoke and grant again, and «one of this flow's grants»
            // is not something anybody can act on.
            "SELECT id, kind, value, payload FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let mut granted = HashSet::new();
    let mut pins: HashMap<(GrantKind, String), Params> = HashMap::new();
    for r in &res.rows {
        let Some(kind) = GrantKind::parse(r["kind"].as_str().unwrap_or_default()) else {
            continue;
        };
        let value = r["value"].as_str().unwrap_or_default().to_string();
        // A pin only means something for a kind that CARRIES one, and only when it parses
        // (hub#1623 for a `command`, hub#1662 for a `query`). What a row holding garbage in
        // `payload` means is hub#1636: **nothing**. It used to pin nothing and still be granted, so
        // an unreadable RESTRICTION became a wider AUTHORISATION — the one direction a permission
        // may never move on its own, and the opposite of the rule the gate reads by ("the safe
        // reading of a bug on an authorisation path is deny").
        //
        // So the row is dropped: default-deny by absence, exactly as the header of this file
        // states. Only for a kind that can be pinned — `replace` refuses a payload on every other
        // one, so denying a `notify` over a column nothing consults would stop a flow for no gain
        // in containment. hub#1662 moved `query` from that second group into the first: a read now
        // carries a pin, so an unreadable one closes the read exactly as it closes a write.
        //
        // Nothing reachable produces this state (the column is `NOT NULL DEFAULT '{}'`, `replace`
        // serialises an object and `parse_pairs` refuses anything else), which is precisely why it
        // is REPORTED and not only refused: an owner whose automation stopped at 3 AM has no other
        // thread back to a row their permissions screen still shows as granted.
        if kind.can_pin() {
            match parse_pin(&r["payload"]) {
                Some(pin) => {
                    if !pin.is_empty() {
                        pins.insert((kind, value.clone()), pin);
                    }
                }
                None => {
                    let id = r["id"].as_str().unwrap_or_default();
                    let event = unreadable_pin_event(id, flow_id, &value);
                    eprintln!("✗ {}", event.message);
                    crate::error_registry::ErrorRegistry::global().report(event);
                    continue;
                }
            }
        }
        granted.insert((kind, value));
    }
    Ok(Authority { granted, pins })
}

/// hub#1636 — the stable code of «a grant row holds a pin nobody can read». Not a `flow.…` refusal
/// code: nothing is being said to the caller here (the caller is told [`ERR_GRANT_DENIED`], which is
/// the truth from where it stands). This is the code the ALERT and the support filter are programmed
/// against, in the `error_registry` namespace the rest of the hub's reports use.
pub const ERR_UNREADABLE_GRANT_PAYLOAD_EVENT: &str = "flow_grant_payload_unreadable";

/// The report of a grant whose stored pin cannot be read.
///
/// Separate from the place that sends it so a test can pin its CONTENT — the stable code and the row
/// it names — instead of pinning that a global sink was called (`failed_install_event`, hub#1477).
/// And it is a report and not only a log for the reason that issue wrote down: a log inside a
/// container is read by nobody, and this one is the only thread connecting «the automation stopped»
/// to «this row has to be granted again».
fn unreadable_pin_event(
    grant_id: &str,
    flow_id: &str,
    command: &str,
) -> crate::error_registry::ErrorEvent {
    use crate::error_registry::{severity, source, ErrorEvent};

    ErrorEvent::new(
        source::HUB,
        ERR_UNREADABLE_GRANT_PAYLOAD_EVENT,
        format!(
            "the grant `{grant_id}` of flow `{flow_id}` for command `{command}` holds a `payload` \
             that is not a readable JSON object; it authorises NOTHING until it is revoked and \
             granted again"
        ),
        severity::UNEXPECTED,
    )
    .with_context(serde_json::json!({
        "grant_id": grant_id,
        "flow_id": flow_id,
        "command": command,
    }))
}

/// The stored `payload` column back into the map the gate compares against. Stored as TEXT holding
/// a JSON object (the `_flow_approvals.payload` convention), so both the string and the already
/// decoded object are accepted — SQLite and Postgres do not agree on which one a driver hands back.
fn parse_pin(raw: &Json) -> Option<Params> {
    match raw {
        Json::Object(map) => Some(map.clone()),
        Json::String(text) => serde_json::from_str::<Json>(text)
            .ok()
            .and_then(|v| v.as_object().cloned()),
        _ => None,
    }
}

/// The reference this pin value names, if it names one (hub#1662).
///
/// A pin value is a **bare path** (`steps.resolve_customer.id`) or a **literal** — never prose with
/// `{{…}}` in it. [`def::is_path`] is what tells them apart, and it is the very function the mapping
/// language uses, so a grant reads like the flow document an owner already knows. A literal like
/// `"customer"` is not rooted at `input`/`steps`/`event`/`secret`, so every pin written before this
/// existed keeps comparing byte for byte.
fn pin_reference(value: &Json) -> Option<&str> {
    value.as_str().filter(|s| def::is_path(s))
}

/// The run's own facts, in the shape the mapping language addresses them: `{ input, steps }` — the
/// same object [`crate::flows::executor`] builds for a step's `params`.
///
/// Read **fresh**, at the instant of the gate, like the grants themselves: the pin is judged against
/// what this run has actually resolved, not against a snapshot somebody took earlier.
async fn run_scope(db: &dyn DatabaseAdapter, hub_id: &str, run_id: &str) -> Result<Json> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT input, vars FROM _flow_runs \
             WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    // No run, no scope, no read. A gate that shrugged here would resolve every reference to
    // nothing, and «nothing» must never read as «no restriction» (hub#1636).
    let Some(row) = res.rows.first() else {
        return Err(RuntimeError::Domain {
            code: ERR_GRANT_PAYLOAD_DENIED.to_string(),
            message: format!(
                "the grant fixes values against run `{run_id}`, and that run cannot be read; \
                 refused (ADR-0283 §2)."
            ),
        });
    };
    // SQLite and Postgres do not agree on whether a JSON column comes back decoded or as text, the
    // same split `parse_pin` handles two functions up.
    let parse = |v: &Json| -> Json {
        match v {
            Json::Object(_) => v.clone(),
            Json::String(text) => serde_json::from_str(text).unwrap_or(Json::Null),
            _ => Json::Null,
        }
    };
    let vars = parse(&row["vars"]);
    Ok(json!({
        "input": parse(&row["input"]),
        "steps": vars.get("steps").cloned().unwrap_or_else(|| json!({})),
    }))
}

/// The pin with its references resolved against this run (hub#1662).
///
/// **A reference that resolves to nothing is a refusal, never a free pass.** Renaming the step that
/// resolves the customer, or reaching the read before that step ran, would otherwise turn a pinned
/// grant back into the wide one — «edit the flow» as the way round a permission the owner gave.
/// Same direction hub#1636 chose for an unreadable pin, and for the same reason.
fn resolve_pin(
    flow_id: &str,
    noun: &str,
    name: &str,
    pin: &Params,
    scope: &Json,
) -> Result<Params> {
    let mut out = Params::new();
    for (field, written) in pin {
        let value = match pin_reference(written) {
            None => written.clone(),
            Some(path) => def::resolve_path(path, scope)
                .filter(|v| !v.is_null())
                .ok_or_else(|| RuntimeError::Domain {
                    code: ERR_GRANT_PAYLOAD_DENIED.to_string(),
                    message: format!(
                        "flow `{flow_id}` may run {noun} `{name}` only with `{field}` = \
                         `{path}`, and this run has no value there. A grant that cannot be \
                         resolved authorises nothing (ADR-0283 §2)."
                    ),
                })?,
        };
        out.insert(field.clone(), value);
    }
    Ok(out)
}

/// Does this call honour what the grant FIXED? (hub#1623 for a write, hub#1662 for a read)
///
/// Every pinned field must be **present and equal**. Absence is a refusal and not a pass, because
/// the field the pin names is exactly the one whose default the caller must not get to choose: a
/// grant that said «as the customer» and let an omitted `channel` through would be bypassed by
/// leaving it out, which is easier than contradicting it.
///
/// Fields the pin does NOT name are free. The pin narrows a grant; it is not a schema, and the
/// operation's own schema is still the thing that decides whether the rest is valid.
///
/// `written` is what the GRANT says and `resolved` is what it came to in this run; the refusal
/// quotes the first. An owner reads «only with `customer_id` = `steps.resolve_customer.id`», which
/// is the sentence they authorised — and neither the resolved value nor the one that was sent
/// reaches the message, because both are somebody's data and an error string travels much further
/// than this gate does.
fn check_payload_pin(
    flow_id: &str,
    noun: &str,
    name: &str,
    written: &Params,
    resolved: &Params,
    payload: &Params,
) -> Result<()> {
    for (field, fixed) in resolved {
        let sent = payload.get(field);
        if sent == Some(fixed) {
            continue;
        }
        let says = written.get(field).unwrap_or(fixed);
        return Err(RuntimeError::Domain {
            code: ERR_GRANT_PAYLOAD_DENIED.to_string(),
            message: format!(
                "flow `{flow_id}` may run {noun} `{name}` only with `{field}` = {says}, and this \
                 call {}. A grant fixes what it fixes; the call does not get to argue with it \
                 (ADR-0283 §2).",
                match sent {
                    Some(_) => "sent another value",
                    None => "omitted it",
                }
            ),
        });
    }
    Ok(())
}

/// The pin of `name` and what it resolves to in this run — or `None` when the grant pins nothing.
///
/// The run is read **only when a pin really names one** ([`pin_reference`]), so the overwhelmingly
/// common gate — a grant with no pin, or one that fixes a literal — still costs exactly the one
/// query it always did.
async fn resolved_pin(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    noun: &str,
    name: &str,
    pin: Option<&Params>,
) -> Result<Option<(Params, Params)>> {
    let Some(pin) = pin else { return Ok(None) };
    let scope = if pin.values().any(|v| pin_reference(v).is_some()) {
        run_scope(db, hub_id, run_id).await?
    } else {
        Json::Null
    };
    let resolved = resolve_pin(flow_id, noun, name, pin, &scope)?;
    Ok(Some((pin.clone(), resolved)))
}

/// **The gate**, as the dispatcher calls it (`commands::execute_at` under
/// [`crate::commands::Origin::Automation`]). A fresh read on purpose: this is what makes a
/// revocation take effect at the next step of a running flow instead of at the next restart.
pub async fn check_command_grant(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    command: &str,
    payload: &Params,
) -> Result<()> {
    let authority = authority(db, hub_id, flow_id).await?;
    if authority.allows_command(command) {
        // hub#1623 — granted is only half the question when the grant FIXED part of the payload.
        // Asked HERE, in the same read, so a caller cannot get the name checked and skip the pin:
        // the dispatcher calls this one function and there is no second door.
        if let Some((written, resolved)) = resolved_pin(
            db,
            hub_id,
            flow_id,
            run_id,
            "command",
            command,
            authority.command_pin(command),
        )
        .await?
        {
            check_payload_pin(flow_id, "command", command, &written, &resolved, payload)?;
        }
        return Ok(());
    }
    Err(RuntimeError::Domain {
        code: ERR_GRANT_DENIED.to_string(),
        message: format!(
            "flow `{flow_id}` has no live grant for command `{command}`. A flow runs with its own \
             explicit grants (ADR-0283 D2), never with the role of whoever created it."
        ),
    })
}

/// The same gate for a READ (hub#665). It is the door `Runtime::execute_flow_query` goes through,
/// so a query the flow was not granted is refused by the runtime and not by the agent runner's
/// good manners — the runner is the caller, and a gate a caller can skip is not a gate.
pub async fn check_query_grant(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    query: &str,
    params: &Params,
) -> Result<()> {
    let authority = authority(db, hub_id, flow_id).await?;
    if authority.allows_query(query) {
        // hub#1662 — granted is «what», and on a read the other half is «WHOSE». The identity IS
        // the filter here: `customer_id` is not a field of what comes back, it is what decides what
        // comes back, so there is no row for a module to compare a caller against. Which is why the
        // pin is resolved in this door, in the same read as the name.
        if let Some((written, resolved)) = resolved_pin(
            db,
            hub_id,
            flow_id,
            run_id,
            "query",
            query,
            authority.query_pin(query),
        )
        .await?
        {
            check_payload_pin(flow_id, "query", query, &written, &resolved, params)?;
        }
        return Ok(());
    }
    Err(RuntimeError::Domain {
        code: ERR_GRANT_DENIED.to_string(),
        message: format!(
            "flow `{flow_id}` has no live grant for query `{query}`. A flow reads only what it was \
             explicitly granted (ADR-0283 D2)."
        ),
    })
}

/// The gate a `notify` step passes before anything is queued (hub#821): the CHANNEL and the
/// RECIPIENT are two grants, and both have to be live at this instant.
///
/// Returns the **id** of the recipient grant, which is what travels with the queued event as
/// `resolved_via` and is re-read at delivery ([`check_notify_release`]). Returning the id rather
/// than a bool is the point: the release the message carries names the very row that authorised it,
/// so revoking that row is what stops the message.
pub async fn check_notify_grants(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    authority: &Authority,
    channel: Channel,
    query: &str,
    field: &str,
) -> Result<String> {
    let deny = |what: String| RuntimeError::Domain {
        code: ERR_GRANT_DENIED.to_string(),
        message: format!(
            "flow `{flow_id}` has no live {what}. A flow messages the people an owner listed for \
             it, through the channel they allowed, and nothing else (ADR-0283 §5)."
        ),
    };
    if !authority.allows_notify(channel) {
        return Err(deny(format!(
            "`notify` grant for the channel `{}`",
            channel.as_str()
        )));
    }
    if !authority.allows_recipient(query, field) {
        return Err(deny(format!(
            "`recipient_query` grant for `{}`",
            recipient_value(query, field)
        )));
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("value".into(), json!(recipient_value(query, field)));
    p.insert("kind".into(), json!(GrantKind::RecipientQuery.as_str()));
    let res = db
        .query(
            "SELECT id FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND kind = :kind AND value = :value \
               AND deleted_at IS NULL",
            &p,
        )
        .await?;
    res.rows
        .first()
        .and_then(|r| r["id"].as_str().map(|s| s.to_string()))
        .ok_or_else(|| {
            deny(format!(
                "`recipient_query` grant for `{}`",
                recipient_value(query, field)
            ))
        })
}

/// **The release, re-read at delivery** (hub#821) — the property the whole design turns on.
///
/// A queued message is durable: it survives a restart, it is retried with backoff, and a `delay`
/// step can put hours between the decision and the send. If the grants were only checked when the
/// event was built, revoking one would stop the NEXT message and let the one already in the queue
/// through — and «I revoked it» has to mean the message does not go.
///
/// So the outbox asks again, here, with the row in front of it: the run still exists, the grant it
/// names is still alive and still belongs to that run's flow, and the channel is still allowed.
/// Any of those gone and the send is refused — the row is not marked delivered, it retries and it
/// ends in the dead-letter, visibly, instead of quietly going out.
pub async fn check_notify_release(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    run_id: &str,
    resolved_via: &str,
    channel: Channel,
) -> Result<()> {
    let refuse = |why: String| {
        Err(RuntimeError::Notify(format!(
            "el destinatario lo autorizó un flujo (`{resolved_via}`) y esa autorización ya no vale: \
             {why} → no se envía"
        )))
    };
    let Some(grant_id) = resolved_via.strip_prefix(FLOW_GRANT_PREFIX) else {
        return refuse("no nombra un grant de flujo".to_string());
    };

    // The flow is read from the RUN, never from the payload: `run_id` is stamped by the runtime
    // from the automation context (hub#666) and a module cannot put one there.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("run_id".into(), json!(run_id));
    let res = db
        .query(
            "SELECT flow_id FROM _flow_runs WHERE id = :run_id AND hub_id = :hub_id \
               AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let Some(flow_id) = res
        .rows
        .first()
        .and_then(|r| r["flow_id"].as_str().map(|s| s.to_string()))
    else {
        return refuse("el run que la pidió ya no existe".to_string());
    };

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("id".into(), json!(grant_id));
    p.insert("kind".into(), json!(GrantKind::RecipientQuery.as_str()));
    let res = db
        .query(
            "SELECT value FROM _flow_grants \
             WHERE id = :id AND hub_id = :hub_id AND flow_id = :flow_id AND kind = :kind \
               AND deleted_at IS NULL",
            &p,
        )
        .await?;
    if res.rows.is_empty() {
        return refuse(format!(
            "el grant `recipient_query` del flujo `{flow_id}` fue REVOCADO"
        ));
    }
    if !authority(db, hub_id, &flow_id)
        .await?
        .allows_notify(channel)
    {
        return refuse(format!(
            "el flujo `{flow_id}` ya no tiene grant `notify` para el canal `{}`",
            channel.as_str()
        ));
    }
    Ok(())
}

/// Replaces the whole grant list of a flow (the `PUT …/grants` contract): what disappears is
/// **revoked** (soft-delete + `revoked_by`), what stays is left alone with its original
/// `granted_by`, and what is new is inserted.
///
/// A replace and not a patch because the question an owner answers is "what may this flow do?",
/// and that is a list they see whole. Re-granting something already live is a no-op rather than a
/// conflict — otherwise saving the same screen twice would fail on the unique index.
pub async fn replace(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    registry: &Registry,
    wanted: &[GrantSpec],
    granted_by: &str,
) -> Result<()> {
    for GrantSpec {
        kind,
        value,
        payload,
    } in wanted
    {
        // The five kinds of ADR-0283 §2 are all real since hub#821, so nothing lands here any
        // more. The guard stays because the rule it enforces is the one that got them here one at a
        // time: a grant is stored only when something enforces it.
        if !kind.is_available() {
            return Err(RuntimeError::Domain {
                code: ERR_GRANT_KIND_NOT_AVAILABLE.to_string(),
                message: format!(
                    "grants of kind `{}` cannot be created yet. Refused rather than stored as a \
                     permission nothing enforces.",
                    kind.as_str()
                ),
            });
        }
        // A grant naming an operation that does not exist is a promise about nothing — and, worse,
        // it reads as authorisation on the screen. `PUT …/grants` refuses the whole list (§9).
        if *kind == GrantKind::Command {
            if registry.get_command(value).is_none() {
                return Err(RuntimeError::CommandNotFound(value.clone()));
            }
            // hub#824: existing is not enough. An internal command exists AND is unreachable, which
            // is the worst combination for a screen — it looks granted and it is denied at 3 AM.
            refuse_internal_command(registry, value)?;
        }
        if *kind == GrantKind::Query && registry.get_query(value).is_none() {
            return Err(RuntimeError::QueryNotFound(value.clone()));
        }
        if *kind == GrantKind::Http {
            check_http_pattern(value)?;
        }
        if *kind == GrantKind::Notify {
            check_notify_channel(value)?;
        }
        if *kind == GrantKind::RecipientQuery {
            check_recipient_pattern(registry, value)?;
        }
        // hub#1623, widened by hub#1662 — a pin is only enforced where a gate is handed values to
        // judge: `check_command_grant` (a payload) and `check_query_grant` (the parameters).
        // Storing one anywhere else would put a restriction on the screen that nothing applies,
        // which is the exact failure `is_available` exists to prevent one kind at a time.
        if !payload.is_empty() {
            if !kind.can_pin() {
                return Err(RuntimeError::Domain {
                    code: ERR_INVALID_GRANT_PAYLOAD.to_string(),
                    message: format!(
                        "only a `command` or a `query` grant can fix values; a `{}` grant is \
                         handed none, so the fixed fields would restrict nothing.",
                        kind.as_str()
                    ),
                });
            }
            for (field, written) in payload {
                check_pin_value(kind, value, field, written)?;
            }
        }
    }

    let live = list(db, hub_id, flow_id).await?;
    let now = now_rfc3339();

    for grant in &live {
        // hub#1623 — the PIN is part of the grant, so a grant whose pin changed is not «still
        // wanted»: it is revoked and re-granted below. That is the honest audit trail (the old
        // authorisation ended, with its `revoked_by` and its timestamp) and it is also the only
        // safe order — silently keeping the row would leave the OLD pin enforcing while the screen
        // showed the new one, and widening a grant is what this whole feature exists to stop.
        let still_wanted = wanted.iter().any(|w| {
            w.kind.as_str() == grant.kind && w.value == grant.value && pin_of(grant) == w.payload
        });
        if !still_wanted {
            let (sql, p) = revoke_op(hub_id, &grant.id, &now, granted_by);
            db.execute(&sql, &p).await?;
        }
    }

    for spec in wanted {
        if live.iter().any(|g| {
            g.kind == spec.kind.as_str() && g.value == spec.value && pin_of(g) == spec.payload
        }) {
            continue; // already live, pin included: keep the original `granted_by`/`created_at`.
        }
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("kind".into(), json!(spec.kind.as_str()));
        p.insert("value".into(), json!(spec.value));
        // TEXT holding a JSON object, the `_flow_approvals.payload` convention. `{}` for a grant
        // that fixes nothing, so the column is never NULL and every reader has one shape to handle.
        p.insert(
            "payload".into(),
            json!(Json::Object(spec.payload.clone()).to_string()),
        );
        p.insert("now".into(), json!(now));
        p.insert("by".into(), json!(granted_by));
        db.execute(
            "INSERT INTO _flow_grants \
               (id, hub_id, flow_id, kind, value, payload, created_at, granted_by) \
             VALUES (:id, :hub_id, :flow_id, :kind, :value, :payload, :now, :by)",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// The pin of a stored grant, in the shape `GrantSpec::payload` has, so the two can be compared.
fn pin_of(grant: &Grant) -> Params {
    grant.payload.as_object().cloned().unwrap_or_default()
}

/// The `UPDATE` that revokes ONE grant, as a statement a caller can execute or put in its own
/// transaction — the shape the rest of the kernel uses for a write it wants to be able to reason
/// about (`write_step_op`, `advance_index_op`, `delivery_op`).
///
/// Two clauses beyond the id, and neither is decoration (hub#735):
///
/// - **`hub_id`** — the id came from a hub-scoped read, but the read and the write are two
///   statements. The twelfth caller is the one that forgets, and this is the file where a
///   forgotten scope revokes somebody else's authorisation.
/// - **`deleted_at IS NULL`** — revocation is a FACT WITH A TIMESTAMP, and re-revoking must not
///   move it. `replace` reads the live grants and then writes; between those two, `revoke_all`
///   (which `delete` calls) can land. Without this clause the later write overwrites `deleted_at`
///   and `revoked_by`, and what the header of this file promises — «who could do what, and until
///   when» — becomes «until whenever somebody last pressed save».
fn revoke_op(hub_id: &str, grant_id: &str, now: &str, revoked_by: &str) -> (String, Params) {
    let mut p = Params::new();
    p.insert("id".into(), json!(grant_id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("now".into(), json!(now));
    p.insert("by".into(), json!(revoked_by));
    (
        "UPDATE _flow_grants SET deleted_at = :now, revoked_by = :by \
         WHERE id = :id AND hub_id = :hub_id AND deleted_at IS NULL"
            .to_string(),
        p,
    )
}

/// Live grants of a flow, oldest first.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Vec<Grant>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    let res = db
        .query(
            "SELECT id, kind, value, payload, granted_by, created_at FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL \
             ORDER BY created_at, id",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(grant_row).collect())
}

/// Revokes every grant of a flow (used when the flow itself is deleted): the flow stops being
/// able to act the moment it stops existing, without waiting for anything to notice.
pub async fn revoke_all(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    revoked_by: &str,
) -> Result<()> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("by".into(), json!(revoked_by));
    db.execute(
        "UPDATE _flow_grants SET deleted_at = :now, revoked_by = :by \
         WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
        &p,
    )
    .await?;
    Ok(())
}

fn grant_row(row: &Json) -> Grant {
    let text = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    Grant {
        id: text("id"),
        kind: text("kind"),
        value: text("value"),
        // hub#1623 — as an OBJECT, never the raw TEXT: a screen that got `"{\"channel\":…}"` as a
        // string would print the quotes, and the grants screen is the one place this has to read
        // like the sentence it is.
        payload: Json::Object(parse_pin(&row["payload"]).unwrap_or_default()),
        granted_by: text("granted_by"),
        created_at: text("created_at"),
    }
}

/// Parses the `{kind, value}` pairs of a `PUT …/grants` body. An unknown kind is refused by name:
/// a typo that silently dropped a grant would be read as "denied" and the flow would fail later,
/// far from the screen where it was typed.
pub fn parse_pairs(body: &Json) -> Result<Vec<GrantSpec>> {
    let Some(items) = body.as_array() else {
        return Err(RuntimeError::Domain {
            code: ERR_UNKNOWN_GRANT_KIND.to_string(),
            message: "grants are a list of `{kind, value}`".to_string(),
        });
    };
    let mut out = Vec::new();
    for item in items {
        let kind = item
            .get("kind")
            .and_then(|k| k.as_str())
            .and_then(GrantKind::parse)
            .ok_or_else(|| RuntimeError::Domain {
                code: ERR_UNKNOWN_GRANT_KIND.to_string(),
                message: format!(
                    "a grant `kind` is one of {}",
                    GrantKind::ALL
                        .iter()
                        .map(|k| k.as_str())
                        .collect::<Vec<_>>()
                        .join(", ")
                ),
            })?;
        let value = item
            .get("value")
            .and_then(|v| v.as_str())
            .unwrap_or_default()
            .trim()
            .to_string();
        if value.is_empty() {
            return Err(RuntimeError::Domain {
                code: ERR_UNKNOWN_GRANT_KIND.to_string(),
                message: format!("a `{}` grant needs a value", kind.as_str()),
            });
        }
        // hub#1623 — the optional `payload`: the fields this grant FIXES. Absent is the old shape
        // and means «fixes nothing»; present and not an object is refused rather than ignored,
        // because a pin that is silently dropped is a containment the owner believes they gave.
        let payload = match item.get("payload") {
            None | Some(Json::Null) => Params::new(),
            Some(Json::Object(map)) => map.clone(),
            Some(other) => {
                return Err(RuntimeError::Domain {
                    code: ERR_INVALID_GRANT_PAYLOAD.to_string(),
                    message: format!(
                        "a grant `payload` is an object of the fields it fixes, got {other}"
                    ),
                })
            }
        };
        out.push(GrantSpec {
            kind,
            value,
            payload,
        });
    }
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-grants";
    const FLOW: &str = "flow-1";
    /// A run id for the gates that never look one up: the run is read only when a pin REFERENCES
    /// it (hub#1662), so a grant with no pin — or one that fixes a literal — never touches it.
    const RUN: &str = "run-unused";

    fn registry() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.commands.insert(
            "sales.sale.create".into(),
            crate::flows::test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        reg.commands.insert(
            "sales.sale.void".into(),
            crate::flows::test_support::command("sales", "sales.void_sale", "SELECT 1;", vec![]),
        );
        // hub#824 — the two spellings of «internal», both real in the catalogue: the legacy `_`
        // convention on the last segment, and the explicit `internal: true` on a name that does not
        // carry it. A door that only knew the first would still let the second through.
        reg.commands.insert(
            "sales._insert_sale".into(),
            crate::flows::test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]),
        );
        let mut flagged =
            crate::flows::test_support::command("sales", "sales.add_sale", "SELECT 1;", vec![]);
        flagged.def.internal = true;
        reg.commands.insert("sales.reindex".into(), flagged);
        reg.queries.insert(
            "sales.sale.list".into(),
            crate::flows::test_support::query("sales", "sales.view_sale", "SELECT 1;"),
        );
        reg.queries.insert(
            "sales.sale.totals".into(),
            crate::flows::test_support::query("sales", "sales.view_sale", "SELECT 1;"),
        );
        reg
    }

    async fn db_with_schema() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        crate::flows::test_support::ensure_schema(&db, HUB).await;
        db
    }

    /// The stable CODE of a domain refusal. `Display` carries only the message, and the code is the
    /// half the editor programs against (flows.md §13.8).
    fn code_of(err: &RuntimeError) -> &str {
        match err {
            RuntimeError::Domain { code, .. } => code,
            other => panic!("expected a domain refusal, got {other}"),
        }
    }

    /// An URL the way the kernel really produces one: through the single parse of [`net`]. Nothing
    /// in these tests may hand the allow-list a string, because nothing in the kernel can.
    fn url(raw: &str) -> Url {
        net::parse(raw).unwrap_or_else(|e| panic!("`{raw}`: {e}"))
    }

    /// A pin, as an owner gives one: «may cancel appointments **as the customer**».
    fn pin(field: &str, value: &str) -> Params {
        let mut p = Params::new();
        p.insert(field.into(), json!(value));
        p
    }

    /// The payload a step really sends.
    fn sent(field: &str, value: &str) -> Params {
        pin(field, value)
    }

    /// hub#1623 — **the issue, in one test.** A flow whose payload is written by a model reading a
    /// stranger's WhatsApp message asks to cancel «on behalf of the salon». The command is granted;
    /// the CHANNEL is not, and the channel is what decides whether the salon's own cancellation
    /// rules (and the ownership check of appointments#140) apply at all.
    #[tokio::test]
    async fn a_pinned_grant_refuses_the_payload_that_contradicts_it() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:1",
        )
        .await
        .unwrap();

        let err = check_command_grant(
            &db,
            HUB,
            FLOW,
            RUN,
            "sales.sale.void",
            &sent("channel", "staff"),
        )
            .await
            .expect_err("«de parte del salón» is not what was granted");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);
        // The refusal names the field, because the owner's screen has to be able to say WHICH part
        // of the grant was contradicted, not just that something was.
        assert!(format!("{err}").contains("channel"), "{err}");

        check_command_grant(
            &db,
            HUB,
            FLOW,
            RUN,
            "sales.sale.void",
            &sent("channel", "customer"),
        )
        .await
        .expect("the very same command, asked for the way it was granted, runs");
    }

    /// hub#1623 — omitting the pinned field is **not** a way round the pin. Leaving `channel` out
    /// is easier than contradicting it, and it would hand the decision back to the module's own
    /// default — the exact thing the pin exists to take away from a stranger's message.
    #[tokio::test]
    async fn a_pinned_field_the_payload_omits_is_refused() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:1",
        )
        .await
        .unwrap();

        let err = check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &Params::new())
            .await
            .expect_err("absence is not agreement");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);
        assert!(format!("{err}").contains("omitted it"), "{err}");
    }

    /// hub#1623 — the pin narrows, it does not become a schema. A field the grant does not name is
    /// none of its business; the command's own schema still judges the rest of the payload.
    #[tokio::test]
    async fn fields_the_pin_does_not_name_stay_free() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:1",
        )
        .await
        .unwrap();

        let mut payload = sent("channel", "customer");
        payload.insert("appointment_id".into(), json!("appt-7"));
        payload.insert("reason".into(), json!("me ha surgido algo"));
        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &payload)
            .await
            .expect("what the grant did not fix, it did not forbid");
    }

    /// hub#1623 — **the comparison is strict**, because every lenient reading is a way round the
    /// pin: a different case, a different JSON type, the value wrapped one level down, a trailing
    /// space, or the pinned key written twice so that «the last one wins» (which is how
    /// `serde_json` reads a duplicate). All of them are «not the value the owner fixed», and all
    /// of them are refused. Guarded here so nobody ever «relaxes» the match to be helpful. (The
    /// other order of the duplicate — the honest value LAST — is not an evasion: the map the gate
    /// judges is the very map the handler runs with, so what passes is what executes.)
    #[tokio::test]
    async fn the_pin_is_matched_strictly_case_type_shape_and_duplicate_keys() {
        let db = db_with_schema().await;
        let mut pinned = pin("channel", "customer");
        pinned.insert("max_items".into(), json!(1));
        pinned.insert("notify".into(), json!(true));
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pinned)],
            "hub_user:1",
        )
        .await
        .unwrap();

        let honest: Params =
            serde_json::from_str(r#"{"channel":"customer","max_items":1,"notify":true}"#).unwrap();
        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &honest)
            .await
            .expect("the exact values pass");

        let evasions = [
            ("case of the value", r#"{"channel":"Customer","max_items":1,"notify":true}"#),
            ("case of the key", r#"{"Channel":"customer","max_items":1,"notify":true}"#),
            ("trailing space", r#"{"channel":"customer ","max_items":1,"notify":true}"#),
            ("number as a string", r#"{"channel":"customer","max_items":"1","notify":true}"#),
            ("integer as a float", r#"{"channel":"customer","max_items":1.0,"notify":true}"#),
            ("bool as a string", r#"{"channel":"customer","max_items":1,"notify":"true"}"#),
            ("bool as a number", r#"{"channel":"customer","max_items":1,"notify":1}"#),
            (
                "value nested one level down",
                r#"{"channel":{"value":"customer"},"max_items":1,"notify":true}"#,
            ),
            (
                "pinned key written twice, the honest value first",
                r#"{"channel":"customer","channel":"staff","max_items":1,"notify":true}"#,
            ),
        ];
        for (how, raw) in evasions {
            let payload: Params =
                serde_json::from_str(raw).unwrap_or_else(|e| panic!("{how}: {e}"));
            let err = check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &payload)
                .await
                .err()
                .unwrap_or_else(|| panic!("{how}: got through the pin"));
            assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED, "{how}");
        }
    }

    /// hub#1623 — every grant written before this existed pins nothing, and must keep behaving
    /// exactly as it did: the NAME is the whole question. A regression here would break every flow
    /// in every hub at once.
    #[tokio::test]
    async fn a_grant_that_pins_nothing_still_accepts_any_payload() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.void")],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &sent("channel", "staff"))
            .await
            .expect("an unpinned grant is the pre-hub#1623 grant, and it judges the name");
    }

    /// hub#1623 — the pin is part of the grant, so narrowing (or widening) one is a REVOCATION plus
    /// a new grant, not a quiet edit of the live row. Otherwise the screen and the gate would
    /// disagree: the owner would read the new sentence while the old one was still being enforced.
    #[tokio::test]
    async fn changing_the_pin_revokes_the_old_grant_and_writes_a_new_one() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.void")],
            "hub_user:1",
        )
        .await
        .unwrap();
        let before = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(before.len(), 1);

        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:2",
        )
        .await
        .unwrap();

        let after = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(after.len(), 1, "one live grant per command, pin included");
        assert_ne!(after[0].id, before[0].id, "the narrowed grant is a NEW row");
        assert_eq!(after[0].payload, json!({"channel": "customer"}));
        // And the gate follows the new row, not the old one.
        assert_eq!(
            code_of(
                &check_command_grant(
                    &db,
                    HUB,
                    FLOW,
                    RUN,
                    "sales.sale.void",
                    &sent("channel", "staff"),
                )
                    .await
                    .expect_err("the widened call is refused from now on")
            ),
            ERR_GRANT_PAYLOAD_DENIED
        );
    }

    /// hub#1623 — re-saving the SAME pin is still a no-op, so the owner pressing save twice does not
    /// churn `granted_by`/`created_at`. The property `replace` already had, now including the pin.
    #[tokio::test]
    async fn re_saving_the_same_pin_keeps_the_original_row() {
        let db = db_with_schema().await;
        let reg = registry();
        let wanted = [GrantSpec::pinned(
            "sales.sale.void",
            pin("channel", "customer"),
        )];
        replace(&db, HUB, FLOW, &reg, &wanted, "hub_user:1")
            .await
            .unwrap();
        let first = list(&db, HUB, FLOW).await.unwrap();
        replace(&db, HUB, FLOW, &reg, &wanted, "hub_user:2")
            .await
            .unwrap();
        let second = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(second.len(), 1);
        assert_eq!(second[0].id, first[0].id, "saving twice is not a re-grant");
        assert_eq!(second[0].granted_by, "hub_user:1");
    }

    /// hub#1623, **narrowed by hub#1662** — a pin is only enforced where a gate is handed values to
    /// judge: a `command`'s payload and a `query`'s parameters. On `notify`, `http` and
    /// `recipient_query` nothing is ever compared against it, so storing one would put a
    /// restriction on the screen that nothing applies — the same rule `is_available` enforces for
    /// the kinds themselves. The list is spelled out here so adding a kind cannot quietly gain a
    /// pin nobody enforces.
    #[tokio::test]
    async fn a_pin_is_refused_on_a_kind_that_is_handed_no_values() {
        let db = db_with_schema().await;
        for (kind, value) in [
            (GrantKind::Notify, "email"),
            (GrantKind::Http, "https://example.com/*"),
            (GrantKind::RecipientQuery, "sales.sale.list#email"),
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec {
                    kind,
                    value: value.into(),
                    payload: pin("channel", "customer"),
                }],
                "hub_user:1",
            )
            .await
            .unwrap_err();
            assert_eq!(code_of(&err), ERR_INVALID_GRANT_PAYLOAD, "{}", kind.as_str());
            assert!(
                list(&db, HUB, FLOW).await.unwrap().is_empty(),
                "and nothing was stored"
            );
        }
        assert!(
            !GrantKind::ALL.iter().any(|k| k.can_pin()
                && !matches!(k, GrantKind::Command | GrantKind::Query)),
            "a new kind that can be pinned has to be added to this test with its gate"
        );
    }

    /// hub#1623 — the pin survives the trip through the `PUT …/grants` body, and a `payload` that
    /// is not an object is REFUSED rather than dropped: a pin silently ignored is a containment the
    /// owner believes they gave.
    #[test]
    fn parse_pairs_reads_the_pin_and_refuses_one_that_is_not_an_object() {
        let parsed = parse_pairs(&json!([
            {"kind": "command", "value": "sales.sale.void", "payload": {"channel": "customer"}},
            {"kind": "command", "value": "sales.sale.create"}
        ]))
        .expect("both shapes are valid");
        assert_eq!(parsed[0].payload, pin("channel", "customer"));
        assert!(parsed[1].payload.is_empty(), "absent means «fixes nothing»");

        let err = parse_pairs(&json!([
            {"kind": "command", "value": "sales.sale.void", "payload": "channel=customer"}
        ]))
        .expect_err("a pin that cannot be read is refused, never ignored");
        assert_eq!(code_of(&err), ERR_INVALID_GRANT_PAYLOAD);
    }

    /// A row whose stored pin stopped being READABLE. No door of this kernel can produce one — the
    /// column is `NOT NULL DEFAULT '{}'`, `replace` always serialises an object and `parse_pairs`
    /// refuses anything else — so it is written here by SQL on purpose: the guard has to hold for a
    /// row that got there some other way (edited by hand, a botched column change, a mangled
    /// restore), which is the only way this state exists at all.
    async fn corrupt_the_stored_pin(db: &dyn DatabaseAdapter, command: &str, raw: &str) {
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        p.insert("flow_id".into(), json!(FLOW));
        p.insert("value".into(), json!(command));
        p.insert("payload".into(), json!(raw));
        db.execute(
            "UPDATE _flow_grants SET payload = :payload \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND kind = 'command' \
               AND value = :value AND deleted_at IS NULL",
            &p,
        )
        .await
        .expect("the fixture writes the row this guard exists for");
    }

    /// hub#1636 — **the residual risk hub#1623 left behind, in one test.** A `command` grant carries
    /// its pin in a TEXT column. When that text stopped being readable the gate read it as «this
    /// grant fixes nothing» and let the call through UNPINNED: an unreadable RESTRICTION became a
    /// wider AUTHORISATION, which is the one direction a permission may never move on its own.
    ///
    /// Now the row is not a grant at all — default-deny by absence, the rule the header of this file
    /// states — so the refusal is [`ERR_GRANT_DENIED`] and not [`ERR_GRANT_PAYLOAD_DENIED`]: there
    /// is no pin to contradict, there is a grant that cannot be read.
    #[tokio::test]
    async fn a_grant_whose_stored_pin_cannot_be_read_authorises_nothing() {
        // Every shape `parse_pin` cannot turn into an object, including the two that LOOK like
        // JSON: `null` and `[]` parse fine and are still not a set of fixed fields.
        for raw in ["garbage", "", "null", "[]", "7", "\"channel=customer\""] {
            let db = db_with_schema().await;
            let reg = registry();
            replace(
                &db,
                HUB,
                FLOW,
                &reg,
                &[
                    GrantSpec::pinned("sales.sale.void", pin("channel", "customer")),
                    GrantSpec::pair(GrantKind::Command, "sales.sale.create"),
                ],
                "hub_user:1",
            )
            .await
            .unwrap();
            corrupt_the_stored_pin(&db, "sales.sale.void", raw).await;

            // Not the payload the pin asked for, not one that contradicts it, and not the empty one
            // that a grant fixing nothing would wave through. The row says nothing the gate can
            // honour, so it authorises nothing.
            for attempt in [
                sent("channel", "customer"),
                sent("channel", "staff"),
                Params::new(),
            ] {
                let err = check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &attempt)
                    .await
                    .expect_err("an unreadable grant is not an unrestricted one");
                assert_eq!(code_of(&err), ERR_GRANT_DENIED, "payload `{raw}`");
            }

            // And ONE broken row is one denial, not an authority wiped clean: the other grants of
            // the same flow still answer, or a single mangled byte would silently stop every
            // automation the owner has.
            check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.create", &Params::new())
                .await
                .unwrap_or_else(|e| {
                    panic!("payload `{raw}`: the readable grant still answers: {e}")
                });
        }
    }

    /// The control for the test above: `{}` is READABLE and means «fixes nothing», so it has to keep
    /// authorising every payload. Without this, a gate that denied every `command` grant outright
    /// would pass the guard while breaking every flow in the hub.
    #[tokio::test]
    async fn a_readable_empty_pin_still_means_fixes_nothing() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.void")],
            "hub_user:1",
        )
        .await
        .unwrap();
        corrupt_the_stored_pin(&db, "sales.sale.void", "{}").await;

        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &sent("channel", "staff"))
            .await
            .expect("`{}` fixes nothing, so nothing is contradicted");
    }

    /// hub#1636, **re-decided by hub#1662**. That issue scoped the guard to `command` and wrote down
    /// why: a `query` row carried no pin, so its `payload` column decided nothing and denying the
    /// read would have bought containment with availability and got neither. hub#1662 gave a read a
    /// pin, so the premise is gone and the rule that outlives it is hub#1636's own — an unreadable
    /// RESTRICTION must never become a wider AUTHORISATION. The read closes exactly like the write.
    #[tokio::test]
    async fn an_unreadable_pin_on_a_query_grant_closes_the_read_too() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "resolve_customer": { "id": 4470 } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("steps.resolve_customer.id")),
            )],
            "hub_user:1",
        )
        .await
        .unwrap();
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(HUB));
        p.insert("flow_id".into(), json!(FLOW));
        db.execute(
            "UPDATE _flow_grants SET payload = 'garbage' \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND kind = 'query'",
            &p,
        )
        .await
        .unwrap();

        let err = check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!(4470)),
        )
        .await
        .expect_err("a pin nobody can read authorises nothing, on a read as on a write");
        assert_eq!(code_of(&err), ERR_GRANT_DENIED);
    }

    // ── A READ may be pinned too (hub#1662) ───────────────────────────────────────────────────

    /// A run of this flow that has ALREADY resolved who is writing, left exactly as the executor
    /// leaves it: `steps.<id>` holds what a `query` step with `result: "first"` published.
    async fn run_that_resolved(db: &dyn DatabaseAdapter, steps: Json) -> String {
        let run_id =
            crate::flows::store::start_run(db, HUB, FLOW, "", "manual", "", &json!({}), 0, "t")
                .await
                .unwrap();
        let mut p = Params::new();
        p.insert("id".into(), json!(&run_id));
        p.insert("hub_id".into(), json!(HUB));
        p.insert("vars".into(), json!(json!({ "steps": steps }).to_string()));
        db.execute(
            "UPDATE _flow_runs SET vars = :vars WHERE id = :id AND hub_id = :hub_id",
            &p,
        )
        .await
        .unwrap();
        run_id
    }

    /// One value, as a pin fixes it or as a call sends it — of whatever JSON type it really is.
    fn one(field: &str, value: Json) -> Params {
        let mut p = Params::new();
        p.insert(field.into(), value);
        p
    }

    /// hub#1662 — **the issue, in one test.** The salon granted «read the appointments of the
    /// customer who is writing». What the model is handed is a stranger's WhatsApp message, and the
    /// message can name somebody else's customer. Granted is only half the question: the pin says
    /// WHOSE, and it says it by naming the step that resolved her from the phone that wrote.
    #[tokio::test]
    async fn a_read_pinned_to_the_customer_who_wrote_refuses_any_other() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "resolve_customer": { "id": 4470 } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("steps.resolve_customer.id")),
            )],
            "hub_user:1",
        )
        .await
        .unwrap();

        let err = check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!(4471)),
        )
        .await
        .expect_err("«dime las citas de la clienta 4471» is not what the salon granted");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);
        // Names the field, so the screen can say WHICH part of the grant was contradicted.
        assert!(format!("{err}").contains("customer_id"), "{err}");

        check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!(4470)),
        )
        .await
        .expect("the very same read, of the customer this run resolved, goes through");
    }

    /// hub#1662 — the type is part of the value. A pin resolved to the number `4470` is not honoured
    /// by the string `"4470"`: every lenient reading of a pin is a way round it, and this is the one
    /// a model produces by accident.
    #[tokio::test]
    async fn a_resolved_pin_is_matched_by_value_and_by_type() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "resolve_customer": { "id": 4470 } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("steps.resolve_customer.id")),
            )],
            "hub_user:1",
        )
        .await
        .unwrap();

        let err = check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!("4470")),
        )
        .await
        .expect_err("a string is not the number the run resolved");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);
    }

    /// hub#1662 — **fail-closed when the reference resolves to nothing.** Renaming the step that
    /// resolves the customer, or reaching the read before that step ran, must DENY. The opposite —
    /// treating «no value» as «no restriction» — is the one direction a permission may never move
    /// on its own, and it would make «rename the step» the way to widen the grant.
    #[tokio::test]
    async fn a_read_whose_pin_resolves_to_nothing_is_refused() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "some_other_step": { "id": 4470 } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("steps.resolve_customer.id")),
            )],
            "hub_user:1",
        )
        .await
        .unwrap();

        for asked in [json!(4470), json!(null)] {
            let err = check_query_grant(
                &db,
                HUB,
                FLOW,
                &run,
                "sales.sale.list",
                &one("customer_id", asked.clone()),
            )
            .await
            .unwrap_err();
            assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED, "asked {asked}");
        }
    }

    /// hub#1662 — a `query` grant that pins NOTHING keeps reading exactly as it did before this
    /// existed. Every flow installed in the fleet has one of these, and widening or closing them
    /// silently is the regression this test is here to stop.
    #[tokio::test]
    async fn a_query_grant_without_a_pin_reads_as_it_always_did() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({})).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Query, "sales.sale.list")],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!(4471)),
        )
        .await
        .expect("an unpinned grant says what it says in `value` and judges no parameter");
    }

    /// hub#1662 — a pin may name the RUN (`input.…`, `steps.…`) and nothing else. A `secret.…`
    /// reference would turn the gate into an oracle — try values until the read passes and the
    /// secret is yours — and an `event.…` one names something the run scope does not carry, so it
    /// could only ever deny. Both are refused at save, the rule this file already applies to a pin
    /// on a kind that carries none: never store a restriction nothing can enforce.
    #[tokio::test]
    async fn a_pin_may_name_the_run_and_never_a_secret() {
        let db = db_with_schema().await;
        // `now.…` joined the mapping language in hub#1694 and this scope is `{input, steps}`: a pin
        // on the clock could only ever resolve to null and deny everything, so it is refused where
        // it is written instead of at 3 AM.
        for reference in ["secret.stripe_key", "event.customer_id", "now.iso"] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pinned_query(
                    "sales.sale.list",
                    one("customer_id", json!(reference)),
                )],
                "hub_user:1",
            )
            .await
            .unwrap_err();
            assert_eq!(code_of(&err), ERR_INVALID_GRANT_PAYLOAD, "{reference}");
        }

        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("input.customer_id")),
            )],
            "hub_user:1",
        )
        .await
        .expect("the run's own trigger input is a legal reference");
    }

    /// hub#1662 — the same mechanism on the WRITE side, which hub#1623 left half open: pinning
    /// `channel: "customer"` stopped the automation cancelling «on behalf of the salon», and left
    /// the model free to name ANY appointment. A pin that resolves against the run closes that too.
    #[tokio::test]
    async fn a_command_pin_may_name_the_run_so_a_stranger_cannot_choose_the_row() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "resolve_customer": { "id": 4470 } })).await;
        let mut pinned = pin("channel", "customer");
        pinned.insert(
            "customer_id".into(),
            json!("steps.resolve_customer.id"),
        );
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pinned)],
            "hub_user:1",
        )
        .await
        .unwrap();

        let mut theirs = sent("channel", "customer");
        theirs.insert("customer_id".into(), json!(4471));
        let err = check_command_grant(&db, HUB, FLOW, &run, "sales.sale.void", &theirs)
            .await
            .expect_err("cancelling somebody else's appointment is not what was granted");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);

        let mut hers = sent("channel", "customer");
        hers.insert("customer_id".into(), json!(4470));
        check_command_grant(&db, HUB, FLOW, &run, "sales.sale.void", &hers)
            .await
            .expect("her own appointment, as the customer, is exactly the grant");
    }

    /// hub#1662 — a literal pin is still literal. `"customer"` is not a path (it is not rooted at
    /// `input`/`steps`), so every grant written before this existed keeps comparing byte for byte.
    #[tokio::test]
    async fn a_literal_pin_is_never_read_as_a_reference() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "customer": { "id": 1 } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_command_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.void",
            &sent("channel", "customer"),
        )
        .await
        .expect("the pre-hub#1662 grant compares against the word it stored");
    }

    /// hub#1662 — a pin is a VALUE, not a sentence. A `{{…}}` template would be rendered: a number
    /// flattened to a string and, worse, an unresolved template renders EMPTY, so the pin would
    /// quietly stop matching anything and the containment would read as working while it denied
    /// everything. It is refused at save, on a read as on a write — the bare path is the way to
    /// say «what this run resolved», and it keeps the type.
    #[tokio::test]
    async fn a_pin_is_a_value_and_never_a_template() {
        let db = db_with_schema().await;
        for (kind, name) in [
            (GrantKind::Query, "sales.sale.list"),
            (GrantKind::Command, "sales.sale.void"),
        ] {
            for written in [
                "{{steps.resolve_customer.id}}",
                "cust-{{steps.resolve_customer.id}}",
            ] {
                let err = replace(
                    &db,
                    HUB,
                    FLOW,
                    &registry(),
                    &[GrantSpec {
                        kind,
                        value: name.into(),
                        payload: one("customer_id", json!(written)),
                    }],
                    "hub_user:1",
                )
                .await
                .unwrap_err();
                assert_eq!(
                    code_of(&err),
                    ERR_INVALID_GRANT_PAYLOAD,
                    "{} `{written}`",
                    kind.as_str()
                );
                assert!(
                    list(&db, HUB, FLOW).await.unwrap().is_empty(),
                    "and nothing was stored"
                );
            }
        }
    }

    /// hub#1662 — a step that RAN and resolved nobody publishes `id: null`, and `null` is not «no
    /// restriction». Left alone, a caller sending `customer_id: null` would match it and read
    /// whatever the query does with a null filter. A reference that resolves to `null` resolves to
    /// nothing, and nothing refuses — the same answer as a step that never ran.
    #[tokio::test]
    async fn a_pin_that_resolves_to_null_refuses_even_the_null_that_was_sent() {
        let db = db_with_schema().await;
        let run = run_that_resolved(&db, json!({ "resolve_customer": { "id": null } })).await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pinned_query(
                "sales.sale.list",
                one("customer_id", json!("steps.resolve_customer.id")),
            )],
            "hub_user:1",
        )
        .await
        .unwrap();

        let err = check_query_grant(
            &db,
            HUB,
            FLOW,
            &run,
            "sales.sale.list",
            &one("customer_id", json!(null)),
        )
        .await
        .expect_err("nobody is not a customer, and null does not match null here");
        assert_eq!(code_of(&err), ERR_GRANT_PAYLOAD_DENIED);
    }

    /// hub#1636 — a broken authorisation row that only failed at 3 AM would be a mystery: the flow
    /// stops, the permissions screen still shows the grant, and nothing connects the two. So the
    /// denial is also REPORTED, naming the row that has to be revoked and granted again.
    ///
    /// Pinned on the event BUILDER and not on the sink, like `failed_install_event` (hub#1477): what
    /// is programmed against is the stable code and the row it names, not that a global was called.
    #[test]
    fn the_report_of_an_unreadable_pin_names_the_row_to_re_grant() {
        let event = unreadable_pin_event("g-7", FLOW, "sales.sale.void");
        assert_eq!(event.error_code, ERR_UNREADABLE_GRANT_PAYLOAD_EVENT);
        assert_eq!(event.severity, crate::error_registry::severity::UNEXPECTED);
        assert_eq!(event.source, crate::error_registry::source::HUB);
        assert_eq!(event.context["grant_id"], json!("g-7"));
        assert_eq!(event.context["flow_id"], json!(FLOW));
        assert_eq!(event.context["command"], json!("sales.sale.void"));
    }

    /// hub#1623 — revoking a pinned grant is the same soft-delete as any other, and the gate stops
    /// answering for it. Belt and braces on the freshness property the file's header promises.
    #[tokio::test]
    async fn revoking_a_pinned_grant_closes_it_like_any_other() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pinned("sales.sale.void", pin("channel", "customer"))],
            "hub_user:1",
        )
        .await
        .unwrap();
        check_command_grant(
            &db,
            HUB,
            FLOW,
            RUN,
            "sales.sale.void",
            &sent("channel", "customer"),
        )
        .await
        .unwrap();

        replace(&db, HUB, FLOW, &reg, &[], "hub_user:1")
            .await
            .unwrap();
        assert_eq!(
            code_of(
                &check_command_grant(
                    &db,
                    HUB,
                    FLOW,
                    RUN,
                    "sales.sale.void",
                    &sent("channel", "customer"),
                )
                .await
                .expect_err("revoked is revoked, pinned or not")
            ),
            ERR_GRANT_DENIED,
            "and it reads as «no grant», not as «wrong payload»"
        );
    }

    #[tokio::test]
    async fn a_flow_with_no_grants_may_run_nothing() {
        let db = db_with_schema().await;
        let err = check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.create", &Params::new())
            .await
            .expect_err("default-deny: absence is the answer, not an empty allow-list");
        assert!(format!("{err}").contains("sales.sale.create"), "{err}");
    }

    #[tokio::test]
    async fn a_grant_opens_exactly_the_command_it_names() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.create")],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.create", &Params::new())
            .await
            .expect("the granted command runs");
        // A sibling command of the same module is a different question with the same answer as
        // before: no.
        assert!(check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.void", &Params::new())
            .await
            .is_err());
    }

    #[tokio::test]
    async fn a_grant_belongs_to_one_flow_and_one_hub() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.create")],
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(
            check_command_grant(&db, HUB, "flow-2", RUN, "sales.sale.create", &Params::new())
                .await
                .is_err(),
            "another flow of the same hub is not covered"
        );
        assert!(
            check_command_grant(&db, "hub-other", FLOW, RUN, "sales.sale.create", &Params::new())
                .await
                .is_err(),
            "the same flow id in another tenant is not covered"
        );
    }

    #[tokio::test]
    async fn revoking_is_a_soft_delete_and_takes_effect_on_the_next_read() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [GrantSpec::pair(GrantKind::Command, "sales.sale.create")];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1")
            .await
            .unwrap();
        check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.create", &Params::new())
            .await
            .unwrap();

        // The owner empties the list — this is what `PUT …/grants` with `[]` does.
        replace(&db, HUB, FLOW, &reg, &[], "hub_user:2")
            .await
            .unwrap();

        assert!(check_command_grant(&db, HUB, FLOW, RUN, "sales.sale.create", &Params::new())
            .await
            .is_err());
        assert!(list(&db, HUB, FLOW).await.unwrap().is_empty());
        // The row survives, naming who took it away: that is the audit trail.
        let rows = db
            .query(
                "SELECT revoked_by FROM _flow_grants WHERE deleted_at IS NOT NULL",
                &Params::new(),
            )
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1);
        assert_eq!(rows[0]["revoked_by"], json!("hub_user:2"));
    }

    #[tokio::test]
    async fn re_saving_the_same_list_keeps_the_original_attribution() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [GrantSpec::pair(GrantKind::Command, "sales.sale.create")];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1")
            .await
            .unwrap();
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:2")
            .await
            .unwrap();

        let live = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(
            live.len(),
            1,
            "saving the same screen twice is not a conflict"
        );
        assert_eq!(live[0].granted_by, "hub_user:1", "who granted it first");
    }

    #[tokio::test]
    async fn a_grant_for_a_command_that_does_not_exist_is_refused() {
        let db = db_with_schema().await;
        let err = replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Command, "ghost.command")],
            "hub_user:1",
        )
        .await
        .expect_err("a grant naming nothing reads as authorisation on the screen");
        assert!(format!("{err}").contains("ghost.command"), "{err}");
    }

    /// **hub#824** — an INTERNAL command exists in the registry, so the «does it exist» check waves
    /// it through; and `execute_at` will refuse it three seconds later, because `Origin::Automation`
    /// is barred from internals exactly like `External` (flows.md §2). Between those two moments the
    /// grants screen says «granted» about something that can never run — and a grant that promises
    /// what nobody enforces is worse than its absence, because the owner reads it as authorisation.
    ///
    /// So the refusal moves to the door that already resolves the name, and it is refused by CODE:
    /// the editor has to be able to say «that one is internal», not «error».
    #[tokio::test]
    async fn an_internal_command_cannot_be_granted_even_though_it_exists() {
        let db = db_with_schema().await;
        for internal in ["sales._insert_sale", "sales.reindex"] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::Command, internal)],
                "hub_user:1",
            )
            .await
            .unwrap_err();
            assert_eq!(
                code_of(&err),
                ERR_INTERNAL_COMMAND,
                "`{internal}` must be refused by its own code: {err}"
            );
            assert!(
                format!("{err}").contains(internal),
                "the refusal names the command so the screen can point at it: {err}"
            );
        }

        // The whole list is refused, so the owner never half-grants: nothing landed, not even the
        // public command that shared the request.
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[
                GrantSpec::pair(GrantKind::Command, "sales.sale.create"),
                GrantSpec::pair(GrantKind::Command, "sales._insert_sale"),
            ],
            "hub_user:1",
        )
        .await
        .expect_err("one bad grant refuses the list (§9)");
        assert!(
            list(&db, HUB, FLOW).await.unwrap().is_empty(),
            "a refused PUT stores nothing at all"
        );

        // …and the ordinary command still goes through, which is the half that must not regress.
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.create")],
            "hub_user:1",
        )
        .await
        .unwrap();
        assert!(authority(&db, HUB, FLOW)
            .await
            .unwrap()
            .allows_command("sales.sale.create"));
    }

    /// hub#821 closes the list: every kind of ADR-0283 §2 is now something the kernel enforces, so
    /// none of them is refused for being a promise. What still gets refused is a VALUE the kernel
    /// cannot enforce — which is the same rule, one level down.
    #[tokio::test]
    async fn every_kind_of_the_frozen_vocabulary_is_creatable_now() {
        let db = db_with_schema().await;
        for spec in [
            GrantSpec::pair(GrantKind::Command, "sales.sale.create"),
            GrantSpec::pair(GrantKind::Query, "sales.sale.list"),
            GrantSpec::pair(GrantKind::Http, "https://api.example.com/v1/send*"),
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#email"),
        ] {
            let kind = spec.kind;
            replace(&db, HUB, FLOW, &registry(), &[spec], "hub_user:1")
                .await
                .unwrap_or_else(|e| panic!("`{}` is enforced by this kernel: {e}", kind.as_str()));
        }
        assert!(GrantKind::ALL.iter().all(|k| k.is_available()));
    }

    // ── notify and recipient_query (hub#821) ──────────────────────────────────────────────────

    /// The two grants are SEPARATE, and each one is a whole veto. Being allowed to email a
    /// customer is not being allowed to WhatsApp them (Meta meters and bills every message), and
    /// being allowed the channel says nothing about whose address may be dialled.
    #[tokio::test]
    async fn the_channel_and_the_recipient_are_two_independent_permissions() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[
                GrantSpec::pair(GrantKind::Notify, "email"),
                GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#email"),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();
        let authority = authority(&db, HUB, FLOW).await.unwrap();

        assert!(authority.allows_notify(Channel::Email));
        assert!(
            !authority.allows_notify(Channel::Whatsapp),
            "the channel that costs money is not thrown in with the one that does not"
        );
        assert!(authority.allows_recipient("sales.sale.list", "email"));
        // Another field of the same query, and the same field of another query: two different
        // permissions with the same default answer.
        assert!(!authority.allows_recipient("sales.sale.list", "phone"));
        assert!(!authority.allows_recipient("sales.sale.totals", "email"));
        // …and a recipient grant is NOT a query grant: it authorises taking one column out to
        // address a message, never handing the row to an `ai` step.
        assert!(
            !authority.allows_query("sales.sale.list"),
            "a recipient grant must not become a read the model can call"
        );
    }

    /// `check_notify_grants` is the door the step goes through, and it answers with the ID of the
    /// row that authorised it — which is what makes revoking that row stop the message later.
    #[tokio::test]
    async fn the_step_gate_returns_the_id_of_the_grant_that_authorised_the_recipient() {
        let db = db_with_schema().await;
        let grants = [
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#phone"),
        ];
        replace(&db, HUB, FLOW, &registry(), &grants, "hub_user:1")
            .await
            .unwrap();

        let authority = authority(&db, HUB, FLOW).await.unwrap();
        let id = check_notify_grants(
            &db,
            HUB,
            FLOW,
            &authority,
            Channel::Whatsapp,
            "sales.sale.list",
            "phone",
        )
        .await
        .expect("both grants are live");
        let live = list(&db, HUB, FLOW).await.unwrap();
        assert!(
            live.iter()
                .any(|g| g.id == id && g.kind == "recipient_query"),
            "the id names the recipient grant itself"
        );

        // The channel it was not given, and the field it was not given: refused by name.
        assert!(check_notify_grants(
            &db,
            HUB,
            FLOW,
            &authority,
            Channel::Email,
            "sales.sale.list",
            "phone"
        )
        .await
        .is_err());
        assert!(check_notify_grants(
            &db,
            HUB,
            FLOW,
            &authority,
            Channel::Whatsapp,
            "sales.sale.list",
            "email"
        )
        .await
        .is_err());
    }

    /// The release a queued message carries is re-read at delivery, and REVOKING cuts it. The two
    /// grants are two vetoes: either one gone and the message does not go.
    #[tokio::test]
    async fn a_release_stops_being_valid_the_moment_either_grant_is_revoked() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [
            GrantSpec::pair(GrantKind::Notify, "whatsapp"),
            GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#phone"),
        ];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1")
            .await
            .unwrap();
        let authority = authority(&db, HUB, FLOW).await.unwrap();
        let id = check_notify_grants(
            &db,
            HUB,
            FLOW,
            &authority,
            Channel::Whatsapp,
            "sales.sale.list",
            "phone",
        )
        .await
        .unwrap();
        let release = crate::host_notify::flow_grant_release(&id);

        // A run of this flow, which is what the outbox row would point at.
        let run_id = crate::flows::store::start_run(
            &db,
            HUB,
            FLOW,
            "",
            "manual",
            "",
            &json!({}),
            0,
            "hub_user:1",
        )
        .await
        .unwrap();
        check_notify_release(&db, HUB, &run_id, &release, Channel::Whatsapp)
            .await
            .expect("both grants alive, the message may go");

        // A release that names a grant of ANOTHER flow, or nothing at all, is not a release.
        assert!(
            check_notify_release(&db, HUB, &run_id, "flow_grant:made-up", Channel::Whatsapp)
                .await
                .is_err()
        );
        assert!(
            check_notify_release(&db, HUB, &run_id, &id, Channel::Whatsapp)
                .await
                .is_err(),
            "without the prefix it names nothing"
        );

        // Revoke the recipient grant only: the channel is still allowed and the message still
        // stops, because whose address it was is the question that was withdrawn.
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Notify, "whatsapp")],
            "hub_user:2",
        )
        .await
        .unwrap();
        let err = check_notify_release(&db, HUB, &run_id, &release, Channel::Whatsapp)
            .await
            .expect_err("a revoked grant stops a message that was already queued");
        assert!(format!("{err}").contains("REVOCADO"), "{err}");

        // And the mirror: recipient back, channel gone.
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:3")
            .await
            .unwrap();
        let regranted = super::authority(&db, HUB, FLOW).await.unwrap();
        let id = check_notify_grants(
            &db,
            HUB,
            FLOW,
            &regranted,
            Channel::Whatsapp,
            "sales.sale.list",
            "phone",
        )
        .await
        .unwrap();
        let release = crate::host_notify::flow_grant_release(&id);
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#phone")],
            "hub_user:4",
        )
        .await
        .unwrap();
        assert!(
            check_notify_release(&db, HUB, &run_id, &release, Channel::Whatsapp)
                .await
                .is_err(),
            "the channel grant is a live veto too"
        );
    }

    /// A `notify` grant names ONE channel this hub can really send on. `sms` is in ADR-0012's
    /// vocabulary and has no transport anywhere: granting it would read as permission and turn
    /// into eight retries and a dead-letter the first night the flow ran.
    #[tokio::test]
    async fn a_notify_grant_for_a_channel_with_no_transport_is_refused_by_name() {
        let db = db_with_schema().await;
        for value in ["sms", "", "carrier_pigeon", "email,whatsapp"] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::Notify, value)],
                "hub_user:1",
            )
            .await
            .expect_err("a grant nothing can honour must not be stored");
            assert!(
                format!("{err}").contains("channel") || format!("{err}").contains("transport"),
                "{err}"
            );
        }
    }

    /// A recipient grant that does not name «one field of one declared read» is refused, for the
    /// same reason an http pattern that does not name one host is: nobody could read it correctly.
    #[tokio::test]
    async fn a_recipient_grant_that_is_not_one_field_of_one_query_is_refused() {
        let db = db_with_schema().await;
        for value in [
            "sales.sale.list",                // no field
            "#email",                         // no query
            "sales.sale.list#",               // no field
            "ghost.query#email",              // a query that does not exist
            "sales.sale.list#customer.email", // a path, not a column
            "sales.sale.list#*",              // not a column name either
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::RecipientQuery, value)],
                "hub_user:1",
            )
            .await
            .expect_err("a grant naming nothing reads as authorisation on the screen");
            assert!(
                format!("{err}").contains(value) || format!("{err}").contains("ghost.query"),
                "{err}"
            );
        }
    }

    /// The permission union carries the read behind a recipient grant, or the `notify` step would
    /// pass the flow's gate and be refused by the permission check inside `queries::execute` — one
    /// door open and the next one shut, the same trap the `query` grant had.
    #[tokio::test]
    async fn the_context_permissions_include_the_read_behind_a_recipient_grant() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::RecipientQuery, "sales.sale.list#email")],
            "hub_user:1",
        )
        .await
        .unwrap();
        let permissions = authority(&db, HUB, FLOW).await.unwrap().permissions(&reg);
        assert_eq!(permissions, HashSet::from(["sales.view_sale".to_string()]));
    }

    // ── the http allow-list (hub#662) ─────────────────────────────────────────────────────────

    #[tokio::test]
    async fn an_http_grant_opens_exactly_the_urls_its_pattern_covers() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Http, "https://api.example.com/v1/messages*")],
            "hub_user:1",
        )
        .await
        .unwrap();
        let authority = authority(&db, HUB, FLOW).await.unwrap();

        assert!(authority.allows_http(&url("https://api.example.com/v1/messages")));
        assert!(authority.allows_http(&url("https://api.example.com/v1/messages/42?dry=1")));
        // Another path of the same host is a different permission.
        assert!(!authority.allows_http(&url("https://api.example.com/v1/customers")));
        // A host that merely STARTS with the granted one is the classic allow-list escape
        // (`api.example.com.evil.test`); the origin is compared whole, never by prefix.
        assert!(!authority.allows_http(&url("https://api.example.com.evil.test/v1/messages")));
        // The scheme is part of the origin: a grant for https never authorises cleartext.
        assert!(!authority.allows_http(&url("http://api.example.com/v1/messages")));
        // And an URL that merely CONTAINS the pattern is not covered by it.
        assert!(!authority.allows_http(&url(
            "https://evil.test/?u=https://api.example.com/v1/messages"
        )));
    }

    #[tokio::test]
    async fn a_flow_with_no_http_grant_may_call_nothing() {
        let db = db_with_schema().await;
        let authority = authority(&db, HUB, FLOW).await.unwrap();
        assert!(!authority.allows_http(&url("https://api.example.com/v1/messages")));
    }

    /// hub#729 — the allow-list compares the path a client will really request, not the one that
    /// was typed. `/v1/send/../../admin/keys` READS as covered by `/v1/send*` and is fetched from
    /// `/admin/keys`, so a grant for "only the send endpoint" hands over the whole API with the
    /// key that was given to it.
    #[tokio::test]
    async fn a_dot_segment_cannot_walk_out_of_the_granted_path() {
        let db = db_with_schema().await;
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Http, "https://api.example.com/v1/send*")],
            "hub_user:1",
        )
        .await
        .unwrap();
        let authority = authority(&db, HUB, FLOW).await.unwrap();

        for escape in [
            "https://api.example.com/v1/send/../../admin/keys",
            // WHATWG turns `\` into `/` for special schemes, so this is the same escape.
            r"https://api.example.com/v1/send\..\..\admin\keys",
            // …and it treats a percent-encoded dot as a dot when resolving segments.
            "https://api.example.com/v1/send/%2e%2e/%2e%2e/admin/keys",
            "https://api.example.com/v1/send/./../admin/keys",
        ] {
            assert!(
                !authority.allows_http(&url(escape)),
                "`{escape}` is fetched from /admin/keys, which nobody granted"
            );
        }

        // The twin that must keep working, or the fix would just be "block everything": the path
        // is judged RESOLVED, so a `..` that lands back inside the grant is inside the grant.
        assert!(authority.allows_http(&url("https://api.example.com/v1/send/42")));
        assert!(authority.allows_http(&url("https://api.example.com/v1/messages/../send/42")));
        // And normalisation is the same on both sides: a default port and a shouted host are the
        // same origin, not a different one.
        assert!(authority.allows_http(&url("https://API.EXAMPLE.COM:443/v1/send/42")));
    }

    /// hub#728 — a pattern is refused unless it is **written the way it will be matched**.
    ///
    /// `http://2130706433:8791/api*` IS `http://127.0.0.1:8791/api*`, and nobody reads it that way
    /// on the grants screen; `http://2852039166/latest*` is the cloud metadata service and reads
    /// like a phone number. The refusal says what the pattern really means, so an admin who wants
    /// it has to write it down in the notation everybody can read — and it is the ADDRESS guard,
    /// not the allow-list, that then refuses to dial it (that separation is deliberate: an admin
    /// may legitimately grant a LAN address, and the answer is still no at call time).
    #[tokio::test]
    async fn a_pattern_must_be_written_the_way_it_will_be_matched() {
        let db = db_with_schema().await;
        for (pattern, reads_as) in [
            ("http://2130706433:8791/api*", "http://127.0.0.1:8791/api*"),
            ("http://0x7f000001/x*", "http://127.0.0.1/x*"),
            ("http://127.1/x*", "http://127.0.0.1/x*"),
            (
                "http://2852039166/latest*",
                "http://169.254.169.254/latest*",
            ),
            // A pattern that does not say what it covers: it reads `/v1/…` and grants `/admin*`.
            (
                "https://api.example.com/v1/../admin*",
                "https://api.example.com/admin*",
            ),
            (
                r"https://api.example.com/v1\..\admin*",
                "https://api.example.com/admin*",
            ),
            // A shouted host and a default port are the same origin written twice.
            (
                "https://API.EXAMPLE.COM:443/v1*",
                "https://api.example.com/v1*",
            ),
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::Http, pattern)],
                "hub_user:1",
            )
            .await
            .expect_err("a grant nobody can read correctly is worse than no grant");
            let text = format!("{err}");
            assert!(text.contains(pattern), "{text}");
            assert!(
                text.contains(reads_as),
                "the refusal has to say what it really covers, or it is not actionable: {text}"
            );
        }

        // Credentials in the authority are not something an allow-list can reason about, and there
        // is no canonical form to suggest — that one is refused outright.
        replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Http, "https://user:pass@api.example.com/v1*")],
            "hub_user:1",
        )
        .await
        .expect_err("`https://api.example.com@evil.test` is the oldest trick there is");

        // …and everything an admin would really type is still grantable — including, deliberately,
        // an address inside the network, which the guard refuses at call time and not here.
        for ok in [
            "https://api.example.com/v1/send*",
            "http://127.0.0.1:8791/api*",
            "http://169.254.169.254/latest*",
            "http://[::1]/x*",
            "https://api.example.com/v1/send",
        ] {
            replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::Http, ok)],
                "hub_user:1",
            )
            .await
            .unwrap_or_else(|e| panic!("`{ok}` is a perfectly readable pattern: {e}"));
        }
    }

    #[tokio::test]
    async fn a_pattern_that_does_not_name_a_concrete_host_is_refused() {
        let db = db_with_schema().await;
        for pattern in [
            "*",
            "https://*",
            "https://*.example.com/x",
            "api.example.com/v1*",
            "ftp://example.com/*",
            "https://example.com",
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[GrantSpec::pair(GrantKind::Http, pattern)],
                "hub_user:1",
            )
            .await
            .expect_err(
                "a grant that does not name one host and one path prefix is no containment",
            );
            assert!(format!("{err}").contains(pattern), "{err}");
        }
    }

    // ── query grants (hub#665) ────────────────────────────────────────────────────────────────

    /// hub#665 opens the third kind. Until the agent runner existed, `query` was refused with the
    /// rest — a grant nothing enforced. Now it is the third filter over the tools the model is
    /// offered ("assembled ∩ declared by the step ∩ granted"), and it is a real gate: without it,
    /// intersecting reads with the grants would be a sentence with nothing behind it.
    #[tokio::test]
    async fn a_query_grant_opens_exactly_the_query_it_names() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Query, "sales.sale.list")],
            "hub_user:1",
        )
        .await
        .unwrap();

        let run = run_that_resolved(&db, json!({})).await;
        check_query_grant(&db, HUB, FLOW, &run, "sales.sale.list", &Params::new())
            .await
            .expect("the granted query runs");
        assert!(
            check_query_grant(&db, HUB, FLOW, &run, "sales.sale.totals", &Params::new())
                .await
                .is_err(),
            "a sibling query is a different question with the same default answer: no"
        );
        // And granting a READ never opens a WRITE, whatever they share.
        assert!(
            check_command_grant(&db, HUB, FLOW, &run, "sales.sale.create", &Params::new())
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn a_query_grant_naming_a_query_that_does_not_exist_is_refused() {
        let db = db_with_schema().await;
        let err = replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Query, "ghost.query")],
            "hub_user:1",
        )
        .await
        .expect_err("a grant naming nothing reads as authorisation on the screen");
        assert!(format!("{err}").contains("ghost.query"), "{err}");
    }

    /// The permission union has to carry the granted QUERIES too, or a query with a live grant
    /// would still be refused downstream by the permission check inside `queries::execute` — the
    /// grant would open one door and the next one would be shut.
    #[tokio::test]
    async fn the_context_permissions_include_the_granted_queries() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Query, "sales.sale.list")],
            "hub_user:1",
        )
        .await
        .unwrap();
        let permissions = authority(&db, HUB, FLOW).await.unwrap().permissions(&reg);
        assert_eq!(permissions, HashSet::from(["sales.view_sale".to_string()]));
    }

    #[tokio::test]
    async fn the_context_permissions_are_the_union_of_the_granted_commands() {
        let db = db_with_schema().await;
        let reg = registry();
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[
                GrantSpec::pair(GrantKind::Command, "sales.sale.create"),
                GrantSpec::pair(GrantKind::Command, "sales.sale.void"),
            ],
            "hub_user:1",
        )
        .await
        .unwrap();

        let permissions = authority(&db, HUB, FLOW).await.unwrap().permissions(&reg);
        assert_eq!(
            permissions,
            HashSet::from(["sales.add_sale".to_string(), "sales.void_sale".to_string()]),
            "a flow behaves downstream like a user holding exactly these, and no wildcard"
        );
        assert!(
            !permissions.contains("*"),
            "a grant never becomes a wildcard"
        );
    }

    #[test]
    fn an_unknown_grant_kind_is_refused_instead_of_dropped() {
        let err = parse_pairs(&json!([{ "kind": "commnd", "value": "sales.sale.create" }]))
            .expect_err("a typo must not become a silent denial noticed at 3 AM");
        assert!(format!("{err}").contains("command"), "{err}");
    }

    // ── hub#735: a revocation is a fact with a timestamp, and it belongs to one hub ────────────

    /// The neighbour hub, sharing this database with [`HUB`].
    const OTHER: &str = "hub-grants-neighbour";

    async fn live_grant(db: &dyn DatabaseAdapter, hub: &str, flow: &str) -> String {
        replace(
            db,
            hub,
            flow,
            &registry(),
            &[GrantSpec::pair(GrantKind::Command, "sales.sale.create")],
            "hub_user:1",
        )
        .await
        .unwrap();
        list(db, hub, flow).await.unwrap().remove(0).id
    }

    /// The whole row, unfiltered — a scoped read cannot tell «the write was refused» from «the
    /// write happened and the row is now invisible».
    async fn raw_grant(db: &dyn DatabaseAdapter, id: &str) -> Json {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        db.query("SELECT * FROM _flow_grants WHERE id = :id", &p)
            .await
            .unwrap()
            .rows
            .remove(0)
    }

    #[tokio::test]
    async fn a_revocation_names_its_hub_and_is_never_rewritten() {
        let db = db_with_schema().await;
        crate::flows::test_support::ensure_schema(&db, OTHER).await;
        let mine = live_grant(&db, HUB, FLOW).await;
        let theirs = live_grant(&db, OTHER, FLOW).await;
        let theirs_before = raw_grant(&db, &theirs).await;

        // The neighbour cannot revoke what is not its own, even naming the row by id.
        let (sql, p) = revoke_op(OTHER, &mine, "2020-01-01T00:00:00+00:00", "hub_user:9");
        db.execute(&sql, &p).await.unwrap();
        assert_eq!(
            raw_grant(&db, &mine).await["deleted_at"],
            Json::Null,
            "our grant is still live"
        );

        // Its owner can, once. The timestamp of that «once» is the audit trail.
        let (sql, p) = revoke_op(HUB, &mine, "2026-01-01T00:00:00+00:00", "hub_user:1");
        db.execute(&sql, &p).await.unwrap();
        let revoked = raw_grant(&db, &mine).await;
        assert_eq!(revoked["deleted_at"], json!("2026-01-01T00:00:00+00:00"));
        assert_eq!(revoked["revoked_by"], json!("hub_user:1"));

        // A second revocation — the shape of `replace` racing the `revoke_all` of a delete — is a
        // no-op. It must not move «until when» forward, nor rename who did it.
        let (sql, p) = revoke_op(HUB, &mine, "2026-06-06T00:00:00+00:00", "hub_user:2");
        db.execute(&sql, &p).await.unwrap();
        assert_eq!(
            raw_grant(&db, &mine).await,
            revoked,
            "the first revocation is the one that happened"
        );

        assert_eq!(
            raw_grant(&db, &theirs).await,
            theirs_before,
            "and the neighbour's grant was never in this story"
        );
    }
}
