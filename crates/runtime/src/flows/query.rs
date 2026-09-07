//! **The `query` step: a flow reading, deterministically** (hub#954).
//!
//! Nothing about the AUTHORITY here is new. `GrantKind::Query` and
//! [`grants::check_query_grant`] have gated a flow's reads since hub#665; what needed a language
//! model in front of it until now was the ACT of reading. This file is the door without the model.
//!
//! ```text
//!   step + run scope ─▶ query grant (fresh, at this instant)
//!                                  │
//!            the read, with the flow's own context: machine principal, no user RBAC
//!                                  ▼
//!                    queries::execute_page  ──▶  rows ≤ limit  +  a truthful total
//!                                  │
//!                       steps.<id> = fields of row 0 + found + count
//! ```
//!
//! ## Why the paginated engine and not [`crate::queries::execute`]
//!
//! `Runtime::execute_flow_query` — the door the `ai` step's runner uses — returns
//! `Vec<Json>` from `queries::execute`, which is the WHOLE set: no `LIMIT`, no total. Trimming
//! afterwards would mean the table was already loaded **inside the tick, under the runtime's
//! global lock**, and a `count` taken off a trimmed result would be a smaller number stated as if
//! it were the whole truth. [`execute_flow_query_page`] is the sibling that keeps the same gate and
//! routes to [`crate::queries::execute_page`]: a real ceiling on the rows AND a total that means
//! what it says.
//!
//! ## What is written down
//!
//! The output lands in `_flow_run_steps` and is READABLE — it cannot be redacted the way a secret
//! is (flows.md §8), because the mapping language reads later steps out of exactly that row. So a
//! read of customer data leaves customer data in the run history. That is an accepted consequence
//! and its control is the **grant**, not redaction: nothing is read that an owner did not name, and
//! the history is swept by the 90-day retention (`retention.rs`).
use erplora_db::{DatabaseAdapter, Params};
use serde_json::{json, Map, Value as Json};

use crate::errors::{Result, RuntimeError};
use crate::flows::def::{self, OptionShape, QueryResult, StepDef, StepSpec};
use crate::flows::grants;
use crate::queries::{self, QueryPage};
use crate::registry::{AutomationCtx, Registry, RequestContext};

/// A `query` step, performed: what the run history records and what later steps read.
#[derive(Debug)]
pub(crate) struct Read {
    /// What `_flow_run_steps.input` keeps — the read that was decided on, params included.
    pub recorded_input: Json,
    /// What later steps address as `steps.<id>`.
    pub output: Json,
}

/// Runs the step's read and shapes its output, or refuses.
///
/// Refuses when the flow has no live `query` grant for that name (`flow.grant_denied`) or when the
/// read itself fails. Both happen before anything is written, so the reason lands on the step.
///
/// **Zero rows is not a refusal.** The run carries on with `found: false`, which is what makes
/// «tell me *if* stock is low» writable: the decision belongs to a `condition` step the author can
/// see, not to a failure they cannot.
pub(crate) async fn run(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    step: &StepDef,
    scope: &Json,
) -> Result<Read> {
    let StepSpec::Query(spec) = &step.spec else {
        return Err(RuntimeError::Domain {
            code: grants::ERR_GRANT_DENIED.to_string(),
            message: format!("step `{}` is not a query step", step.id),
        });
    };

    let params: Params = def::resolve_map(&spec.params, scope);
    let page = execute_flow_query_page(
        db,
        registry,
        hub_id,
        flow_id,
        run_id,
        &spec.query,
        &params,
        spec.limit,
    )
    .await?;

    // The number the author asked about is how many rows MATCH, not how many were carried into the
    // run — that is the whole point of routing through the paginated engine. Salesforce's «up to a
    // specified limit» and Power Automate's `Row Count` are this same distinction.
    let count = page.total;
    let found = count > 0;
    let output = match spec.result {
        QueryResult::Count => json!({ "count": count, "found": found }),
        // hub#1641 — the list travels WHOLE, already in the transport's row shape, and is
        // addressed as one value (`steps.<id>.options`). Nothing indexes it, which is why this
        // needed nothing from `resolve_path`.
        QueryResult::Options => {
            let shape = spec.options.as_ref().ok_or_else(|| {
                bad_option(format!(
                    "step `{}`: a read that publishes `options` carries the columns that make \
                     them up; this one parsed without them.",
                    step.id
                ))
            })?;
            json!({
                "options": shape_options(&step.id, &page.rows, shape)?,
                "found": found,
                "count": count,
            })
        }
        QueryResult::First => {
            let mut fields = page
                .rows
                .first()
                .and_then(|row| row.as_object().cloned())
                .unwrap_or_else(Map::new);
            // The two contract keys are written LAST on purpose: a table with a column called
            // `count` must not be able to change what `steps.<id>.count` means, because a
            // condition downstream is reading it as the number of rows.
            fields.insert("found".into(), json!(found));
            fields.insert("count".into(), json!(count));
            Json::Object(fields)
        }
    };

    Ok(Read {
        recorded_input: json!({
            "query": spec.query,
            "params": Json::Object(params),
            "result": spec.result.as_str(),
            "limit": spec.limit,
            "options": spec.options.as_ref().map(|o| json!({
                "id": o.id, "title": o.title, "description": o.description,
            })),
        }),
        output,
    })
}

