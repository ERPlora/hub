//! **The event stream** — `GET /ws` and `GET /api/events` (hub#504, ADR-0057 extended).
//!
//! This is the channel every domain event of every module goes out on, payload and all:
//! `sale.completed`, what `cash_register` emits, what `orders` emits. Until hub#504 it asked for
//! **nothing**: on Cloud, anybody on the internet who knew the subdomain could open a socket and
//! watch the business trade — what it sells, for how much, at what time. The fix is not a new
//! authorisation model, it is the one this hub already has:
//!
//! > **Nobody reads `/ws` or `/api/events` without an API key of this hub that may read.**
//!
//! # …and a key only hears what it was given (hub#529)
//!
//! hub#504 put the door there and left the fan-out all-or-nothing: once inside, every frame of
//! every module went to everybody. So the accountant's `custom` key with read on `invoice`
//! (ADR-0057 §7) also heard `sale.completed`, the cash register and the kitchen orders, payloads
//! and all — the permission decided who entered and not what they took, which makes the module ×
//! {read, write} matrix decoration on this channel.
//!
//! [`may_receive`] is the filter, and it is **one function for both transports**. What it filters
//! on is the [`crate::state::FRAME_MODULE`] field the sink writes from
//! [`erplora_runtime::EventSource`] — the emitting module as the *dispatcher* knows it, not the
//! prefix of the event's name, which is a convention nothing verifies: a module may declare
//! `emit: ["invoice.paid"]` and hand itself another module's audience.
//!
//! # Our own app listens as the person using it (hub#2501)
//!
//! The shell — the webview that prints tickets and refreshes the dashboard — needs this channel,
//! and it has no key: it has a person's session. It asks `POST /api/events/ticket` for a ticket
//! **bound to that session** ([`TicketHolder::Session`]), and the socket it opens hears what that
//! person's role reads through the normal API ([`StreamAudience::Session`]): the frames of the
//! modules with a query their permissions let through, the hub's housekeeping frames, and the
//! hub's own named events (a flow's question names the customer) only if they administer the hub.
//! Until hub#2501 the ticket was bound to a `read_only` key the hub minted for itself, so a
//! cashier's till heard every customer, every WhatsApp and every approval of the business. There
//! is still no `if this_is_our_app` anywhere in this file: the person is the principal, exactly as
//! on the query door.
//!
//! # Ending the credential ends the channel (hub#2522)
//!
//! The audience is decided once, when the channel opens — but the credential it opened with can
//! end while it is open. Signing out, revoking a key and rotating it call
//! [`StreamLimiter::cut`] with the credential's [`Lifeline`] tag, and every channel opened with it
//! gets [`ERR_CREDENTIAL_ENDED`] as its last frame and closes. A ticket minted before its session
//! signed out opens nothing afterwards. Until hub#2522 a till that signed out, or an integration
//! whose key was revoked, kept hearing everything it heard at connect time until it reconnected.
//! Changing a person's access cuts their [`person_tag`] the same way (hub#2571).
//!
//! A session also ends **by itself**, when its time runs out (hub#2600): no door is called then, so
//! no cut is issued. The session's [`Lifeline`] carries that instant instead ([`Lifeline::ends_at`],
//! read when the ticket is minted) and the channel ends at it with the same last frame. A session
//! never lengthens with use (HUB-F136), so the instant read at mint time is the one that holds.
//!
//! # How the credential travels
//!
//! A browser cannot put a header on a WebSocket handshake, and `EventSource` cannot either. So:
//!
//! | Client | How |
//! |--------|-----|
//! | Anything that controls headers (an integration, `websocat`, `erplora-sync`) | `Authorization: Bearer erpl_live_…` on the handshake / the SSE request |
//! | The browser, on `/ws` | the **first frame**: `{"type":"auth","token":…}` — the same shape `/ws/print` uses (hub#343), and for the same reason: the query string ends up in every access log and proxy trace along the way |
//! | The browser, on `/api/events` | `?ticket=erpl_tkt_…`, because SSE has no first frame — and **only** a ticket: a key there is refused ([`ERR_KEY_IN_URL`], hub#2523) |
//!
//! **A ticket is not a key.** It is minted by `POST /api/events/ticket`, which needs a hub session,
//! and it is single-use and lives [`TICKET_TTL_SECONDS`] seconds, in memory only. That is what lets
//! the app authenticate without a long-lived secret sitting in a browser tab: an `erpl_live_…` in
//! `localStorage` would be liftable by any XSS and would open the whole read API, not just this
//! channel. It is also why a ticket in a query string is acceptable where a key never would be —
//! by the time anyone reads that log line, it is spent.
//!
//! Tickets are never persisted, so they cannot travel in a backup or a blueprint (the same
//! reasoning hub#361 used for not persisting the elevation window).
//!
//! # The refusals, each with its own code
//!
//! | Code | Status | When |
//! |------|--------|------|
//! | [`ERR_UNAUTHENTICATED`] | 401 | no credential, or one this hub does not recognise — including a key of **another hub**, whose rows are not this hub's (the *message* tells them apart, the code does not: existence is not something to leak) |
//! | [`ERR_READ_REQUIRED`] | 403 | a valid key that may not read (a `write_only` feed). It is a different answer from "who are you?" on purpose: if both refusals said the same thing, either guard could be deleted and every test would still pass |
//! | [`ERR_NOT_READY`] | — | any frame on `/ws` before the socket authenticated |
//! | [`ERR_CREDENTIAL_ENDED`] | — | the last frame of an open channel whose credential ended: the session signed out, or the key was revoked or rotated (hub#2522) |
//! | [`ERR_KEY_IN_URL`] | 400 | `/api/events?ticket=` carrying anything but a ticket — a key in the address is a key in the log, so it is refused by its shape, unresolved, even with a good header beside it (hub#2523) |
use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use axum::extract::ws::{Message, WebSocket, WebSocketUpgrade};
use axum::extract::{Query, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::sse::{Event, KeepAlive, Sse};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope};
use erplora_runtime::RequestContext;
use serde_json::{json, Value};

use crate::auth;
use crate::state::{AppState, AuthMode, WsEvent, FRAME_MODULE};

/// Marks a stream ticket apart from an API key token (`erpl_live_…`), so one door can take both
/// and neither is ever mistaken for the other.
pub const TICKET_PREFIX: &str = "erpl_tkt_";

/// How long a ticket is worth anything. Long enough for the browser to open the socket it was
/// minted for, short enough that a copy out of a log or a history is already dead.
pub const TICKET_TTL_SECONDS: i64 = 60;

/// How long a socket may stay silent before authenticating. A connection that never says who it is
/// is not a listener; it is something holding a file descriptor open.
pub const AUTH_TIMEOUT_SECONDS: u64 = 15;

/// Longest client→server frame accepted. The only frame this channel takes carries a credential
/// and nothing else, and it is accepted **before** anybody has proved who they are.
pub const MAX_FRAME_BYTES: usize = 4 * 1024;

/// No credential, or one that does not resolve here.
pub const ERR_UNAUTHENTICATED: &str = "unauthenticated";
/// A valid key that may not read anything.
pub const ERR_READ_REQUIRED: &str = "events.read_required";
/// A frame that arrived before the socket authenticated.
pub const ERR_NOT_READY: &str = "events.not_ready";
/// A frame this channel does not speak, on a socket that HAS authenticated.
pub const ERR_INVALID_FRAME: &str = "invalid_payload";
/// A peer pushing more than [`MAX_FRAME_BYTES`] at a socket that may not even be authenticated.
pub const ERR_FRAME_TOO_LARGE: &str = "events.frame_too_large";
/// The last frame of a channel whose credential ended while it was open (hub#2522): the session
/// signed out, or the key was revoked or rotated. The channel closes right after it.
pub const ERR_CREDENTIAL_ENDED: &str = "events.credential_ended";
/// Something other than a ticket in the address of `/api/events` (hub#2523): a key there is a key
/// in every access log on the way. Refused by its shape, before anything is looked up.
pub const ERR_KEY_IN_URL: &str = "events.key_in_url";

/// Who a ticket was minted for, and so who the socket it opens listens as.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TicketHolder {
    /// An API key, by id: the socket hears what the key's scope may read ([`may_receive`]).
    Key(String),
    /// A person of the hub (hub#2501): the session's user and the permissions its role had when
    /// the ticket was minted. The socket hears what those permissions read through the normal API
    /// ([`StreamAudience::Session`]) — never the hub's blanket key, which used to hand a cashier
    /// every event of the business.
    Session {
        user_id: String,
        permissions: HashSet<String>,
        /// What ends the socket (hub#2522, hub#2571), checked when the ticket was minted: the
        /// person's [`person_tag`] — their role changed, they were taken off the team — and the
        /// session's [`session_tag`] — it signed out, a device limit threw it out. The session's
        /// is missing only without a session token (`AuthMode::Dev`).
        lifelines: Vec<Lifeline>,
    },
}

/// **What a channel listens with, so that ending it ends the channel** (hub#2522).
///
/// The audience of a channel is decided once, when it opens; this is what still ties it to the
/// credential afterwards. `tag` names the credential — [`session_tag`] for a person's session,
/// [`key_tag`] for an API key — and `checked_at` is when the hub last saw it valid: for a key, when
/// the socket presented it; for a session, when its ticket was minted (the ticket is the session's
/// word, spent up to [`TICKET_TTL_SECONDS`] later). A cut issued after `checked_at` ends the
/// channel; one issued before it does not, because that check already saw the credential's new
/// state — that is what lets a rotated key reconnect with its new secret at once.
///
/// `ends_at` is when the credential runs out by itself (hub#2600): a session's expiry. Nothing cuts
/// at that instant — no door is called — so the channel watches the clock as well as the cut. `None`
/// for what does not run out: an API key, a person.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Lifeline {
    pub tag: String,
    pub checked_at: Instant,
    pub ends_at: Option<Instant>,
}

impl Lifeline {
    /// Whether the credential has run out by itself at `now`.
    fn has_run_out(&self, now: Instant) -> bool {
        self.ends_at.is_some_and(|ends_at| ends_at <= now)
    }
}

/// The monotonic instant at which the wall-clock `ends` falls, as seen now; `now` if it has passed.
fn instant_at(ends: chrono::DateTime<chrono::Utc>) -> Instant {
    let left = (ends - chrono::Utc::now())
        .to_std()
        .unwrap_or(Duration::ZERO);
    Instant::now() + left
}

