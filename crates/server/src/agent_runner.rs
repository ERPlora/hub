//! **The server-side agent runner** (ADR-0283 K5/D3 — hub#665): the piece that lets the hub answer
//! a customer at 3 AM, read its own diary, reason about how long the service takes, and book the
//! appointment — with the sensitive writes waiting for a person.
//!
//! It lives in `crates/server` and not in the runtime for one reason: it needs `cloud-client`, and
//! **the runtime has no network by design** (ARQUITECTURA.md §9.3 — the hub never talks to an LLM
//! directly; everything goes through the SaaS proxy, which meters it).
//!
//! ```text
//!   flows_tick ──▶ PendingIo::Ai ──▶ run_step  (NO lock held)
//!                                      │
//!                     ┌────────────────┴──────────────────┐
//!                     │  build tools  →  POST SSE  →  aggregate  →  dispatch │
//!                     └────────────────┬──────────────────┘
//!                    query → run it    │  command+auto → run it   │  command+manual → APPROVAL
//! ```
//!
//! ## Why the loop lives here at all
//!
//! Until now the assistant's tool loop lived in the **browser** (`apps/web/src/lib/assistant.ts`):
//! the runtime forwarded `function_call` events and the page ran them with the user's session. That
//! shape cannot serve this feature — there is no page open at 3 AM, and the writes were cut off
//! there on purpose (a mutation needs a confirm-card, and nobody is looking at one). So the loop is
//! rebuilt here, in Rust, with the flow's own authority instead of a user's session, and with the
//! confirm-card replaced by something durable: a row in `_flow_approvals`.
//!
//! ## The three-way tool intersection (ADR-0283 §7)
//!
//! A tool is offered to the model only if it is **(1)** assembled from the registry under the
//! flow's own permissions, **(2)** declared by this step, and **(3)** granted to this flow. Two out
//! of three is not enough, and the one most easily forgotten is the step's list — it is how an
//! author bounds what one particular agent turn may touch, independently of what the flow may do in
//! general.
//!
//! The intersection only decides what is OFFERED. What is *allowed* is re-checked by the runtime
//! when the call is made (`Runtime::execute_flow_query` / `execute_flow_command`), because a gate
//! the caller can skip is not a gate.
//!
//! ## The SSE spike (flows.md §12.2): are the `function_call` arguments complete?
//!
//! Two questions hide behind that one, and only the second is a real hazard.
//!
//! - **Across SSE events: no.** The SaaS orchestrator accumulates the provider's streamed tool-call
//!   deltas itself (`openai_provider`: `frag["arguments"] += fn.arguments`) and yields ONE
//!   `function_call` event per call, after the provider stream closes, carrying the whole
//!   normalised `arguments` string (`orchestrator.run_turn` → `views.proxy_chat_stream`).
//! - **Across TCP chunks: yes**, and this one is silent. A single `data: {…}` line arrives split
//!   wherever the network split it; half a JSON object parses as nothing, and
//!   [`assistant::translate_sse_line`] would then fall through to its non-JSON branch and emit the
//!   fragment as a *token*. The tool call would simply vanish: the model would be told nothing
//!   happened, and the appointment would never be booked, with no error anywhere.
//!
//! So [`Aggregator`] buffers by LINE and only translates complete ones (the same discipline the
//! browser path uses in `assistant_chat_stream`), and it accumulates `arguments` per `call_id`
//! across events as belt and braces, in case a future provider path streams them after all.
use std::collections::{HashMap, HashSet};
use std::time::Duration;

use erplora_db::Params;
use erplora_runtime::flows::{def::AiPolicy, AiRequest, IoResult, NewApproval};
use erplora_runtime::RequestContext;
use futures_util::StreamExt;
use serde_json::{json, Value};

use crate::assistant;
use crate::auth;
use crate::state::AppState;

/// The whole step is bounded, not just each call. A model that answers slowly ten times in a row
/// would otherwise hold a run open for minutes while its lease quietly expires underneath it.
const STEP_TIMEOUT: Duration = Duration::from_secs(60);

