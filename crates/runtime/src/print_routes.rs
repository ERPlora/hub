//! **Print routing** — the module says WHAT it prints, the hub decides WHERE it comes out (hub#987).
//!
//! hub#457 made the destination a row ([`crate::print_stations`]) instead of a string compared
//! character by character. It left the other half of the same diagram unbuilt:
//!
//! ```text
//!   document type ──(FK)──▶ STATION (id, name) ◀──(FK)── printer / host
//!   ^^^^^^^^^^^^^^^^^^^^^^                       ^^^^^^^^^^^^^^^^^^^^^^^
//!   THIS module (hub#987)                        print_hosts (hub#342)
//! ```
//!
//! Until this existed, the left arrow did not: `sales` shipped `role: 'receipt'` hard-coded and
//! `inventory` shipped `role: 'label'`, so **a business module was naming a merchant's peripheral**
//! — the leak the market decision of hub#457 pointed at. A module cannot know that this particular
//! restaurant sends its kitchen orders to *Grill* and its bar chits to *Barra 2*; only the hub can,
//! because only the hub is the merchant's.
//!
//! So the axis a module is competent to declare is the one it already sends in the same payload:
//! `documentType` ([`crate::print_queue::DOCUMENT_TYPES`], eight closed values). This module maps
//! that onto a station, per hub, and the mapping is the merchant's configuration — exactly Square's
//! receipts/orders/labels split and Oracle Simphony's *print class*.
//!
//! ## `role` is now an OVERRIDE, and it is deprecated
//!
//! A producer that still sends `role` gets what it asked for: it is a full override, it goes through
//! the same [`crate::print_stations::resolve`] door as before, and an unknown one is still a **422**
//! naming the stations this hub has. Nothing published breaks. What changes is that omitting `role`
//! is now the **normal** path, and the modules can stop naming hardware one PR at a time.
//!
//! ## Failing OPEN, which is the whole point of the fallback
//!
//! A job that arrives with no `role` and whose document type has no usable route **must not
//! disappear**. Toast prints to every station when the routing is empty; Odoo with an empty list
//! prints everything. The silent closed failure is Clover's and Loyverse's, and their forums are the
//! documentation of why. Here the nearest thing to "print it anyway" is [`route_for`] falling back
//! to [`crate::print_stations::PROTECTED_KEY`] — `receipt`, the one station a hub cannot delete —
//! and **never** to nowhere.
//!
//! Two ways a route stops being usable, and both fall open:
//!
//!  1. **no row** — a document type nobody ever routed (a hub seeded before the type existed);
//!  2. **a dangling row** — the station it points at was deleted afterwards.
//!
//! ⚠️ The fail-open is for a job that already got in and lost its destination. It is **not** a
//! relaxation of the door: a producer that explicitly names a station that does not exist still gets
//! the 422, because there the producer is a human or a UI and the typo has to be visible.
//!
//! Persistence: `_print_route(hub_id, document_type, station_id, updated_at, updated_by)`, **system
//! migration v50**, seeded per hub by [`ensure_routes`] from [`apply`](crate::system_migrations::apply)
//! on every boot — same reasoning as `ensure_stations`: a system migration is registered per
//! DATABASE, and the legacy pre-ADR-0201 shape (several hubs, one database) would leave the second
//! hub unrouted.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::print_stations::{self, PrintStation};
use crate::registry::now_rfc3339;

/// **The routing every hub starts with: exactly what it printed yesterday.**
///
/// This table IS the compatibility guarantee of hub#987, the way `CORE_STATIONS` was hub#457's. The
/// two producers in the published catalogue send `role: 'receipt'` (`sales`) and `role: 'label'`
/// (`inventory`), and the shell defaults to `receipt` when a caller names nothing; every entry below
/// reproduces that, so switching a module over to "send no role" changes **where nothing** comes
/// out.
///
/// It is keyed by [`crate::print_queue::DOCUMENT_TYPES`] and must stay exhaustive over it — see
/// [`tests::every_document_type_the_queue_accepts_has_a_default_route`], which is the guard.
pub const DEFAULT_ROUTES: [(&str, &str); 8] = [
    ("receipt", "receipt"),
    // The one entry that is not `receipt`, and the reason this module exists: a kitchen order goes
    // to the kitchen. `sales` should never have had to know that.
    ("kitchen_order", "kitchen"),
    ("invoice", "receipt"),
    ("delivery_note", "receipt"),
    ("barcode_label", "label"),
    ("cash_session_report", "receipt"),
    // The bill taken to the table (ADR-0141): it is handed to the customer, so it comes out where
    // the customer is — the counter — and not in the kitchen.
    ("prebill", "receipt"),
    ("generic", "receipt"),
];