/// The [`Lifeline`] tag of a person's session: a digest of its token, so the hub never keeps a
/// second copy of a live credential in memory to be able to find it again.
pub fn session_tag(session_token: &str) -> String {
    use sha2::{Digest, Sha256};
    let digest = Sha256::digest(session_token.as_bytes());
    let hex: String = digest.iter().map(|b| format!("{b:02x}")).collect();
    format!("session:{hex}")
}

/// The [`Lifeline`] tag of a person of the hub (hub#2571): what they may hear was decided by their
/// role when their channel opened, so changing the role or taking them off the team ends every
/// channel they hold, on every device. By hub as well as by id: one process can serve several hubs
/// (ADR-0005), and a cut in one must never close a channel of the other.
pub fn person_tag(hub_id: &str, user_id: &str) -> String {
    format!("person:{hub_id}:{user_id}")
}

/// The [`Lifeline`] tag of an API key, by id — every secret the key ever had, old and new.
pub fn key_tag(key_id: &str) -> String {
    format!("key:{key_id}")
}

/// One minted, not yet spent, stream ticket.
struct Ticket {
    /// The hub it was minted in. One process can serve several (ADR-0005), so a ticket that
    /// forgot this would be a door between tenants.
    hub_id: String,
    holder: TicketHolder,
    expires_at: i64,
}

/// The short-lived tickets this process has minted. In memory on purpose: a credential that
/// survives a restart is a credential that can be found later, and a hub is one process.
#[derive(Default)]
pub struct StreamTickets {
    inner: Mutex<HashMap<String, Ticket>>,
}

impl std::fmt::Debug for StreamTickets {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Never print the tickets themselves: they are bearer credentials.
        let held = self.inner.lock().map(|t| t.len()).unwrap_or(0);
        write!(f, "StreamTickets({held} outstanding)")
    }
}

impl StreamTickets {
    /// Mints a ticket for `key_id` in `hub_id`, valid for [`TICKET_TTL_SECONDS`] from `now`.
    pub fn mint_at(&self, hub_id: &str, key_id: &str, now: i64) -> String {
        self.mint_for_at(hub_id, TicketHolder::Key(key_id.to_string()), now)
    }

    /// Mints a ticket for `holder` in `hub_id`, valid for [`TICKET_TTL_SECONDS`] from `now`.
    pub fn mint_for_at(&self, hub_id: &str, holder: TicketHolder, now: i64) -> String {
        let ticket = format!("{TICKET_PREFIX}{}", random_ticket_secret());
        if let Ok(mut held) = self.inner.lock() {
            // Sweep what nobody came back for, so a hub that runs for months does not grow a map
            // of dead tickets.
            held.retain(|_, t| t.expires_at > now);
            held.insert(
                ticket.clone(),
                Ticket {
                    hub_id: hub_id.to_string(),
                    holder,
                    expires_at: now + TICKET_TTL_SECONDS,
                },
            );
        }
        ticket
    }

    /// Spends a ticket: `Some(holder)` once, and never again. A ticket of another hub, or an
    /// expired one, resolves to nothing **and is not spent** — refusing it must not be a way to
    /// burn somebody else's ticket.
    pub fn redeem_at(&self, ticket: &str, hub_id: &str, now: i64) -> Option<TicketHolder> {
        let mut held = self.inner.lock().ok()?;
        let found = held.get(ticket)?;
        if found.hub_id != hub_id || found.expires_at <= now {
            return None;
        }
        held.remove(ticket).map(|t| t.holder)
    }

    pub fn mint(&self, hub_id: &str, key_id: &str) -> String {
        self.mint_at(hub_id, key_id, chrono::Utc::now().timestamp())
    }

    /// Mints a ticket for a person's session (hub#2501): the socket it opens listens with the
    /// permissions of `ctx`, not with any key, and closes when the session ends (hub#2522) or runs
    /// out (hub#2600), or the person's access changes (hub#2571). `session` is the session's token
    /// and when it runs out, if it does. `checked_at` is when `ctx` was about to be read: taken
    /// before, so a change that lands while it is read counts as after the check.
    pub fn mint_session(
        &self,
        hub_id: &str,
        ctx: &RequestContext,
        session: Option<(&str, Option<Instant>)>,
        checked_at: Instant,
    ) -> String {
        let mut lifelines = vec![Lifeline {
            tag: person_tag(hub_id, &ctx.user_id),
            checked_at,
            ends_at: None,
        }];
        if let Some((token, ends_at)) = session {
            lifelines.push(Lifeline {
                tag: session_tag(token),
                checked_at,
                ends_at,
            });
        }
        self.mint_for_at(
            hub_id,
            TicketHolder::Session {
                user_id: ctx.user_id.clone(),
                permissions: ctx.permissions.clone(),
                lifelines,
            },
            chrono::Utc::now().timestamp(),
        )
    }

    pub fn redeem(&self, ticket: &str, hub_id: &str) -> Option<TicketHolder> {
        self.redeem_at(ticket, hub_id, chrono::Utc::now().timestamp())
    }

    /// How many minted tickets are still held. Only the sweep's own test needs this: a map that
    /// only ever grows is the failure a garbage collector is supposed to prevent.
    pub fn outstanding(&self) -> usize {
        self.inner.lock().map(|held| held.len()).unwrap_or(0)
    }
}

/// 32 random bytes in hex — literally the generator an API key secret uses. A ticket is
/// short-lived, which is not the same as guessable.
fn random_ticket_secret() -> String {
    erplora_runtime::api_keys::random_secret()
}

/// The most simultaneous live connections a single API key may hold on this channel (hub#531).
///
/// A hub is one container per business (ADR-0201): there is nowhere to scale to. A key that opens
/// an unbounded number of sockets — each carrying a `broadcast::Receiver` (256-frame buffer) and a
/// task — exhausts the hub's descriptors or memory and **stops the till**, which in a POS is worse
/// than a data leak. The app rarely holds more than a handful (one per tab/device); a reconnection
/// bug that forgets to close the old socket is what reaches the ceiling.
pub const MAX_STREAMS_PER_KEY: usize = 16;

/// `events.too_many_connections` — a key with read access that has opened too many simultaneous
/// sockets. A third refusal (after `unauthenticated` and `events.read_required`): the credential is
/// correct AND entitled to read, it has just opened too many things. Reusing one of the other two
/// would let the limiter be deleted with every test still green.
pub const ERR_TOO_MANY_CONNECTIONS: &str = "events.too_many_connections";

/// Counts the live stream connections held by each API key, so one credential cannot exhaust the
/// hub by opening N sockets (hub#531). Lives in `AppState` next to [`StreamTickets`], in memory:
/// like tickets, a count that survives a restart is a count nobody trusts.
///
/// The guard ([`StreamSlot`]) is the only public API: `acquire` it when a socket authenticates, and
/// it decrements on its own when the socket goes away — on a clean close, on an error, on a panic,
/// on the auth-timeout. A counter that only ever goes up is a ceiling that ends up locking the hub
/// out of its own channel, which is exactly the failure this exists to prevent.
///
/// It is also where a credential's end reaches the channels it opened (hub#2522): every live
/// channel holds a [`CutWatch`] on its [`Lifeline`], and [`StreamLimiter::cut`] — called by the
/// doors that end a credential: sign-out, revoking a key, rotating it — closes all of them.
#[derive(Default)]
pub struct StreamLimiter {
    inner: Mutex<HashMap<String, usize>>,
    cuts: Mutex<Cuts>,
}

/// How long a cut is remembered. A credential is checked before its channel registers — a key
/// when the socket presents it (milliseconds), a session when its ticket is minted (up to
/// [`TICKET_TTL_SECONDS`] earlier) — so a cut that lands in between must still be there when the
/// channel registers. Twice the ticket's life covers both with room to spare.
const CUT_MEMORY: Duration = Duration::from_secs(2 * TICKET_TTL_SECONDS as u64);

/// The live channels by [`Lifeline`] tag, and the tags cut recently.
#[derive(Default)]
struct Cuts {
    /// Tag → (how many channels watch it, the signal that ends them).
    live: HashMap<String, (usize, Arc<tokio::sync::watch::Sender<bool>>)>,
    /// Tag → when it was cut. Swept on every cut, after [`CUT_MEMORY`].
    ended: HashMap<String, Instant>,
}

impl Cuts {
    fn ended_after(&self, lifeline: &Lifeline) -> bool {
        self.ended
            .get(&lifeline.tag)
            .is_some_and(|cut_at| *cut_at >= lifeline.checked_at)
    }
}

impl std::fmt::Debug for StreamLimiter {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        let open = self
            .inner
            .lock()
            .map(|m| m.values().sum::<usize>())
            .unwrap_or(0);
        write!(f, "StreamLimiter({open} open)")
    }
}

impl StreamLimiter {
    /// Reserves a slot for `key_id`. Returns a guard that releases the slot when dropped, or `None`
    /// if `key_id` already holds [`MAX_STREAMS_PER_KEY`] live connections.
    ///
    /// The guard's `Drop` is the whole safety: whatever path the socket takes out — `break`, an
    /// `Err`, a `select!` arm that returns, a panic in the loop — the slot is released. Without that
    /// the counter only goes up and the limit becomes a denial-of-service against the hub's owner.
    pub fn acquire(self: &Arc<Self>, key_id: &str) -> Option<StreamSlot> {
        let mut held = self.inner.lock().ok()?;
        let count = held.entry(key_id.to_string()).or_insert(0);
        if *count >= MAX_STREAMS_PER_KEY {
            return None;
        }
        *count += 1;
        Some(StreamSlot {
            limiter: Arc::clone(self),
            key_id: key_id.to_string(),
        })
    }

    /// Ends every live channel opened with the credential `tag` names ([`session_tag`],
    /// [`key_tag`]) and remembers the cut for [`CUT_MEMORY`], so a channel whose credential was
    /// checked before this instant and has not registered yet is ended as it registers. Call it
    /// **after** the credential's new state is stored: a check that starts after the cut must see
    /// it. Returns how many channels were told.
    pub fn cut(&self, tag: &str) -> usize {
        // A poisoned lock is recovered, never skipped: a cut that silently does nothing is the
        // hole this exists to close.
        let mut cuts = self.cuts.lock().unwrap_or_else(|p| p.into_inner());
        let now = Instant::now();
        cuts.ended
            .retain(|_, cut_at| now.duration_since(*cut_at) < CUT_MEMORY);
        cuts.ended.insert(tag.to_string(), now);
        match cuts.live.remove(tag) {
            Some((watching, signal)) => {
                signal.send_replace(true);
                watching
            }
            None => 0,
        }
    }

