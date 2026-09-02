//! Scheduler, flows, runs and approvals — split out of `lib.rs` verbatim (hub#1403).

use crate::*;

impl Runtime {
    /// Un ciclo del barrido del **scheduler** (ADR-0011): ejecuta las scheduled tasks vencidas de
    /// los módulos activos. Lo llama el bucle de background del server (junto al relay del outbox).
    /// Devuelve cuántas tareas corrió. `hub_id` es el del despliegue (contexto de sistema).
    pub async fn process_scheduler(&self, hub_id: &str) -> Result<usize> {
        scheduler::process_once(self.db.as_ref(), &self.registry, hub_id).await
    }

    // ── Automation kernel (ADR-0283, hub#661) ───────────────────────────────────────────────
    // The REST surface (`crates/server/src/flows_api.rs`) is the only caller of these; there are
    // deliberately no `hub.*` commands for flows (ADR-0283 §9 — the core is being frozen, and the
    // dispatcher is not where new core surface goes).

    /// One cycle of the flows kernel: fire due clock triggers, wake finished delays, advance
    /// claimed runs. Called from the same 1 s loop as the outbox relay and the scheduler.
    pub async fn process_flows(&self) -> Result<flows::executor::TickReport> {
        flows::tick(self.db.as_ref(), &self.registry, &self.hub_id).await
    }

    /// The **complete** half of claim → I/O → complete (hub#662): the server performed the call
    /// outside the lock and hands back what it produced, so the run can carry on — or stop.
    pub async fn complete_flow_io(
        &self,
        run_id: &str,
        step_id: &str,
        result: flows::IoResult,
    ) -> Result<()> {
        flows::executor::complete_io(self.db.as_ref(), &self.hub_id, run_id, step_id, result).await
    }

    /// Names of the `_flow_secrets` this hub holds. **Never the values** — there is no method that
    /// returns one, and the only reader is the executor while it builds a request (ADR-0283 §4).
    pub async fn list_flow_secrets(&self) -> Result<Vec<flows::secrets::SecretInfo>> {
        flows::secrets::list(self.db.as_ref(), &self.hub_id).await
    }

    pub async fn put_flow_secret(
        &self,
        name: &str,
        value: &str,
        by: &str,
    ) -> Result<flows::secrets::SecretInfo> {
        flows::secrets::put(self.db.as_ref(), &self.hub_id, name, value, by).await
    }

    pub async fn delete_flow_secret(&self, name: &str, by: &str) -> Result<()> {
        flows::secrets::delete(self.db.as_ref(), &self.hub_id, name, by).await
    }

    pub async fn list_flows(&self) -> Result<Vec<flows::Flow>> {
        flows::store::list(self.db.as_ref(), &self.hub_id).await
    }

    pub async fn get_flow(&self, id: &str) -> Result<flows::Flow> {
        flows::store::get(self.db.as_ref(), &self.hub_id, id).await
    }

    /// Saves a flow. The registry travels with it because the document names COMMANDS, and a
    /// document naming one the kernel can never invoke is refused at save (hub#824) — same reason
    /// `replace_flow_grants` carries it.
    pub async fn create_flow(&self, new: &flows::NewFlow, by: &str) -> Result<flows::Flow> {
        flows::store::create(self.db.as_ref(), &self.hub_id, &self.registry, new, by).await
    }

    pub async fn update_flow(
        &self,
        id: &str,
        new: &flows::NewFlow,
        by: &str,
    ) -> Result<flows::Flow> {
        flows::store::update(self.db.as_ref(), &self.hub_id, id, &self.registry, new, by).await
    }

    pub async fn delete_flow(&self, id: &str, by: &str) -> Result<()> {
        flows::store::delete(self.db.as_ref(), &self.hub_id, id, by).await
    }

    pub async fn list_flow_grants(&self, flow_id: &str) -> Result<Vec<flows::grants::Grant>> {
        flows::grants::list(self.db.as_ref(), &self.hub_id, flow_id).await
    }