/// One row of the map, resolved: the document type and the station it comes out of.
///
/// The station's `key` and `label` travel with it so a screen can paint the row without joining
/// anything, and so the answer is readable in a log.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintRoute {
    /// One of [`crate::print_queue::DOCUMENT_TYPES`].
    pub document_type: String,
    pub station_id: String,
    /// The station's wire name (`kitchen`). Empty when the row dangles — see the module docs.
    pub station_key: String,
    /// What the owner reads ("Cocina"). Empty when the row dangles.
    pub station_label: String,
}

fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "print.route".to_string(),
        detail: detail.into(),
    }
}

/// Every routed document type of this hub, ordered by document type.
///
/// A dangling row (its station was deleted) is **listed**, with empty `station_key`/`station_label`,
/// instead of being hidden: it is the row a screen has to show as broken so the merchant can repoint
/// it. Hiding it would make the map look complete while the job silently comes out somewhere else.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<PrintRoute>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let res = db
        .query(
            "SELECT r.document_type AS document_type, r.station_id AS station_id, \
                    COALESCE(s.key, '') AS station_key, COALESCE(s.label, '') AS station_label \
               FROM _print_route r \
               LEFT JOIN _print_station s ON s.id = r.station_id AND s.hub_id = r.hub_id \
              WHERE r.hub_id = :hub_id ORDER BY r.document_type",
            &p,
        )
        .await?;
    Ok(res.rows.iter().map(row_to_route).collect())
}

/// **Resolves where a document comes out, failing OPEN.**
///
/// This is the door the routing turns on, and it is deliberately the opposite shape to
/// [`crate::print_stations::resolve`]: that one **refuses** an unknown input, this one **never**
/// does. The difference is who is asking. `resolve` answers a producer that named a station, where a
/// typo has to be visible; this answers a job that named only what it *is*, where there is no typo
/// to show anybody and the only options are "some paper" or "no paper".
///
/// Returns the fallback station ([`crate::print_stations::PROTECTED_KEY`]) when the document type has
/// no route or its route dangles. The only error it can return is the one from a hub with **no
/// stations at all**, which is not a routing failure: there is genuinely nowhere for paper to come
/// out, and saying so beats pretending.
pub async fn route_for(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    document_type: &str,
) -> Result<PrintStation> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("document_type".into(), json!(document_type.trim()));
    // INNER JOIN on purpose: a row pointing at a deleted station must answer "no usable route", not
    // "a route with no station". The two ways of losing a destination collapse into one answer here
    // precisely so the fallback below is the single place that decides what happens next.
    let res = db
        .query(
            "SELECT s.id AS id, s.key AS key, s.label AS label, s.created_at AS created_at \
               FROM _print_route r \
               JOIN _print_station s ON s.id = r.station_id AND s.hub_id = r.hub_id \
              WHERE r.hub_id = :hub_id AND r.document_type = :document_type",
            &p,
        )
        .await?;
    if let Some(row) = res.rows.first() {
        return Ok(row_to_station(row));
    }
    // **Fail open.** Not a warning and not an error: paper.
    print_stations::resolve(db, hub_id, print_stations::PROTECTED_KEY).await
}