    /// Whether `lifeline`'s credential was cut after it was checked, or has run out (hub#2600) —
    /// the socket must not open.
    pub fn has_ended(&self, lifeline: &Lifeline) -> bool {
        if lifeline.has_run_out(Instant::now()) {
            return true;
        }
        let cuts = self.cuts.lock().unwrap_or_else(|p| p.into_inner());
        cuts.ended_after(lifeline)
    }

    /// Ties a channel to its credential: the returned [`CutWatch`] resolves when the credential is
    /// [`cut`](Self::cut) — at once, if that already happened after `lifeline` was checked — or
    /// when it runs out ([`Lifeline::ends_at`]). Hold it for the life of the channel; dropping it is
    /// what forgets the channel.
    pub fn watch(self: &Arc<Self>, lifeline: Lifeline) -> CutWatch {
        let mut cuts = self.cuts.lock().unwrap_or_else(|p| p.into_inner());
        if cuts.ended_after(&lifeline) {
            let (_, ended) = tokio::sync::watch::channel(true);
            return CutWatch {
                limiter: Arc::clone(self),
                tag: lifeline.tag,
                signal: None,
                ended,
                ends_at: lifeline.ends_at,
            };
        }
        let entry = cuts.live.entry(lifeline.tag.clone()).or_insert_with(|| {
            let (signal, _) = tokio::sync::watch::channel(false);
            (0, Arc::new(signal))
        });
        entry.0 += 1;
        CutWatch {
            limiter: Arc::clone(self),
            tag: lifeline.tag,
            ended: entry.1.subscribe(),
            signal: Some(Arc::clone(&entry.1)),
            ends_at: lifeline.ends_at,
        }
    }

    /// How many live connections `key_id` holds. Only tests need this: the limiter is correct when
    /// its observable effect (a 17th socket is refused) is correct, not when a number is.
    pub fn held_by(&self, key_id: &str) -> usize {
        self.inner
            .lock()
            .map(|m| *m.get(key_id).unwrap_or(&0))
            .unwrap_or(0)
    }
}

/// A held stream slot. Dropping it decrements the limiter — the only way the count ever goes down.
/// Held across the whole life of a socket so the release tracks the socket, not a code path.
pub struct StreamSlot {
    limiter: Arc<StreamLimiter>,
    key_id: String,
}

impl Drop for StreamSlot {
    fn drop(&mut self) {
        if let Ok(mut held) = self.limiter.inner.lock() {
            if let Some(count) = held.get_mut(&self.key_id) {
                *count = count.saturating_sub(1);
                if *count == 0 {
                    held.remove(&self.key_id);
                }
            }
        }
    }
}

/// A live channel's hold on its credential ([`StreamLimiter::watch`], hub#2522).
pub struct CutWatch {
    limiter: Arc<StreamLimiter>,
    tag: String,
    /// The signal this channel was registered under; `None` for one born already cut.
    signal: Option<Arc<tokio::sync::watch::Sender<bool>>>,
    ended: tokio::sync::watch::Receiver<bool>,
    /// When the credential runs out by itself ([`Lifeline::ends_at`], hub#2600).
    ends_at: Option<Instant>,
}

impl CutWatch {
    /// Resolves once the credential has been cut or has run out. Cancel-safe, so it can sit in a
    /// `select!`: the deadline is an absolute instant, not a timer that restarts on every poll.
    pub async fn ended(&mut self) {
        // The sender lives as long as this watch holds `signal`, so `Err` cannot happen; if it
        // ever did, the safe reading of "nobody can tell me any more" is that the channel ends.
        let cut = self.ended.wait_for(|ended| *ended);
        match self.ends_at {
            Some(ends_at) => tokio::select! {
                _ = cut => {}
                _ = tokio::time::sleep_until(tokio::time::Instant::from_std(ends_at)) => {}
            },
            None => {
                let _ = cut.await;
            }
        }
    }
}

impl Drop for CutWatch {
    fn drop(&mut self) {
        let Some(signal) = &self.signal else { return };
        let mut cuts = self.limiter.cuts.lock().unwrap_or_else(|p| p.into_inner());
        // Only the entry this watch registered under: after a cut, the same tag may already name
        // the channels of a NEW check (a rotated key reconnecting), whose count is not ours.
        if let Some((watching, live)) = cuts.live.get_mut(&self.tag) {
            if Arc::ptr_eq(live, signal) {
                *watching = watching.saturating_sub(1);
                if *watching == 0 {
                    cuts.live.remove(&self.tag);
                }
            }
        }
    }
}

/// Resolves when any of `watches` is cut; never, for a channel with nothing to watch.
async fn credential_ended(watches: &mut [CutWatch]) {
    if watches.is_empty() {
        return std::future::pending().await;
    }
    futures_util::future::select_all(watches.iter_mut().map(|w| Box::pin(w.ended()))).await;
}

/// The last frame of a channel whose credential ended ([`ERR_CREDENTIAL_ENDED`]).
fn credential_ended_frame() -> Value {
    json!({
        "type": "stream.error",
        "code": ERR_CREDENTIAL_ENDED,
        "message": "the credential this channel was opened with has ended (signed out, expired, revoked, rotated, or the person's access changed)",
    })
}

/// **The one filter: what a listener may be sent** (hub#529).
///
/// hub#504 decided *who enters*; this decides *what they take*. Without it the per-module matrix
/// of ADR-0057 was decoration on this channel: a `custom` key with read on `invoice` — the
/// accountant's key of §7 — also heard every `sale.completed`, the cash register and the kitchen
/// orders, payloads included.
///
/// | Key | Gets |
/// |-----|------|
/// | `full` / `read_only` (blanket) | everything, including the hub's own frames. This is the shell: the app reads with the hub's own `read_only` key, and the owner watching their own till is not who this filter is for |
/// | `custom` | exactly the modules ticked with `read` — and **nothing** that belongs to no module |
/// | `write_only` | nothing (it never gets past [`authenticate`] either; two guards that agree) |
///
/// **A frame with no [`FRAME_MODULE`] is the hub's own**: `module.installed`,
/// `module.install.progress`, `print.queued`, a flow approval, an inbound WhatsApp message. Those
/// are facts about the business as a whole, not rows of a module, and a key that was handed a list
/// of modules was never handed the hub. Refusing them is the fail-closed reading, and it is also
/// the one that survives a new core event being added by someone who never reads this file.
///
/// It is deliberately **one function** for both transports. The issue asked for that in so many
/// words: a rule written twice is a rule one copy of which can be deleted with the suite green.
pub fn may_receive(scope: &ApiKeyScope, frame: &WsEvent) -> bool {
    match scope.access {
        ApiKeyAccess::Full | ApiKeyAccess::ReadOnly => true,
        ApiKeyAccess::WriteOnly => false,
        ApiKeyAccess::Custom => match frame.get(FRAME_MODULE).and_then(Value::as_str) {
            Some(module) => scope
                .modules
                .iter()
                .any(|entry| entry.read && entry.module == module),
            None => false,
        },
    }
}

/// The hub's own frames that say nothing about anybody and that every screen needs, whoever is
/// looking at it (hub#2501): an app was installed, updated, switched on or off, removed — the
/// menu refreshes — and a ticket was queued for a print role, which carries the role and nothing
/// else (`print.rs` says so on purpose). Anything else that belongs to no module is a fact about
/// the business with content in it, and goes only to whoever can see it ([`StreamAudience`]).
fn is_housekeeping(frame: &WsEvent) -> bool {
    match frame.get("type").and_then(Value::as_str) {
        Some(kind) => kind.starts_with("module.") || kind == crate::print_ws::EVENT_JOB_QUEUED,
        None => false,
    }
}

/// **Who a live connection is talking to**, decided once when it authenticates.
///
/// | Audience | Gets |
/// |----------|------|
/// | an API key | [`may_receive`] on its scope (hub#529) |
/// | a person's session (hub#2501) | the frames of the modules their role may read through the normal API ([`erplora_runtime::Registry::modules_readable_by`] — the query door's own predicate), the hub's housekeeping frames, and the hub's own named events (a flow's question, which names the customer) only if they administer the hub, which is who the approvals tray serves |
///
/// The default grants **nothing**, so a connection that somehow reached the fan-out without
/// authenticating is sent nothing rather than everything.
#[derive(Debug, Clone)]
pub enum StreamAudience {
    Key(ApiKeyScope),
    Session {
        /// The session holds `*` (dev mode, the runtime's own contexts): it reads everything.
        wildcard: bool,
        /// It holds [`erplora_runtime::hub_users::ADMINISTER_PERMISSION`].
        administers: bool,
        /// Active modules with at least one query its permissions let through.
        modules: HashSet<String>,
    },
}

impl Default for StreamAudience {
    fn default() -> Self {
        StreamAudience::Key(ApiKeyScope::default())
    }
}

impl StreamAudience {
    /// The session audience of `ctx`, read against the modules installed right now.
    pub fn of_session(registry: &erplora_runtime::Registry, ctx: &RequestContext) -> Self {
        StreamAudience::Session {
            wildcard: ctx
                .permissions
                .contains(erplora_runtime::permissions::WILDCARD),
            administers: erplora_runtime::permissions::has(
                ctx,
                erplora_runtime::hub_users::ADMINISTER_PERMISSION,
            ),
            modules: registry.modules_readable_by(ctx),
        }
    }

    /// Whether this audience is entitled to `frame`. **One rule for both transports**: the socket
    /// loop and the SSE stream both ask here.
    pub fn may_receive(&self, frame: &WsEvent) -> bool {
        match self {
            StreamAudience::Key(scope) => may_receive(scope, frame),
            StreamAudience::Session {
                wildcard,
                administers,
                modules,
            } => {
                if *wildcard {
                    return true;
                }
                match frame.get(FRAME_MODULE).and_then(Value::as_str) {
                    Some(module) => modules.contains(module),
                    None => is_housekeeping(frame) || *administers,
                }
            }
        }
    }
}

/// What a credential that may listen is granted.
#[derive(Debug)]
pub struct StreamGrant {
    /// Whose connections the per-holder cap counts ([`StreamLimiter`]): the key's id, or
    /// `session:<user id>` for a person — so one person's tabs never lock another person out.
    pub holder_id: String,
    pub audience: StreamAudience,
    /// What the channel ends with (hub#2522, hub#2571): the key, or the person and their session.
    pub lifelines: Vec<Lifeline>,
}