/// One turn's HTTP timeout. Below [`STEP_TIMEOUT`] so a single hung call cannot eat the budget.
const TURN_TIMEOUT: Duration = Duration::from_secs(45);

pub const ERR_MAX_ITERS: &str = "flow.agent_max_iters";
pub const ERR_TIMEOUT: &str = "flow.agent_timeout";
pub const ERR_NO_CREDENTIAL: &str = "flow.agent_no_cloud_credential";
pub const ERR_UPSTREAM: &str = "flow.agent_upstream";

/// Performs the agent turn of a step the tick handed over, and answers with what the run should
/// do next.
///
/// **Never called with the runtime lock held** ([`crate::flow_io::dispatch`] is the caller, and it
/// runs outside it). It takes and releases the lock around each piece of LOCAL work — reading the
/// step, running a tool, writing the approval — and holds nothing at all while the network call is
/// in flight. That is the whole reason this function exists instead of the tick doing the work.
///
/// It never returns an error: every failure is an [`IoResult::Failed`] carrying a reason written
/// for whoever reads the run history tomorrow morning.
pub async fn run_turn(st: &AppState, run_id: &str, step_id: &str) -> IoResult {
    match tokio::time::timeout(STEP_TIMEOUT, drive(st, run_id, step_id)).await {
        Ok(Ok(result)) => result,
        Ok(Err(failure)) => IoResult::Failed(failure),
        Err(_) => IoResult::Failed(format!(
            "{ERR_TIMEOUT}: the agent turn did not finish within {} s and was abandoned; a run \
             held open indefinitely outlives its own lease",
            STEP_TIMEOUT.as_secs()
        )),
    }
}

/// The loop. Every `Err` here is a step failure with its reason already written for a human.
async fn drive(st: &AppState, run_id: &str, step_id: &str) -> Result<IoResult, String> {
    let (request, tools) = prepare(st, run_id, step_id).await?;
    let Some(auth) = auth::machine_auth(st) else {
        return Err(format!(
            "{ERR_NO_CREDENTIAL}: this hub has no machine token, so it cannot reach the assistant \
             proxy. A flow acts when nobody is logged in, so a user's JWT is not a fallback here."
        ));
    };

    // The conversation, in the shape the Cloud reads (`build_cloud_body`). The prompt is the user
    // turn; what the tools answer comes back as `role: "tool"` messages, exactly as the browser
    // loop does it.
    let mut messages = vec![json!({ "role": "user", "content": request.prompt })];
    let instructions = {
        let rt = st.runtime.read().await;
        let now = chrono::Utc::now();
        assistant::build_instructions(
            rt.registry(),
            &[automation_briefing(&request)],
            &format!(
                "{} ({})",
                now.format("%Y-%m-%dT%H:%M:%SZ"),
                now.format("%A")
            ),
        )
    };

    let mut answered = String::new();
    let mut calls_made: Vec<Value> = Vec::new();

    for _ in 0..request.max_iters {
        let body = assistant::build_cloud_body(
            &json!({ "messages": messages }),
            tools.offered.clone(),
            None,
            &instructions,
        );
        let turn = one_turn(st, &auth, &body).await?;
        answered = turn.text.clone();

        if turn.calls.is_empty() {
            return Ok(IoResult::Done(
                json!({ "text": answered, "tool_calls": calls_made }),
            ));
        }

        // Rebuild the assistant message that carried the tool calls, then answer each of them —
        // same wire shape as `apps/web/src/lib/assistant.ts`, so the Cloud continues the turn.
        messages.push(json!({
            "role": "assistant",
            "content": turn.text,
            "tool_calls": turn.calls.iter().map(|c| json!({
                "id": c.call_id,
                "type": "function",
                "function": { "name": c.name, "arguments": c.arguments }
            })).collect::<Vec<_>>(),
        }));

        for call in &turn.calls {
            // Everything the turn has produced so far. It travels with an approval park so that a
            // decision taken hours later completes the WHOLE turn — the model's explanation and
            // the reads it did — and not just its ending.
            let so_far = json!({ "text": turn.text, "tool_calls": calls_made });
            match dispatch(st, &request, &tools, call, &so_far).await? {
                Dispatched::Result(result) => {
                    calls_made.push(json!({
                        "name": call.name,
                        "arguments": call.arguments,
                        "result": result,
                    }));
                    messages.push(json!({
                        "role": "tool",
                        "tool_call_id": call.call_id,
                        "content": result.to_string(),
                    }));
                }
                // The turn ENDS here. Feeding «queued for approval» back and letting the model
                // keep going would have it narrate a booking that has not happened, and spend
                // another metered turn doing it. What the turn produced travels with the park, so
                // the decision taken hours later completes the WHOLE turn and not just its ending.
                Dispatched::AwaitingApproval => return Ok(IoResult::AwaitingApproval(so_far)),
            }
        }
    }

    Err(format!(
        "{ERR_MAX_ITERS}: the agent asked for tools {} times without answering, which is the cap \
         this step declared. Every turn is a real call through the SaaS proxy, so the loop is cut \
         here rather than left to the model. Last text: {}",
        request.max_iters,
        if answered.is_empty() {
            "(none)"
        } else {
            &answered
        }
    ))
}

