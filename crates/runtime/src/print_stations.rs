//! **Print stations** — the merchant's printing destinations, as ROWS (hub#457).
//!
//! Until this module existed, "which printer prints this" travelled as a **free string** compared
//! character by character: `print_queue::enqueue` stored whatever `role` arrived, `print_hosts`
//! registered whatever `role` arrived, and `claim_next` joined the two with `role = :role`. Nothing
//! ever checked that the two sides had typed the same thing, so `Kitchen`, `kitchen` and `kitchn`
//! were **three different queues** — and the third one had no host, ever, silently.
//!
//! ## Why a table and not a closed enum (the market decided, 2026-08-15)
//!
//! Twelve references (Toast, Square, Lightspeed K, Odoo, Clover, Loyverse, TouchBistro, Revel,
//! Oracle Simphony, Shopify POS, Epson ePOS, Star CloudPRNT) plus their community forums say the
//! same thing with one voice:
//!
//! ```text
//!   item / document type ──(FK)──▶ STATION (id, name) ◀──(FK)── printer / host
//! ```
//!
//! **Not one mature system compares a string typed at print time.** The *vocabulary* is open — real
//! stations are called *Grill*, *Cold*, *Bar 2*, *Terrace* — and what is closed is the **link**,
//! because it is a foreign key picked from a selector. Clover, the one reference with a closed set
//! of labels, is the one whose forums are full of merchants who cannot express their layout.
//!
//! So: neither `trim`+`to_lowercase` (it collapses `Kitchen`→`kitchen` and leaves `kitchn` as its
//! own orphan queue — one of the three examples fixed) nor a hard-coded four-value enum (breaks in
//! the first real restaurant, and pays for it by breaking a published contract).
//!
//! ## What this buys, beyond the typo
//!
//! With stations as rows, `waiting > 0, liveHosts: 0` means **exactly one thing**: the till is off.
//! It can no longer also mean "somebody typed the queue's name wrong", because a queue is not
//! created by typing — only by pressing *new station*. The diagnosis the issue asked for comes for
//! free, by construction.
//!
//! ## Where the input tolerance lives
//!
//! `trim` + `to_lowercase` survive, but **only as tolerance at the door** ([`normalize_key`]) —
//! never as identity. `  Kitchen ` resolves to the station whose key is `kitchen`; it does not
//! *become* a key. Everything downstream stores the station's own `key` and its `id`.
//!
//! Persistence: `_print_station(id, hub_id, key, label, created_at)`, **system migration v47**,
//! plus a `station_id` column on `_print_queue` and `_print_host`. The four stations of ADR-0196
//! (`receipt`, `kitchen`, `bar`, `label`) are seeded with `key` = the string in use today, which is
//! what keeps every published contract (`POST /api/print/jobs`, `erplora_set_device_role`,
//! `devices.json`, `sdk.print`) resolving without being touched.
use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::{Result, RuntimeError};
use crate::registry::{new_id, now_rfc3339};

/// The stations every hub starts with: the four wire strings of ADR-0196 §6, with an
/// **English-canonical** label (ADR-0055 — the Spanish the owner reads travels in the UI's i18n,
/// like [`crate::roles::BASE_ROLES`]).
///
/// They are a **seed, not a set**: a hub can add, rename and remove them. What makes them special
/// is only that they are the keys the shell and the published modules already send.
pub const CORE_STATIONS: [(&str, &str); 4] = [
    ("receipt", "Receipt"),
    ("kitchen", "Kitchen"),
    ("bar", "Bar"),
    ("label", "Label"),
];

/// The one station a hub may not delete.
///
/// `receipt` is the default of the shell (`apps/web/src/lib/print.ts` falls back to it when a
/// caller names no role) and the destination the follow-up will fail **open** onto. A hub without
/// it could not print a sales ticket at all, which is a foot-gun the owner would fire once and
/// diagnose never. Every other station — `kitchen`, `bar`, `label` included — is the merchant's.
pub const PROTECTED_KEY: &str = "receipt";

/// Longest key a station may carry. A key is an identifier on the wire, not prose.
pub const MAX_KEY_CHARS: usize = 40;

/// Longest human name a station may carry ("Bar de la terraza"). Same cap as a print host's label.
pub const MAX_LABEL_CHARS: usize = 120;

