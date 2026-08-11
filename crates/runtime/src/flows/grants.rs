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
use std::collections::HashSet;

use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Value as Json};

use crate::errors::{Result, RuntimeError};
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
    pub granted_by: String,
    pub created_at: String,
}

/// The live grants of one flow, read once. Everything the gate and the context need comes from
/// this snapshot, so a step asks the database once and then answers consistently for that step.
#[derive(Debug, Clone, Default)]
pub struct Authority {
    granted: HashSet<(GrantKind, String)>,
}

impl Authority {
    /// May this flow run this command RIGHT NOW? Default-deny: an unknown flow, a flow with no
    /// grants and a flow whose grant was revoked a second ago all answer the same.
    pub fn allows_command(&self, command: &str) -> bool {
        self.granted
            .contains(&(GrantKind::Command, command.to_string()))
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
    if !field
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '_')
        || field.chars().next().is_some_and(|c| c.is_ascii_digit())
    {
        return refuse(format!(
            "`{field}` is not a column name; the recipient is ONE column of the row the query \
             returns"
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
            "SELECT kind, value FROM _flow_grants \
             WHERE hub_id = :hub_id AND flow_id = :flow_id AND deleted_at IS NULL",
            &p,
        )
        .await?;
    let granted = res
        .rows
        .iter()
        .filter_map(|r| {
            let kind = GrantKind::parse(r["kind"].as_str().unwrap_or_default())?;
            Some((kind, r["value"].as_str().unwrap_or_default().to_string()))
        })
        .collect();
    Ok(Authority { granted })
}

/// **The gate**, as the dispatcher calls it (`commands::execute_at` under
/// [`crate::commands::Origin::Automation`]). A fresh read on purpose: this is what makes a
/// revocation take effect at the next step of a running flow instead of at the next restart.
pub async fn check_command_grant(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    flow_id: &str,
    command: &str,
) -> Result<()> {
    if authority(db, hub_id, flow_id).await?.allows_command(command) {
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
    query: &str,
) -> Result<()> {
    if authority(db, hub_id, flow_id).await?.allows_query(query) {
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
    if !authority(db, hub_id, &flow_id).await?.allows_notify(channel) {
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
    wanted: &[(GrantKind, String)],
    granted_by: &str,
) -> Result<()> {
    for (kind, value) in wanted {
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
    }

    let live = list(db, hub_id, flow_id).await?;
    let now = now_rfc3339();

    for grant in &live {
        let still_wanted = wanted
            .iter()
            .any(|(k, v)| k.as_str() == grant.kind && v == &grant.value);
        if !still_wanted {
            let mut p = Params::new();
            p.insert("id".into(), json!(grant.id));
            p.insert("now".into(), json!(now));
            p.insert("by".into(), json!(granted_by));
            db.execute(
                "UPDATE _flow_grants SET deleted_at = :now, revoked_by = :by WHERE id = :id",
                &p,
            )
            .await?;
        }
    }

    for (kind, value) in wanted {
        if live
            .iter()
            .any(|g| g.kind == kind.as_str() && &g.value == value)
        {
            continue; // already live: keep the original `granted_by`/`created_at`.
        }
        let mut p = Params::new();
        p.insert("id".into(), json!(new_id()));
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("flow_id".into(), json!(flow_id));
        p.insert("kind".into(), json!(kind.as_str()));
        p.insert("value".into(), json!(value));
        p.insert("now".into(), json!(now));
        p.insert("by".into(), json!(granted_by));
        db.execute(
            "INSERT INTO _flow_grants (id, hub_id, flow_id, kind, value, created_at, granted_by) \
             VALUES (:id, :hub_id, :flow_id, :kind, :value, :now, :by)",
            &p,
        )
        .await?;
    }
    Ok(())
}

/// Live grants of a flow, oldest first.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str, flow_id: &str) -> Result<Vec<Grant>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("flow_id".into(), json!(flow_id));
    let res = db
        .query(
            "SELECT id, kind, value, granted_by, created_at FROM _flow_grants \
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
        granted_by: text("granted_by"),
        created_at: text("created_at"),
    }
}

/// Parses the `{kind, value}` pairs of a `PUT …/grants` body. An unknown kind is refused by name:
/// a typo that silently dropped a grant would be read as "denied" and the flow would fail later,
/// far from the screen where it was typed.
pub fn parse_pairs(body: &Json) -> Result<Vec<(GrantKind, String)>> {
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
        out.push((kind, value));
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

    #[tokio::test]
    async fn a_flow_with_no_grants_may_run_nothing() {
        let db = db_with_schema().await;
        let err = check_command_grant(&db, HUB, FLOW, "sales.sale.create")
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
            &[(GrantKind::Command, "sales.sale.create".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_command_grant(&db, HUB, FLOW, "sales.sale.create")
            .await
            .expect("the granted command runs");
        // A sibling command of the same module is a different question with the same answer as
        // before: no.
        assert!(check_command_grant(&db, HUB, FLOW, "sales.sale.void")
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
            &[(GrantKind::Command, "sales.sale.create".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        assert!(check_command_grant(&db, HUB, "flow-2", "sales.sale.create")
            .await
            .is_err(), "another flow of the same hub is not covered");
        assert!(check_command_grant(&db, "hub-other", FLOW, "sales.sale.create")
            .await
            .is_err(), "the same flow id in another tenant is not covered");
    }

    #[tokio::test]
    async fn revoking_is_a_soft_delete_and_takes_effect_on_the_next_read() {
        let db = db_with_schema().await;
        let reg = registry();
        let grants = [(GrantKind::Command, "sales.sale.create".to_string())];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1").await.unwrap();
        check_command_grant(&db, HUB, FLOW, "sales.sale.create").await.unwrap();

        // The owner empties the list — this is what `PUT …/grants` with `[]` does.
        replace(&db, HUB, FLOW, &reg, &[], "hub_user:2").await.unwrap();

        assert!(check_command_grant(&db, HUB, FLOW, "sales.sale.create").await.is_err());
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
        let grants = [(GrantKind::Command, "sales.sale.create".to_string())];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1").await.unwrap();
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:2").await.unwrap();

        let live = list(&db, HUB, FLOW).await.unwrap();
        assert_eq!(live.len(), 1, "saving the same screen twice is not a conflict");
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
            &[(GrantKind::Command, "ghost.command".into())],
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
                &[(GrantKind::Command, internal.into())],
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
                (GrantKind::Command, "sales.sale.create".into()),
                (GrantKind::Command, "sales._insert_sale".into()),
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
            &[(GrantKind::Command, "sales.sale.create".into())],
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
        for (kind, value) in [
            (GrantKind::Command, "sales.sale.create"),
            (GrantKind::Query, "sales.sale.list"),
            (GrantKind::Http, "https://api.example.com/v1/send*"),
            (GrantKind::Notify, "whatsapp"),
            (GrantKind::RecipientQuery, "sales.sale.list#email"),
        ] {
            replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[(kind, value.into())],
                "hub_user:1",
            )
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
                (GrantKind::Notify, "email".into()),
                (GrantKind::RecipientQuery, "sales.sale.list#email".into()),
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
            (GrantKind::Notify, "whatsapp".to_string()),
            (GrantKind::RecipientQuery, "sales.sale.list#phone".to_string()),
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
            live.iter().any(|g| g.id == id && g.kind == "recipient_query"),
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
            (GrantKind::Notify, "whatsapp".to_string()),
            (GrantKind::RecipientQuery, "sales.sale.list#phone".to_string()),
        ];
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:1").await.unwrap();
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
            &db, HUB, FLOW, "", "manual", "", &json!({}), 0, "hub_user:1",
        )
        .await
        .unwrap();
        check_notify_release(&db, HUB, &run_id, &release, Channel::Whatsapp)
            .await
            .expect("both grants alive, the message may go");

        // A release that names a grant of ANOTHER flow, or nothing at all, is not a release.
        assert!(check_notify_release(&db, HUB, &run_id, "flow_grant:made-up", Channel::Whatsapp)
            .await
            .is_err());
        assert!(check_notify_release(&db, HUB, &run_id, &id, Channel::Whatsapp)
            .await
            .is_err(), "without the prefix it names nothing");

        // Revoke the recipient grant only: the channel is still allowed and the message still
        // stops, because whose address it was is the question that was withdrawn.
        replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[(GrantKind::Notify, "whatsapp".to_string())],
            "hub_user:2",
        )
        .await
        .unwrap();
        let err = check_notify_release(&db, HUB, &run_id, &release, Channel::Whatsapp)
            .await
            .expect_err("a revoked grant stops a message that was already queued");
        assert!(format!("{err}").contains("REVOCADO"), "{err}");

        // And the mirror: recipient back, channel gone.
        replace(&db, HUB, FLOW, &reg, &grants, "hub_user:3").await.unwrap();
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
            &[(GrantKind::RecipientQuery, "sales.sale.list#phone".to_string())],
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
                &[(GrantKind::Notify, value.into())],
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
            "sales.sale.list",             // no field
            "#email",                      // no query
            "sales.sale.list#",            // no field
            "ghost.query#email",           // a query that does not exist
            "sales.sale.list#customer.email", // a path, not a column
            "sales.sale.list#*",           // not a column name either
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[(GrantKind::RecipientQuery, value.into())],
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
            &[(GrantKind::RecipientQuery, "sales.sale.list#email".into())],
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
            &[(
                GrantKind::Http,
                "https://api.example.com/v1/messages*".into(),
            )],
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
        assert!(!authority.allows_http(&url("https://evil.test/?u=https://api.example.com/v1/messages")));
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
            &[(GrantKind::Http, "https://api.example.com/v1/send*".into())],
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
            ("http://2852039166/latest*", "http://169.254.169.254/latest*"),
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
            ("https://API.EXAMPLE.COM:443/v1*", "https://api.example.com/v1*"),
        ] {
            let err = replace(
                &db,
                HUB,
                FLOW,
                &registry(),
                &[(GrantKind::Http, pattern.into())],
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
            &[(GrantKind::Http, "https://user:pass@api.example.com/v1*".into())],
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
                &[(GrantKind::Http, ok.into())],
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
                &[(GrantKind::Http, pattern.into())],
                "hub_user:1",
            )
            .await
            .expect_err("a grant that does not name one host and one path prefix is no containment");
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
            &[(GrantKind::Query, "sales.sale.list".into())],
            "hub_user:1",
        )
        .await
        .unwrap();

        check_query_grant(&db, HUB, FLOW, "sales.sale.list")
            .await
            .expect("the granted query runs");
        assert!(
            check_query_grant(&db, HUB, FLOW, "sales.sale.totals")
                .await
                .is_err(),
            "a sibling query is a different question with the same default answer: no"
        );
        // And granting a READ never opens a WRITE, whatever they share.
        assert!(check_command_grant(&db, HUB, FLOW, "sales.sale.create")
            .await
            .is_err());
    }

    #[tokio::test]
    async fn a_query_grant_naming_a_query_that_does_not_exist_is_refused() {
        let db = db_with_schema().await;
        let err = replace(
            &db,
            HUB,
            FLOW,
            &registry(),
            &[(GrantKind::Query, "ghost.query".into())],
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
            &[(GrantKind::Query, "sales.sale.list".into())],
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
                (GrantKind::Command, "sales.sale.create".into()),
                (GrantKind::Command, "sales.sale.void".into()),
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
        assert!(!permissions.contains("*"), "a grant never becomes a wildcard");
    }

    #[test]
    fn an_unknown_grant_kind_is_refused_instead_of_dropped() {
        let err = parse_pairs(&json!([{ "kind": "commnd", "value": "sales.sale.create" }]))
            .expect_err("a typo must not become a silent denial noticed at 3 AM");
        assert!(format!("{err}").contains("command"), "{err}");
    }
}