// ── the tools ─────────────────────────────────────────────────────────────────────────────────

/// What the model may be offered, and what each name resolves to.
struct Tools {
    /// The tool specs sent to the Cloud.
    offered: Vec<Value>,
    /// name → `"query"` | `"command"`, for dispatch.
    kinds: HashMap<String, String>,
}

/// Reads the parked request and assembles the tool catalogue, under ONE lock: the registry the
/// tools come from and the grants they are filtered by must be the same snapshot, or a revocation
/// landing between the two reads would produce a catalogue that never existed.
async fn prepare(st: &AppState, run_id: &str, step_id: &str) -> Result<(AiRequest, Tools), String> {
    let rt = st.runtime.read().await;
    let request = rt
        .load_flow_ai_request(run_id, step_id)
        .await
        .map_err(|e| format!("agent: run {run_id} is not ready for a turn: {e}"))?;
    let authority = rt.flow_authority(&request.flow_id).await.map_err(|e| {
        format!(
            "agent: could not read the grants of flow {}: {e}",
            request.flow_id
        )
    })?;

    // (1) Assembled from the registry under the FLOW's own permissions. This is the same catalogue
    // the drawer builds for a user — only the authority differs, and it is the flow's.
    let ctx = RequestContext::new(
        st.hub_id(),
        format!("flow:{}", request.flow_id),
        authority.permissions(rt.registry()),
    );
    let assembled = assistant::assemble_tools(rt.registry(), &ctx);

    // (2) Declared by this step. An empty list means the author gave this turn nothing to call,
    // which is a legitimate way to ask for an answer in words.
    let declared: HashSet<&str> = request
        .queries
        .iter()
        .chain(request.commands.iter())
        .map(String::as_str)
        .collect();

    let mut offered = Vec::new();
    let mut kinds = HashMap::new();
    for tool in assembled {
        let (Some(name), Some(kind)) = (
            tool.get("name").and_then(Value::as_str),
            tool.get("kind").and_then(Value::as_str),
        ) else {
            continue;
        };
        if !declared.contains(name) {
            continue;
        }
        // (3) Granted to this flow, right now. The core's own tools (`module_id: "hub"`) have no
        // grant to check and are deliberately NOT offered here: they are a user's capabilities in
        // the drawer (install a module, read the setup checklist), not a flow's.
        let permitted = match kind {
            "query" => authority.allows_query(name),
            "command" => authority.allows_command(name),
            _ => false,
        };
        if !permitted {
            continue;
        }
        kinds.insert(name.to_string(), kind.to_string());
        offered.push(tool);
    }
    Ok((request, Tools { offered, kinds }))
}

