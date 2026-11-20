// What a run of the probes with the real model keeps of each turn, to compare models on the same phrases: the tools
// the model called in order with their arguments, the card, the verdict, the rounds, the tokens and the cost the
// business spent (its usage row in the stack's SaaS, emptied before each probe), the latency, and whether the
// probe's tool was among the tools the turn offered (a ranking failure is the same for every model). The report is
// `.artifacts/qa/<run>/bench.json`; assistant-bench-compare.ts reads several of them. Pure, so Vitest proves it.
import { type Frame, observe, parseFrames } from './assistant-battery.ts';
import { type Catalog, catalogKey, type Probe, type ProbeOutcome, probeVerdict } from './assistant-probes.ts';
import type { ScenarioRow } from './assistant-scenario-bench.ts';
import type { AnswerChoice } from './assistant-seed.ts';

export type BenchVerdict = 'pass' | 'fail' | 'n/a';

/** A tool the model called: its operation, the arguments it gave and how the call ended (`pending`: it never ran). */
export interface BenchCall {
  name: string;
  arguments: unknown;
  outcome: string;
  code: string;
}

/** What the business spent over one probe: its usage row of the month in the SaaS. */
export interface Usage {
  tokensIn: number;
  tokensOut: number;
  tokensEmbedding: number;
  costUsd: number;
}

export interface BenchTurn {
  probe: string;
  app: string;
  phrase: string;
  role: string;
  language: string;
  /** Where it was asked: the Hub, or the panel's `web` or `app` surface. */
  surface: string;
  expect: string;
  /** Whether the probe's tool reads or writes. */
  kind: 'read' | 'write';
  tool: string;
  lookups: string[];
  /** Whether the tool was among the tools offered on the first round; null when it does not apply (refused, n/a). */
  offered: boolean | null;
  calls: BenchCall[];
  card: boolean;
  cards: string[];
  verdict: BenchVerdict;
  reasons: string[];
  /** The turn's requests to the assistant: the first, and one more after each round of tools or each card. */
  rounds: number;
  tokensIn: number | null;
  tokensOut: number | null;
  tokensEmbedding: number | null;
  costUsd: number | null;
  latencyMs: number | null;
  error: string | null;
}

export interface BenchModel {
  /** How reports name the model: its kind and id, and the fallback when there is one. */
  label: string;
  provider: string;
  kind: string;
  id: string;
  baseUrl: string;
  priceIn: number | null;
  priceOut: number | null;
  fallback: string | null;
  /** Whether it sees images (the seed writes it on its model). */
  vision?: boolean;
}

export interface BenchMeta {
  product: 'hub' | 'saas';
  run: string;
  date: string;
  model: BenchModel;
  files: string[];
  /** The probes of the files, before any sample. */
  corpus: number;
  sample: { size: number; seed: number } | null;
  /** The setup a sampled run made before its first probe (assistant-setup.ts), and the steps of it that failed. */
  setup?: { file: string; failed: { step: number; tool: string; why: string }[] } | null;
  /** A scenario run's simulated owner (assistant-owner.ts), the same model for every assistant compared. */
  owner?: { model: string } | null;
}

export interface BenchReport {
  schema: 1;
  meta: BenchMeta;
  turns: BenchTurn[];
  /** A scenario run's scenarios (assistant-scenario-bench.ts); its `turns` are empty. */
  scenarios?: ScenarioRow[];
}

/** What the spec measured around one probe, besides what the verdict reads. */
export interface Measured {
  bodies: string[];
  latencyMs: number | null;
  usage: Usage | null;
  /** The tools the turn offered for the probe's phrase, or null when they were not ranked. */
  offered: string[] | null;
  kind: 'read' | 'write';
  /** Why the turn never finished, when it did not. */
  error: string | null;
}

export function benchModel(choice: AnswerChoice): BenchModel {
  const named = `${choice.kind}/${choice.model}`;
  return {
    label: choice.fallback ? `${named} + ${choice.fallback}` : named,
    provider: choice.provider,
    kind: choice.kind,
    id: choice.model,
    baseUrl: choice.baseUrl,
    priceIn: choice.priceIn,
    priceOut: choice.priceOut,
    fallback: choice.fallback,
    vision: choice.vision,
  };
}

