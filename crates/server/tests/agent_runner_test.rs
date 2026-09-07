//! **The agent runner, end to end** (hub#665 — ADR-0283 K5/D3): the piece that makes the star
//! case possible — *the AI answers WhatsApp at 3 AM, reads the diary, reasons about how long the
//! service takes, and books the appointment; the sensitive writes wait for a person.*
//!
//! Everything here runs against a **fake SaaS**: a real HTTP server on `127.0.0.1:0` speaking the
//! same SSE dialect as `saas/apps/assistant/api/views.py::proxy_chat_stream`. Not a mocked client
//! — the actual bytes, over the actual socket, through the actual `reqwest` in `AppState`. The one
//! thing that cannot be faked away is exactly what this issue is most likely to get wrong.
//!
//! ## The spike (`flows.md` §12.2): are the `function_call` arguments complete?
//!
//! Two different questions hide behind that sentence, and only one of them is a real hazard.
//!
//! 1. **Across SSE events** — no. The SaaS orchestrator accumulates the provider's streamed
//!    tool-call deltas itself (`openai_provider`: `frag["arguments"] += fn.arguments`) and only
//!    yields ONE `function_call` event per call, after the provider stream closes, with the whole
//!    normalised `arguments` string. Nothing to reassemble at the event level.
//! 2. **Across TCP chunks** — YES, and this is the failure that would have been silent. A single
//!    `data: {…}` line arrives split wherever the network split it, and half a JSON object parses
//!    as nothing. `translate_sse_line` would then fall through to its non-JSON branch and emit the
//!    fragment as a *token*: the tool call would simply vanish, the model would be told nothing
//!    happened, and the appointment would never be booked — with no error anywhere.
//!
//! So the runner buffers by LINE and only translates complete ones (the same discipline the
//! browser path uses in `assistant_chat_stream`), and it accumulates `arguments` per `call_id`
//! across events as belt and braces, in case a future provider path streams them. Both are pinned
//! below by `a_tool_call_split_across_tcp_chunks_is_reassembled_not_lost`, which cuts the line in
//! the middle of the arguments on purpose.
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use async_trait::async_trait;
use axum::body::Body;
use axum::http::{Request, StatusCode};
use axum::response::Response as AxumResponse;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::flows::grants::{GrantKind, GrantSpec};
use erplora_runtime::flows::{approvals, store, NewFlow};
use erplora_runtime::native::{NativeHandler, NativeHost};
use erplora_runtime::Runtime;
use erplora_server::{agent_runner, app, AppState, AuthMode, HubConfig};
use erplora_wasm_host::Output;
use http_body_util::BodyExt;
use serde_json::{json, Value};
use tower::ServiceExt;

const HUB: &str = "hub-agent-runner";

// ── the fake SaaS ─────────────────────────────────────────────────────────────────────────────

/// A scripted assistant proxy. Each request pops the next script; the bodies it received are kept
/// so a test can assert **what the hub offered the model**, which is where the three-way tool
/// intersection either happens or does not.
/// One scripted turn, as a list of the **network chunks** it is delivered in. A turn is normally
/// one chunk; the spike test hands over two, cut mid-JSON.
type Turn = Vec<String>;

#[derive(Clone, Default)]
struct FakeCloud {
    scripts: Arc<Mutex<Vec<Turn>>>,
    seen: Arc<Mutex<Vec<Value>>>,
}

impl FakeCloud {
    fn with(scripts: Vec<Turn>) -> Self {
        Self {
            // Popped from the back after reversing, so the script reads in turn order.
            scripts: Arc::new(Mutex::new(scripts.into_iter().rev().collect())),
            seen: Arc::new(Mutex::new(Vec::new())),
        }
    }

    fn bodies(&self) -> Vec<Value> {
        self.seen.lock().unwrap().clone()
    }

    fn turns(&self) -> usize {
        self.seen.lock().unwrap().len()
    }

    /// Binds the fake SaaS and returns its base URL. It lives for the whole test.
    async fn serve(&self) -> String {
        let state = self.clone();
        let router = axum::Router::new().route(
            "/api/v1/hub/device/assistant/chat/stream/",
            axum::routing::post(move |axum::Json(body): axum::Json<Value>| {
                let state = state.clone();
                async move {
                    state.seen.lock().unwrap().push(body);
                    let turn = state
                        .scripts
                        .lock()
                        .unwrap()
                        .pop()
                        .unwrap_or_else(|| sse_text("(no script left)"));
                    // Each element is written as its OWN chunk, with a yield between them, so a
                    // split line really crosses a read boundary on the hub's side.
                    let stream = futures_util::stream::iter(
                        turn.into_iter()
                            .map(|chunk| Ok::<_, std::io::Error>(axum::body::Bytes::from(chunk))),
                    );
                    AxumResponse::builder()
                        .header("content-type", "text/event-stream")
                        .body(Body::from_stream(stream))
                        .unwrap()
                }
            }),
        );
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let address = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, router).await.unwrap();
        });
        format!("http://{address}")
    }
}

/// A turn that answers in plain text and stops.
fn sse_text(text: &str) -> Turn {
    vec![format!(
        "data: {}\n\ndata: [DONE]\n\n",
        json!({ "type": "text_delta", "text": text })
    )]
}