/// The extra system turn that tells the model where it is standing.
///
/// [`assistant::build_instructions`] describes the drawer next to somebody who is working — true
/// for the chat, false here. Without this the model asks clarifying questions of an empty room and
/// promises to «check with you first», which under `policy:"auto"` is a promise it cannot keep.
fn automation_briefing(request: &AiRequest) -> String {
    let mut s = String::from(
        "## You are running UNATTENDED, inside an automation\n\n\
         There is no chat window and no person reading this. You were started by a flow of this \
         hub, so:\n\n\
         - **Nobody can answer a question.** Do not ask for clarification and do not promise to \
         check something later: decide with the tools you have, or say plainly what you could not \
         do. Whatever you write is stored as the step's answer for the rest of the flow to use.\n\
         - **Use the tools for anything factual.** Your only view of this business is what they \
         return.\n",
    );
    match request.policy {
        AiPolicy::Auto => s.push_str(
            "- **Writes take effect immediately.** The owner of this hub pre-authorised the \
             actions you were given, so calling one of them changes real data. Call it once, with \
             the values you actually mean.\n",
        ),
        AiPolicy::Manual => s.push_str(
            "- **Writes do NOT take effect yet.** Any action you call is queued for a person to \
             approve, and your turn ends there. So make the single best proposal you can and \
             describe it precisely — never claim the action is done.\n",
        ),
    }
    s
}

// ── one turn against the SaaS proxy ───────────────────────────────────────────────────────────

/// A tool call the model asked for, with its arguments **whole** (see the spike note above).
#[derive(Debug, Clone, Default)]
struct ToolCall {
    name: String,
    call_id: String,
    arguments: String,
}

#[derive(Debug, Default)]
struct Turn {
    text: String,
    calls: Vec<ToolCall>,
}

/// POSTs one turn and aggregates its SSE. No lock is held for the length of this call.
async fn one_turn(st: &AppState, auth: &cloud_client::Auth, body: &Value) -> Result<Turn, String> {
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let req = cloud.assistant_chat_stream(auth);
    let mut builder = st.http.post(&req.url).timeout(TURN_TIMEOUT).json(body);
    for (k, v) in &req.headers {
        builder = builder.header(*k, v);
    }

    let response = builder
        .send()
        .await
        .and_then(|r| r.error_for_status())
        .map_err(|e| format!("{ERR_UPSTREAM}: the assistant proxy did not answer: {e}"))?;

    let mut aggregator = Aggregator::default();
    let mut stream = response.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk.map_err(|e| format!("{ERR_UPSTREAM}: the stream broke mid-turn: {e}"))?;
        if let Some(error) = aggregator.push(&String::from_utf8_lossy(&chunk)) {
            return Err(format!("{ERR_UPSTREAM}: {error}"));
        }
    }
    aggregator.finish()
}

/// Turns a byte stream of SSE into one [`Turn`].
///
/// **This is the spike.** It buffers by LINE, because a `data:` line is split wherever the network
/// split it and half a JSON object parses as nothing — and it accumulates `arguments` per `call_id`
/// across events, so that a provider path which ever DID stream them would be absorbed here instead
/// of silently losing the tail of a booking.
///
/// The translation of the Cloud's dialect is deliberately not re-implemented: it goes through
/// [`assistant::translate_sse_line`], the same function the browser path uses, so the two cannot
/// drift into disagreeing about what a `function_call` looks like. That function answers with an
/// already-formatted `data: …` frame, which is parsed straight back — a small ugliness bought in
/// exchange for having ONE place that knows the wire vocabulary.
#[derive(Default)]
struct Aggregator {
    buffer: String,
    text: String,
    /// Insertion-ordered, because the order the model asked for calls is the order they run.
    order: Vec<String>,
    calls: HashMap<String, ToolCall>,
    error: Option<String>,
}

impl Aggregator {
    /// Feeds a network chunk. Returns `Some(error)` if the stream reported one.
    fn push(&mut self, chunk: &str) -> Option<String> {
        self.buffer.push_str(chunk);
        while let Some(idx) = self.buffer.find('\n') {
            let line: String = self.buffer.drain(..=idx).collect();
            self.consume(line.trim_end_matches(['\r', '\n']));
        }
        self.error.clone()
    }