/// What presenting a credential to this channel gets you.
#[derive(Debug)]
pub enum StreamAuth {
    /// A key of this hub that may read, or a person's session ticket.
    Granted(Box<StreamGrant>),
    /// No credential, or one this hub does not know. The string is the *message* — it tells
    /// "you sent none" from "yours is not valid here" without the code leaking which.
    Unauthenticated(String),
    /// A real key of this hub that may not read anything.
    ReadRequired,
    /// Something other than a ticket in the address (hub#2523). Never resolved: whether it was a
    /// real key is not something the address gets to learn.
    KeyInUrl,
}

impl StreamAuth {
    fn code(&self) -> &'static str {
        match self {
            StreamAuth::Granted(_) => "",
            StreamAuth::Unauthenticated(_) => ERR_UNAUTHENTICATED,
            StreamAuth::ReadRequired => ERR_READ_REQUIRED,
            StreamAuth::KeyInUrl => ERR_KEY_IN_URL,
        }
    }

    fn message(&self) -> String {
        match self {
            StreamAuth::Granted(_) => String::new(),
            StreamAuth::Unauthenticated(m) => m.clone(),
            StreamAuth::ReadRequired => {
                "this API key may not read: the event stream is a read".into()
            }
            StreamAuth::KeyInUrl => "the address only takes a single-use ticket from \
                 POST /api/events/ticket: send an API key in the Authorization header"
                .into(),
        }
    }

    fn status(&self) -> StatusCode {
        match self {
            StreamAuth::Granted(_) => StatusCode::OK,
            StreamAuth::Unauthenticated(_) => StatusCode::UNAUTHORIZED,
            StreamAuth::ReadRequired => StatusCode::FORBIDDEN,
            StreamAuth::KeyInUrl => StatusCode::BAD_REQUEST,
        }
    }
}

/// **The one door.** Resolves whatever credential was presented — an API key token or a stream
/// ticket — and answers whether it may listen. Every surface of this channel goes through here.
pub async fn authenticate(st: &AppState, credential: Option<&str>) -> StreamAuth {
    let credential = credential.map(str::trim).unwrap_or_default();
    if credential.is_empty() {
        return StreamAuth::Unauthenticated(
            "this channel needs an API key of this hub: none was sent".into(),
        );
    }
    // hub#2522: taken BEFORE the key is looked up, so a revocation that lands while it is being
    // verified (argon2 is slow on purpose) counts as after the check: the channel is born cut
    // when it registers (`StreamLimiter::watch`) and closes before it forwards anything.
    let checked_at = Instant::now();
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return StreamAuth::Unauthenticated(e.to_string()),
    };
    let rt = arc.read().await;

    let resolved = if credential.starts_with(TICKET_PREFIX) {
        match st.stream_tickets.redeem(credential, &hub_id) {
            Some(TicketHolder::Key(key_id)) => rt.resolve_api_key_id(&key_id).await,
            Some(TicketHolder::Session {
                user_id,
                permissions,
                lifelines,
            }) => {
                // hub#2522: a ticket minted before its session signed out is the word of a session
                // that no longer exists — and, hub#2571, one minted before the person's role changed
                // carries permissions they no longer have.
                if lifelines.iter().any(|l| st.stream_limiter.has_ended(l)) {
                    return credential_not_valid();
                }
                let ctx = RequestContext::new(hub_id.clone(), user_id.clone(), permissions);
                return StreamAuth::Granted(Box::new(StreamGrant {
                    holder_id: format!("session:{user_id}"),
                    audience: StreamAudience::of_session(rt.registry(), &ctx),
                    lifelines,
                }));
            }
            None => Ok(None),
        }
    } else {
        rt.resolve_api_key(credential).await
    };
    match resolved {
        Ok(Some(principal)) => {
            let lifeline = Lifeline {
                tag: key_tag(&principal.key_id),
                checked_at,
                ends_at: None,
            };
            if principal.scope.can_read() {
                StreamAuth::Granted(Box::new(StreamGrant {
                    holder_id: principal.key_id,
                    audience: StreamAudience::Key(principal.scope),
                    lifelines: vec![lifeline],
                }))
            } else {
                StreamAuth::ReadRequired
            }
        }
        // Unknown, revoked, wrong secret, expired ticket, or a credential of ANOTHER hub — all the
        // same answer: this hub does not know it.
        Ok(None) | Err(_) => credential_not_valid(),
    }
}

fn credential_not_valid() -> StreamAuth {
    StreamAuth::Unauthenticated(
        "this credential is not valid in this hub (unknown, revoked or expired)".into(),
    )
}

/// Credential presented on an HTTP request: the `Authorization: Bearer` header, else the `ticket`
/// query parameter (the browser's only option on `EventSource`).
///
/// hub#2523: the address takes a **ticket** and nothing else. Anything else there is refused by its
/// prefix, here and not in [`authenticate`] — so it is never resolved (the address is no oracle for
/// which keys exist) and a good header beside it does not launder it: the secret reached the access
/// log the moment the request was made, and the integration has to hear that.
fn http_credential(
    headers: &HeaderMap,
    ticket: Option<&str>,
) -> Result<Option<String>, StreamAuth> {
    let ticket = ticket.map(str::trim).filter(|t| !t.is_empty());
    if ticket.is_some_and(|t| !t.starts_with(TICKET_PREFIX)) {
        return Err(StreamAuth::KeyInUrl);
    }
    Ok(auth::api_key_token(headers).or_else(|| ticket.map(str::to_string)))
}

#[derive(serde::Deserialize, Default)]
pub struct StreamQuery {
    /// Single-use ticket from `POST /api/events/ticket`.
    pub ticket: Option<String>,
}

fn refused(auth: &StreamAuth) -> Response {
    (
        auth.status(),
        Json(json!({
            "ok": false,
            "error": { "code": auth.code(), "message": auth.message() }
        })),
    )
        .into_response()
}

/// `POST /api/events/ticket` — **the app asking the hub for its own credential.**
///
/// Authenticated by the hub session, so an anonymous browser cannot get one. The ticket is bound to
/// **that session's permissions** (hub#2501): the socket it opens hears what the person's role may
/// read, not what the hub's own blanket key may — which used to give a cashier every event of the
/// business, customers and flow questions included.
pub async fn mint_ticket(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let hub_id = st.hub_id();
    let arc = match st.runtime_for(&hub_id).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.read().await;
    // hub#2571: before the session and its role are read (see `StreamTickets::mint_session`).
    let checked_at = Instant::now();
    let ctx = match auth::require_user_session(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx,
        Err(e) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({
                    "ok": false,
                    "error": { "code": ERR_UNAUTHENTICATED, "message": e.message() }
                })),
            )
                .into_response();
        }
    };
    let session = auth::session_token(&headers);
    // hub#2600: when the session runs out, so does the channel this ticket opens. Read through the
    // same scoped door that just resolved it; a session that ran out in between is refused like
    // any other. Without sessions (`AuthMode::Dev`) there is nothing to run out.
    let ends_at = match (&st.config.auth_mode, session.as_deref()) {
        (AuthMode::Session, Some(token)) => match rt.session_expires_at(token).await {
            Ok(Some(ends)) => Some(instant_at(ends)),
            Ok(None) => {
                return (
                    StatusCode::UNAUTHORIZED,
                    Json(json!({
                        "ok": false,
                        "error": {
                            "code": ERR_UNAUTHENTICATED,
                            "message": "the session ended while the ticket was being minted",
                        }
                    })),
                )
                    .into_response();
            }
            Err(e) => {
                let (status, body) = crate::dispatch_api::error_payload(&e);
                return (status, Json(body)).into_response();
            }
        },
        _ => None,
    };
    let ticket = st.stream_tickets.mint_session(
        &hub_id,
        &ctx,
        session.as_deref().map(|token| (token, ends_at)),
        checked_at,
    );
    Json(json!({
        "ok": true,
        "data": { "ticket": ticket, "expires_in_seconds": TICKET_TTL_SECONDS }
    }))
    .into_response()
}

/// `GET /api/events` — the same channel as `/ws`, as Server-Sent Events (hub#19). Subscribes to the
/// shared `AppState.events` broadcast (no second fan-out) and emits each event as `data: <json>`,
/// the identical frame the WebSocket sends. `KeepAlive` survives the proxy's idle timeout; the
/// browser (`EventSource`) reconnects on its own — with a **fresh** ticket, since the old one is
/// spent.
pub async fn sse(
    State(st): State<AppState>,
    headers: HeaderMap,
    Query(q): Query<StreamQuery>,
) -> Response {
    let credential = match http_credential(&headers, q.ticket.as_deref()) {
        Ok(credential) => credential,
        Err(refusal) => return refused(&refusal),
    };
    let grant = match authenticate(&st, credential.as_deref()).await {
        StreamAuth::Granted(g) => g,
        refusal => return refused(&refusal),
    };
    // hub#531: the per-key cap applies to SSE too — `EventSource` reconnects on its own, and a bug
    // that spawns reconnections without closing the old one reaches the ceiling the same way.
    let slot = match st.stream_limiter.acquire(&grant.holder_id) {
        Some(s) => s,
        None => {
            return (
                StatusCode::TOO_MANY_REQUESTS,
                Json(json!({
                    "ok": false,
                    "error": {
                        "code": ERR_TOO_MANY_CONNECTIONS,
                        "message": format!("this key already holds {MAX_STREAMS_PER_KEY} live connections on this channel"),
                    }
                })),
            )
                .into_response();
        }
    };
    let rx = st.events.subscribe();
    // hub#529, hub#2501: the same filter the socket applies, from the same function. The audience
    // travels with the stream so a later frame is judged by who opened it, not by a re-read.
    let audience = grant.audience;
    // hub#2522: …and the credential travels with it too, so ending it ends the stream.
    let watches: Vec<CutWatch> = grant
        .lifelines
        .into_iter()
        .map(|l| st.stream_limiter.watch(l))
        .collect();
    let stream = futures_util::stream::unfold(
        (rx, slot, audience, watches, false),
        |(mut rx, slot, audience, mut watches, ended)| async move {
            if ended {
                // The last frame went out: end the response. `slot` and `watches` drop here.
                return None;
            }
            loop {
                tokio::select! {
                    // A cut wins over a frame queued at the same instant: nothing more goes out.
                    biased;
                    _ = credential_ended(&mut watches) => {
                        let data = credential_ended_frame().to_string();
                        return Some((
                            Ok::<Event, std::convert::Infallible>(Event::default().data(data)),
                            (rx, slot, audience, watches, true),
                        ));
                    }
                    event = rx.recv() => match event {
                        Ok(ev) => {
                            if !audience.may_receive(&ev) {
                                continue;
                            }
                            let data = serde_json::to_string(&ev).unwrap_or_else(|_| "{}".into());
                            return Some((
                                Ok(Event::default().data(data)),
                                (rx, slot, audience, watches, false),
                            ));
                        }
                        // A slow subscriber skips what it lost and carries on (as the socket does).
                        Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                        // Broadcast closed: the stream ends. `slot` drops here, releasing the count.
                        Err(tokio::sync::broadcast::error::RecvError::Closed) => return None,
                    },
                }
            }
        },
    );
    Sse::new(stream)
        .keep_alive(KeepAlive::default())
        .into_response()
}