/// A turn that asks for one tool call, exactly as the SaaS emits it: one event, whole arguments
/// (the orchestrator has already accumulated the provider's deltas — see the spike note above).
fn sse_call(name: &str, call_id: &str, arguments: Value) -> Turn {
    vec![format!(
        "data: {}\n\ndata: [DONE]\n\n",
        json!({
            "type": "function_call",
            "name": name,
            "call_id": call_id,
            "arguments": arguments.to_string()
        })
    )]
}

// ── the hub ───────────────────────────────────────────────────────────────────────────────────

/// The `agenda` module's native engine, so its ONE handler-backed operation actually runs.
///
/// `agenda.availability.check` is the shape hub#1595 is about: an operation a module publishes as
/// a *command* — because answering needs a handler, not a SELECT — that changes nothing. It has no
/// `sql` and no `emit`, and it asks for `agenda.view`, the same permission the module gives its own
/// queries. Without a body behind it the test could only prove that no approval row was written;
/// with one it also proves the ANSWER came back into the turn.
#[derive(Debug)]
struct AgendaEngine;

#[async_trait]
impl NativeHandler for AgendaEngine {
    async fn call(
        &self,
        function: &str,
        input: &Value,
        _host: &dyn NativeHost,
    ) -> Result<Output, erplora_runtime::RuntimeError> {
        match function {
            // Answers, and only answers: no `Operation`, no event, just the verdict.
            "check_availability" => Ok(Output::new().with_result(json!({
                "slot_id": input["payload"]["slot_id"].clone(),
                "free": true,
            }))),
            other => Err(erplora_runtime::RuntimeError::Native(format!(
                "the agenda fixture has no native function `{other}`"
            ))),
        }
    }
}

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_agent/agenda")
}

/// The SAME module, one version later, with a stricter schema for `agenda.booking.create`
/// (`minutes` becomes required). It exists to reproduce the one thing validating at proposal time
/// cannot cover: the contract moving between the proposal and the approval (hub#825).
fn stricter_fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_agent/agenda_v2")
}

fn config(cloud_base_url: String, tag: &str) -> HubConfig {
    let temp = std::env::temp_dir().join(format!("erplora-agent-{tag}-{}", std::process::id()));
    HubConfig {
        demo: false,
        hub_id: HUB.into(),
        cloud_base_url,
        module_cache: temp.join("modules-cache"),
        auth_mode: AuthMode::Session,
        jwt_public_key: None,
        // The runner talks to the SaaS with the hub's MACHINE credential: there is nobody logged
        // in at 3 AM, which is the entire point of the feature.
        cloud_api_token: Some("machine-secret".into()),
        device_trust_enforce: false,
        media_dir: temp,
        sector: None,
        dev_mode: false,
        dev_modules_dir: None,
        module_trusted_keys: Vec::new(),
    }
}

struct Hub {
    state: AppState,
    router: axum::Router,
    admin_session: String,
    admin_id: String,
    flow_id: String,
}

/// A hub with the `agenda` module installed, one flow whose only step is the agent turn, and the
/// grants the story needs: read the diary, write a booking.
async fn hub(
    cloud_base_url: String,
    tag: &str,
    step: Value,
    grants: &[GrantSpec],
) -> Hub {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), HUB);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture()).await.unwrap();
    rt.register_native("agenda", Arc::new(AgendaEngine));
    let admin = rt.create_user("Ioan", "1111", "admin", None).await.unwrap();
    let admin_session = rt.create_session(&admin, 3600, None).await.unwrap();

    let flow = rt
        .create_flow(
            &NewFlow {
                name: "WhatsApp booking".into(),
                enabled: true,
                definition: json!({ "schema_version": 1, "steps": [step] }),
            },
            "hub_user:owner",
        )
        .await
        .unwrap();
    rt.replace_flow_grants(&flow.id, grants, "hub_user:owner")
        .await
        .unwrap();

    let state = AppState::with_config(rt, config(cloud_base_url, tag));
    Hub {
        router: app(state.clone()),
        state,
        admin_session,
        admin_id: admin,
        flow_id: flow.id,
    }
}

/// The step of the story: read the diary, then book.
fn agent_step(policy: &str) -> Value {
    json!({
        "id": "agent",
        "kind": "ai",
        "prompt": "A customer wrote at 3 AM: «{{input.text}}». Book them in.",
        "tools": {
            "queries": ["agenda.slots.list"],
            "commands": ["agenda.booking.create"]
        },
        "policy": policy
    })
}

/// The step of hub#1595: the automation has to ASK something before it can propose anything.
/// `agenda.availability.check` is a command that only answers; `agenda.booking.create` writes.
fn agent_step_that_asks_before_it_writes(policy: &str) -> Value {
    json!({
        "id": "agent",
        "kind": "ai",
        "prompt": "A customer wrote at 3 AM: «{{input.text}}». Book them in.",
        "tools": {
            "queries": [],
            "commands": ["agenda.availability.check", "agenda.booking.create"]
        },
        "policy": policy
    })
}

async fn start_run(h: &Hub, input: Value) -> String {
    let rt = h.state.runtime.read().await;
    rt.start_flow_run(&h.flow_id, &input, "hub_user:owner")
        .await
        .unwrap();
    let report = rt.process_flows().await.unwrap();
    match report.pending_io.first() {
        Some(erplora_runtime::flows::executor::PendingIo::Ai { run_id, .. }) => run_id.clone(),
        other => panic!("the tick must hand the agent turn to the server: {other:?}"),
    }
}