/// Points `document_type` at the station whose key is `station_key`. Upsert: a document type has
/// exactly one destination.
///
/// Both halves are validated against reality — an unknown document type would be a route no job can
/// ever match, and an unknown station a route that is born dangling. Neither is a configuration the
/// merchant meant to make, so both are 422s naming what would have worked.
pub async fn set(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    document_type: &str,
    station_key: &str,
    actor: &str,
) -> Result<PrintRoute> {
    let document_type = document_type.trim();
    if !crate::print_queue::DOCUMENT_TYPES.contains(&document_type) {
        return Err(invalid(format!(
            "unknown document type `{document_type}` (expected one of {})",
            crate::print_queue::DOCUMENT_TYPES.join(", ")
        )));
    }
    // Reuses the station door, so "which stations exist" has ONE answer and the refusal names this
    // hub's real ones — including the merchant's own.
    let station = print_stations::resolve(db, hub_id, station_key).await?;
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("document_type".into(), json!(document_type));
    p.insert("station_id".into(), json!(station.id));
    p.insert("now".into(), json!(now_rfc3339()));
    p.insert("actor".into(), json!(actor));
    db.execute(
        "INSERT INTO _print_route (hub_id, document_type, station_id, updated_at, updated_by) \
         VALUES (:hub_id, :document_type, :station_id, :now, :actor) \
         ON CONFLICT (hub_id, document_type) DO UPDATE \
           SET station_id = EXCLUDED.station_id, updated_at = EXCLUDED.updated_at, \
               updated_by = EXCLUDED.updated_by",
        &p,
    )
    .await?;
    Ok(PrintRoute {
        document_type: document_type.to_string(),
        station_id: station.id,
        station_key: station.key,
        station_label: station.label,
    })
}