/** A tool's name as the model calls it (`sale__sale__today`) and as the Hub runs it (`sale.sale.today`). */
const operationName = (name: string): string => name.split('__').join('.');

function argumentsOf(raw: unknown): unknown {
  if (typeof raw !== 'string') return raw ?? null;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

function remember(calls: Map<string, BenchCall>, call: unknown): void {
  const asked = (call ?? {}) as Record<string, unknown>;
  const id = String(asked.call_id ?? '');
  if (!id || calls.has(id)) return;
  calls.set(id, { name: operationName(String(asked.name ?? '')), arguments: argumentsOf(asked.arguments), outcome: 'pending', code: '' });
}

function ran(calls: Map<string, BenchCall>, frame: Frame): void {
  const id = String(frame.call_id ?? '');
  const row = calls.get(id) ?? { name: '', arguments: null, outcome: '', code: '' };
  calls.set(id, { ...row, name: String(frame.name), outcome: String(frame.outcome ?? ''), code: String(frame.code ?? '') });
}

/** Every tool the model called over a probe's turns, in order and once each, with its arguments and its end. */
export function callsOf(bodies: string[]): BenchCall[] {
  const calls = new Map<string, BenchCall>();
  for (const frame of bodies.flatMap(parseFrames)) {
    // The model's calls come in each round's `done` (a card's call too, before it shows); what ran, in `executed`.
    if (frame.type === 'done') for (const call of (frame.pending ?? []) as unknown[]) remember(calls, call);
    else if (frame.type === 'executed') ran(calls, frame);
  }
  return [...calls.values()];
}

const VERDICTS = { PASS: 'pass', FAIL: 'fail', 'N/A': 'n/a' } as const;

/** Whether the probe's tool reads or writes: the owner's catalogue says it; without it, what the probe expects. */
export function toolKind(probe: Probe, catalogs: Record<string, Catalog>): 'read' | 'write' {
  const tool = catalogs[catalogKey('owner', probe.language)]?.find((row) => row.name === probe.tool);
  if (tool) return tool.kind;
  return probe.expect === 'card' ? 'write' : 'read';
}

type Spend = Pick<BenchTurn, 'tokensIn' | 'tokensOut' | 'tokensEmbedding' | 'costUsd'>;

const spendOf = (usage: Usage | null): Spend => ({
  tokensIn: usage?.tokensIn ?? null,
  tokensOut: usage?.tokensOut ?? null,
  tokensEmbedding: usage?.tokensEmbedding ?? null,
  costUsd: usage?.costUsd ?? null,
});

/** The verdict of the turn; one that never finished fails with why first. */
function judged(outcome: ProbeOutcome, error: string | null): Pick<BenchTurn, 'verdict' | 'reasons'> {
  const { verdict, reasons } = probeVerdict(outcome);
  return error ? { verdict: 'fail', reasons: [error, ...reasons] } : { verdict: VERDICTS[verdict], reasons };
}

/** The record of one probe's turn. */
export function benchTurn(outcome: ProbeOutcome, measured: Measured): BenchTurn {
  const { probe, observed } = outcome;
  const asked = !outcome.problems.length;
  const ranked = asked && probe.expect !== 'refused' ? measured.offered : null;
  return {
    probe: probe.id,
    app: probe.app,
    phrase: probe.phrase,
    role: probe.role,
    language: probe.language,
    surface: 'hub',
    expect: probe.expect,
    kind: measured.kind,
    tool: probe.tool,
    lookups: probe.lookups ?? [],
    offered: ranked ? ranked.includes(probe.tool) : null,
    calls: callsOf(measured.bodies),
    card: observed.cards.length > 0,
    cards: observed.cards.map((card) => card.operation),
    ...judged(outcome, measured.error),
    rounds: measured.bodies.length,
    ...spendOf(asked ? measured.usage : null),
    latencyMs: asked ? measured.latencyMs : null,
    error: measured.error ?? (observed.errors.join(', ') || null),
  };
}

/** A probe whose page failed before its question (sign-in, the panel): not asked, so not the model's; the reason says
 *  why, and its record stays out of the score. */
export function notAsked(probe: Probe, error: Error): ProbeOutcome {
  const problems = [`the page failed before the question: ${error.message.split('\n')[0]}`];
  return { probe, answer: '', observed: observe([]), decided: 'none', notices: [], screenshot: '', problems };
}

/** What `a` spent this month in the stack's SaaS, as one line `tokens in|tokens out|embedding tokens|cost`. */
export const USAGE_SQL =
  "select coalesce(sum(tokens_input), 0) || '|' || coalesce(sum(tokens_output), 0) || '|' || " +
  "coalesce(sum(tokens_embedding), 0) || '|' || coalesce(sum(cost_usd), 0) " +
  "from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')";

export function parseUsage(line: string): Usage {
  const values = line.trim().split('|').map(Number);
  if (values.length !== 4 || values.some((value) => !Number.isFinite(value)) || !line.trim()) {
    throw new Error(`the business's usage could not be read: «${line.trim().slice(0, 200)}»`);
  }
  const [tokensIn, tokensOut, tokensEmbedding, costUsd] = values;
  return { tokensIn, tokensOut, tokensEmbedding, costUsd };
}

/**
 * The Hub's side (`manage.py shell -c`): the tools a turn offers each probe's phrase (`base.assistant.relevance`, as
 * `base.assistant.turn` ranks the conversation's last question), from the catalogue of the probe's role with every app
 * on, as `export_assistant_catalog` builds it. The probes come in the file `QA_OFFERED_FILE`; it prints one line of
 * JSON, the offered names by probe.
 */
export const OFFERED_PY = `
import json, os
from live.meta import all_live_app_configs
from live.context import OperationContext
from base import assistant
from base.management.commands.export_assistant_catalog import EXPORT_SCOPE, ROLES
from base.permissions import permissions_of_role

with open(os.environ["QA_OFFERED_FILE"], encoding="utf-8") as handle:
    probes = json.load(handle)
labels = {config.label for config in all_live_app_configs()}
catalogs = {}
offered = {}
for probe in probes:
    key = (probe["role"], probe["language"])
    if key not in catalogs:
        ctx = OperationContext(scope=EXPORT_SCOPE, actor=None, permissions=permissions_of_role(ROLES[key[0]]), language=key[1])
        catalogs[key] = assistant.tools.catalog(ctx, active_labels=labels)
    offered[probe["id"]] = [op.name for op in assistant.relevance.relevant(catalogs[key], [probe["phrase"]], key[1])]
print(json.dumps(offered))
`;

/** How the ranking runs from the Hub's checkout, the probes in `file`. */
export function offeredCommand(file: string, env: Record<string, string | undefined>): { file: string; args: string[]; env: Record<string, string> } {
  const base = Object.fromEntries(Object.entries(env).filter((entry): entry is [string, string] => entry[1] !== undefined));
  return { file: 'uv', args: ['run', 'python', 'manage.py', 'shell', '-c', OFFERED_PY], env: { ...base, QA_OFFERED_FILE: file } };
}

/** The offered tools by probe, from the shell's output (its last line). */
export function parseOffered(output: string): Record<string, string[]> {
  return JSON.parse(output.trim().split('\n').at(-1) ?? '{}') as Record<string, string[]>;
}

/** The run's report with `turn` in it (a probe asked again replaces its turn), in the order of the run's probes. */
export function withTurn(report: BenchReport | null, meta: BenchMeta, turn: BenchTurn, order: string[]): BenchReport {
  const kept = report && report.meta.run === meta.run ? report : null;
  if (kept && kept.meta.model.label !== meta.model.label) {
    throw new Error(`the run ${meta.run} was answered by ${kept.meta.model.label}, not ${meta.model.label}: ask it in a new run`);
  }
  const turns = [...(kept?.turns ?? []).filter((row) => row.probe !== turn.probe), turn];
  const place = (row: BenchTurn) => order.indexOf(row.probe);
  return { schema: 1, meta: kept?.meta ?? meta, turns: turns.sort((a, b) => place(a) - place(b)) };
}