async fn bookings(h: &Hub) -> Vec<Value> {
    let rt = h.state.runtime.read().await;
    rt.db_for_test()
        .query(
            "SELECT customer, starts_at, minutes, created_by FROM agenda_booking ORDER BY starts_at",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
}

/// Performs the parked agent turn exactly as production does: the runner answers with an
/// [`IoResult`] and `flow_io::dispatch` hands it to `complete_flow_io`. Doing both here — rather
/// than calling the runner alone — is what keeps these tests honest about the seam.
async fn perform(h: &Hub, run_id: &str) {
    let result = agent_runner::run_turn(&h.state, run_id, "agent").await;
    let rt = h.state.runtime.read().await;
    rt.complete_flow_io(run_id, "agent", result).await.unwrap();
}

/// One turn of the background loop. The tick — never the runner — is what carries a run past the
/// step the agent finished, exactly as it does for every other kind of step.
async fn tick(h: &Hub) {
    let rt = h.state.runtime.read().await;
    rt.process_flows().await.unwrap();
}

async fn run_status(h: &Hub, run_id: &str) -> String {
    let rt = h.state.runtime.read().await;
    rt.get_flow_run(run_id).await.unwrap().0.status
}

async fn step_output(h: &Hub, run_id: &str) -> Value {
    let rt = h.state.runtime.read().await;
    let (_, steps) = rt.get_flow_run(run_id).await.unwrap();
    steps
        .iter()
        .find(|s| s.step_id == "agent")
        .map(|s| s.output.clone())
        .unwrap_or(Value::Null)
}

async fn seed_slots(h: &Hub) {
    let rt = h.state.runtime.read().await;
    let mut p = Params::new();
    p.insert("hub".into(), json!(HUB));
    rt.db_for_test()
        .execute(
            "INSERT INTO agenda_slot (id, hub_id, starts_at, minutes) \
             VALUES ('slot-1', :hub, '2026-08-10T10:00:00Z', 30)",
            &p,
        )
        .await
        .unwrap();
}

async fn body_json(response: axum::response::Response) -> Value {
    let bytes = response.into_body().collect().await.unwrap().to_bytes();
    serde_json::from_slice(&bytes).unwrap()
}

fn request(method: &str, uri: &str, session: Option<&str>, body: Option<Value>) -> Request<Body> {
    let mut builder = Request::builder().method(method).uri(uri);
    if let Some(token) = session {
        builder = builder.header("x-hub-session", token);
    }
    match body {
        Some(value) => builder
            .header("content-type", "application/json")
            .body(Body::from(value.to_string()))
            .unwrap(),
        None => builder.body(Body::empty()).unwrap(),
    }
}

// ── the star case ─────────────────────────────────────────────────────────────────────────────

/// The whole story, at 3 AM, with nobody at the counter: the model reads the diary on its own
/// (a query runs unattended — it changes nothing), then proposes the booking, and THAT waits.
#[tokio::test]
async fn the_agent_reads_the_diary_by_itself_and_the_booking_waits_for_a_person() {
    let cloud = FakeCloud::with(vec![
        sse_call("agenda.slots.list", "c1", json!({})),
        sse_call(
            "agenda.booking.create",
            "c2",
            json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 30 }),
        ),
    ]);
    let h = hub(
        cloud.serve().await,
        "star",
        agent_step("manual"),
        &[
            GrantSpec::pair(GrantKind::Query, "agenda.slots.list"),
            GrantSpec::pair(GrantKind::Command, "agenda.booking.create"),
        ],
    )
    .await;
    seed_slots(&h).await;
    let run_id = start_run(&h, json!({ "text": "can I come tomorrow at 10?" })).await;

    perform(&h, &run_id).await;

    // The read ran on its own — that is the "consults the diary" half of the case.
    assert_eq!(
        cloud.turns(),
        2,
        "the query's result was fed back and the turn continued"
    );
    let second = &cloud.bodies()[1];
    let roles: Vec<&str> = second["messages"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|m| m["role"].as_str())
        .collect();
    assert!(
        roles.contains(&"tool"),
        "the query's rows go back to the model as a tool result: {second}"
    );

    // The write did NOT run — it became a row a person will read in the morning.
    assert!(
        bookings(&h).await.is_empty(),
        "an unattended model does not write to the business database (ADR-0283 D3)"
    );
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_WAITING_APPROVAL
    );

    let rt = h.state.runtime.read().await;
    let pending = rt
        .list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
        .await
        .unwrap();
    drop(rt);
    assert_eq!(pending.len(), 1);
    assert_eq!(pending[0].command, "agenda.booking.create");
    assert_eq!(
        pending[0].payload["customer"], "Marta",
        "the tray shows exactly what will run, not an opaque id"
    );
    assert_eq!(
        pending[0].payload["minutes"], 30,
        "including the duration the model reasoned about"
    );

    // …and the turn ENDED there: no third call to the model while it waits.
    assert_eq!(
        cloud.turns(),
        2,
        "a proposal awaiting approval ends the turn; it does not keep the model spinning"
    );
}