/// Seeds [`DEFAULT_ROUTES`] for **this hub**. Idempotent, cheap, run on every boot from
/// [`crate::system_migrations::apply`] right after `ensure_stations` (it needs the stations to
/// exist).
///
/// **Per missing document type, never wholesale.** Unlike `ensure_stations` — which seeds only into
/// a hub with no stations at all, so a merchant who deleted `bar` does not find it back — a route is
/// not something the merchant can delete: the CRUD only re-points one. So there is no "deliberately
/// absent" route to protect, and filling the gaps one by one is what lets a document type added in a
/// later version reach its station on an existing hub instead of falling open forever.
///
/// A default whose station this hub deleted is **skipped**, not invented: re-creating `kitchen` for
/// a salon that removed it would undo the merchant's decision to get a routing table that looks
/// tidy. That gap is exactly what [`route_for`] fails open on.
///
/// Returns how many routes exist for this hub afterwards.
pub async fn ensure_routes(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<usize> {
    for (document_type, station_key) in DEFAULT_ROUTES {
        let Some(station) = print_stations::find(db, hub_id, station_key).await? else {
            continue; // the merchant deleted it — `route_for` falls open, see the docs above
        };
        let mut p = Params::new();
        p.insert("hub_id".into(), json!(hub_id));
        p.insert("document_type".into(), json!(document_type));
        p.insert("station_id".into(), json!(station.id));
        p.insert("now".into(), json!(now_rfc3339()));
        // `DO NOTHING`: seeding must never overwrite a destination the merchant chose.
        db.execute(
            "INSERT INTO _print_route (hub_id, document_type, station_id, updated_at, updated_by) \
             VALUES (:hub_id, :document_type, :station_id, :now, 'system') \
             ON CONFLICT DO NOTHING",
            &p,
        )
        .await?;
    }
    Ok(list(db, hub_id).await?.len())
}

fn row_to_route(row: &serde_json::Value) -> PrintRoute {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    PrintRoute {
        document_type: s("document_type"),
        station_id: s("station_id"),
        station_key: s("station_key"),
        station_label: s("station_label"),
    }
}

fn row_to_station(row: &serde_json::Value) -> PrintStation {
    let s = |k: &str| row[k].as_str().unwrap_or_default().to_string();
    PrintStation {
        id: s("id"),
        key: s("key"),
        label: s("label"),
        created_at: s("created_at"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::testutil::TestDb;
    use erplora_db::PgAdapter;

    /// A hub with the system schema in place (routes are system migration v50).
    async fn route_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    /// Where `document_type` really comes out, by station key.
    async fn destination(db: &PgAdapter, hub_id: &str, document_type: &str) -> String {
        route_for(db, hub_id, document_type).await.unwrap().key
    }

    /// **The two vocabularies must not drift.** A document type the queue accepts but nobody routed
    /// would fail open to `receipt` forever — silently correct for a ticket, silently wrong for a
    /// kitchen order. Same twin-guard shape as `DOCUMENT_TYPES` itself.
    #[test]
    fn every_document_type_the_queue_accepts_has_a_default_route() {
        for kind in crate::print_queue::DOCUMENT_TYPES {
            assert!(
                DEFAULT_ROUTES.iter().any(|(dt, _)| *dt == kind),
                "`{kind}` can be queued but has no default route: it would fail open forever"
            );
        }
        for (document_type, _) in DEFAULT_ROUTES {
            assert!(
                crate::print_queue::DOCUMENT_TYPES.contains(&document_type),
                "`{document_type}` is routed but the queue would refuse it at the door"
            );
        }
    }

    /// Every default points at one of the four stations a hub is seeded with, or the routing would
    /// be born dangling on a brand-new hub.
    #[test]
    fn every_default_route_points_at_a_seeded_station() {
        for (document_type, station_key) in DEFAULT_ROUTES {
            assert!(
                print_stations::CORE_STATIONS
                    .iter()
                    .any(|(key, _)| *key == station_key),
                "`{document_type}` is routed to `{station_key}`, which a new hub does not have"
            );
        }
    }

    /// **The compatibility promise.** A fresh hub routes exactly the way the published modules print
    /// today: the sale's ticket to the counter, the kitchen order to the kitchen, the barcode to the
    /// label printer. Switching a module over to "send no role" must change nothing that comes out.
    #[tokio::test]
    async fn a_new_hub_is_routed_the_way_it_printed_yesterday() {
        let db = route_db().await;
        assert_eq!(destination(&db, "h1", "receipt").await, "receipt");
        assert_eq!(destination(&db, "h1", "kitchen_order").await, "kitchen");
        assert_eq!(destination(&db, "h1", "barcode_label").await, "label");
        assert_eq!(destination(&db, "h1", "prebill").await, "receipt");
        assert_eq!(
            list(&db, "h1").await.unwrap().len(),
            DEFAULT_ROUTES.len(),
            "every document type is routed on a fresh hub"
        );
    }

    /// The point of the whole module: the merchant re-points a document type without anybody
    /// touching a module.
    #[tokio::test]
    async fn the_hub_decides_where_a_document_comes_out() {
        let db = route_db().await;
        let terrace = print_stations::create(&db, "h1", "", "Barra de la terraza")
            .await
            .unwrap();
        let route = set(&db, "h1", "kitchen_order", &terrace.key, "u1")
            .await
            .unwrap();
        assert_eq!(route.station_id, terrace.id);
        assert_eq!(route.station_label, "Barra de la terraza");
        assert_eq!(
            destination(&db, "h1", "kitchen_order").await,
            terrace.key,
            "the module never said `kitchen`: it said `kitchen_order`, and the hub decided"
        );
        assert_eq!(
            destination(&db, "h1", "receipt").await,
            "receipt",
            "re-pointing one document type moves nothing else"
        );
    }

    /// **Fail open, case 1: no row.** A document type nobody routed still produces paper — on the
    /// one station that cannot be deleted — instead of vanishing.
    #[tokio::test]
    async fn a_document_with_no_route_at_all_falls_open_to_receipt() {
        let db = route_db().await;
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("h1"));
        db.execute(
            "DELETE FROM _print_route WHERE hub_id = :hub_id AND document_type = 'kitchen_order'",
            &p,
        )
        .await
        .unwrap();

        assert_eq!(
            destination(&db, "h1", "kitchen_order").await,
            print_stations::PROTECTED_KEY,
            "an unrouted document goes to the counter, NEVER nowhere"
        );
    }

    /// **Fail open, case 2: a dangling row.** The merchant deleted the station a route pointed at.
    /// The row survives (deleting a station does not rewrite the merchant's map), and the job comes
    /// out at the counter rather than addressing a station that no longer exists.
    #[tokio::test]
    async fn a_route_whose_station_was_deleted_falls_open_to_receipt() {
        let db = route_db().await;
        let bar = print_stations::resolve(&db, "h1", "bar").await.unwrap();
        set(&db, "h1", "kitchen_order", "bar", "u1").await.unwrap();
        assert_eq!(destination(&db, "h1", "kitchen_order").await, "bar");

        assert_eq!(
            print_stations::delete(&db, "h1", &bar.id).await.unwrap(),
            print_stations::DeleteOutcome::Deleted
        );

        assert_eq!(
            destination(&db, "h1", "kitchen_order").await,
            print_stations::PROTECTED_KEY,
            "the destination disappeared; the ticket must not"
        );
        let dangling = list(&db, "h1")
            .await
            .unwrap()
            .into_iter()
            .find(|r| r.document_type == "kitchen_order")
            .expect("the row is LISTED, so a screen can show it as broken and repoint it");
        assert_eq!(
            dangling.station_key, "",
            "an unresolvable station reads as empty, not as a station that exists"
        );
    }

    /// A route the merchant chose survives the next boot: `ensure_routes` fills gaps, it does not
    /// restore defaults.
    #[tokio::test]
    async fn re_seeding_never_overwrites_a_destination_the_merchant_chose() {
        let db = route_db().await;
        set(&db, "h1", "kitchen_order", "bar", "u1").await.unwrap();

        ensure_routes(&db, "h1").await.unwrap();

        assert_eq!(
            destination(&db, "h1", "kitchen_order").await,
            "bar",
            "the seed is for gaps, not a rule the merchant has to keep fighting"
        );
    }

    /// A gap left by a deleted station is filled by the FALLBACK, not by re-creating the station.
    /// Undoing the merchant's deletion to make the table look tidy would be the worse of the two.
    #[tokio::test]
    async fn seeding_skips_a_default_whose_station_the_hub_deleted() {
        let db = route_db().await;
        let bar = print_stations::resolve(&db, "h1", "bar").await.unwrap();
        print_stations::delete(&db, "h1", &bar.id).await.unwrap();
        let label = print_stations::resolve(&db, "h1", "label").await.unwrap();
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("h1"));
        db.execute("DELETE FROM _print_route WHERE hub_id = :hub_id", &p)
            .await
            .unwrap();
        print_stations::delete(&db, "h1", &label.id).await.unwrap();

        ensure_routes(&db, "h1").await.unwrap();

        assert!(
            !print_stations::list(&db, "h1")
                .await
                .unwrap()
                .iter()
                .any(|s| s.key == "label"),
            "seeding a route must never resurrect a station the merchant removed"
        );
        assert_eq!(
            destination(&db, "h1", "barcode_label").await,
            print_stations::PROTECTED_KEY,
            "the label printer is gone, so the label comes out at the counter"
        );
    }

    /// A route can only name a document type the queue would accept: anything else is a row no job
    /// can ever match.
    #[tokio::test]
    async fn a_route_for_a_document_type_the_queue_refuses_is_rejected() {
        let db = route_db().await;
        let err = set(&db, "h1", "kitchn_order", "kitchen", "u1")
            .await
            .unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidPayload { .. }));
        assert!(
            err.to_string().contains("kitchen_order"),
            "the refusal names the types that would have worked: {err}"
        );
    }

    /// …and only a station this hub really has, or the route would be born dangling.
    #[tokio::test]
    async fn a_route_to_a_station_that_does_not_exist_is_rejected() {
        let db = route_db().await;
        let err = set(&db, "h1", "kitchen_order", "kitchn", "u1")
            .await
            .unwrap_err();
        assert!(matches!(err, RuntimeError::InvalidPayload { .. }));
        assert!(
            err.to_string().contains("kitchen"),
            "the refusal names this hub's real stations: {err}"
        );
    }

    /// Each hub owns its map. A neighbour in the same database (the legacy pre-ADR-0201 shape) gets
    /// its own seed and cannot be re-pointed from here.
    #[tokio::test]
    async fn the_map_is_per_hub() {
        let db = route_db().await;
        assert!(
            list(&db, "h2").await.unwrap().is_empty(),
            "the neighbour has not booted yet"
        );
        crate::system_migrations::apply(&db, "h2").await.unwrap();

        set(&db, "h1", "kitchen_order", "bar", "u1").await.unwrap();

        assert_eq!(destination(&db, "h1", "kitchen_order").await, "bar");
        assert_eq!(
            destination(&db, "h2", "kitchen_order").await,
            "kitchen",
            "re-pointing one hub's kitchen never moves the neighbour's"
        );
    }
}