/// A printing destination of this hub.
#[derive(Debug, Clone, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PrintStation {
    /// Opaque row id. **This** is what the queue and the host registry point at.
    pub id: String,
    /// The wire name (`kitchen`). Stable: it is what published contracts send.
    pub key: String,
    /// What the owner sees ("Cocina"). Renaming this never moves a job.
    pub label: String,
    pub created_at: String,
}

/// What [`delete`] did, or why it refused.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DeleteOutcome {
    /// Gone, together with the host registrations that pointed at it.
    Deleted,
    /// No station with that id in **this** hub.
    NotFound,
    /// It still has unfinished work: deleting it would drop tickets on the floor.
    HasWork(i64),
    /// It is [`PROTECTED_KEY`].
    Protected,
}

/// Columns every read returns, in the order [`row_to_station`] expects.
const STATION_FIELDS: &str = "id, key, label, created_at";

fn invalid(detail: impl Into<String>) -> RuntimeError {
    RuntimeError::InvalidPayload {
        name: "print.station".to_string(),
        detail: detail.into(),
    }
}

/// **Input tolerance, never identity**: `  Kitchen ` and `kitchen` name the same station.
///
/// This is the whole of what `trim`+`to_lowercase` are allowed to do in this subsystem. They map a
/// string a client typed onto a key that must **already exist**; they never mint one.
pub fn normalize_key(raw: &str) -> String {
    raw.trim().to_lowercase()
}

/// Derives a key from a human name, for the merchant who presses *new station* and types "Barra 2".
///
/// Unicode letters and digits survive (a `cocinería` station keeps its `í`); everything else folds
/// to `_`, and runs of `_` collapse. An empty result is rejected by [`create`], not silently
/// replaced: a station nobody can name is not a station.
pub fn key_from_label(label: &str) -> String {
    let mut out = String::new();
    for ch in label.trim().to_lowercase().chars() {
        if ch.is_alphanumeric() {
            out.push(ch);
        } else if !out.ends_with('_') {
            out.push('_');
        }
    }
    out.trim_matches('_').to_string()
}

/// Whether `key` is shaped like a wire identifier: alphanumeric, `_` or `-`, nothing else.
fn key_is_wire_safe(key: &str) -> bool {
    !key.is_empty() && key.chars().all(|c| c.is_alphanumeric() || c == '_' || c == '-')
}

/// Every station of this hub, by key.
pub async fn list(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<Vec<PrintStation>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    let sql = format!(
        "SELECT {STATION_FIELDS} FROM _print_station WHERE hub_id = :hub_id ORDER BY key"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.iter().map(row_to_station).collect())
}

/// The station of this hub whose key is `key` (already normalised), or `None`.
pub async fn find(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    key: &str,
) -> Result<Option<PrintStation>> {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("key".into(), json!(normalize_key(key)));
    let sql =
        format!("SELECT {STATION_FIELDS} FROM _print_station WHERE hub_id = :hub_id AND key = :key");
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.first().map(row_to_station))
}

/// **Resolves a role string onto a station of this hub, or refuses naming the ones that exist.**
///
/// This is the door the whole design turns on. It is `device_mode::DeviceMode::parse` — the same
/// "refuse at the edge with the accepted values in the message" shape — except the accepted values
/// come from a **table** instead of a constant, so a hub that added *Terrace* has *Terrace* in the
/// error and a hub that never did does not.
///
/// The refusal is [`RuntimeError::InvalidPayload`] → **422**, not a 404: the caller sent a payload
/// that cannot mean anything here, and it has to be able to read *what would have* meant something.
pub async fn resolve(db: &dyn DatabaseAdapter, hub_id: &str, role: &str) -> Result<PrintStation> {
    let key = normalize_key(role);
    if key.is_empty() {
        return Err(invalid(
            "role is required (which station prints this)".to_string(),
        ));
    }
    if let Some(station) = find(db, hub_id, &key).await? {
        return Ok(station);
    }
    let known = list(db, hub_id).await?;
    let names: Vec<String> = known.iter().map(|s| s.key.clone()).collect();
    Err(invalid(if names.is_empty() {
        format!("unknown print station `{key}`: this hub has no stations configured")
    } else {
        format!(
            "unknown print station `{key}` (this hub has {})",
            names.join(", ")
        )
    }))
}