/// **hub#1595 — a question is not a proposal.**
///
/// The automation that answers WhatsApp has to consult before it can propose: is that slot still
/// free? The answer lives behind an operation the module publishes as a *command*, because
/// answering it needs a handler and not a SELECT. Under `policy: "manual"` — the default, and the
/// policy any step that ALSO writes has to use — that question used to be parked in
/// `_flow_approvals` and end the turn: the owner opened the tray in the morning and was asked to
/// approve «check availability», which is not a decision anybody can take, and the appointment was
/// never proposed at all.
///
/// A command that only answers now runs in the turn, exactly like a query, and the model carries
/// on to the part that DOES need a person. The rule is the one hub#1594 already proved and left
/// `pub(crate)` for this: no `sql`, no `emit`, no row expectations, normal risk, and a permission
/// the module also gives its own queries.
#[tokio::test]
async fn a_question_the_automation_asks_is_answered_in_the_turn_and_only_the_write_waits() {
    let cloud = FakeCloud::with(vec![
        sse_call(
            "agenda.availability.check",
            "c1",
            json!({ "slot_id": "slot-1" }),
        ),
        sse_call(
            "agenda.booking.create",
            "c2",
            json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 30 }),
        ),
    ]);
    let h = hub(
        cloud.serve().await,
        "asks",
        agent_step_that_asks_before_it_writes("manual"),
        &[
            GrantSpec::pair(GrantKind::Command, "agenda.availability.check"),
            GrantSpec::pair(GrantKind::Command, "agenda.booking.create"),
        ],
    )
    .await;
    seed_slots(&h).await;
    let run_id = start_run(&h, json!({ "text": "is 10 still free tomorrow?" })).await;

    perform(&h, &run_id).await;

    // (1) The question was ANSWERED — the turn continued instead of ending on the question.
    assert_eq!(
        cloud.turns(),
        2,
        "a command that only answers runs in the turn, like a query does"
    );

    // (2) …and what came back is the handler's own answer, not an acknowledgement. This is what
    // separates «it ran» from «it was routed somewhere that happened not to fail».
    let second = &cloud.bodies()[1];
    let tool_message = second["messages"]
        .as_array()
        .unwrap()
        .iter()
        .find(|m| m["role"] == "tool" && m["tool_call_id"] == "c1")
        .unwrap_or_else(|| panic!("the answer never reached the model: {second}"))
        .clone();
    let content: Value =
        serde_json::from_str(tool_message["content"].as_str().unwrap()).expect("a JSON result");
    assert_eq!(content["ok"], json!(true), "got {content}");
    assert_eq!(
        content["result"]["result"],
        json!({ "slot_id": "slot-1", "free": true }),
        "the handler's verdict travels to the model whole: {content}"
    );

    // (3) The tray holds the BOOKING and nothing else: the question never became a decision for a
    // person, and the write still waits for one.
    let rt = h.state.runtime.read().await;
    let pending = rt
        .list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
        .await
        .unwrap();
    drop(rt);
    let parked: Vec<&str> = pending.iter().map(|a| a.command.as_str()).collect();
    assert_eq!(
        parked,
        vec!["agenda.booking.create"],
        "only the write waits for a person"
    );
    assert!(
        bookings(&h).await.is_empty(),
        "the write itself did not run: it is a proposal (ADR-0283 D3)"
    );
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_WAITING_APPROVAL
    );
}