/// hub#1641 — a row could not be turned into the option it promised to be.
///
/// It is a RUN-time failure and not a save-time one on purpose: the column names are checked when
/// the document is written (`def::parse_option_shape`), but whether a row actually HAS something
/// in them is data, and data is only known here. It lands on the step like any other refusal, so
/// the run history names the column instead of leaving an empty list to be refused by the proxy.
pub const ERR_BAD_OPTION: &str = "flow.query_bad_option";

fn bad_option(message: String) -> RuntimeError {
    RuntimeError::Domain {
        code: ERR_BAD_OPTION.to_string(),
        message,
    }
}

/// A column's value as the text a tappable row carries. `None` for anything that is not one
/// scalar: a `null`, an object or an array is not something a customer can read off a row.
fn scalar_text(value: &Json) -> Option<String> {
    match value {
        Json::String(s) => Some(s.trim().to_string()),
        Json::Number(n) => Some(n.to_string()),
        Json::Bool(b) => Some(b.to_string()),
        Json::Null | Json::Object(_) | Json::Array(_) => None,
    }
}

/// One REQUIRED column of one row, or the refusal that names it.
fn required_text(
    step_id: &str,
    row: &Map<String, Json>,
    column: &str,
    field: &str,
    at: usize,
) -> Result<String> {
    let Some(value) = row.get(column) else {
        return Err(bad_option(format!(
            "step `{step_id}`: the read has no column `{column}`, and the options say it is their \
             `{field}`. The columns of an option are the ones the read selects."
        )));
    };
    scalar_text(value)
        .filter(|text| !text.is_empty())
        .ok_or_else(|| {
            bad_option(format!(
                "step `{step_id}`: row {at} has nothing in `{column}` for the option's `{field}`. \
                 A row with no `{field}` is a row nobody can tap, and a message that carries it is \
                 refused whole — so the read is narrowed to the rows that have one."
            ))
        })
}

