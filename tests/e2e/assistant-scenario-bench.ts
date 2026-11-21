// What a scenario run keeps of each scenario (assistant-scenario.ts), in the bench report family
// (`.artifacts/qa/<run>/bench.json`, assistant-bench.ts) so `pnpm qa:bench-compare` shows the scenarios per model: the
// score (assistant-scenario-score.ts), the checks, the conversation, every call with its arguments and every card the
// owner confirmed, and the money and time of the assistant (the business's usage row) apart from the simulated owner's
// (assistant-owner.ts). Pure, so Vitest proves it (assistant-scenario-bench.test.ts).
import { type BenchCall, type BenchMeta, type BenchReport, keptReport, type Usage } from './assistant-bench.ts';
import type { Exchange } from './assistant-owner.ts';
import type { Scenario } from './assistant-scenario.ts';
import type { AskScore } from './assistant-scenario-ask.ts';
import type { AskOutcome, CheckResult, ScenarioScore, ScenarioTurn, SeenCard } from './assistant-scenario-score.ts';

/** `scored`: asked and scored; `not_runnable`: a precheck kept it out (the same for every model); `excluded`: its
 *  setup or golden path failed, so no model could pass it on this stack. */
export type ScenarioStatus = 'scored' | 'not_runnable' | 'excluded';

export type EndedBy = 'done' | 'gave_up' | 'turn_limit' | 'error';

export interface ScenarioRow {
  scenario: string;
  title: string;
  vertical: string;
  language: string;
  status: ScenarioStatus;
  why: string | null;
  done: boolean;
  fraction: number;
  checks: { expect: CheckResult[]; forbidden: CheckResult[] };
  forbidden: string[];
  unwanted: string[];
  wrongCards: string[];
  wrongWrites: number;
  mustAsk: { id: string; outcome: AskOutcome }[];
  invented: number;
  /** Whether it asked before acting: its first move, the writes before the owner made the job clear, and the score. */
  ask: AskScore;
  ownerMessages: number;
  endedBy: EndedBy | null;
  wallMs: number | null;
  tokensIn: number | null;
  tokensOut: number | null;
  tokensEmbedding: number | null;
  costUsd: number | null;
  owner: { tokensIn: number; tokensOut: number; costUsd: number | null };
  calls: BenchCall[];
  cards: SeenCard[];
  errors: string[];
  transcript: Exchange[];
}

export interface ScenarioMeasured {
  status: ScenarioStatus;
  why: string | null;
  score?: ScenarioScore;
  checks?: { expect: CheckResult[]; forbidden: CheckResult[] };
  turns?: ScenarioTurn[];
  endedBy?: EndedBy;
  wallMs?: number;
  usage?: Usage | null;
  owner?: { tokensIn: number; tokensOut: number; costUsd: number | null };
}

const NOT_SCORED: ScenarioScore = {
  done: false,
  fraction: 0,
  forbidden: [],
  unwanted: [],
  wrongCards: [],
  wrongWrites: 0,
  mustAsk: [],
  invented: 0,
  ask: { said: null, firstMove: null, writesBeforeClear: [], right: null },
};

function transcriptOf(turns: ScenarioTurn[]): Exchange[] {
  return turns.flatMap((turn): Exchange[] => [
    { who: 'owner', text: turn.owner },
    { who: 'assistant', text: turn.assistant, cards: turn.cards.map((card) => card.operation) },
  ]);
}

const spendOf = (usage: Usage | null | undefined): Pick<ScenarioRow, 'tokensIn' | 'tokensOut' | 'tokensEmbedding' | 'costUsd'> => ({
  tokensIn: usage?.tokensIn ?? null,
  tokensOut: usage?.tokensOut ?? null,
  tokensEmbedding: usage?.tokensEmbedding ?? null,
  costUsd: usage?.costUsd ?? null,
});

/** The record of one scenario: how it went, or why it was not asked. */
export function scenarioRow(scenario: Scenario, measured: ScenarioMeasured): ScenarioRow {
  const score = measured.score ?? NOT_SCORED;
  const turns = measured.turns ?? [];
  return {
    scenario: scenario.id,
    title: scenario.title,
    vertical: scenario.vertical,
    language: scenario.language,
    status: measured.status,
    why: measured.why,
    ...score,
    checks: measured.checks ?? { expect: [], forbidden: [] },
    ownerMessages: turns.length,
    endedBy: measured.endedBy ?? null,
    wallMs: measured.wallMs ?? null,
    ...spendOf(measured.usage),
    owner: measured.owner ?? { tokensIn: 0, tokensOut: 0, costUsd: null },
    calls: turns.flatMap((turn) => turn.calls),
    cards: turns.flatMap((turn) => turn.cards),
    errors: turns.flatMap((turn) => turn.errors),
    transcript: transcriptOf(turns),
  };
}

/** The run's report with `row` in it (a scenario asked again replaces its row), in the order of the run's scenarios. */
export function withScenario(report: BenchReport | null, meta: BenchMeta, row: ScenarioRow, order: string[]): BenchReport {
  const kept = keptReport(report, meta);
  const rows = [...(kept?.scenarios ?? []).filter((earlier) => earlier.scenario !== row.scenario), row];
  const place = (earlier: ScenarioRow) => order.indexOf(earlier.scenario);
  return { schema: 1, meta: kept?.meta ?? meta, turns: [], scenarios: rows.sort((a, b) => place(a) - place(b)) };
}