/// Adds a station. `key` empty is derived from `label` ([`key_from_label`]).
///
/// Refuses a duplicate key instead of quietly returning the existing row: "new station" that
/// silently hands back somebody else's is how two names end up on one queue.
pub async fn create(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    key: &str,
    label: &str,
) -> Result<PrintStation> {
    let label = label.trim();
    let key = if key.trim().is_empty() {
        key_from_label(label)
    } else {
        normalize_key(key)
    };
    if key.is_empty() {
        return Err(invalid(
            "a station needs a name (nothing could be derived from the label)",
        ));
    }
    if key.chars().count() > MAX_KEY_CHARS {
        return Err(invalid(format!(
            "the station key is {} characters, over the {MAX_KEY_CHARS} character cap",
            key.chars().count()
        )));
    }
    if !key_is_wire_safe(&key) {
        return Err(invalid(format!(
            "`{key}` is not a valid station key (letters, digits, `_` and `-` only)"
        )));
    }
    let label_chars = label.chars().count();
    if label_chars > MAX_LABEL_CHARS {
        return Err(invalid(format!(
            "the station name is {label_chars} characters, over the {MAX_LABEL_CHARS} character cap"
        )));
    }
    if find(db, hub_id, &key).await?.is_some() {
        return Err(invalid(format!("this hub already has a `{key}` station")));
    }
    let station = PrintStation {
        id: new_id(),
        key,
        label: if label.is_empty() {
            String::new()
        } else {
            label.to_string()
        },
        created_at: now_rfc3339(),
    };
    insert(db, hub_id, &station).await?;
    Ok(station)
}

/// Renames a station — the **label** only. `None` = no such station in this hub.
///
/// The `key` is deliberately immutable: it is what the published contracts send and what every
/// queued job already carries. Renaming the display name of the kitchen must not strand its
/// tickets, which is the whole reason the queue points at an `id` and not at a word.
pub async fn rename(
    db: &dyn DatabaseAdapter,
    hub_id: &str,
    id: &str,
    label: &str,
) -> Result<Option<PrintStation>> {
    let label = label.trim();
    if label.is_empty() {
        return Err(invalid("a station name cannot be empty"));
    }
    let label_chars = label.chars().count();
    if label_chars > MAX_LABEL_CHARS {
        return Err(invalid(format!(
            "the station name is {label_chars} characters, over the {MAX_LABEL_CHARS} character cap"
        )));
    }
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id.trim()));
    p.insert("label".into(), json!(label));
    let sql = format!(
        "UPDATE _print_station SET label = :label WHERE hub_id = :hub_id AND id = :id \
         RETURNING {STATION_FIELDS}"
    );
    let res = db.query(&sql, &p).await?;
    Ok(res.rows.first().map(row_to_station))
}

/// Removes a station, **and the host registrations that pointed at it**.
///
/// Two guards, and they are different refusals on purpose:
///
///  - [`DeleteOutcome::HasWork`] — a `pending`/`printing` job still points here. Deleting would
///    make a queued ticket unreachable for good, which is the silent loss ADR-0196 §6 exists to
///    rule out. Drain it or let it die first.
///  - [`DeleteOutcome::Protected`] — [`PROTECTED_KEY`], see there.
///
/// The host rows go with it because a registration for a station that no longer exists would keep
/// showing up in the registry and in `coverage` as a live host of nothing.
pub async fn delete(db: &dyn DatabaseAdapter, hub_id: &str, id: &str) -> Result<DeleteOutcome> {
    let id = id.trim();
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("id".into(), json!(id));
    let sql =
        format!("SELECT {STATION_FIELDS} FROM _print_station WHERE hub_id = :hub_id AND id = :id");
    let res = db.query(&sql, &p).await?;
    let Some(station) = res.rows.first().map(row_to_station) else {
        return Ok(DeleteOutcome::NotFound);
    };
    if station.key == PROTECTED_KEY {
        return Ok(DeleteOutcome::Protected);
    }

    let mut q = Params::new();
    q.insert("hub_id".into(), json!(hub_id));
    q.insert("id".into(), json!(id));
    q.insert("pending".into(), json!(crate::print_queue::STATUS_PENDING));
    q.insert("printing".into(), json!(crate::print_queue::STATUS_PRINTING));
    let res = db
        .query(
            "SELECT COUNT(*) AS n FROM _print_queue \
             WHERE hub_id = :hub_id AND station_id = :id AND status IN (:pending, :printing)",
            &q,
        )
        .await?;
    let unfinished = res.rows.first().and_then(|r| r["n"].as_i64()).unwrap_or(0);
    if unfinished > 0 {
        return Ok(DeleteOutcome::HasWork(unfinished));
    }

    // Both writes in ONE transaction: a station gone with its hosts left behind would leave the
    // registry claiming somebody prints a destination that does not exist.
    let ops = vec![
        (
            "DELETE FROM _print_host WHERE hub_id = :hub_id AND station_id = :id".to_string(),
            p.clone(),
        ),
        (
            "DELETE FROM _print_station WHERE hub_id = :hub_id AND id = :id".to_string(),
            p.clone(),
        ),
    ];
    db.execute_tx(&ops).await?;
    Ok(DeleteOutcome::Deleted)
}