    fn consume(&mut self, line: &str) {
        // No tool-kind map is passed: the annotation is for the browser's confirm-card, and here
        // the kind comes from the catalogue this runner assembled itself.
        let Some(frame) = assistant::translate_sse_line(line, &HashMap::new()) else {
            return;
        };
        let Some(event) = frame
            .strip_prefix("data: ")
            .and_then(|p| serde_json::from_str::<Value>(p.trim_end()).ok())
        else {
            return;
        };
        match event.get("type").and_then(Value::as_str) {
            Some("token") => {
                if let Some(t) = event.get("text").and_then(Value::as_str) {
                    self.text.push_str(t);
                }
            }
            Some("function_call") => {
                let call_id = event
                    .get("call_id")
                    .and_then(Value::as_str)
                    .unwrap_or_default()
                    .to_string();
                if !self.calls.contains_key(&call_id) {
                    self.order.push(call_id.clone());
                    self.calls.insert(
                        call_id.clone(),
                        ToolCall {
                            call_id: call_id.clone(),
                            ..ToolCall::default()
                        },
                    );
                }
                let entry = self.calls.get_mut(&call_id).expect("just inserted");
                if let Some(name) = event.get("name").and_then(Value::as_str) {
                    if !name.is_empty() {
                        entry.name = name.to_string();
                    }
                }
                // Appended, never replaced: whole today, and safe if it ever arrives in pieces.
                if let Some(args) = event.get("arguments").and_then(Value::as_str) {
                    entry.arguments.push_str(args);
                }
            }
            Some("error") => {
                self.error = Some(
                    event
                        .get("error")
                        .and_then(Value::as_str)
                        .unwrap_or("the assistant reported an error")
                        .to_string(),
                );
            }
            _ => {}
        }
    }

    /// Closes the stream, translating whatever is left in the buffer (a body that ended without a
    /// trailing newline still carries a complete event).
    fn finish(mut self) -> Result<Turn, String> {
        if !self.buffer.is_empty() {
            let rest = std::mem::take(&mut self.buffer);
            self.consume(rest.trim());
        }
        if let Some(error) = self.error {
            return Err(error);
        }
        let calls = self
            .order
            .iter()
            .filter_map(|id| self.calls.get(id).cloned())
            .filter(|c| !c.name.is_empty())
            .collect();
        Ok(Turn {
            text: self.text,
            calls,
        })
    }
}

// ── dispatch ──────────────────────────────────────────────────────────────────────────────────

enum Dispatched {
    Result(Value),
    AwaitingApproval,
}