/// **The rows, in the shape the transport receives** (hub#1641).
///
/// `id` and `title` are what Meta cannot send a tappable row without, so a row missing either is
/// a refusal that names the column. `description` is the optional second line and an empty one is
/// simply LEFT OUT rather than sent as an empty string: Meta refuses a `description: null`, and a
/// row that shows a blank line under the title is worse than a row that shows none.
///
/// Meta's own limits on the message — three buttons, ten rows across sections, the length of each
/// title — stay where they already live, in the SaaS proxy that composes the send. Writing them
/// twice is how two validators drift apart. What is guaranteed HERE is the shape of each row.
fn shape_options(step_id: &str, rows: &[Json], shape: &OptionShape) -> Result<Json> {
    let mut options = Vec::with_capacity(rows.len());
    for (index, row) in rows.iter().enumerate() {
        let at = index + 1;
        let Some(row) = row.as_object() else {
            return Err(bad_option(format!(
                "step `{step_id}`: row {at} of the read is not a row of columns, so there is \
                 nothing to read an option out of."
            )));
        };
        let mut option = Map::new();
        option.insert(
            "id".into(),
            json!(required_text(step_id, row, &shape.id, "id", at)?),
        );
        option.insert(
            "title".into(),
            json!(required_text(step_id, row, &shape.title, "title", at)?),
        );
        if let Some(column) = shape.description.as_deref() {
            if let Some(text) = row.get(column).and_then(scalar_text) {
                if !text.is_empty() {
                    option.insert("description".into(), json!(text));
                }
            }
        }
        options.push(Json::Object(option));
    }
    Ok(Json::Array(options))
}