/// Brings **this hub's** stations up: seeds, adopts, folds and backfills. Idempotent, cheap, and
/// run on every boot from [`crate::system_migrations::apply`].
///
/// It is Rust and not migration SQL for one reason: a system migration is registered **per
/// database**, and a hub that joins a database whose migrations already ran would never be seeded.
/// That is the legacy pre-ADR-0201 shape (several hubs, one database), and it is exactly the hub
/// that would boot unable to print anything at all.
///
/// Four steps, each one idempotent on its own:
///
/// 1. **Seed** [`CORE_STATIONS`] — but only if this hub has **none**. A merchant who deleted `bar`
///    must not find it back tomorrow; a hub with an empty list cannot print at all and is either
///    brand new or was never seeded.
/// 2. **Adopt** every destination this hub already has a registered **host** for. A host row is
///    evidence the merchant configured that station with real hardware, so it survives. A `role`
///    sitting only in the *queue* is **not** adopted: an unhosted queued string is the typo this
///    issue is about, and canonising it is the one thing we must not do.
/// 3. **Fold** case variants of a host's role onto the newest row, then normalise the role to its
///    key, so `Kitchen` and `kitchen` stop being two registrations of one device.
/// 4. **Backfill** `station_id` on both tables wherever it is empty and a station matches.
///
/// Returns how many stations exist for this hub afterwards.
pub async fn ensure_stations(db: &dyn DatabaseAdapter, hub_id: &str) -> Result<usize> {
    // 1 — seed, only into an empty hub.
    if list(db, hub_id).await?.is_empty() {
        for (key, label) in CORE_STATIONS {
            let station = PrintStation {
                id: new_id(),
                key: key.to_string(),
                label: label.to_string(),
                created_at: now_rfc3339(),
            };
            insert(db, hub_id, &station).await?;
        }
    }

    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub_id));

    // 2 — adopt what real hardware already points at.
    let hosted = db
        .query(
            "SELECT DISTINCT LOWER(BTRIM(role)) AS key FROM _print_host WHERE hub_id = :hub_id",
            &p,
        )
        .await?;
    for row in &hosted.rows {
        let key = row["key"].as_str().unwrap_or_default().to_string();
        if key.is_empty() || find(db, hub_id, &key).await?.is_some() {
            continue;
        }
        let station = PrintStation {
            id: new_id(),
            key: key.clone(),
            label: key,
            created_at: now_rfc3339(),
        };
        insert(db, hub_id, &station).await?;
    }

    // 3 — fold case variants of one device's role onto the newest, then normalise.
    db.execute(
        "DELETE FROM _print_host a USING _print_host b \
          WHERE a.hub_id = :hub_id AND b.hub_id = :hub_id AND a.device_id = b.device_id \
            AND LOWER(BTRIM(a.role)) = LOWER(BTRIM(b.role)) AND a.role <> b.role \
            AND (a.last_seen_at < b.last_seen_at \
                 OR (a.last_seen_at = b.last_seen_at AND a.ctid < b.ctid))",
        &p,
    )
    .await?;
    db.execute(
        "UPDATE _print_host SET role = LOWER(BTRIM(role)) \
          WHERE hub_id = :hub_id AND role <> LOWER(BTRIM(role))",
        &p,
    )
    .await?;

    // 4 — point the existing rows at their station.
    db.execute(
        "UPDATE _print_host h SET station_id = s.id FROM _print_station s \
          WHERE s.hub_id = h.hub_id AND s.key = h.role \
            AND h.hub_id = :hub_id AND h.station_id = ''",
        &p,
    )
    .await?;
    db.execute(
        "UPDATE _print_queue q SET station_id = s.id, role = s.key FROM _print_station s \
          WHERE s.hub_id = q.hub_id AND s.key = LOWER(BTRIM(q.role)) \
            AND q.hub_id = :hub_id AND q.station_id = ''",
        &p,
    )
    .await?;

    Ok(list(db, hub_id).await?.len())
}