/// Runs one tool call, or parks it for a person.
///
/// Everything that goes wrong on this path comes back as a tool RESULT rather than as a step
/// failure: a model that asked for something it may not have should be told so and given the chance
/// to answer the customer honestly, not have the whole run die on it. What does end the run is a
/// broken proposal path — an approval that cannot be written is a booking nobody will ever see.
async fn dispatch(
    st: &AppState,
    request: &AiRequest,
    tools: &Tools,
    call: &ToolCall,
    so_far: &Value,
) -> Result<Dispatched, String> {
    let Some(kind) = tools.kinds.get(&call.name) else {
        // Defence in depth: the model was never offered this, so it should not be asking. It is
        // told, and the turn continues.
        return Ok(Dispatched::Result(json!({
            "error": format!(
                "`{}` is not one of the tools this automation may use", call.name
            )
        })));
    };
    let params = parse_arguments(&call.arguments);

    if kind == "query" {
        let rt = st.runtime.read().await;
        return Ok(Dispatched::Result(
            match rt
                .execute_flow_query(&request.flow_id, &request.run_id, &call.name, &params)
                .await
            {
                Ok(rows) => json!({ "rows": rows }),
                Err(e) => json!({ "error": format!("{e}") }),
            },
        ));
    }

    // A WRITE. Under `manual` — the default — it becomes a row and the turn ends here.
    if !request.policy.is_auto() {
        let rt = st.runtime.read().await;

        // **hub#825 — the tray only ever shows what, if approved, runs.** The payload is judged
        // against the command's JSON Schema HERE, before the row exists, by the same code that will
        // judge it at execution (`Runtime::validate_command_payload`).
        //
        // Without this, `manual` — the DEFAULT, the policy that exists precisely so a person is
        // involved — postponed a failure the hub could already see until after somebody had decided:
        // the owner opened the tray at 9 AM, pressed «approve», got a `422`, and was left with a row
        // marked `approved` **with an error**, a `failed` run, nothing to edit and no way to retry.
        // Her decision was spent on a proposal that was never executable.
        //
        // The path out already existed one branch below: under `policy:"auto"` the same refusal goes
        // back to the model as a tool RESULT and the run survives, because a model that asks for
        // something it cannot have must be able to say so to the customer (flows.md §14.9). Schema
        // validation is a tool failure like any other, so `manual` takes that path too and the model
        // corrects itself in the same turn — the person never sees the impossible version.
        if let Err(e) = rt.validate_command_payload(&call.name, &params) {
            return Ok(Dispatched::Result(json!({ "error": format!("{e}") })));
        }

        rt.request_flow_approval(&NewApproval {
            run_id: request.run_id.clone(),
            flow_id: request.flow_id.clone(),
            step_id: request.step_id.clone(),
            command: call.name.clone(),
            payload: Value::Object(params),
            reason: self_reported_reason(&request.prompt),
            partial_output: {
                let mut parked = so_far.clone();
                if let Some(map) = parked.as_object_mut() {
                    map.insert(
                        "proposed".to_string(),
                        json!({ "command": call.name, "arguments": call.arguments }),
                    );
                }
                parked
            },
        })
        .await
        .map_err(|e| {
            format!(
                "agent: `{}` was proposed but the approval could not be written ({e}); the run is \
                 stopped rather than left believing somebody will see it",
                call.name
            )
        })?;
        return Ok(Dispatched::AwaitingApproval);
    }

    // `policy: "auto"` — the owner said so in writing. The gate is still the runtime's:
    // `execute_flow_command` re-reads the grant and runs through `Origin::Automation`, so the
    // fiscal gates, the schema validation and the transactional outbox all still apply.
    let rt = st.runtime.read().await;
    Ok(Dispatched::Result(
        match rt
            .execute_flow_command(
                &request.flow_id,
                &request.run_id,
                request.depth,
                &call.name,
                &params,
            )
            .await
        {
            Ok(output) => json!({ "ok": true, "result": output }),
            Err(e) => json!({ "error": format!("{e}") }),
        },
    ))
}

/// The model's arguments as a params map. A model that sends something that is not a JSON object
/// gets an empty payload and the command's own schema validation refuses it by name — better than
/// this layer inventing a shape.
fn parse_arguments(raw: &str) -> Params {
    serde_json::from_str::<Value>(raw)
        .ok()
        .and_then(|v| v.as_object().cloned())
        .unwrap_or_default()
}

/// What the tray shows as «why». There is no separate channel for the model to justify a call, so
/// the honest thing to show is the task it was given — not a sentence this layer made up.
fn self_reported_reason(prompt: &str) -> String {
    format!("proposed by the assistant while doing: {prompt}")
}

#[cfg(test)]
mod tests {
    use super::*;

    /// **The spike, at the unit that owns it.** The same bytes, delivered in two writes, must
    /// produce the same tool call. Without line buffering the first fragment parses as nothing,
    /// `translate_sse_line` emits it as a token, and the call disappears — silently.
    #[test]
    fn a_data_line_split_across_chunks_is_reassembled_before_it_is_parsed() {
        let whole = format!(
            "data: {}\n\ndata: [DONE]\n\n",
            json!({
                "type": "function_call",
                "name": "agenda.booking.create",
                "call_id": "c1",
                "arguments": "{\"customer\":\"Marta\",\"starts_at\":\"2026-08-10T10:00:00Z\"}"
            })
        );
        let cut = whole
            .find("starts_at")
            .expect("the cut lands mid-arguments");

        let mut split = Aggregator::default();
        assert!(split.push(&whole[..cut]).is_none());
        assert!(split.push(&whole[cut..]).is_none());
        let from_split = split.finish().unwrap();

        let mut once = Aggregator::default();
        once.push(&whole);
        let from_one = once.finish().unwrap();

        assert_eq!(from_split.calls.len(), 1, "the call must survive the split");
        assert_eq!(from_split.calls[0].name, "agenda.booking.create");
        assert_eq!(
            from_split.calls[0].arguments, from_one.calls[0].arguments,
            "a split delivery and a whole one are the same turn"
        );
        // …and the arguments really are complete JSON, not a truncated prefix.
        let parsed: Value = serde_json::from_str(&from_split.calls[0].arguments).unwrap();
        assert_eq!(parsed["starts_at"], "2026-08-10T10:00:00Z");
    }