/// **The paginated sibling of `Runtime::execute_flow_query`** (hub#954), with the same gate.
///
/// The grant is checked HERE, freshly, for the same reason it is checked there: a gate the caller
/// can skip is not a gate. What differs is the engine — [`crate::queries::execute_page`] instead of
/// `queries::execute` — and that difference is the whole feature: the rows are capped and the
/// total is real.
///
/// The cap reaches the SQL for a query that declares a `list` block, which is where a big table
/// would actually hurt. A plain query has no page to compose (the module wrote the whole `SELECT`),
/// so the engine hands back everything it selected and the ceiling is applied to the result — the
/// total stays the truthful one either way.
#[allow(clippy::too_many_arguments)] // one read's worth of context, same as `notify::prepare`
pub(crate) async fn execute_flow_query_page(
    db: &dyn DatabaseAdapter,
    registry: &Registry,
    hub_id: &str,
    flow_id: &str,
    run_id: &str,
    name: &str,
    params: &Params,
    limit: i64,
) -> Result<QueryPage> {
    grants::check_query_grant(db, hub_id, flow_id, name).await?;

    // The context the read runs under: attributed to the flow, machine-principal (never offered a
    // manager's PIN, hub#361), carrying only the permissions of what this flow was granted.
    let authority = grants::authority(db, hub_id, flow_id).await?;
    let ctx = RequestContext::new(
        hub_id.to_string(),
        format!("flow:{flow_id}"),
        authority.permissions(registry),
    )
    .as_machine()
    .with_automation(AutomationCtx {
        flow_id: flow_id.to_string(),
        run_id: run_id.to_string(),
    });

    let mut bound = params.clone();
    // `limit`/`offset` are the LIST engine's own parameters and are only added for a query that
    // declares a `list` block. A plain query composes no page, and its declared JSON Schema is
    // validated against exactly these params (`queries::execute_page`): pushing two keys it never
    // asked for into a strict schema would turn a legal read into `flow.invalid_payload`.
    if registry
        .get_query(name)
        .is_some_and(|q| q.def.list.is_some())
    {
        bound.insert("limit".into(), json!(limit));
        bound.insert("offset".into(), json!(0));
    }
    let mut page = queries::execute_page(db, registry, name, &bound, &ctx).await?;
    // The ceiling, applied wherever the engine could not apply it — a plain query hands back
    // everything its `SELECT` selected. `total` is left alone: it is the truthful count, and the
    // whole reason this routes through the paginated engine.
    page.rows.truncate(limit.max(0) as usize);
    page.limit = limit.max(0) as u64;
    Ok(page)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::flows::def::FlowDefinition;
    use crate::flows::grants::{GrantKind, GrantSpec};
    use crate::flows::test_support;
    use crate::registry::ModuleStatus;
    use erplora_db::testutil::fresh_db;

    const HUB: &str = "hub-query";
    const FLOW: &str = "flow-1";

    fn registry() -> Registry {
        let mut reg = Registry::new();
        reg.status.insert("sales".into(), ModuleStatus::Active);
        reg.queries.insert(
            "sales.summary".into(),
            test_support::query(
                "sales",
                "sales.view_sale",
                "SELECT id, total FROM sale WHERE day = :day ORDER BY id",
            ),
        );
        reg.queries.insert(
            "sales.all".into(),
            test_support::query(
                "sales",
                "sales.view_sale",
                "SELECT id, total FROM sale ORDER BY id",
            ),
        );
        // A read with a NULLABLE column, which is the only way to test what an option does when
        // the row simply has nothing in the column the document named.
        reg.queries.insert(
            "sales.detail".into(),
            test_support::query(
                "sales",
                "sales.view_sale",
                "SELECT id, day, total, note FROM sale ORDER BY id",
            ),
        );
        reg
    }

    async fn db() -> impl DatabaseAdapter {
        let db = fresh_db().await;
        test_support::ensure_schema(&db, HUB).await;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS sale (id TEXT PRIMARY KEY, day TEXT NOT NULL, \
             total TEXT NOT NULL, note TEXT);",
        )
        .await
        .unwrap();
        db
    }

    async fn sale(db: &dyn DatabaseAdapter, id: &str, day: &str, total: &str) {
        sale_noted(db, id, day, total, Json::Null).await;
    }

    async fn sale_noted(db: &dyn DatabaseAdapter, id: &str, day: &str, total: &str, note: Json) {
        let mut p = Params::new();
        p.insert("id".into(), json!(id));
        p.insert("day".into(), json!(day));
        p.insert("total".into(), json!(total));
        p.insert("note".into(), note);
        db.execute(
            "INSERT INTO sale (id, day, total, note) VALUES (:id, :day, :total, :note)",
            &p,
        )
        .await
        .unwrap();
    }

    async fn allow(db: &dyn DatabaseAdapter, query: &str) {
        grants::replace(
            db,
            HUB,
            FLOW,
            &registry(),
            &[GrantSpec::pair(GrantKind::Query, query.to_string())],
            "hub_user:1",
        )
        .await
        .unwrap();
    }

    fn step(spec: Json) -> StepDef {
        FlowDefinition::parse(&json!({ "schema_version": 1, "steps": [spec] }))
            .unwrap()
            .steps
            .remove(0)
    }

    fn scope() -> Json {
        json!({ "input": { "day": "2026-08-15" }, "steps": {} })
    }

    async fn read(db: &dyn DatabaseAdapter, spec: Json) -> Result<Read> {
        run(db, &registry(), HUB, FLOW, "run-1", &step(spec), &scope()).await
    }

    /// `result: "first"` puts the row's own fields where the mapping language can read them —
    /// `steps.week.total`, not `steps.week.rows.0.total`, which `resolve_path` cannot walk.
    #[tokio::test]
    async fn the_first_row_lands_at_the_root_of_the_step_with_found_and_count() {
        let db = db().await;
        sale(&db, "s-1", "2026-08-15", "120.50").await;
        sale(&db, "s-2", "2026-08-15", "80.00").await;
        allow(&db, "sales.summary").await;

        let read = read(
            &db,
            json!({
                "id": "week", "kind": "query", "query": "sales.summary",
                "params": { "day": "input.day" }
            }),
        )
        .await
        .unwrap();

        assert_eq!(
            read.output["id"],
            json!("s-1"),
            "the fields of the FIRST row"
        );
        assert_eq!(read.output["total"], json!("120.50"));
        assert_eq!(read.output["found"], json!(true));
        assert_eq!(
            read.output["count"],
            json!(2),
            "how many MATCH, not how many were carried"
        );
        assert_eq!(read.recorded_input["query"], json!("sales.summary"));
        assert_eq!(read.recorded_input["params"]["day"], json!("2026-08-15"));
    }

    // ── `result: "options"` — the list that TRAVELS (hub#1641) ────────────────────────────────

    /// **What the issue asked for.** The list is already in the database, so nobody has to pay a
    /// language model to read it out loud: the read publishes it whole, already in the row shape
    /// an `interactive` send receives, under ONE addressable name (`steps.<id>.options`).
    #[tokio::test]
    async fn a_read_publishes_the_whole_list_in_the_shape_a_tappable_message_receives() {
        let db = db().await;
        sale_noted(&db, "s-1", "2026-08-15", "120.50", json!("con Ana")).await;
        sale_noted(&db, "s-2", "2026-08-15", "80.00", json!("con Marta")).await;
        allow(&db, "sales.detail").await;

        let read = read(
            &db,
            json!({
                "id": "free", "kind": "query", "query": "sales.detail",
                "result": "options",
                "options": { "id": "id", "title": "total", "description": "note" }
            }),
        )
        .await
        .unwrap();

        assert_eq!(
            read.output["options"],
            json!([
                { "id": "s-1", "title": "120.50", "description": "con Ana" },
                { "id": "s-2", "title": "80.00", "description": "con Marta" }
            ]),
            "the rows come out as Meta's own row shape, ready to be the `rows` of a list"
        );
        assert_eq!(read.output["found"], json!(true));
        assert_eq!(read.output["count"], json!(2));
        // The history says which columns were asked for, the same way it says which read was.
        assert_eq!(read.recorded_input["options"]["title"], json!("total"));

        // And the whole point: the mapping language reaches it as ONE value, with its type
        // intact, without indexing anything — which is what `resolve_path` refuses to do.
        let scope = json!({ "steps": { "free": read.output } });
        let filled = def::resolve(
            &json!({ "action": { "sections": [{ "rows": "steps.free.options" }] } }),
            &scope,
        );
        let rows = &filled["action"]["sections"][0]["rows"];
        assert!(rows.is_array(), "the list keeps its type: {filled}");
        assert_eq!(rows[1]["title"], json!("80.00"));
        assert_eq!(
            def::resolve_path("steps.free.options.0.title", &scope),
            None,
            "and it is still NOT indexable: v1's refusal is untouched"
        );
    }

    /// Zero rows is not a failure here either — `found: false` and an EMPTY list, so a `condition`
    /// the author can see decides what to say instead of a message going out with nothing to tap.
    #[tokio::test]
    async fn a_read_that_finds_nothing_publishes_an_empty_list_and_says_so() {
        let db = db().await;
        allow(&db, "sales.detail").await;

        let read = read(
            &db,
            json!({
                "id": "free", "kind": "query", "query": "sales.detail",
                "result": "options",
                "options": { "id": "id", "title": "total" }
            }),
        )
        .await
        .unwrap();

        assert_eq!(read.output["options"], json!([]));
        assert_eq!(read.output["found"], json!(false));
        assert_eq!(read.output["count"], json!(0));
    }

    /// The optional second line is LEFT OUT when the row has nothing in it, never sent blank:
    /// Meta refuses a `description: null`, and a row with an empty line under the title reads as
    /// broken. The row that DOES have one keeps it, so the zero means something.
    #[tokio::test]
    async fn an_empty_second_line_is_left_out_instead_of_sent_blank() {
        let db = db().await;
        sale_noted(&db, "s-1", "2026-08-15", "120.50", Json::Null).await;
        sale_noted(&db, "s-2", "2026-08-15", "80.00", json!("   ")).await;
        sale_noted(&db, "s-3", "2026-08-15", "12.00", json!("con Ana")).await;
        allow(&db, "sales.detail").await;

        let read = read(
            &db,
            json!({
                "id": "free", "kind": "query", "query": "sales.detail",
                "result": "options",
                "options": { "id": "id", "title": "total", "description": "note" }
            }),
        )
        .await
        .unwrap();

        let options = read.output["options"].as_array().expect("a list").clone();
        assert!(
            options[0].get("description").is_none(),
            "a NULL second line is not a key: {:?}",
            options[0]
        );
        assert!(
            options[1].get("description").is_none(),
            "nor is one that is only spaces: {:?}",
            options[1]
        );
        assert_eq!(options[2]["description"], json!("con Ana"));
    }

    /// A row with nothing to tap stops the step NAMING the column. The alternative is a message
    /// the proxy refuses whole, in a background tick, with the customer already waiting — and the
    /// run history saying only that the send failed.
    #[tokio::test]
    async fn a_row_with_no_id_or_no_title_stops_the_step_naming_the_column() {
        let db = db().await;
        sale_noted(&db, "s-1", "2026-08-15", "120.50", json!("con Ana")).await;
        sale_noted(&db, "s-2", "2026-08-15", "80.00", Json::Null).await;
        allow(&db, "sales.detail").await;

        let err = read(
            &db,
            json!({
                "id": "free", "kind": "query", "query": "sales.detail",
                "result": "options",
                "options": { "id": "id", "title": "note" }
            }),
        )
        .await
        .expect_err("a row nobody can tap is not an option");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_BAD_OPTION),
            "{err}"
        );
        let text = format!("{err}");
        assert!(text.contains("note"), "it names the column: {text}");
        assert!(text.contains('2'), "and which row it was: {text}");
    }

    /// A column the read does not select is the typo every author makes once. It is a refusal
    /// about the DOCUMENT, not about a row, so it says so without a row number.
    #[tokio::test]
    async fn a_column_the_read_does_not_select_is_refused_naming_it() {
        let db = db().await;
        sale(&db, "s-1", "2026-08-15", "120.50").await;
        allow(&db, "sales.detail").await;

        let err = read(
            &db,
            json!({
                "id": "free", "kind": "query", "query": "sales.detail",
                "result": "options",
                "options": { "id": "id", "title": "titulo" }
            }),
        )
        .await
        .expect_err("the columns of an option are the ones the read selects");
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == ERR_BAD_OPTION),
            "{err}"
        );
        assert!(format!("{err}").contains("titulo"), "{err}");
    }

    /// `result: "count"` carries no row at all: «are there any, and how many».
    #[tokio::test]
    async fn a_count_read_answers_with_the_number_and_nothing_else() {
        let db = db().await;
        sale(&db, "s-1", "2026-08-15", "120.50").await;
        allow(&db, "sales.summary").await;

        let read = read(
            &db,
            json!({
                "id": "week", "kind": "query", "query": "sales.summary",
                "params": { "day": "input.day" }, "result": "count"
            }),
        )
        .await
        .unwrap();

        assert_eq!(
            read.output,
            json!({ "count": 1, "found": true }),
            "no row travels with a count: {}",
            read.output
        );
    }

    /// Nobody is not a failure. «Avísame SI hay stock bajo» is written as a read that finds
    /// nothing followed by a `condition`, and a step that failed on zero rows would make that
    /// sentence unwritable.
    #[tokio::test]
    async fn zero_rows_is_an_answer_and_not_a_failure() {
        let db = db().await;
        allow(&db, "sales.summary").await;

        let read = read(
            &db,
            json!({
                "id": "week", "kind": "query", "query": "sales.summary",
                "params": { "day": "input.day" }
            }),
        )
        .await
        .expect("an empty read is a fact, not an error");

        assert_eq!(read.output["found"], json!(false));
        assert_eq!(read.output["count"], json!(0));
    }

    /// The grant is the whole permission model of this step, and it is re-read at the instant of
    /// the read: revoking it mid-run stops the very next step.
    #[tokio::test]
    async fn without_a_live_query_grant_nothing_is_read() {
        let db = db().await;
        sale(&db, "s-1", "2026-08-15", "120.50").await;

        // No grant at all.
        let err = read(
            &db,
            json!({ "id": "week", "kind": "query", "query": "sales.summary" }),
        )
        .await
        .unwrap_err();
        assert!(
            matches!(&err, RuntimeError::Domain { code, .. } if code == grants::ERR_GRANT_DENIED),
            "{err}"
        );

        // A grant for the read NEXT to it is not this read's grant.
        allow(&db, "sales.all").await;
        let err = read(
            &db,
            json!({ "id": "week", "kind": "query", "query": "sales.summary" }),
        )
        .await
        .unwrap_err();
        assert!(format!("{err}").contains("sales.summary"), "{err}");
    }

    /// The reason this step routes through `execute_page` instead of `queries::execute`: the rows
    /// are really capped, and the total is really the total. A `count` taken off a trimmed result
    /// would be a smaller number stated as the whole truth.
    #[tokio::test]
    async fn the_ceiling_bounds_the_rows_and_the_total_still_tells_the_truth() {
        let db = db().await;
        for i in 1..=5 {
            sale(&db, &format!("s-{i}"), "2026-08-15", "10.00").await;
        }
        allow(&db, "sales.all").await;

        let page = execute_flow_query_page(
            &db,
            &registry(),
            HUB,
            FLOW,
            "run-1",
            "sales.all",
            &Params::new(),
            2,
        )
        .await
        .unwrap();

        assert_eq!(page.rows.len(), 2, "the ceiling is real");
        assert_eq!(page.total, 5, "and the total is not the ceiling");
    }

    /// A plain query declares its own JSON Schema and it is validated against exactly the params
    /// it is given. `limit`/`offset` belong to the LIST engine, so pushing them at a query that
    /// composes no page would turn a legal read into `flow.invalid_payload` — the ceiling is
    /// applied to the result instead.
    #[tokio::test]
    async fn a_strict_schema_does_not_see_paging_parameters_it_never_declared() {
        let db = db().await;
        for i in 1..=3 {
            sale(&db, &format!("s-{i}"), "2026-08-15", "10.00").await;
        }
        let mut reg = registry();
        let mut strict = test_support::query(
            "sales",
            "sales.view_sale",
            "SELECT id, total FROM sale WHERE day = :day ORDER BY id",
        );
        strict.schema = Some(
            crate::registry::CompiledSchema::compile(&json!({
                "type": "object",
                "properties": { "day": { "type": "string" } },
                "required": ["day"],
                "additionalProperties": false
            }))
            .unwrap(),
        );
        reg.queries.insert("sales.strict".into(), strict);
        grants::replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Query, "sales.strict")],
            "hub_user:1",
        )
        .await
        .unwrap();

        let read = run(
            &db,
            &reg,
            HUB,
            FLOW,
            "run-1",
            &step(json!({
                "id": "s", "kind": "query", "query": "sales.strict",
                "params": { "day": "input.day" }, "limit": 2
            })),
            &scope(),
        )
        .await
        .expect("a read whose schema forbids extra keys still runs");

        assert_eq!(
            read.output["count"],
            json!(3),
            "and the total is still the truth"
        );
    }

    /// A row whose own column is called `count` must not be able to redefine what the contract key
    /// means: a `condition` downstream reads it as the number of rows.
    #[tokio::test]
    async fn a_column_cannot_shadow_the_contract_keys() {
        let db = db().await;
        db.execute_batch("CREATE TABLE shadow (count TEXT NOT NULL, found TEXT NOT NULL);")
            .await
            .unwrap();
        db.execute(
            "INSERT INTO shadow (count, found) VALUES ('mil', 'quizas')",
            &Params::new(),
        )
        .await
        .unwrap();
        let mut reg = registry();
        reg.queries.insert(
            "sales.shadow".into(),
            test_support::query(
                "sales",
                "sales.view_sale",
                "SELECT count, found FROM shadow",
            ),
        );
        grants::replace(
            &db,
            HUB,
            FLOW,
            &reg,
            &[GrantSpec::pair(GrantKind::Query, "sales.shadow")],
            "hub_user:1",
        )
        .await
        .unwrap();

        let read = run(
            &db,
            &reg,
            HUB,
            FLOW,
            "run-1",
            &step(json!({ "id": "s", "kind": "query", "query": "sales.shadow" })),
            &scope(),
        )
        .await
        .unwrap();

        assert_eq!(read.output["count"], json!(1));
        assert_eq!(read.output["found"], json!(true));
    }
}