/// `GET /ws` — the same channel over a WebSocket. A client that can set headers is authenticated
/// at the handshake; a browser sends `{"type":"auth","token":…}` as its first frame.
///
/// There is deliberately **no** `?ticket=` here: the WebSocket has a first frame, so nothing has
/// to go in the URL, and a credential in a URL is a credential in the access log.
pub async fn upgrade(
    State(st): State<AppState>,
    headers: HeaderMap,
    ws: WebSocketUpgrade,
) -> Response {
    let credential = auth::api_key_token(&headers);
    ws.on_upgrade(move |socket| stream_loop(socket, st, credential))
}

/// What the socket knows about its peer. Empty until it authenticated, and that emptiness IS the
/// "not authenticated" state — there is no boolean anybody can forget to set.
#[derive(Debug, Default)]
pub struct StreamConnection {
    /// Whose connections the cap counts: a key id, or `session:<user id>` ([`StreamGrant`]).
    key_id: String,
    /// What the credential that opened this socket may read (hub#529, hub#2501). The default
    /// grants **nothing**, so a socket that somehow reached the fan-out without going through
    /// [`handle_frame`] is sent nothing rather than everything.
    audience: StreamAudience,
    /// What the socket ends with (hub#2522, hub#2571), until the loop turns it into [`CutWatch`]es.
    lifelines: Vec<Lifeline>,
}

impl StreamConnection {
    pub fn is_ready(&self) -> bool {
        !self.key_id.is_empty()
    }

    /// Whether this socket is entitled to `frame`. Delegates to [`may_receive`] — the socket loop
    /// must not grow a second copy of the rule.
    pub fn may_receive(&self, frame: &WsEvent) -> bool {
        self.audience.may_receive(frame)
    }
}

/// A frame to send back, and whether the socket survives it.
pub struct Reply {
    pub frame: Value,
    pub keep_open: bool,
}

/// Handles one client frame. Split from the socket loop so the guard is testable without a
/// transport — and so the test drives the **same** function the transport does.
pub async fn handle_frame(st: &AppState, conn: &mut StreamConnection, raw: &str) -> Reply {
    if raw.len() > MAX_FRAME_BYTES {
        return Reply {
            frame: json!({
                "type": "stream.error",
                "code": ERR_FRAME_TOO_LARGE,
                "message": format!("a frame of {} bytes is over the {MAX_FRAME_BYTES} byte cap for this channel", raw.len()),
            }),
            keep_open: false,
        };
    }
    let parsed: Value = match serde_json::from_str(raw) {
        Ok(v) => v,
        Err(_) => Value::Null,
    };
    let frame_type = parsed
        .get("type")
        .and_then(Value::as_str)
        .unwrap_or_default();
    if frame_type != "auth" || conn.is_ready() {
        // This channel speaks ONE client frame, ONCE. Before `auth` that is an unauthenticated peer
        // trying its luck and the socket goes; after it, a client talking nonsense on a channel
        // that only listens — two different facts, so two different answers. A second `auth` is
        // the second kind (hub#2501): a socket keeps the audience it opened with, so a cashier's
        // socket cannot be widened by presenting somebody else's key.
        let (code, message) = if conn.is_ready() {
            (
                ERR_INVALID_FRAME,
                "this channel only pushes: there is nothing to say on it after `auth`",
            )
        } else {
            (
                ERR_NOT_READY,
                "authenticate first: {\"type\":\"auth\",\"token\":…}",
            )
        };
        return Reply {
            frame: json!({ "type": "stream.error", "code": code, "message": message }),
            keep_open: conn.is_ready(),
        };
    }
    let token = parsed
        .get("token")
        .and_then(Value::as_str)
        .unwrap_or_default();
    match authenticate(st, Some(token)).await {
        StreamAuth::Granted(grant) => {
            let StreamGrant {
                holder_id,
                audience,
                lifelines,
            } = *grant;
            conn.key_id = holder_id;
            // hub#529: what this socket may be sent is decided here, once, from the credential it
            // presented. What a later change of that credential does is the lifeline's job
            // (hub#2522): ending it closes the socket, so the audience is never re-read per frame.
            conn.audience = audience;
            conn.lifelines = lifelines;
            Reply {
                frame: json!({ "type": "stream.ready" }),
                keep_open: true,
            }
        }
        refusal => Reply {
            frame: json!({
                "type": "stream.error",
                "code": refusal.code(),
                "message": refusal.message(),
            }),
            // A socket that cannot authenticate has nothing else to say.
            keep_open: false,
        },
    }
}

