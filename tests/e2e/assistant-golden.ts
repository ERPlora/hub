// A scenario's setup and golden path (assistant-scenario.ts): tool calls run in the business `a` as its owner, with no
// model. The setup goes through the assistant's tool runner (`live.assistant.run_tool`), as the probes' setup does; the
// golden path goes through the assistant's own turn (`base.assistant.turn`): a read runs, a write shows its card and runs
// with the owner's yes, typing its word when it asks one, exactly as the chat confirms it. A step may take a value from
// an earlier step's result (`{"$ref": "<id>", "where": {...}, "take": "id"}`), so the steps run in batches of one shell
// each. Pure but for the executor it is given, so Vitest proves it (assistant-golden.test.ts).
import type { ToolStep } from './assistant-scenario.ts';
import { hubShellCommand, type ShellCommand } from './assistant-setup.ts';

/** What one step answered: the outcome and code of the tool, its content (the result's JSON), and whether a card
 *  showed (and was confirmed) on the way. */
export interface StepRun {
  tool: string;
  outcome: string;
  code: string;
  content: string;
  card: boolean;
}

export interface StepsRun {
  results: StepRun[];
  failed: { step: number; tool: string; why: string } | null;
}

export type Executor = (batch: ToolStep[]) => StepRun[];

type Raw = Record<string, unknown>;
const isObject = (value: unknown): value is Raw => typeof value === 'object' && value !== null && !Array.isArray(value);
const isRef = (value: unknown): value is { $ref: string; where?: Raw; take: string } => isObject(value) && typeof value.$ref === 'string';
const plain = (value: unknown): unknown => (typeof value === 'string' ? value.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase() : value);

function matching(value: unknown, where: Raw): Raw | undefined {
  if (Array.isArray(value)) {
    for (const item of value) {
      const found = matching(item, where);
      if (found) return found;
    }
    return undefined;
  }
  if (!isObject(value)) return undefined;
  if (Object.entries(where).every(([key, wanted]) => plain(value[key]) === plain(wanted))) return value;
  return matching(Object.values(value), where);
}

function lookUp(ref: { $ref: string; where?: Raw; take: string }, results: Record<string, unknown>): unknown {
  if (!(ref.$ref in results)) throw new Error(`no step ${ref.$ref} ran before`);
  const source = results[ref.$ref];
  const found = ref.where ? matching(source, ref.where) : isObject(source) ? source : undefined;
  const value = found?.[ref.take];
  if (value === undefined) throw new Error(`${ref.$ref} has no ${ref.take} where ${JSON.stringify(ref.where ?? {})}`);
  return value;
}

/** `value` with every `$ref` written as the value it names in the earlier `results` (by step id, parsed). */
export function resolved(value: unknown, results: Record<string, unknown>): unknown {
  if (isRef(value)) return lookUp(value, results);
  if (Array.isArray(value)) return value.map((item) => resolved(item, results));
  if (isObject(value)) return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, resolved(item, results)]));
  return value;
}

function refsOf(value: unknown): string[] {
  if (isRef(value)) return [value.$ref];
  if (Array.isArray(value)) return value.flatMap(refsOf);
  if (isObject(value)) return Object.values(value).flatMap(refsOf);
  return [];
}

const parsed = (content: string): unknown => {
  try {
    return JSON.parse(content) as unknown;
  } catch {
    return content;
  }
};

/** The batches of `steps`: consecutive steps go together until one needs the result of a step of the same batch. */
function batchesOf(steps: ToolStep[]): { start: number; steps: ToolStep[] }[] {
  const batches: { start: number; steps: ToolStep[] }[] = [];
  let current: { start: number; steps: ToolStep[] } = { start: 0, steps: [] };
  steps.forEach((step, index) => {
    const pending = new Set(current.steps.map((earlier) => earlier.id).filter(Boolean));
    if (refsOf(step.arguments).some((id) => pending.has(id))) {
      batches.push(current);
      current = { start: index, steps: [] };
    }
    current.steps.push(step);
  });
  if (current.steps.length) batches.push(current);
  return batches;
}

/** Runs `steps` batch by batch with `execute`, writing earlier results into later steps; stops at the first step that
 *  did not end `ok`, or whose values could not be written in. */