    /// Replaces the grant list of a flow. The commands are checked against the **registry** here,
    /// so a grant naming something that does not exist is refused with the whole list.
    pub async fn replace_flow_grants(
        &self,
        flow_id: &str,
        wanted: &[(flows::grants::GrantKind, String)],
        granted_by: &str,
    ) -> Result<()> {
        // 404 first: granting to a flow that is not here must not create rows for a ghost.
        flows::store::get(self.db.as_ref(), &self.hub_id, flow_id).await?;
        flows::grants::replace(
            self.db.as_ref(),
            &self.hub_id,
            flow_id,
            &self.registry,
            wanted,
            granted_by,
        )
        .await
    }

    /// `manual` trigger: starts a run and returns its id. The run itself is advanced by the tick,
    /// never by the request — a flow with a delay would otherwise hold the HTTP call open.
    pub async fn start_flow_run(
        &self,
        flow_id: &str,
        input: &Json,
        started_by: &str,
    ) -> Result<String> {
        flows::executor::start_manual_run(
            self.db.as_ref(),
            &self.hub_id,
            flow_id,
            input,
            started_by,
        )
        .await
    }

    /// The history of one flow, newest first. `before` is the id of the last run of the previous
    /// page (a cursor, not an offset — see [`flows::store::list_runs`]).
    pub async fn list_flow_runs(
        &self,
        flow_id: &str,
        limit: i64,
        before: Option<&str>,
    ) -> Result<Vec<flows::FlowRun>> {
        flows::store::list_runs(self.db.as_ref(), &self.hub_id, flow_id, limit, before).await
    }

    pub async fn get_flow_run(
        &self,
        run_id: &str,
    ) -> Result<(flows::FlowRun, Vec<flows::FlowRunStep>)> {
        flows::store::get_run(self.db.as_ref(), &self.hub_id, run_id).await
    }

    /// The events one run emitted — the forward link from a run into everything downstream of it
    /// (hub#666).
    pub async fn events_of_run(&self, run_id: &str) -> Result<Vec<outbox::CorrelatedEvent>> {
        outbox::events_of_run(self.db.as_ref(), &self.hub_id, run_id).await
    }

    /// The `ai` step a run is stopped on, read once, with its prompt already resolved.
    pub async fn load_flow_ai_request(
        &self,
        run_id: &str,
        step_id: &str,
    ) -> Result<flows::AiRequest> {
        flows::agent::prepare(self.db.as_ref(), &self.hub_id, run_id, step_id).await
    }

    /// The live grants of a flow — what the runner intersects the offered tools with.
    pub async fn flow_authority(&self, flow_id: &str) -> Result<flows::grants::Authority> {
        flows::grants::authority(self.db.as_ref(), &self.hub_id, flow_id).await
    }