/// Approving from the tray executes exactly what was proposed — through the automation door, so
/// the grant is re-checked and the row is attributed to the flow — and never re-enters the model.
#[tokio::test]
async fn approving_from_the_tray_books_the_appointment_without_asking_the_model_again() {
    let cloud = FakeCloud::with(vec![sse_call(
        "agenda.booking.create",
        "c1",
        json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 45 }),
    )]);
    let h = hub(
        cloud.serve().await,
        "approve",
        agent_step("manual"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;
    perform(&h, &run_id).await;

    let id = {
        let rt = h.state.runtime.read().await;
        rt.list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap()[0]
            .id
            .clone()
    };

    let response = h
        .router
        .clone()
        .oneshot(request(
            "POST",
            &format!("/api/hub/flows/approvals/{id}/approve"),
            Some(&h.admin_session),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    let decided = body_json(response).await;
    assert_eq!(decided["data"]["status"], approvals::STATUS_APPROVED);
    assert_eq!(
        decided["data"]["decided_by"],
        json!(format!("hub_user:{}", h.admin_id)),
        "who decided comes from the resolved session, never from the body"
    );

    let rows = bookings(&h).await;
    assert_eq!(rows.len(), 1, "exactly one booking, exactly as proposed");
    assert_eq!(rows[0]["customer"], "Marta");
    assert_eq!(rows[0]["minutes"], 45);
    assert!(
        rows[0]["created_by"]
            .as_str()
            .unwrap_or_default()
            .starts_with("flow:"),
        "the audit says a flow wrote this: {rows:?}"
    );
    assert_eq!(
        cloud.turns(),
        1,
        "approving runs the proposal; it does not re-plan (re-planning is product, not kernel)"
    );
    tick(&h).await;
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_DONE,
        "the run was handed back to the tick, which carried it to the end"
    );
}

/// Rejecting is worth as much as approving: nothing is written, and the run stops rather than
/// carrying on as if the booking had happened.
#[tokio::test]
async fn rejecting_from_the_tray_books_nothing() {
    let cloud = FakeCloud::with(vec![sse_call(
        "agenda.booking.create",
        "c1",
        json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z" }),
    )]);
    let h = hub(
        cloud.serve().await,
        "reject",
        agent_step("manual"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;
    perform(&h, &run_id).await;
    let id = {
        let rt = h.state.runtime.read().await;
        rt.list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap()[0]
            .id
            .clone()
    };

    let response = h
        .router
        .clone()
        .oneshot(request(
            "POST",
            &format!("/api/hub/flows/approvals/{id}/reject"),
            Some(&h.admin_session),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    assert!(bookings(&h).await.is_empty(), "a rejection writes nothing");
    assert_eq!(run_status(&h, &run_id).await, store::STATUS_CANCELLED);
    assert_eq!(cloud.turns(), 1, "and the model is not asked to try again");
}

/// **hub#1622 — the document's answer reaches the row, and a refusal it lets through carries the
/// run on with its turn.** Between the document and the approval row there are two hops the kernel
/// tests never drive — `prepare` copies `on_reject` into the `AiRequest`, `dispatch` copies it into
/// the `NewApproval` — and pinning either to `cancel` left every other test green while every
/// template's `on_reject: "continue"` became a dead letter. This drives the REAL runner against a
/// scripted SaaS, then says no from the tray.
#[tokio::test]
async fn hub1622_a_refusal_the_document_lets_through_carries_the_run_on_with_its_turn() {
    // The shape a real turn has: the model WRITES (the sentence a later step is meant to send
    // on) and then proposes. One turn, two events.
    let text = "No free slot on Friday; I can offer Monday at 10.";
    let cloud = FakeCloud::with(vec![vec![format!(
        "data: {}\n\ndata: {}\n\ndata: [DONE]\n\n",
        json!({ "type": "text_delta", "text": text }),
        json!({
            "type": "function_call",
            "name": "agenda.booking.create",
            "call_id": "c1",
            "arguments": json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z" }).to_string()
        })
    )]]);
    let mut step = agent_step("manual");
    step["on_reject"] = json!("continue");
    let h = hub(
        cloud.serve().await,
        "reject-continue",
        step,
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;
    perform(&h, &run_id).await;

    let pending = {
        let rt = h.state.runtime.read().await;
        rt.list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap()
    };
    assert_eq!(pending.len(), 1, "the write waits for a person");
    assert_eq!(
        pending[0].on_reject,
        approvals::ON_REJECT_CONTINUE,
        "the row records what the DOCUMENT said, carried through the request — not the default"
    );

    let response = h
        .router
        .clone()
        .oneshot(request(
            "POST",
            &format!("/api/hub/flows/approvals/{}/reject", pending[0].id),
            Some(&h.admin_session),
            Some(json!({ "comment": "we are full that day" })),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);

    assert!(bookings(&h).await.is_empty(), "a rejection writes nothing");
    tick(&h).await;
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_DONE,
        "`continue` means the run finishes its remaining steps instead of dying in `cancelled`"
    );
    let output = step_output(&h, &run_id).await;
    assert_eq!(output["status"], json!(approvals::STATUS_REJECTED));
    assert_eq!(output["decision"], json!(approvals::STATUS_REJECTED));
    assert_eq!(output["comment"], json!("we are full that day"));
    assert_eq!(
        output["text"],
        json!(text),
        "the turn parked when the model stopped to ask is handed over, not just how it ended"
    );
    assert_eq!(cloud.turns(), 1, "and the model is not asked to try again");
}

/// **hub#1634 — the document's answer about a SILENCE reaches the row, and an expiry it lets
/// through carries the run on with its turn.** The exact twin of the test above, and it exists
/// because hub#1622's own review found that the two hops between the document and the row
/// (`prepare` → `AiRequest`, `dispatch` → `NewApproval`) had no test: pinning either to `reject`
/// leaves the whole kernel green while every template's `on_expire: "continue"` is a dead letter.
///
/// This is the customer-visible half of whatsapp_inbox#70: the salon never looks at the tray, the
/// proposal expires at 72 h, and the woman who wrote at 3 AM has to be told — which cannot happen
/// if the run dies in `cancelled` the moment the sweep touches it.
#[tokio::test]
async fn hub1634_a_proposal_nobody_answers_carries_the_run_on_with_its_turn() {
    // The same shape a real turn has: the model WRITES the sentence a later step is meant to send
    // on, and then proposes. One turn, two events.
    let text = "No free slot on Friday; I can offer Monday at 10.";
    let cloud = FakeCloud::with(vec![vec![format!(
        "data: {}\n\ndata: {}\n\ndata: [DONE]\n\n",
        json!({ "type": "text_delta", "text": text }),
        json!({
            "type": "function_call",
            "name": "agenda.booking.create",
            "call_id": "c1",
            "arguments": json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z" }).to_string()
        })
    )]]);
    let mut step = agent_step("manual");
    step["on_expire"] = json!("continue");
    let h = hub(
        cloud.serve().await,
        "expire-continue",
        step,
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;
    perform(&h, &run_id).await;

    let pending = {
        let rt = h.state.runtime.read().await;
        rt.list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap()
    };
    assert_eq!(pending.len(), 1, "the write waits for a person");
    assert_eq!(
        pending[0].on_expire,
        approvals::ON_EXPIRE_CONTINUE,
        "the row records what the DOCUMENT said about a silence, carried through the request — \
         not the default the row used to be pinned to"
    );

    // Nobody answers, and the 72 h pass. The sweep is the only piece that reads the policy.
    {
        let rt = h.state.runtime.read().await;
        let mut p = Params::new();
        p.insert("id".into(), json!(pending[0].id));
        rt.db_for_test()
            .execute(
                "UPDATE _flow_approvals SET expires_at = '2020-01-01T00:00:00+00:00' \
                 WHERE id = :id",
                &p,
            )
            .await
            .unwrap();
        let report = rt.sweep_expired_flow_approvals().await.unwrap();
        assert_eq!(report.expired, 1);
        assert_eq!(
            report.runs_resumed, 1,
            "`continue` resumes the run instead of killing it: {report:?}"
        );
    }

    assert!(
        bookings(&h).await.is_empty(),
        "an expiry is the opposite of an approval: nothing the model proposed is executed"
    );
    tick(&h).await;
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_DONE,
        "`continue` means the run finishes its remaining steps instead of dying in `cancelled`"
    );
    let output = step_output(&h, &run_id).await;
    assert_eq!(output["status"], json!(approvals::STATUS_EXPIRED));
    assert_eq!(
        output["text"],
        json!(text),
        "the turn parked when the model stopped to ask is handed over, so the step written to \
         answer the customer has something to say"
    );
    assert_eq!(cloud.turns(), 1, "and the model is not asked to try again");
}

/// `policy: "auto"` is the owner saying, in writing, "do it". Then the command runs in the turn
/// and the model is told what happened, so it can answer the customer.
#[tokio::test]
async fn under_policy_auto_the_command_runs_in_the_turn() {
    let cloud = FakeCloud::with(vec![
        sse_call(
            "agenda.booking.create",
            "c1",
            json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 30 }),
        ),
        sse_text("Booked for tomorrow at 10."),
    ]);
    let h = hub(
        cloud.serve().await,
        "auto",
        agent_step("auto"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;

    perform(&h, &run_id).await;

    assert_eq!(bookings(&h).await.len(), 1);
    tick(&h).await;
    assert_eq!(run_status(&h, &run_id).await, store::STATUS_DONE);
    assert_eq!(
        step_output(&h, &run_id).await["text"],
        "Booked for tomorrow at 10.",
        "the answer the model produced is the step's output, readable by later steps"
    );
}

/// The gate is the grant, and it is the SAME gate the kernel's own `command` steps go through
/// (`Origin::Automation`). Under `policy:"auto"` a command the flow was not granted is refused by
/// the runtime, not by the runner's good manners.
#[tokio::test]
async fn a_command_without_a_grant_is_refused_even_under_policy_auto() {
    let cloud = FakeCloud::with(vec![
        sse_call("agenda.booking.cancel", "c1", json!({ "id": "whatever" })),
        sse_text("I could not do that."),
    ]);
    let h = hub(
        cloud.serve().await,
        "nogrant",
        json!({
            "id": "agent", "kind": "ai", "prompt": "cancel it", "policy": "auto",
            // The document DECLARES the tool; the grant is what is missing.
            "tools": { "commands": ["agenda.booking.cancel"] }
        }),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({})).await;

    perform(&h, &run_id).await;

    let bodies = cloud.bodies();
    let offered: Vec<&str> = bodies[0]["tools"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|t| t["name"].as_str())
        .collect();
    assert!(
        !offered.contains(&"agenda.booking.cancel"),
        "a tool outside the grants is not even OFFERED to the model: {offered:?}"
    );
}

/// The three-way intersection of ADR-0283 §7, asserted on the wire. A tool has to be (1) assembled
/// from the registry under the flow's own permissions, (2) declared by the step, and (3) granted.
/// Two out of three is not enough — and the one that is easiest to forget is the step's list, which
/// is how an author bounds what a specific agent turn may touch.
#[tokio::test]
async fn the_model_is_offered_the_intersection_of_the_registry_the_step_and_the_grants() {
    let cloud = FakeCloud::with(vec![sse_text("nothing to do")]);
    let h = hub(
        cloud.serve().await,
        "intersect",
        json!({
            "id": "agent", "kind": "ai", "prompt": "just look",
            // Declares ONE of the two granted reads. `agenda.bookings.list` is granted but not
            // declared: this turn is about free slots.
            "tools": { "queries": ["agenda.slots.list"] }
        }),
        &[
            GrantSpec::pair(GrantKind::Query, "agenda.slots.list"),
            GrantSpec::pair(GrantKind::Query, "agenda.bookings.list"),
            GrantSpec::pair(GrantKind::Command, "agenda.booking.create"),
        ],
    )
    .await;
    let run_id = start_run(&h, json!({})).await;

    perform(&h, &run_id).await;

    let bodies = cloud.bodies();
    let offered: Vec<&str> = bodies[0]["tools"]
        .as_array()
        .unwrap()
        .iter()
        .filter_map(|t| t["name"].as_str())
        .collect();
    assert_eq!(
        offered,
        vec!["agenda.slots.list"],
        "granted but not declared by the step is still not offered: {offered:?}"
    );
}

/// **The spike, pinned.** The `data:` line carrying the tool call is cut in half mid-JSON, exactly
/// as a TCP chunk boundary would cut it. Without line buffering the fragment parses as nothing,
/// `translate_sse_line` emits it as a token, the call disappears and the appointment is never
/// booked — silently, which is the worst failure this piece can have.
#[tokio::test]
async fn a_tool_call_split_across_tcp_chunks_is_reassembled_not_lost() {
    let whole = sse_call(
        "agenda.booking.create",
        "c1",
        json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 30 }),
    )
    .remove(0);
    // Cut in the middle of the arguments string — mid-JSON, mid-line, mid-value. Same bytes,
    // delivered in two writes.
    let cut = whole.find("starts_at").unwrap();
    let split = vec![whole[..cut].to_string(), whole[cut..].to_string()];

    let cloud = FakeCloud::with(vec![split]);
    let h = hub(
        cloud.serve().await,
        "chunked",
        agent_step("auto"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({})).await;

    perform(&h, &run_id).await;

    let rows = bookings(&h).await;
    assert_eq!(
        rows.len(),
        1,
        "the split line must be reassembled before it is parsed"
    );
    assert_eq!(rows[0]["starts_at"], "2026-08-10T10:00:00Z");
}

/// A model that keeps calling tools forever is real money: every turn goes through the SaaS proxy,
/// which meters it (`AssistantUsage`). The cap is enforced server-side, and hitting it FAILS the
/// step — it does not quietly answer as if the loop had finished.
#[tokio::test]
async fn max_iters_stops_a_runaway_loop_and_fails_the_step() {
    let scripts = (0..12)
        .map(|i| sse_call("agenda.slots.list", &format!("c{i}"), json!({})))
        .collect();
    let cloud = FakeCloud::with(scripts);
    let h = hub(
        cloud.serve().await,
        "maxiters",
        json!({
            "id": "agent", "kind": "ai", "prompt": "look forever", "policy": "auto",
            "max_iters": 3,
            "tools": { "queries": ["agenda.slots.list"] }
        }),
        &[GrantSpec::pair(GrantKind::Query, "agenda.slots.list")],
    )
    .await;
    let run_id = start_run(&h, json!({})).await;

    perform(&h, &run_id).await;

    assert_eq!(
        cloud.turns(),
        3,
        "the cap is counted server-side, not trusted to the model"
    );
    let rt = h.state.runtime.read().await;
    let (run, _) = rt.get_flow_run(&run_id).await.unwrap();
    assert_eq!(run.status, store::STATUS_FAILED);
    assert!(
        run.last_error.contains(agent_runner::ERR_MAX_ITERS),
        "the failure names the cap: {}",
        run.last_error
    );
}

// ── hub#825: the tray only ever shows what, if approved, runs ─────────────────────────────────

/// **The proposal the hub could refute before writing it down.**
///
/// The owner opens the tray at 9 AM, reads «book Marta in», presses **Approve** — and gets a
/// validation error. The row is left `approved` **with an error**, the run `failed`, and there is
/// nothing she can do: she cannot edit the payload, cannot retry, and the model never comes back.
/// Her decision was spent on a proposal the hub already knew it could not execute when it wrote it.
///
/// The kernel proves it knew: under `policy:"auto"` the SAME invalid payload comes back to the model
/// as a tool result and the run survives (§14.9). So the fix is not a new mechanism — it is making
/// `manual` take the path `auto` already takes: validate against the command's JSON Schema **before**
/// the approval row exists, hand the failure to the model as a tool result, and let it correct in the
/// same turn. Nothing impossible reaches a person.
///
/// Both of the QA's payloads are reproduced: a missing required property, and a `null` / wrong type.
#[tokio::test]
async fn an_invalid_proposal_never_reaches_the_tray_and_the_model_corrects_it_in_the_same_turn() {
    for (what, invalid) in [
        // Missing required properties — what a model does with a command whose schema asks for
        // more than the conversation gave it.
        ("missing required", json!({ "customer": "Marta" })),
        // …and the other shape the QA saw: a null where a string is required, and a type that is
        // not the declared one.
        (
            "null / wrong type",
            json!({ "customer": "Marta", "starts_at": null, "minutes": "half an hour" }),
        ),
    ] {
        let cloud = FakeCloud::with(vec![
            sse_call("agenda.booking.create", "c1", invalid),
            // The correction: same turn, same model, now with a payload the schema accepts.
            sse_call(
                "agenda.booking.create",
                "c2",
                json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z", "minutes": 30 }),
            ),
        ]);
        let h = hub(
            cloud.serve().await,
            "invalid-proposal",
            agent_step("manual"),
            &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
        )
        .await;
        let run_id = start_run(&h, json!({ "text": "book me" })).await;

        perform(&h, &run_id).await;

        // The model was TOLD, in the same turn, exactly as `auto` tells it.
        assert_eq!(
            cloud.turns(),
            2,
            "{what}: the refutable payload must come back to the model, not end the turn"
        );
        let second = &cloud.bodies()[1];
        let tool_answer = second["messages"]
            .as_array()
            .unwrap()
            .iter()
            .find(|m| m["role"] == "tool")
            .unwrap_or_else(|| panic!("{what}: the refusal goes back as a tool result: {second}"))
            ["content"]
            .as_str()
            .unwrap_or_default()
            .to_string();
        assert!(
            tool_answer.contains("agenda.booking.create"),
            "{what}: the model has to be told WHICH call failed and why: {tool_answer}"
        );

        // …and the tray holds ONE row: the corrected proposal. The impossible one was never written.
        let rt = h.state.runtime.read().await;
        let pending = rt
            .list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap();
        drop(rt);
        assert_eq!(
            pending.len(),
            1,
            "{what}: a person must only ever be shown what, if approved, runs"
        );
        assert_eq!(pending[0].payload["starts_at"], "2026-08-10T10:00:00Z");
        assert_eq!(
            run_status(&h, &run_id).await,
            store::STATUS_WAITING_APPROVAL,
            "{what}: the run waits for the person, as it should"
        );
    }
}

/// A model that cannot produce a valid payload does not turn into a broken proposal either: it
/// answers in words, the run finishes, and the tray stays empty. The alternative — parking whatever
/// it last said — is the bug this closes wearing a different hat.
#[tokio::test]
async fn a_model_that_never_gets_the_payload_right_ends_in_words_not_in_the_tray() {
    let cloud = FakeCloud::with(vec![
        sse_call(
            "agenda.booking.create",
            "c1",
            json!({ "customer": "Marta" }),
        ),
        sse_text("I could not book that: I am missing the start time."),
    ]);
    let h = hub(
        cloud.serve().await,
        "gives-up",
        agent_step("manual"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;

    perform(&h, &run_id).await;

    let rt = h.state.runtime.read().await;
    assert!(
        rt.list_flow_approvals(None, 50).await.unwrap().is_empty(),
        "nothing impossible was parked for a person"
    );
    drop(rt);
    tick(&h).await;
    assert_eq!(run_status(&h, &run_id).await, store::STATUS_DONE);
    assert!(
        step_output(&h, &run_id).await["text"]
            .as_str()
            .unwrap_or_default()
            .contains("could not"),
        "the model's honest answer is the step's output"
    );
}

/// **The net, for the one case validating at proposal time cannot cover: the schema CHANGED.**
///
/// A module updates between 3 AM and 9 AM and the command now asks for a field the stored payload
/// does not have. Approving must still not execute it — but the row must NOT be burnt as `approved`
/// either. `approved` + error is the state §14.8 reserves for «the person approved and the COMMAND
/// broke»: something ran, or could have. Here nothing could: the refusal happens before the door,
/// exactly like the revoked grant of §7.2, and the remedy is the same — the row stays **pending**, so
/// the person can still reject it and end the run cleanly instead of re-launching the whole flow.
#[tokio::test]
async fn a_schema_that_changed_after_the_proposal_refuses_the_approval_without_burning_it() {
    let cloud = FakeCloud::with(vec![sse_call(
        "agenda.booking.create",
        "c1",
        json!({ "customer": "Marta", "starts_at": "2026-08-10T10:00:00Z" }),
    )]);
    let h = hub(
        cloud.serve().await,
        "schema-moved",
        agent_step("manual"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;
    let run_id = start_run(&h, json!({ "text": "book me" })).await;
    perform(&h, &run_id).await;

    let id = {
        let rt = h.state.runtime.read().await;
        rt.list_flow_approvals(Some(approvals::STATUS_PENDING), 50)
            .await
            .unwrap()[0]
            .id
            .clone()
    };

    // The module updates overnight: `minutes` becomes required, and the stored payload has none.
    {
        let mut rt = h.state.runtime.write().await;
        rt.update_from_dir(&stricter_fixture()).await.unwrap();
    }

    let response = h
        .router
        .clone()
        .oneshot(request(
            "POST",
            &format!("/api/hub/flows/approvals/{id}/approve"),
            Some(&h.admin_session),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNPROCESSABLE_ENTITY);
    let refusal = body_json(response).await["error"]["message"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    assert!(
        refusal.contains("minutes"),
        "the person is told WHAT no longer fits: {refusal}"
    );

    assert!(bookings(&h).await.is_empty(), "nothing was written");
    let rt = h.state.runtime.read().await;
    let row = rt.get_flow_approval(&id).await.unwrap();
    drop(rt);
    assert_eq!(
        row.status,
        approvals::STATUS_PENDING,
        "a decision that could not be carried out is not a decision: the row must not read \
         `approved` about something that never happened"
    );
    assert!(
        row.decided_by.is_empty(),
        "nobody is recorded as having approved it"
    );
    assert_eq!(
        run_status(&h, &run_id).await,
        store::STATUS_WAITING_APPROVAL,
        "the run still waits, so rejecting is still a way out"
    );

    // …and rejecting IS still a way out: the person ends the run cleanly.
    let rejected = h
        .router
        .clone()
        .oneshot(request(
            "POST",
            &format!("/api/hub/flows/approvals/{id}/reject"),
            Some(&h.admin_session),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(rejected.status(), StatusCode::OK);
    assert_eq!(run_status(&h, &run_id).await, store::STATUS_CANCELLED);
}

/// The tray is not a public screen. It is where a person authorises the hub to write while nobody
/// is watching, so it takes an owner/admin session — never an API key, never the machine token
/// (`flows_api.rs` door, ADR-0283 §9).
#[tokio::test]
async fn the_approval_tray_takes_an_admin_session_and_nothing_else() {
    let cloud = FakeCloud::with(vec![sse_text("hi")]);
    let h = hub(
        cloud.serve().await,
        "door",
        agent_step("manual"),
        &[GrantSpec::pair(GrantKind::Command, "agenda.booking.create")],
    )
    .await;

    let anonymous = h
        .router
        .clone()
        .oneshot(request("GET", "/api/hub/flows/approvals", None, None))
        .await
        .unwrap();
    assert_eq!(anonymous.status(), StatusCode::UNAUTHORIZED);

    let signed_in = h
        .router
        .clone()
        .oneshot(request(
            "GET",
            "/api/hub/flows/approvals",
            Some(&h.admin_session),
            None,
        ))
        .await
        .unwrap();
    assert_eq!(signed_in.status(), StatusCode::OK);
    assert_eq!(body_json(signed_in).await["data"], json!([]));
}