/// The single INSERT of a station, so every door writes the same row shape.
async fn insert(db: &dyn DatabaseAdapter, hub_id: &str, station: &PrintStation) -> Result<()> {
    let mut p = Params::new();
    p.insert("id".into(), json!(station.id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("key".into(), json!(station.key));
    p.insert("label".into(), json!(station.label));
    p.insert("created_at".into(), json!(station.created_at));
    db.execute(
        "INSERT INTO _print_station (id, hub_id, key, label, created_at) \
         VALUES (:id, :hub_id, :key, :label, :created_at) ON CONFLICT DO NOTHING",
        &p,
    )
    .await?;
    Ok(())
}

/// Row of [`STATION_FIELDS`] → [`PrintStation`].
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

    /// A hub with the system schema in place (stations are system migration v47).
    async fn station_db() -> PgAdapter {
        let db = TestDb::new().await.adapter().await;
        crate::installer::ensure_hub_module_table(&db)
            .await
            .unwrap();
        crate::identity::ensure_tables(&db).await.unwrap();
        crate::system_migrations::apply(&db, "h1").await.unwrap();
        db
    }

    fn keys(stations: &[PrintStation]) -> Vec<String> {
        stations.iter().map(|s| s.key.clone()).collect()
    }

    /// **The compatibility promise of step 1.** Every hub starts with the four wire strings that
    /// the shell, `erplora_set_device_role`, `devices.json` and `sdk.print` already send, so no
    /// published contract has to be touched for this issue to land.
    #[tokio::test]
    async fn a_hub_starts_with_the_four_stations_in_use_today() {
        let db = station_db().await;
        let stations = list(&db, "h1").await.unwrap();
        assert_eq!(
            keys(&stations),
            vec!["bar", "kitchen", "label", "receipt"],
            "the seed IS the compatibility guarantee: these are the strings already on the wire"
        );
        assert!(
            stations.iter().all(|s| !s.id.is_empty()),
            "a station is an entity: it has an id of its own, which is what everything else points at"
        );
    }

    /// `trim`+`to_lowercase` are **tolerance at the door**, and that is all they are: they map a
    /// sloppy input onto a station that already exists.
    #[tokio::test]
    async fn resolving_tolerates_stray_case_and_spaces_in_the_input() {
        let db = station_db().await;
        let station = resolve(&db, "h1", "  Kitchen ").await.unwrap();
        assert_eq!(station.key, "kitchen");
        assert_eq!(
            station.id,
            resolve(&db, "h1", "kitchen").await.unwrap().id,
            "same station, not a second queue"
        );
    }

    /// **The bug, closed.** `kitchn` is what `to_lowercase` could never fix: it is not a case
    /// variant, it is a different word. Against a table it is simply not a station, and the refusal
    /// names the ones that are — so the caller can see the typo instead of watching a queue nobody
    /// drains.
    #[tokio::test]
    async fn an_unknown_station_is_refused_naming_the_ones_this_hub_has() {
        let db = station_db().await;
        let err = resolve(&db, "h1", "kitchn").await.unwrap_err();
        let msg = err.to_string();
        assert!(
            matches!(err, RuntimeError::InvalidPayload { .. }),
            "an unresolvable station is a bad payload (422), not a missing page: {msg}"
        );
        assert!(msg.contains("kitchn"), "it has to say what was rejected: {msg}");
        for expected in ["bar", "kitchen", "label", "receipt"] {
            assert!(
                msg.contains(expected),
                "the refusal must name the stations this hub DOES have (missing `{expected}`): {msg}"
            );
        }
    }

    /// The vocabulary is open — that is the half Clover gets wrong. A real restaurant has a
    /// *Terrace*, and once created it resolves like any other.
    #[tokio::test]
    async fn a_hub_can_add_a_station_of_its_own_and_it_resolves() {
        let db = station_db().await;
        let created = create(&db, "h1", "", "Barra de la terraza").await.unwrap();
        assert_eq!(
            created.key, "barra_de_la_terraza",
            "the key is derived from the name the merchant typed"
        );
        assert_eq!(created.label, "Barra de la terraza");
        // Resolution goes by **key**, never by the display name: matching what a human typed on a
        // screen would be the very string comparison this issue removes, one layer up.
        assert_eq!(
            resolve(&db, "h1", " Barra_De_La_Terraza ").await.unwrap().id,
            created.id
        );
        assert!(
            resolve(&db, "h1", "Barra de la terraza").await.is_err(),
            "the label is what the owner reads, not an address the wire can use"
        );
    }

    /// "New station" must never hand back somebody else's: two names on one queue is the bug in
    /// another costume.
    #[tokio::test]
    async fn creating_a_station_that_already_exists_is_refused() {
        let db = station_db().await;
        let err = create(&db, "h1", "kitchen", "Cocina").await.unwrap_err();
        assert!(err.to_string().contains("kitchen"));
    }

    /// Renaming is a **label** change. The key stays, because the key is what every queued job and
    /// every published contract already carries — a rename that stranded the tickets would be a
    /// worse bug than the one being fixed.
    #[tokio::test]
    async fn renaming_a_station_changes_the_label_and_never_the_key() {
        let db = station_db().await;
        let kitchen = resolve(&db, "h1", "kitchen").await.unwrap();
        let renamed = rename(&db, "h1", &kitchen.id, "Cocina caliente")
            .await
            .unwrap()
            .expect("the station exists");
        assert_eq!(renamed.label, "Cocina caliente");
        assert_eq!(renamed.key, "kitchen", "the wire name is immutable");
        assert_eq!(
            resolve(&db, "h1", "kitchen").await.unwrap().id,
            kitchen.id,
            "the contract still resolves after a rename"
        );
    }

    /// A station with a ticket still queued cannot be removed: the job would become unreachable,
    /// which is precisely the silent loss the print queue exists to rule out.
    #[tokio::test]
    async fn a_station_with_unfinished_work_cannot_be_deleted() {
        let db = station_db().await;
        let bar = resolve(&db, "h1", "bar").await.unwrap();
        crate::print_queue::enqueue(
            &db,
            "h1",
            &crate::print_queue::NewPrintJob {
                job_id: "j1".into(),
                role: "bar".into(),
                document_type: "receipt".into(),
                document: json!({ "total": 3 }),
                format: crate::print_queue::FORMAT_RECEIPT.into(),
            },
        )
        .await
        .unwrap();

        assert_eq!(
            delete(&db, "h1", &bar.id).await.unwrap(),
            DeleteOutcome::HasWork(1)
        );

        crate::print_queue::mark_done(&db, "h1", "j1").await.unwrap();
        assert_eq!(
            delete(&db, "h1", &bar.id).await.unwrap(),
            DeleteOutcome::Deleted,
            "once nothing is waiting, the merchant's station is the merchant's to remove"
        );
        assert!(!keys(&list(&db, "h1").await.unwrap()).contains(&"bar".to_string()));
    }

    /// Deleting the station a device hosts takes the registration with it: a host of a destination
    /// that no longer exists would keep reporting itself live for nothing.
    #[tokio::test]
    async fn deleting_a_station_retires_the_hosts_that_pointed_at_it() {
        let db = station_db().await;
        let bar = resolve(&db, "h1", "bar").await.unwrap();
        crate::print_hosts::register(&db, "h1", "till-1", "bar", "Barra", "u1")
            .await
            .unwrap();
        crate::print_hosts::register(&db, "h1", "till-1", "kitchen", "Barra", "u1")
            .await
            .unwrap();

        assert_eq!(delete(&db, "h1", &bar.id).await.unwrap(), DeleteOutcome::Deleted);
        let hosts = crate::print_hosts::list(&db, "h1").await.unwrap();
        assert_eq!(
            hosts.iter().map(|h| h.role.clone()).collect::<Vec<_>>(),
            vec!["kitchen"],
            "only the registration of the deleted station goes"
        );
    }

    /// `receipt` is the shell's default and the fail-open destination of the follow-up. A hub
    /// without it could not print a sale, and would find that out at the counter.
    #[tokio::test]
    async fn the_receipt_station_is_protected_from_deletion() {
        let db = station_db().await;
        let receipt = resolve(&db, "h1", "receipt").await.unwrap();
        assert_eq!(
            delete(&db, "h1", &receipt.id).await.unwrap(),
            DeleteOutcome::Protected
        );
    }

    /// The seed fires **once**. A hub that deleted a station it does not use must not find it back
    /// on the next boot — which is what `ensure_stations` running on every start would do if it
    /// re-seeded unconditionally.
    #[tokio::test]
    async fn a_deleted_station_does_not_come_back_on_the_next_boot() {
        let db = station_db().await;
        let bar = resolve(&db, "h1", "bar").await.unwrap();
        assert_eq!(delete(&db, "h1", &bar.id).await.unwrap(), DeleteOutcome::Deleted);

        ensure_stations(&db, "h1").await.unwrap();

        assert_eq!(
            keys(&list(&db, "h1").await.unwrap()),
            vec!["kitchen", "label", "receipt"],
            "the seed is for an empty hub, not a rule the merchant has to keep fighting"
        );
    }

    /// A hub that arrives at an already-migrated database (the legacy pre-ADR-0201 shape: several
    /// hubs, one database) gets its own stations anyway — the migration is registered per database
    /// and would never seed it.
    #[tokio::test]
    async fn a_hub_joining_an_already_migrated_database_still_gets_its_stations() {
        let db = station_db().await;
        assert!(
            list(&db, "h2").await.unwrap().is_empty(),
            "the neighbour has not booted yet"
        );
        crate::system_migrations::apply(&db, "h2").await.unwrap();
        assert_eq!(keys(&list(&db, "h2").await.unwrap()).len(), 4);
        assert!(
            resolve(&db, "h2", "kitchen").await.unwrap().id
                != resolve(&db, "h1", "kitchen").await.unwrap().id,
            "each hub owns its stations: same key, different row"
        );
    }

    /// **Existing hardware is evidence; an unhosted queued string is not.** A device already
    /// registered for a destination this hub uses keeps working (its station is adopted), while a
    /// `kitchn` that only ever existed as a queued job is left unadopted — canonising the typo is
    /// the one thing this issue must not do.
    #[tokio::test]
    async fn a_configured_host_gets_its_station_adopted_but_a_queued_typo_does_not() {
        let db = station_db().await;
        // A hub configured before stations existed: a real host on a destination of its own, and a
        // job queued against a word nobody hosts.
        let mut p = Params::new();
        p.insert("hub_id".into(), json!("h1"));
        p.insert("now".into(), json!(now_rfc3339()));
        db.execute(
            "INSERT INTO _print_host (hub_id, device_id, role, label, registered_at, \
             registered_by, last_seen_at) \
             VALUES (:hub_id, 'till-9', 'Terraza', 'Terraza', :now, 'u1', :now)",
            &p,
        )
        .await
        .unwrap();
        db.execute(
            "INSERT INTO _print_queue (hub_id, job_id, role, document_type, document, format, \
             status, attempts, created_at) \
             VALUES (:hub_id, 'j-typo', 'kitchn', 'receipt', '{}', 'receipt', 'pending', 0, :now)",
            &p,
        )
        .await
        .unwrap();

        ensure_stations(&db, "h1").await.unwrap();

        let all = keys(&list(&db, "h1").await.unwrap());
        assert!(
            all.contains(&"terraza".to_string()),
            "a registered host is a station the merchant really configured: {all:?}"
        );
        assert!(
            !all.contains(&"kitchn".to_string()),
            "a queued string nobody hosts is the typo, not a station: {all:?}"
        );
        let hosts = crate::print_hosts::list(&db, "h1").await.unwrap();
        assert_eq!(hosts[0].role, "terraza", "the legacy row is normalised onto its key");
        assert!(
            !hosts[0].station_id.is_empty(),
            "and it is pointed at the station, so `claim_next` can find it"
        );
    }
}