    /// Runs a READ on behalf of a flow. The grant is checked HERE, freshly, so a query the flow
    /// was not granted is refused by the runtime and not by the runner's good manners — a gate the
    /// caller can skip is not a gate.
    pub async fn execute_flow_query(
        &self,
        flow_id: &str,
        run_id: &str,
        name: &str,
        params: &Params,
    ) -> Result<Vec<Json>> {
        flows::grants::check_query_grant(self.db.as_ref(), &self.hub_id, flow_id, name).await?;
        let ctx = self.automation_ctx(flow_id, run_id).await?;
        let r = queries::execute(self.db.as_ref(), &self.registry, name, params, &ctx).await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "query", name, params);
        }
        r
    }

    /// Runs a WRITE on behalf of a flow, through the SAME door the kernel's own `command` steps
    /// use ([`commands::Origin::Automation`]). That is the whole reason ADR-0283 D2 puts the
    /// automation gate inside `execute_at`: a flow's command inherits the fiscal gates, the schema
    /// validation and the transactional outbox whole, instead of getting a dispatcher of its own.
    pub async fn execute_flow_command(
        &self,
        flow_id: &str,
        run_id: &str,
        depth: i64,
        name: &str,
        payload: &Params,
    ) -> Result<Json> {
        let ctx = self.automation_ctx(flow_id, run_id).await?;
        let r = commands::execute_at(
            self.db.as_ref(),
            &self.registry,
            name,
            payload,
            &ctx,
            depth.max(0) as u32,
            &[],
            commands::Origin::Automation,
            // No approval to spend: an elevation is a person authorising an action at the counter,
            // and there is nobody at the counter (hub#361).
            None,
        )
        .await;
        if let Err(e) = &r {
            self.report_dispatch_error(e, "command", name, payload);
        }
        r
    }

    /// **Would this payload be accepted by `name`, if it were run right now?** — asked without
    /// running anything, and answered by the same code that will judge it at execution
    /// ([`commands::validate_payload`]).
    ///
    /// hub#825: the agent runner asks this BEFORE parking a proposal in the approval tray. A
    /// proposal the hub can already refute must never become a question for a person — approving it
    /// would spend her decision on something that cannot happen.
    pub fn validate_command_payload(&self, name: &str, payload: &Params) -> Result<()> {
        commands::validate_payload(&self.registry, name, payload)
    }

    /// The context a flow acts under: attributed to the flow, machine-principal (never offered a
    /// manager's PIN), and carrying only the permissions of what it was granted.
    async fn automation_ctx(&self, flow_id: &str, run_id: &str) -> Result<RequestContext> {
        let authority = self.flow_authority(flow_id).await?;
        Ok(RequestContext::new(
            self.hub_id.clone(),
            format!("flow:{flow_id}"),
            authority.permissions(&self.registry),
        )
        .as_machine()
        .with_automation(AutomationCtx {
            flow_id: flow_id.to_string(),
            run_id: run_id.to_string(),
        }))
    }

    // ── The approval tray (ADR-0283 D3) ─────────────────────────────────────────────────────

    /// Parks a write the model proposed: the row a person reads in the morning, and the run
    /// stopped in the same gesture. A proposal with a run still marching forward would be a
    /// question nobody is waiting for.
    pub async fn request_flow_approval(&self, new: &flows::NewApproval) -> Result<flows::Approval> {
        let approval = flows::approvals::create(self.db.as_ref(), &self.hub_id, new).await?;
        // The park goes through the SAME seam an `http` step completes by (hub#662): one place
        // decides what «this run stopped on its I/O step» means, and a second one would drift.
        self.complete_flow_io(
            &new.run_id,
            &new.step_id,
            flows::IoResult::AwaitingApproval(new.partial_output.clone()),
        )
        .await?;
        // Ephemeral, WS-only (`events::notify_sink`): the tray lights up without polling. The
        // SCREEN is the module `flows`'s job — the core emits the fact and nothing else.
        let mut payload = Params::new();
        payload.insert("approval_id".into(), Json::from(approval.id.clone()));
        payload.insert("flow_id".into(), Json::from(approval.flow_id.clone()));
        payload.insert("run_id".into(), Json::from(approval.run_id.clone()));
        payload.insert("command".into(), Json::from(approval.command.clone()));
        events::notify_sink(
            &self.registry,
            registry::EventSource::Core,
            flows::approvals::EVENT_APPROVAL_CREATED,
            &payload,
        );
        Ok(approval)
    }

    /// What the agent turn had produced when it stopped for approval — parked on the step row, so
    /// a decision taken hours later completes the whole turn and not just its ending. Degrades to
    /// an empty object: a missing partial must not stop a booking somebody just approved.
    async fn parked_step_output(&self, run_id: &str) -> Json {
        self.get_flow_run(run_id)
            .await
            .ok()
            .and_then(|(run, steps)| {
                steps
                    .into_iter()
                    .find(|s| s.step_index == run.current_step)
                    .map(|s| s.output)
            })
            .filter(Json::is_object)
            .unwrap_or_else(|| json!({}))
    }

    pub async fn get_flow_approval(&self, id: &str) -> Result<flows::Approval> {
        flows::approvals::get(self.db.as_ref(), &self.hub_id, id).await
    }

    /// **Who may answer this question** (hub#950), resolved server-side at the moment of deciding
    /// and never taken from the request.
    ///
    /// The document names a **role** — Odoo's `Allowed Group` — because naming a person is a flow
    /// that stops working the day they leave, the hole Business Central had to invent a
    /// "substitute" for. An empty role means what the tray has always meant: whoever administers
    /// the hub.
    ///
    /// **An administrator always counts**, even when another role was named, and that is the
    /// deliberate half. The alternative is a question that becomes undecidable the day its role has
    /// nobody left in it — no approve, no reject, and a run parked until the sweep: the orphaned
    /// approval every Power Automate forum is full of and that hub#979 exists to stop. It is also
    /// what Business Central's *approval administrator* and Salesforce's delegated approver are
    /// for. Delegation proper (BC's `Delegate After`) is out of v1.
    ///
    /// The role is read from `hub_user` by the id inside `decided_by`, so it is this hub's current
    /// answer and not whatever a session claimed when it was opened.
    async fn ensure_may_decide(&self, approval: &flows::Approval, decided_by: &str) -> Result<()> {
        if approval.assignee_role.trim().is_empty() {
            return Ok(());
        }
        let user_id = decided_by.strip_prefix("hub_user:").unwrap_or(decided_by);
        let role = hub_users::get(self.db.as_ref(), &self.hub_id, user_id)
            .await?
            .map(|u| u.role)
            .unwrap_or_default();
        if role.eq_ignore_ascii_case(approval.assignee_role.trim())
            || hub_users::is_admin_role(&role)
        {
            return Ok(());
        }
        Err(RuntimeError::Domain {
            code: flows::approvals::ERR_APPROVAL_NOT_YOURS.to_string(),
            message: format!(
                "this approval is addressed to `{}` and `{decided_by}` is `{}`; nothing was \
                 decided and the question is still waiting for somebody who may answer it",
                approval.assignee_role,
                if role.is_empty() { "unknown" } else { &role }
            ),
        })
    }

    /// What an `approval` step leaves in `steps.<id>` — the four fields the steps written after it
    /// read, and the reason the three branches of the original contract compose out of a LINEAR
    /// document: `condition` on `steps.approve.decision` IS the branch.
    fn decision_output(&self, decided: &flows::Approval) -> Json {
        json!({
            "decision": decided.status,
            "decided_by": decided.decided_by,
            "decided_at": decided.decided_at.clone().unwrap_or_default(),
            "comment": decided.comment,
        })
    }

    pub async fn list_flow_approvals(
        &self,
        status: Option<&str>,
        limit: i64,
    ) -> Result<Vec<flows::Approval>> {
        flows::approvals::list(self.db.as_ref(), &self.hub_id, status, limit).await
    }

    /// **The approval contract**, in one method because its four steps are one decision:
    ///
    /// 1. the proposal must still be decidable (once, and not expired);
    /// 2. on `approve`, the grant is **re-checked right now** — a proposal is not a stored
    ///    permission, and between 3 AM and 9 AM the owner may have withdrawn the capability. If it
    ///    is gone, nothing runs and the row stays **pending**: granting again and approving again
    ///    is a working remedy, whereas a burnt approval would force a re-run of the whole flow;
    /// 3. what runs is **exactly** the stored command with the stored payload, through
    ///    `Origin::Automation`. The model is **not** asked again — re-planning after a rejection is
    ///    product (the module `flows`), and a kernel that quietly re-planned would make "I approved
    ///    *this*" mean nothing;
    /// 4. the run continues from the step after the agent's, or — on `reject` — stops as
    ///    `cancelled`, because the steps written after an agent step assumed it acted.
    ///
    /// `decided_by` is the caller's job to resolve from the SESSION; this method never reads it
    /// from a body (same rule as `discarded_by` in `outbox_admin.rs`).
    ///
    /// **Two kinds go through here** since hub#950, and the branch is the row's (`kind`), never the
    /// caller's: a `command` is a write a model proposed and approving RUNS it; a `decision` is a
    /// question an `approval` step asked, and approving runs **nothing** — it records an answer and
    /// lets the run carry on to the step that does the work. Everything around that one difference
    /// is shared on purpose: one tray, one «decided once» rule, one expiry sweep, one audit.
    pub async fn decide_flow_approval(
        &self,
        id: &str,
        approve: bool,
        decided_by: &str,
        comment: &str,
    ) -> Result<flows::Approval> {
        // **Who, before what.** The role is checked against the row as it stands and BEFORE
        // `claim_pending`, so somebody this question was not addressed to gets `not_yours` rather
        // than «already decided by Marta at 04:12» — an authorisation failure must not be a way to
        // read the row it refuses. Today the HTTP tray is admin-only and both callers would see
        // that anyway; the day the module `flows` opens the tray to the role that was named, this
        // order is what stops it being a disclosure.
        let approval = self.get_flow_approval(id).await?;
        self.ensure_may_decide(&approval, decided_by).await?;
        let approval = flows::approvals::claim_pending(self.db.as_ref(), &self.hub_id, id).await?;

        if !approve {
            let decided = flows::approvals::mark_decided_with_comment(
                self.db.as_ref(),
                &self.hub_id,
                id,
                flows::approvals::STATUS_REJECTED,
                decided_by,
                "",
                comment,
            )
            .await?;
            // **What a refusal costs is the ROW's answer, not this method's** (hub#950). For a
            // model's proposal it is always `cancel`, which is exactly what a rejection has always
            // done; for an `approval` step the document chose, and `continue` is what makes the
            // «rejected» branch composable out of a linear document.
            let result = match flows::approvals::RejectPolicy::parse(&approval.on_reject) {
                flows::approvals::RejectPolicy::Continue => {
                    flows::IoResult::Done(self.decision_output(&decided))
                }
                flows::approvals::RejectPolicy::Cancel => flows::IoResult::Cancelled(
                    if approval.kind == flows::approvals::KIND_DECISION {
                        format!("`{}` was rejected by `{decided_by}`", approval.title)
                    } else {
                        format!("`{}` was rejected by `{decided_by}`", approval.command)
                    },
                ),
            };
            self.complete_flow_io(&approval.run_id, &approval.step_id, result)
                .await?;
            return Ok(decided);
        }

        // **A decision executes nothing.** No grant is re-checked because none was ever spent: the
        // step asked a question, and the write — if there is one — is a later step with its own
        // grant, re-read when the tick reaches it. Putting a grant check here would gate the
        // ANSWER on a capability the answer does not use.
        if approval.kind == flows::approvals::KIND_DECISION {
            let decided = flows::approvals::mark_decided_with_comment(
                self.db.as_ref(),
                &self.hub_id,
                id,
                flows::approvals::STATUS_APPROVED,
                decided_by,
                "",
                comment,
            )
            .await?;
            self.complete_flow_io(
                &approval.run_id,
                &approval.step_id,
                flows::IoResult::Done(self.decision_output(&decided)),
            )
            .await?;
            return Ok(decided);
        }

        // Step 2 — the gate, NOW. Deliberately before anything is written: nothing about this
        // approval changes if the answer is no.
        flows::grants::check_command_grant(
            self.db.as_ref(),
            &self.hub_id,
            &approval.flow_id,
            &approval.command,
        )
        .await?;

        // Step 3 — exactly what was proposed.
        let payload: Params = approval.payload.as_object().cloned().unwrap_or_default();

        // Step 3a (hub#825) — **the net, not the first line.** The runner refuses to park a payload
        // the schema already rejects, so nothing reaches this tray that could not run when it was
        // written. What this covers is the one thing that check cannot: the contract MOVING between
        // 3 AM and 9 AM, because a module updated in between.
        //
        // It refuses like the revoked grant of §7.2 and NOT like §14.8: the row stays **pending**
        // and nobody is recorded as having decided it. `approved` with an error is the honest record
        // of «the person approved and the COMMAND broke» — something ran, or could have. Here
        // nothing could: this is refused before the door, so burning the approval would leave the
        // worst possible row, one that says a person authorised something that never happened, and
        // would take away her only remaining exit (rejecting, which ends the run cleanly).
        if let Err(e) = commands::validate_payload(&self.registry, &approval.command, &payload) {
            return Err(match e {
                RuntimeError::InvalidPayload { name, detail } => RuntimeError::InvalidPayload {
                    name,
                    detail: format!(
                        "{detail}. This proposal was written when `{}` accepted it; the command's \
                         contract changed in between, so approving cannot run it. Nothing was \
                         executed and the proposal is still PENDING: reject it to close the flow, \
                         or decide again once the command accepts this payload.",
                        approval.command
                    ),
                },
                other => other,
            });
        }

        let (run, _) =
            flows::store::get_run(self.db.as_ref(), &self.hub_id, &approval.run_id).await?;
        let outcome = self
            .execute_flow_command(
                &approval.flow_id,
                &approval.run_id,
                run.depth,
                &approval.command,
                &payload,
            )
            .await;

        match outcome {
            Ok(result) => {
                let decided = flows::approvals::mark_decided_with_comment(
                    self.db.as_ref(),
                    &self.hub_id,
                    id,
                    flows::approvals::STATUS_APPROVED,
                    decided_by,
                    "",
                    comment,
                )
                .await?;
                // The step's output is the WHOLE turn: what the model produced before it
                // proposed (parked on the step row hours ago) plus how the proposal ended.
                let mut output = self.parked_step_output(&approval.run_id).await;
                if let Some(map) = output.as_object_mut() {
                    map.insert("status".into(), json!(flows::approvals::STATUS_APPROVED));
                    map.insert("approval_id".into(), json!(id));
                    map.insert("command".into(), json!(approval.command));
                    map.insert("result".into(), result);
                }
                self.complete_flow_io(
                    &approval.run_id,
                    &approval.step_id,
                    flows::IoResult::Done(output),
                )
                .await?;
                Ok(decided)
            }
            Err(e) => {
                // The person DID approve; what broke is the command. Both facts are recorded, and
                // the error is returned so the tray shows a failure instead of a green tick.
                let message = format!("{e}");
                flows::approvals::mark_decided_with_comment(
                    self.db.as_ref(),
                    &self.hub_id,
                    id,
                    flows::approvals::STATUS_APPROVED,
                    decided_by,
                    &message,
                    comment,
                )
                .await?;
                self.complete_flow_io(
                    &approval.run_id,
                    &approval.step_id,
                    flows::IoResult::Failed(format!("{}: {message}", approval.command)),
                )
                .await?;
                Err(e)
            }
        }
    }

    /// **Closes the proposals nobody answered** (hub#972) — the active sweep the TTL never had.
    ///
    /// `expires_at` was read only by `claim_pending`, so a proposal past its 72 h could be neither
    /// approved nor rejected (both go through that door) and its run sat in `waiting_approval` for
    /// ever: exempt from the 90-day prune, holding a verbatim `payload` that can carry a customer's
    /// personal details. There was no action a person could take, in a hub with no way to reach the
    /// database.
    ///
    /// What it does per swept row is decided by the ROW (`on_expire`, [`flows::approvals::ExpiryPolicy`]),
    /// never by this method: `reject`/`cancel` end the run, `continue` resumes it at the next step.
    /// The default is the conservative one — the steps written after an `ai` step assumed it acted.
    /// Whatever the policy, **nothing the model proposed is executed**: an expiry is the opposite of
    /// an approval.
    ///
    /// A run that has moved on (or been deleted) since is skipped and counted as `stranded` rather
    /// than aborting the pass: the proposal is already closed, and one broken run must not stop the
    /// hub from closing the rest.
    ///
    /// **One bounded pass** (`SWEEP_BATCH` proposals), like [`retention::prune_once`] and for the
    /// same reason: the caller holds the runtime lock the tills are queueing behind, and it re-takes
    /// it per pass instead of keeping it for a whole catch-up. Driven by the hourly retention tick
    /// in `crates/server`, **before** the prune, so a run that becomes terminal here can be pruned
    /// in the same hour it stops being live.
    pub async fn sweep_expired_flow_approvals(&self) -> Result<flows::ExpirySweepReport> {
        let now = registry::now_rfc3339();
        let mut report = flows::ExpirySweepReport::default();
        let swept = flows::approvals::sweep_expired(
            self.db.as_ref(),
            &self.hub_id,
            &now,
            flows::approvals::SWEEP_BATCH,
        )
        .await?;
        for approval in &swept {
            report.expired += 1;
            let resumed = matches!(approval.on_expire, flows::approvals::ExpiryPolicy::Continue);
            let is_decision = approval.kind == flows::approvals::KIND_DECISION;
            // A question has no command to name; what it had was a title, and the sweep brings it
            // back with the row.
            let subject = if is_decision {
                approval.title.clone()
            } else {
                approval.command.clone()
            };
            let result = if resumed {
                // **The two kinds leave a different shape**, and each is the shape its step's
                // readers already know. A `decision` leaves the same four fields it would have
                // left had somebody answered — so `steps.<id>.decision` reads `expired` and the
                // `condition` after it is n8n's «no answer» path. A model's turn keeps its own
                // output, closed with how it ended.
                let output = if is_decision {
                    json!({
                        "decision": flows::approvals::STATUS_EXPIRED,
                        "decided_by": flows::approvals::DECIDED_BY_EXPIRY,
                        "decided_at": approval.expires_at,
                        "comment": "",
                    })
                } else {
                    let mut output = self.parked_step_output(&approval.run_id).await;
                    if let Some(map) = output.as_object_mut() {
                        map.insert("status".into(), json!(flows::approvals::STATUS_EXPIRED));
                        map.insert("approval_id".into(), json!(approval.id));
                        map.insert("command".into(), json!(approval.command));
                    }
                    output
                };
                flows::IoResult::Done(output)
            } else {
                flows::IoResult::Cancelled(format!(
                    "`{subject}` was never decided: it expired at {} and `on_expire` is `{}`",
                    approval.expires_at,
                    approval.on_expire.as_str()
                ))
            };
            match self
                .complete_flow_io(&approval.run_id, &approval.step_id, result)
                .await
            {
                Ok(()) if resumed => report.runs_resumed += 1,
                Ok(()) => report.runs_stopped += 1,
                Err(e) => {
                    report.stranded += 1;
                    eprintln!(
                        "flows: approval {} expired but its run {} could not be closed: {e}",
                        approval.id, approval.run_id
                    );
                }
            }
            // Ephemeral, WS-only, exactly like `flow.approval.created`: a tray left open all
            // night has to stop showing a question that can no longer be answered, and the
            // SCREEN is the module `flows`'s job.
            let mut payload = Params::new();
            payload.insert("approval_id".into(), Json::from(approval.id.clone()));
            payload.insert("flow_id".into(), Json::from(approval.flow_id.clone()));
            payload.insert("run_id".into(), Json::from(approval.run_id.clone()));
            payload.insert("command".into(), Json::from(approval.command.clone()));
            payload.insert("expires_at".into(), Json::from(approval.expires_at.clone()));
            payload.insert("on_expire".into(), Json::from(approval.on_expire.as_str()));
            events::notify_sink(
                &self.registry,
                registry::EventSource::Core,
                flows::approvals::EVENT_APPROVAL_EXPIRED,
                &payload,
            );
        }
        Ok(report)
    }

    /// Catch-up del scheduler al **arrancar** (Tauri/local): ejecuta una sola vez las tareas con
    /// backlog vencido (collapse) y reprograma las demás. Lo llama el host una vez al arrancar.
    pub async fn scheduler_catch_up(&self, hub_id: &str) -> Result<usize> {
        scheduler::catch_up_on_boot(self.db.as_ref(), &self.registry, hub_id).await
    }
}