export function runSteps(steps: ToolStep[], execute: Executor): StepsRun {
  const results: StepRun[] = [];
  const byId: Record<string, unknown> = {};
  for (const batch of batchesOf(steps)) {
    const ready: ToolStep[] = [];
    for (const [offset, step] of batch.steps.entries()) {
      try {
        ready.push({ ...step, arguments: resolved(step.arguments, byId) as Raw });
      } catch (error) {
        return { results, failed: { step: batch.start + offset + 1, tool: step.tool, why: (error as Error).message } };
      }
    }
    for (const [offset, result] of execute(ready).entries()) {
      results.push(result);
      const step = ready[offset];
      if (result.outcome !== 'ok') return { results, failed: { step: batch.start + offset + 1, tool: step.tool, why: `${result.outcome} ${result.code}: ${result.content.slice(0, 300)}` } };
      if (step.id) byId[step.id] = parsed(result.content);
    }
  }
  return { results, failed: null };
}

/**
 * The Hub's side (`manage.py shell --hub a -c`): the steps of `QA_GOLDEN_FILE` as the owner of `a`, in the language of
 * the scenario. `setup`: each one by the tool runner. `golden`: each one as a call the model made, through the
 * assistant's turn: a write's card comes back first and is confirmed (its word typed when it asks one), as the chat does.
 * It stops at the first step that raises, and prints one line of JSON, what each step answered.
 */
export const GOLDEN_PY = `
import json, os
from base.models import Membership
from base.permissions import permissions_for
from base.schemas.assistant import AssistantTurnIn
from live import assistant as shared
from live.context import OperationContext, Scope
from live.operations import get as get_operation

scope = Scope("host", "a")
member = Membership.objects.filter(host="a", role=Membership.Role.OWNER).select_related("user").first()
if member is None:
    raise SystemExit("the steps run as the owner of a, who has not signed in to it yet")
owner = member.user
ctx = OperationContext(scope=scope, actor=owner, permissions=permissions_for(owner, scope), language=os.environ["QA_GOLDEN_LANGUAGE"])
turn = get_operation("base.assistant.turn")
asked = [{"role": "user", "content": "golden path"}]


def turned(pending, decision=None):
    data = {"messages": asked, "pending": pending, **({"decision": decision} if decision else {})}
    return turn(ctx, AssistantTurnIn.model_validate(data)).model_dump(mode="json")


def through_turn(index, step):
    call = {"call_id": "golden-%d" % index, "name": step["tool"].replace(".", "__"), "arguments": json.dumps(step["arguments"])}
    answer = turned([call])
    card = answer.get("confirm")
    if card:
        decision = {"call_id": call["call_id"], "accepted": True, "typed": card.get("confirm_word") or ""}
        answer = turned(answer["pending"], decision)
    if not answer["executed"]:
        return {"tool": step["tool"], "outcome": "not_run", "code": "card_drawn_again", "content": json.dumps(answer.get("confirm")), "card": bool(card)}
    ran = answer["executed"][-1]
    content = answer["append"][-1]["content"] if answer["append"] else ""
    return {"tool": step["tool"], "outcome": ran["outcome"], "code": ran["code"], "content": content, "card": bool(card)}


def by_runner(index, step):
    outcome = shared.run_tool(ctx, get_operation(step["tool"]), json.dumps(step["arguments"]))
    return {"tool": step["tool"], "outcome": outcome.outcome, "code": outcome.code, "content": outcome.content, "card": False}


with open(os.environ["QA_GOLDEN_FILE"], encoding="utf-8") as handle:
    steps = json.load(handle)
run_one = through_turn if os.environ["QA_GOLDEN_MODE"] == "golden" else by_runner
results = []
for index, step in enumerate(steps):
    try:
        results.append(run_one(index, step))
    except Exception as exc:
        results.append({"tool": step["tool"], "outcome": "exception", "code": type(exc).__name__, "content": str(exc)[:2000], "card": False})
        break
print(json.dumps(results))
`;

/** How a batch runs from the Hub's checkout: its steps in `file`, as the setup or as the golden path. */
export const goldenCommand = (
  batch: { file: string; mode: 'setup' | 'golden'; language: string },
  env: Record<string, string | undefined>,
): ShellCommand => hubShellCommand(GOLDEN_PY, env, { QA_GOLDEN_FILE: batch.file, QA_GOLDEN_MODE: batch.mode, QA_GOLDEN_LANGUAGE: batch.language });

/** What each step answered, from the shell's last line; anything else is the shell's failure, quoted. */
export function parseStepResults(output: string): StepRun[] {
  const last = output.trim().split('\n').at(-1) ?? '';
  try {
    return JSON.parse(last) as StepRun[];
  } catch {
    throw new Error(`the steps' shell did not answer a list: ${last.slice(0, 300)}`);
  }
}