    /// Belt and braces for the half of the spike that today's SaaS does NOT do: the orchestrator
    /// accumulates the provider's deltas itself and emits one whole `function_call`. If a future
    /// path ever streamed them, the tail of a booking must not be lost.
    #[test]
    fn arguments_arriving_in_several_events_are_accumulated_not_overwritten() {
        let mut agg = Aggregator::default();
        for fragment in ["{\"customer\":", "\"Marta\"", "}"] {
            agg.push(&format!(
                "data: {}\n\n",
                json!({
                    "type": "function_call", "name": "agenda.booking.create",
                    "call_id": "c1", "arguments": fragment
                })
            ));
        }
        agg.push("data: [DONE]\n\n");
        let turn = agg.finish().unwrap();
        assert_eq!(turn.calls.len(), 1, "one call, not three");
        assert_eq!(turn.calls[0].arguments, "{\"customer\":\"Marta\"}");
    }

    /// The ordinary turn: text is accumulated, and a body that ends without a trailing newline
    /// still yields its last event.
    #[test]
    fn text_is_accumulated_and_a_body_without_a_final_newline_still_closes() {
        let mut agg = Aggregator::default();
        agg.push("data: {\"type\":\"text_delta\",\"text\":\"Booked \"}\n\n");
        agg.push("data: {\"type\":\"text_delta\",\"text\":\"at 10.\"}");
        let turn = agg.finish().unwrap();
        assert_eq!(turn.text, "Booked at 10.");
        assert!(turn.calls.is_empty());
    }

    /// An upstream error is a step failure, not an empty answer. An empty answer would be recorded
    /// as the agent's output and read by the next step as a fact.
    #[test]
    fn an_error_event_fails_the_turn_instead_of_answering_nothing() {
        let mut agg = Aggregator::default();
        agg.push("data: {\"type\":\"error\",\"error\":\"quota exceeded\"}\n\n");
        let err = agg
            .finish()
            .expect_err("an error must not read as a silent answer");
        assert!(err.contains("quota exceeded"), "{err}");
    }

    /// The briefing has to contradict the chat prompt's "you are in a drawer next to someone
    /// working", or the model asks questions of an empty room — and, under `manual`, must not
    /// claim the write already happened.
    #[test]
    fn the_briefing_says_nobody_is_there_and_what_a_write_means() {
        let manual = automation_briefing(&request_with(AiPolicy::Manual));
        assert!(manual.to_lowercase().contains("unattended"), "{manual}");
        assert!(
            manual.to_lowercase().contains("approve"),
            "under `manual` the model must know a write is only a proposal: {manual}"
        );
        let auto = automation_briefing(&request_with(AiPolicy::Auto));
        assert!(
            auto.to_lowercase().contains("immediately"),
            "under `auto` it must know a write is real: {auto}"
        );
    }

    #[test]
    fn arguments_that_are_not_an_object_degrade_to_an_empty_payload() {
        assert!(parse_arguments("not json").is_empty());
        assert!(parse_arguments("[1,2]").is_empty());
        assert_eq!(parse_arguments("{\"a\":1}").get("a"), Some(&json!(1)));
    }

    fn request_with(policy: AiPolicy) -> AiRequest {
        AiRequest {
            run_id: "r".into(),
            flow_id: "f".into(),
            step_id: "agent".into(),
            depth: 0,
            prompt: "book it".into(),
            queries: Vec::new(),
            commands: Vec::new(),
            policy,
            max_iters: 6,
        }
    }
}