/// The socket loop: **nothing is fanned out before the connection is authenticated**, and a socket
/// that never authenticates is dropped.
async fn stream_loop(mut socket: WebSocket, st: AppState, handshake_credential: Option<String>) {
    let mut conn = StreamConnection::default();
    // The per-key connection cap (hub#531). `None` until the socket authenticates; once it does, it
    // holds a slot that is released when `stream_loop` returns — on a clean close, an error, a
    // panic, the auth-timeout, any `break`. Without a guard tied to the loop's lifetime the counter
    // only goes up and the limit becomes a denial-of-service against the hub's owner.
    let mut slot: Option<StreamSlot> = None;
    // hub#2522: the socket's hold on its credential, taken with the slot. Ending the credential
    // (sign-out, revoked or rotated key) or, hub#2571, changing the person's access resolves it and
    // the loop closes the socket.
    let mut watches: Vec<CutWatch> = Vec::new();
    // Subscribed BEFORE authenticating, and read only after: verifying a credential takes real
    // time (argon2 is slow on purpose), and a sale that happens during the handshake belongs to a
    // listener that turns out to be entitled to it. Holding the receiver is not hearing anything —
    // the fan-out arm below is gated on `is_ready()`.
    let mut rx = st.events.subscribe();
    // A client that could set a header is already authenticated; it never sends a frame.
    if let Some(credential) = handshake_credential {
        if let StreamAuth::Granted(grant) = authenticate(&st, Some(&credential)).await {
            // hub#531: a correct, read-entitled key that has opened too many sockets is a third
            // refusal. The handshake path closes the socket right here.
            match st.stream_limiter.acquire(&grant.holder_id) {
                Some(s) => {
                    slot = Some(s);
                    let StreamGrant {
                        holder_id,
                        audience,
                        lifelines,
                    } = *grant;
                    watches = lifelines
                        .into_iter()
                        .map(|l| st.stream_limiter.watch(l))
                        .collect();
                    conn.key_id = holder_id;
                    // hub#529: the handshake path sets the audience too. Setting only the id here
                    // is exactly how a socket would end up entitled to nothing (or, before the
                    // fail-closed default, to everything).
                    conn.audience = audience;
                }
                None => {
                    let frame = json!({
                        "type": "stream.error",
                        "code": ERR_TOO_MANY_CONNECTIONS,
                        "message": format!("this key already holds {MAX_STREAMS_PER_KEY} live connections on this channel"),
                    });
                    let _ = socket.send(Message::Text(frame.to_string())).await;
                    return;
                }
            }
        }
    }
    let auth_deadline =
        tokio::time::Instant::now() + tokio::time::Duration::from_secs(AUTH_TIMEOUT_SECONDS);

    loop {
        tokio::select! {
            // A cut wins over a frame queued at the same instant: nothing more goes out.
            biased;
            // hub#2522: the credential ended while the socket was open. Say why, and close.
            _ = credential_ended(&mut watches), if !watches.is_empty() => {
                let frame = credential_ended_frame().to_string();
                let _ = socket.send(Message::Text(frame)).await;
                let _ = socket.send(Message::Close(None)).await;
                break;
            }
            incoming = socket.recv() => {
                let Some(Ok(message)) = incoming else { break };
                let text = match message {
                    Message::Text(t) => t,
                    Message::Close(_) => break,
                    _ => continue,
                };
                let Reply { frame, keep_open } = handle_frame(&st, &mut conn, &text).await;
                let payload = serde_json::to_string(&frame).unwrap_or_else(|_| "{}".into());
                if socket.send(Message::Text(payload)).await.is_err() || !keep_open {
                    break;
                }
                // hub#531: the first-frame auth path. `handle_frame` set `conn.key_id` on success;
                // acquire the limiter slot now, or refuse if the key holds too many. This runs only
                // once per socket (the handshake path acquired earlier, and `handle_frame` refuses
                // any second `auth`).
                if conn.is_ready() && slot.is_none() {
                    match st.stream_limiter.acquire(&conn.key_id) {
                        Some(s) => {
                            slot = Some(s);
                            watches = std::mem::take(&mut conn.lifelines)
                                .into_iter()
                                .map(|l| st.stream_limiter.watch(l))
                                .collect();
                        }
                        None => {
                            let frame = json!({
                                "type": "stream.error",
                                "code": ERR_TOO_MANY_CONNECTIONS,
                                "message": format!("this key already holds {MAX_STREAMS_PER_KEY} live connections on this channel"),
                            });
                            let _ = socket.send(Message::Text(frame.to_string())).await;
                            break;
                        }
                    }
                }
            }
            event = rx.recv(), if conn.is_ready() => {
                match event {
                    Ok(ev) => {
                        // hub#529: entitled to listen is not entitled to THIS. Same filter as SSE.
                        if !conn.may_receive(&ev) {
                            continue;
                        }
                        let text = serde_json::to_string(&ev).unwrap_or_else(|_| "{}".into());
                        if socket.send(Message::Text(text)).await.is_err() {
                            break;
                        }
                    }
                    Err(tokio::sync::broadcast::error::RecvError::Lagged(_)) => continue,
                    Err(_) => break,
                }
            }
            _ = tokio::time::sleep_until(auth_deadline), if !conn.is_ready() => {
                let frame = json!({
                    "type": "stream.error",
                    "code": ERR_UNAUTHENTICATED,
                    "message": "no credential within the handshake window",
                }).to_string();
                let _ = socket.send(Message::Text(frame)).await;
                break;
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::AuthMode;
    use erplora_db::testutil::TestDb;
    use erplora_runtime::api_keys::{ApiKeyAccess, ApiKeyScope};
    use erplora_runtime::Runtime;

    const HUB_ID: &str = "hub-events";
    const NEIGHBOUR_ID: &str = "hub-next-door";

    fn config(hub_id: &str) -> crate::HubConfig {
        let temp =
            std::env::temp_dir().join(format!("erplora-event-stream-{}", std::process::id()));
        crate::HubConfig {
            hub_id: hub_id.into(),
            cloud_base_url: "https://example.invalid".into(),
            module_cache: temp.join("modules-cache"),
            auth_mode: AuthMode::Session,
            jwt_public_key: None,
            cloud_api_token: Some("machine-secret".into()),
            device_trust_enforce: false,
            media_dir: temp,
            sector: None,
            dev_mode: false,
            dev_modules_dir: None,
            module_trusted_keys: Vec::new(),
            // hub#376: this hub is not an ephemeral demo.
            demo: false,
        }
    }

    /// Two hubs **in one database** (ADR-0005: they share it) so the isolation tests have a
    /// neighbour that is alive and populated during the refusal, not one that was deleted first —
    /// a query missing its `hub_id` passes that version of the test just as well.
    struct Fixture {
        st: AppState,
        neighbour: AppState,
        session: String,
    }

    async fn fixture() -> Fixture {
        let db = TestDb::new().await;
        let rt = Runtime::with_hub_id(Box::new(db.adapter().await), HUB_ID);
        rt.ensure_system_tables().await.unwrap();
        let user = rt
            .create_user("Cashier", "1111", "employee", None)
            .await
            .unwrap();
        let session = rt.create_session(&user, 3600, None).await.unwrap();

        let neighbour_rt = Runtime::with_hub_id(Box::new(db.adapter().await), NEIGHBOUR_ID);
        neighbour_rt.ensure_system_tables().await.unwrap();

        Fixture {
            st: AppState::with_config(rt, config(HUB_ID)),
            neighbour: AppState::with_config(neighbour_rt, config(NEIGHBOUR_ID)),
            session,
        }
    }

    /// Creates a key in `st` and returns its token.
    async fn key_with(st: &AppState, access: ApiKeyAccess) -> String {
        let arc = st.runtime_for(&st.hub_id()).await.unwrap();
        let rt = arc.read().await;
        rt.create_api_key(
            "Integration",
            &ApiKeyScope::blanket(access),
            60,
            "hub_user:1",
        )
        .await
        .unwrap()
        .secret
    }

    async fn send(st: &AppState, conn: &mut StreamConnection, frame: Value) -> Reply {
        handle_frame(st, conn, &frame.to_string()).await
    }

    fn auth_frame(token: &str) -> Value {
        json!({ "type": "auth", "token": token })
    }

    // ── Who may listen ────────────────────────────────────────────────────────────────────────

    /// **The hole.** An anonymous socket used to be subscribed to every domain event of every
    /// module the moment it connected. Now it is not even subscribed: `is_ready()` is what gates
    /// the fan-out arm of the loop.
    #[tokio::test]
    async fn a_socket_without_a_credential_is_never_subscribed() {
        let f = fixture().await;
        let mut conn = StreamConnection::default();

        let r = send(&f.st, &mut conn, auth_frame("")).await;
        assert_eq!(r.frame["code"], ERR_UNAUTHENTICATED);
        assert!(!r.keep_open, "a socket that cannot authenticate is hung up");
        assert!(!conn.is_ready(), "and it is NOT listening");
    }

    /// A peer that skips the handshake and starts talking gets its own refusal — and stays
    /// unsubscribed. Without this, "authenticate later" would be a way to never authenticate.
    #[tokio::test]
    async fn a_frame_before_the_credential_is_refused_with_its_own_code() {
        let f = fixture().await;
        let mut conn = StreamConnection::default();

        let r = send(&f.st, &mut conn, json!({ "type": "subscribe" })).await;
        assert_eq!(r.frame["code"], ERR_NOT_READY);
        assert!(!r.keep_open);
        assert!(!conn.is_ready());
    }

    /// Once authenticated, nonsense is nonsense — not "you are not authenticated". Same code as an
    /// unparseable frame anywhere else in the hub, and the socket survives it: a listener that
    /// fat-fingered a frame has not stopped being entitled to the channel.
    #[tokio::test]
    async fn an_authenticated_socket_that_talks_nonsense_is_told_so_and_kept() {
        let f = fixture().await;
        let token = key_with(&f.st, ApiKeyAccess::ReadOnly).await;
        let mut conn = StreamConnection::default();
        send(&f.st, &mut conn, auth_frame(&token)).await;

        let r = send(&f.st, &mut conn, json!({ "type": "subscribe" })).await;
        assert_eq!(r.frame["code"], ERR_INVALID_FRAME);
        assert!(r.keep_open);
        assert!(conn.is_ready(), "it does not lose the channel over a typo");
    }

    /// A peer can push bytes before proving anything, so the cap is checked first and the socket
    /// goes. Its own code: "too big" is not "who are you?".
    ///
    /// The boundary is asserted in **both** directions on purpose: a cap that is one byte tight
    /// rejects the largest legitimate frame, and that failure would look like a credential problem
    /// to whoever hits it.
    #[tokio::test]
    async fn an_oversized_frame_is_cut_off_before_it_is_even_parsed() {
        let f = fixture().await;
        let mut conn = StreamConnection::default();

        let huge = "x".repeat(MAX_FRAME_BYTES + 1);
        let r = handle_frame(&f.st, &mut conn, &huge).await;
        assert_eq!(r.frame["code"], ERR_FRAME_TOO_LARGE);
        assert!(!r.keep_open);
        assert!(!conn.is_ready());

        // Exactly at the cap is INSIDE it: this frame gets parsed and answered on its merits.
        let scaffold = json!({ "type": "auth", "token": "" }).to_string();
        let padding = "a".repeat(MAX_FRAME_BYTES - scaffold.len());
        let exactly_at_the_cap = json!({ "type": "auth", "token": padding }).to_string();
        assert_eq!(exactly_at_the_cap.len(), MAX_FRAME_BYTES);
        let r = handle_frame(&f.st, &mut conn, &exactly_at_the_cap).await;
        assert_eq!(
            r.frame["code"], ERR_UNAUTHENTICATED,
            "a frame of exactly the cap is judged by its credential, not by its size"
        );
    }

    /// **A `{:?}` of the hub's state must not print bearer credentials.** `AppState` is `Debug`,
    /// and anything that logs it would otherwise dump every live ticket — which is exactly the
    /// kind of leak that only shows up in somebody's log aggregator months later.
    #[test]
    fn debugging_the_ticket_store_never_prints_a_ticket() {
        let tickets = StreamTickets::default();
        let secret = tickets.mint_at(HUB_ID, "key-1", 1_000);

        let printed = format!("{tickets:?}");
        assert!(
            !printed.contains(&secret),
            "the ticket itself must never appear: {printed}"
        );
        assert!(
            printed.contains('1'),
            "…and it still has to say something useful (how many are out): {printed}"
        );
    }

    /// **The code hides which one it is; the message says it.** Sending nothing and sending
    /// something this hub does not know are different facts, and whoever is wiring an integration
    /// at 2am needs to know which. They must NOT be different *codes* — that would answer "does
    /// this key exist here?" to anyone who asks — so the whole distinction lives in the message,
    /// and a message that stopped distinguishing them would be an invisible loss.
    #[tokio::test]
    async fn the_two_unauthenticated_refusals_differ_in_the_message_not_the_code() {
        let f = fixture().await;

        let mut empty_handed = StreamConnection::default();
        let none = send(&f.st, &mut empty_handed, auth_frame("")).await;
        let mut wrong = StreamConnection::default();
        let bogus = send(&f.st, &mut wrong, auth_frame("erpl_live_dead_beef")).await;

        assert_eq!(
            none.frame["code"], bogus.frame["code"],
            "the code must not tell a stranger whether a key exists here"
        );
        let without = none.frame["message"].as_str().unwrap_or_default();
        let invalid = bogus.frame["message"].as_str().unwrap_or_default();
        assert!(
            !without.is_empty() && !invalid.is_empty(),
            "a refusal says why"
        );
        assert_ne!(without, invalid, "…and these two are not the same why");

        // And the third refusal is a third message: a key that may not read is neither of those.
        let token = key_with(&f.st, ApiKeyAccess::WriteOnly).await;
        let mut feed = StreamConnection::default();
        let refused = send(&f.st, &mut feed, auth_frame(&token)).await;
        let no_read = refused.frame["message"].as_str().unwrap_or_default();
        assert!(!no_read.is_empty());
        assert_ne!(no_read, without);
        assert_ne!(no_read, invalid);
    }

    #[tokio::test]
    async fn a_read_key_of_this_hub_opens_the_socket() {
        let f = fixture().await;
        let token = key_with(&f.st, ApiKeyAccess::ReadOnly).await;
        let mut conn = StreamConnection::default();

        let r = send(&f.st, &mut conn, auth_frame(&token)).await;
        assert_eq!(r.frame["type"], "stream.ready", "{}", r.frame);
        assert!(r.keep_open);
        assert!(conn.is_ready(), "now, and only now, it is subscribed");
    }

    /// **A valid key is not automatically a listener.** A write-only feed authenticates perfectly
    /// and still may not listen — and it is told so with a code of its own, so this guard cannot be
    /// deleted behind the identity one.
    #[tokio::test]
    async fn a_write_only_key_authenticates_and_is_still_refused() {
        let f = fixture().await;
        let token = key_with(&f.st, ApiKeyAccess::WriteOnly).await;
        let mut conn = StreamConnection::default();

        let r = send(&f.st, &mut conn, auth_frame(&token)).await;
        assert_eq!(r.frame["code"], ERR_READ_REQUIRED);
        assert_ne!(
            r.frame["code"], ERR_UNAUTHENTICATED,
            "two guards that answer the same thing are one guard"
        );
        assert!(!conn.is_ready());
    }

    /// A revoked key stops listening. The kill-switch has to reach this channel too.
    #[tokio::test]
    async fn a_revoked_key_stops_opening_the_socket() {
        let f = fixture().await;
        let token = key_with(&f.st, ApiKeyAccess::ReadOnly).await;
        let id = erplora_runtime::api_keys::parse_token(&token).unwrap().0;
        {
            let arc = f.st.runtime_for(&f.st.hub_id()).await.unwrap();
            let rt = arc.read().await;
            rt.revoke_api_key(&id).await.unwrap();
        }
        let mut conn = StreamConnection::default();
        let r = send(&f.st, &mut conn, auth_frame(&token)).await;
        assert_eq!(r.frame["code"], ERR_UNAUTHENTICATED);
        assert!(!conn.is_ready());
    }

    /// **The neighbour's key does not open this hub's stream** — and the proof that the refusal is
    /// about the hub boundary and not about the key being broken is that the neighbour's own
    /// socket opens with it, in the same database, at the same time.
    #[tokio::test]
    async fn a_key_of_another_hub_cannot_listen_here() {
        let f = fixture().await;
        let neighbour_token = key_with(&f.neighbour, ApiKeyAccess::ReadOnly).await;

        let mut here = StreamConnection::default();
        let refusal = send(&f.st, &mut here, auth_frame(&neighbour_token)).await;
        assert_eq!(refusal.frame["code"], ERR_UNAUTHENTICATED);
        assert!(!here.is_ready(), "the neighbour is not listening to us");

        let mut there = StreamConnection::default();
        let accepted = send(&f.neighbour, &mut there, auth_frame(&neighbour_token)).await;
        assert_eq!(
            accepted.frame["type"], "stream.ready",
            "the key still works in ITS hub: {}",
            accepted.frame
        );
        assert!(there.is_ready());
    }

    // ── The ticket ────────────────────────────────────────────────────────────────────────────

    #[test]
    fn a_ticket_is_spent_the_first_time_it_is_used() {
        let tickets = StreamTickets::default();
        let t = tickets.mint_at(HUB_ID, "key-1", 1_000);
        assert!(t.starts_with(TICKET_PREFIX));
        assert_eq!(
            tickets.redeem_at(&t, HUB_ID, 1_000),
            Some(TicketHolder::Key("key-1".into()))
        );
        assert_eq!(
            tickets.redeem_at(&t, HUB_ID, 1_000),
            None,
            "a second use is not a use"
        );
    }

    /// **Minting one ticket must not spend everybody else's.** `mint_at` sweeps dead tickets so a
    /// hub running for months does not grow a map of them — and a sweep that is one comparison off
    /// drops the *live* ones instead. Two tabs of the same till, or a reconnect racing the first
    /// connect, would then find their ticket gone with no way to tell that from a wrong one.
    #[test]
    fn minting_a_ticket_leaves_the_ones_already_out_alone() {
        let tickets = StreamTickets::default();
        let first = tickets.mint_at(HUB_ID, "key-1", 1_000);
        let second = tickets.mint_at(HUB_ID, "key-1", 1_001);

        assert_eq!(
            tickets.redeem_at(&first, HUB_ID, 1_001),
            Some(TicketHolder::Key("key-1".into())),
            "the first tab's ticket survived the second tab asking for one"
        );
        assert_eq!(
            tickets.redeem_at(&second, HUB_ID, 1_001),
            Some(TicketHolder::Key("key-1".into()))
        );
    }

    /// **The sweep and the redemption have to agree on «dead».** They are two comparisons on the
    /// same instant, written in opposite directions (`redeem` refuses `expires_at <= now`, the
    /// sweep keeps `expires_at > now`); if they drifted apart, the map would hold tickets nobody
    /// can ever spend — a leak whose only symptom is memory.
    #[test]
    fn the_sweep_drops_a_ticket_the_moment_it_stops_being_redeemable() {
        let tickets = StreamTickets::default();
        let dead_on_the_dot = tickets.mint_at(HUB_ID, "key-1", 1_000);
        let expiry = 1_000 + TICKET_TTL_SECONDS;
        assert_eq!(
            tickets.redeem_at(&dead_on_the_dot, HUB_ID, expiry),
            None,
            "at its expiry it is already unusable"
        );

        // Somebody asks for a ticket at that exact instant: the unusable one must not be kept.
        tickets.mint_at(HUB_ID, "key-2", expiry);
        assert_eq!(tickets.outstanding(), 1);
    }

    /// …and the sweep does happen: what nobody came back for is gone, not held for ever.
    #[test]
    fn minting_a_ticket_sweeps_the_dead_ones() {
        let tickets = StreamTickets::default();
        let abandoned = tickets.mint_at(HUB_ID, "key-1", 1_000);
        // Long after it expired, somebody asks for another one.
        tickets.mint_at(HUB_ID, "key-1", 1_000 + TICKET_TTL_SECONDS + 1);
        assert_eq!(tickets.outstanding(), 1, "only the live one is still held");
        assert_eq!(
            tickets.redeem_at(&abandoned, HUB_ID, 1_000 + TICKET_TTL_SECONDS + 1),
            None
        );
    }

    #[test]
    fn a_ticket_dies_of_old_age() {
        let tickets = StreamTickets::default();
        let t = tickets.mint_at(HUB_ID, "key-1", 1_000);
        assert_eq!(
            tickets.redeem_at(&t, HUB_ID, 1_000 + TICKET_TTL_SECONDS),
            None,
            "expiry is inclusive: at the deadline it is already gone"
        );
    }

    /// A ticket minted for one hub does not open another's stream — and being refused does **not**
    /// spend it, so a stranger cannot burn the app's ticket by guessing.
    #[test]
    fn a_ticket_of_another_hub_is_refused_without_being_spent() {
        let tickets = StreamTickets::default();
        let t = tickets.mint_at(HUB_ID, "key-1", 1_000);
        assert_eq!(tickets.redeem_at(&t, NEIGHBOUR_ID, 1_000), None);
        assert_eq!(
            tickets.redeem_at(&t, HUB_ID, 1_000),
            Some(TicketHolder::Key("key-1".into())),
            "the rightful owner can still spend it"
        );
    }

    /// **A ticket has to be unguessable, and never the same twice.** It is a bearer credential for
    /// the whole event stream: two tickets that came out equal would also collide in the map (the
    /// second would evict the first), but the reason this is asserted is the other one — a
    /// predictable ticket is a credential anybody can type.
    #[test]
    fn every_ticket_is_a_different_unguessable_string() {
        let tickets = StreamTickets::default();
        let a = tickets.mint_at(HUB_ID, "key-1", 1_000);
        let b = tickets.mint_at(HUB_ID, "key-1", 1_000);

        assert_ne!(a, b);
        assert!(
            a.len() >= TICKET_PREFIX.len() + 32,
            "a ticket that short is not carrying real entropy: {a}"
        );
        assert!(a
            .strip_prefix(TICKET_PREFIX)
            .is_some_and(|s| s.chars().all(|c| c.is_ascii_hexdigit())));
    }

    #[test]
    fn an_unknown_ticket_is_nothing() {
        let tickets = StreamTickets::default();
        assert_eq!(tickets.redeem_at("erpl_tkt_made_up", HUB_ID, 1_000), None);
    }

    /// The app's route end to end: session → ticket from the real door → socket open. This is the
    /// **only** thing standing between the shell and a dead dashboard, so it is asserted through
    /// the real door, not through a helper that fabricates an authenticated context.
    #[tokio::test]
    async fn the_app_reaches_the_stream_with_a_ticket_it_asked_for() {
        let f = fixture().await;
        let mut headers = HeaderMap::new();
        headers.insert("x-hub-session", f.session.parse().unwrap());
        let resp = mint_ticket(State(f.st.clone()), headers).await;
        assert_eq!(resp.status(), StatusCode::OK);
        let bytes = axum::body::to_bytes(resp.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: Value = serde_json::from_slice(&bytes).unwrap();
        let ticket = body["data"]["ticket"].as_str().unwrap().to_string();

        let mut conn = StreamConnection::default();
        let r = send(&f.st, &mut conn, auth_frame(&ticket)).await;
        assert_eq!(r.frame["type"], "stream.ready", "{}", r.frame);
        assert!(conn.is_ready());

        // Single use: the reconnect needs a new one.
        let mut again = StreamConnection::default();
        let second = send(&f.st, &mut again, auth_frame(&ticket)).await;
        assert_eq!(second.frame["code"], ERR_UNAUTHENTICATED);
        assert!(!again.is_ready());
    }

    // ── hub#531: per-key socket cap ─────────────────────────────────────────

    /// The limiter counts up to the cap and then refuses. Dropping a slot frees it for the next
    /// acquire — the whole point of the guard, and the failure mode if it leaks (a counter that
    /// only goes up locks the hub out of its own channel).
    #[test]
    fn limiter_releases_a_slot_when_dropped() {
        let lim = Arc::new(StreamLimiter::default());
        let k = "key-A";

        // Fill to the cap.
        let slots: Vec<StreamSlot> = (0..MAX_STREAMS_PER_KEY)
            .map(|_| lim.acquire(k).expect("slots under the cap"))
            .collect();
        assert_eq!(lim.held_by(k), MAX_STREAMS_PER_KEY);

        // The next one is refused.
        assert!(lim.acquire(k).is_none(), "the cap is enforced");

        // Dropping one frees exactly one slot.
        drop(slots);
        assert_eq!(lim.held_by(k), 0, "all slots released on drop");
        assert!(
            lim.acquire(k).is_some(),
            "a slot is available again after release"
        );
    }

    /// The cap is per key: a second key is not penalised for the first one's connections.
    #[test]
    fn limiter_caps_per_key_not_globally() {
        let lim = Arc::new(StreamLimiter::default());
        let _a = lim.acquire("key-A").unwrap();
        let _many_a: Vec<_> = (0..MAX_STREAMS_PER_KEY - 1)
            .map(|_| lim.acquire("key-A").unwrap())
            .collect();
        assert!(lim.acquire("key-A").is_none(), "key-A is at the cap");

        // key-B is untouched.
        assert_eq!(lim.held_by("key-B"), 0);
        assert!(
            lim.acquire("key-B").is_some(),
            "a different key is not blocked by key-A"
        );
    }

    /// A socket that authenticates and then disconnects (the common case: a tab closed) leaves the
    /// counter clean — verified through the limiter directly, since the WS test harness already
    /// exercises the real close path via `event_stream_ws.rs`.
    #[test]
    fn limiter_drops_to_zero_when_the_last_socket_closes() {
        let lim = Arc::new(StreamLimiter::default());
        {
            let _slot = lim.acquire("key-A").unwrap();
            assert_eq!(lim.held_by("key-A"), 1);
        } // slot drops here
        assert_eq!(
            lim.held_by("key-A"),
            0,
            "the slot was released when the scope ended"
        );
    }

    // ── hub#2522: ending a credential ends its channels ─────────────────────

    /// Whether `watch` has been cut, without waiting for it.
    fn is_cut(watch: &mut CutWatch) -> bool {
        use futures_util::FutureExt;
        watch.ended().now_or_never().is_some()
    }

    fn lifeline(tag: &str) -> Lifeline {
        Lifeline {
            tag: tag.into(),
            checked_at: Instant::now(),
            ends_at: None,
        }
    }

    #[test]
    fn a_persons_tag_names_the_hub_too() {
        // hub#2571, ADR-0005: one process serves several hubs, so a role change in one must not
        // close the channels of a person with the same id in the other.
        let lim = Arc::new(StreamLimiter::default());
        let mut here = lim.watch(lifeline(&person_tag("hub-a", "u-1")));
        let mut next_door = lim.watch(lifeline(&person_tag("hub-b", "u-1")));
        assert_eq!(lim.cut(&person_tag("hub-a", "u-1")), 1);
        assert!(is_cut(&mut here));
        assert!(!is_cut(&mut next_door));
    }

    #[test]
    fn a_cut_ends_every_channel_of_that_credential_and_no_other() {
        let lim = Arc::new(StreamLimiter::default());
        let mut till = lim.watch(lifeline("session:till"));
        let mut tab = lim.watch(lifeline("session:till"));
        let mut phone = lim.watch(lifeline("session:phone"));
        assert!(!is_cut(&mut till), "nothing was cut yet");

        assert_eq!(lim.cut("session:till"), 2, "both channels were told");

        assert!(is_cut(&mut till));
        assert!(is_cut(&mut tab));
        assert!(!is_cut(&mut phone), "another credential keeps listening");
    }

    /// The race the ticket opens: the session is checked when its ticket is minted, signs out, and
    /// only then does the channel register. It must be born cut.
    #[test]
    fn a_channel_checked_before_the_cut_is_born_cut() {
        let lim = Arc::new(StreamLimiter::default());
        let checked = lifeline("session:till");
        lim.cut("session:till");

        assert!(lim.has_ended(&checked));
        assert!(is_cut(&mut lim.watch(checked)));
    }

    /// A rotated key reconnects with its new secret at once: that check came after the cut and saw
    /// the new state, so it is not cut by the old one.
    #[test]
    fn a_channel_checked_after_the_cut_listens() {
        let lim = Arc::new(StreamLimiter::default());
        lim.cut("key:k1");
        let fresh = lifeline("key:k1");

        assert!(!lim.has_ended(&fresh));
        assert!(!is_cut(&mut lim.watch(fresh)));
    }

    /// A channel cut before a reconnection must not, on closing, forget the NEW channel of the same
    /// credential — or the next cut would find nobody to tell.
    #[test]
    fn closing_a_cut_channel_leaves_the_reconnected_one_registered() {
        let lim = Arc::new(StreamLimiter::default());
        let old = lim.watch(lifeline("key:k1"));
        lim.cut("key:k1");
        let mut reconnected = lim.watch(lifeline("key:k1"));

        drop(old);
        assert_eq!(
            lim.cut("key:k1"),
            1,
            "the reconnected channel is still known"
        );
        assert!(is_cut(&mut reconnected));
    }

    #[test]
    fn a_closed_channel_is_forgotten() {
        let lim = Arc::new(StreamLimiter::default());
        drop(lim.watch(lifeline("session:till")));
        assert_eq!(lim.cut("session:till"), 0, "nothing left to tell");
    }

    #[test]
    fn a_cut_is_forgotten_after_its_memory() {
        let lim = Arc::new(StreamLimiter::default());
        let checked = lifeline("session:old");
        lim.cut("session:old");
        // Age the cut past its memory, then cut something else: the sweep runs on every cut.
        if let Ok(mut cuts) = lim.cuts.lock() {
            let aged = Instant::now() - CUT_MEMORY - Duration::from_secs(1);
            cuts.ended.insert("session:old".into(), aged);
        }
        lim.cut("session:other");

        let cuts = lim.cuts.lock().unwrap();
        assert!(!cuts.ended.contains_key("session:old"), "swept");
        assert!(cuts.ended.contains_key("session:other"));
        drop(cuts);
        assert!(!lim.has_ended(&checked));
    }

    #[test]
    fn a_session_tag_never_carries_the_token() {
        let tag = session_tag("hub-session-secret");
        assert!(tag.starts_with("session:"));
        assert!(!tag.contains("hub-session-secret"));
        assert_eq!(tag, session_tag("hub-session-secret"), "stable");
        assert_ne!(tag, session_tag("another-session"));
    }

    // ── hub#529: what a listener may be sent ────────────────────────────────

    use erplora_runtime::api_keys::ScopeEntry;
    use erplora_runtime::EventSource;

    /// A frame built by the **production** builder, so these tests cannot drift from the wire.
    fn frame_of(source: EventSource<'_>, name: &str) -> Value {
        crate::state::event_frame(source, name, &json!({ "total_cents": 4_250 }))
    }

    fn accountant() -> ApiKeyScope {
        ApiKeyScope::custom(vec![ScopeEntry {
            module: "invoice".into(),
            read: true,
            write: false,
        }])
    }

    /// **The hole, at the filter.** A key scoped to `invoice` used to be sent everything.
    #[test]
    fn a_scoped_key_gets_its_module_and_not_the_neighbour() {
        let scope = accountant();
        assert!(may_receive(
            &scope,
            &frame_of(EventSource::Module("invoice"), "invoice.issued")
        ));
        assert!(!may_receive(
            &scope,
            &frame_of(EventSource::Module("sales"), "sale.completed")
        ));
    }

    /// **The name is not the module.** `sales` emitting `invoice.paid` is a module choosing its own
    /// event name, which nothing verifies — the filter reads who emitted, not what it is called.
    /// An implementation that split on `.` passes every other test here.
    #[test]
    fn the_filter_reads_the_emitter_not_the_event_name() {
        let scope = accountant();
        assert!(
            !may_receive(
                &scope,
                &frame_of(EventSource::Module("sales"), "invoice.paid")
            ),
            "an event NAMED after `invoice` but emitted by `sales` is `sales`'"
        );
        assert!(
            may_receive(
                &scope,
                &frame_of(EventSource::Module("invoice"), "something.else")
            ),
            "…and one emitted by `invoice` is `invoice`'s, whatever it is called"
        );
    }

    /// `write` on a module is not `read` on it. The matrix has two columns and this channel is the
    /// read one — a key ticked only for writing on `invoice` hears nothing of it.
    #[test]
    fn write_on_a_module_is_not_permission_to_listen_to_it() {
        let feed = ApiKeyScope::custom(vec![
            ScopeEntry {
                module: "invoice".into(),
                read: false,
                write: true,
            },
            ScopeEntry {
                module: "sales".into(),
                read: true,
                write: false,
            },
        ]);
        assert!(!may_receive(
            &feed,
            &frame_of(EventSource::Module("invoice"), "invoice.issued")
        ));
        assert!(may_receive(
            &feed,
            &frame_of(EventSource::Module("sales"), "sale.completed")
        ));
    }

    /// **The shell.** The app reads with the hub's own blanket `read_only` key: it hears every
    /// module and the hub's own frames too. The owner watching their own till is not who this
    /// filter is for, and a filter that caught them would show up as a dead dashboard.
    #[test]
    fn a_blanket_read_key_hears_the_whole_hub() {
        for access in [ApiKeyAccess::ReadOnly, ApiKeyAccess::Full] {
            let scope = ApiKeyScope::blanket(access);
            assert!(may_receive(
                &scope,
                &frame_of(EventSource::Module("sales"), "sale.completed")
            ));
            assert!(may_receive(
                &scope,
                &frame_of(EventSource::Core, "flow.approval.created")
            ));
            assert!(
                may_receive(
                    &scope,
                    &json!({ "type": "module.installed", "module_id": "sales" })
                ),
                "including the raw system frames the installer publishes"
            );
        }
    }

    /// **A frame of no module belongs to the hub**, and a key handed a list of modules was not
    /// handed the hub. Fail-closed on purpose: the next core event will be added by somebody who
    /// never reads this file, and it must not leak by default.
    #[test]
    fn a_scoped_key_gets_nothing_that_belongs_to_no_module() {
        let scope = accountant();
        assert!(!may_receive(
            &scope,
            &frame_of(EventSource::Core, "hub.whatsapp.message_received")
        ));
        assert!(!may_receive(
            &scope,
            &json!({ "type": "print.queued", "role": "kitchen" })
        ));
        assert!(
            !may_receive(
                &scope,
                &json!({ "type": "module.installed", "module_id": "invoice" })
            ),
            "not even one that NAMES its module in the payload: the field the filter reads is the \
             one the sink writes, and a raw system frame has none"
        );
    }

    /// A scope nobody could parse grants nothing — same reading `scope_of_row` gives it — and so
    /// does the default a socket starts with. The fan-out's fail-closed floor.
    #[test]
    fn an_empty_scope_is_sent_nothing() {
        let nothing = ApiKeyScope::default();
        assert!(!may_receive(
            &nothing,
            &frame_of(EventSource::Module("invoice"), "invoice.issued")
        ));
        assert!(!may_receive(
            &nothing,
            &frame_of(EventSource::Core, "anything")
        ));
        assert!(!StreamConnection::default()
            .may_receive(&frame_of(EventSource::Module("invoice"), "invoice.issued")));
    }

    /// A write-only feed never gets past [`authenticate`]; the filter says the same thing anyway.
    /// Two guards that agree are one that cannot be quietly bypassed by whichever path forgets the
    /// other.
    #[test]
    fn a_write_only_key_is_sent_nothing_even_if_it_got_in() {
        let feed = ApiKeyScope::blanket(ApiKeyAccess::WriteOnly);
        assert!(!may_receive(
            &feed,
            &frame_of(EventSource::Module("sales"), "sale.completed")
        ));
        assert!(!may_receive(
            &feed,
            &frame_of(EventSource::Core, "anything")
        ));
    }

    /// The frame really does carry the emitter, in the field the filter reads. If the builder
    /// stopped writing it, every `custom` key would go silent instead of over-hearing — a
    /// regression that is invisible until an integration complains.
    #[test]
    fn the_frame_carries_the_emitting_module_beside_the_payload() {
        let frame = frame_of(EventSource::Module("sales"), "sale.completed");
        assert_eq!(frame["name"], "sale.completed");
        assert_eq!(frame[crate::state::FRAME_MODULE], "sales");
        assert_eq!(frame["payload"]["total_cents"], 4_250);

        let core = frame_of(EventSource::Core, "flow.approval.created");
        assert!(
            core.get(crate::state::FRAME_MODULE).is_none(),
            "the hub's own events name no module: {core}"
        );
    }
}
