// The score of one scenario (assistant-scenario.ts), from the business's database at the end and from what went over the
// wire turn by turn: whether the job is done and how much of it, the forbidden changes, the writes the job did not want,
// the cards whose values were wrong, and for each fact the owner keeps back whether the assistant asked for it, found it
// with a read or invented it, and whether it asked before acting (assistant-scenario-ask.ts). Pure, so Vitest proves it
// (assistant-scenario-score.test.ts).
import type { Executed } from './assistant-battery.ts';
import type { BenchCall } from './assistant-bench.ts';
import type { CardCheck, Check, MustAsk, Scenario, Use } from './assistant-scenario.ts';
import { type AskScore, askScore } from './assistant-scenario-ask.ts';

/** A card the owner confirmed: its operation, risk, the call's arguments and the fields it showed. */
export interface SeenCard {
  operation: string;
  /** What it does and its app, as the card names them. */
  title: string;
  risk: string;
  arguments: unknown;
  fields: { name: string; label: string; kind: string; value: unknown }[];
}

/** One owner message and everything the assistant did after it, until the turn ended. */
export interface ScenarioTurn {
  owner: string;
  assistant: string;
  calls: BenchCall[];
  cards: SeenCard[];
  executed: Executed[];
  errors: string[];
}

export interface CheckResult {
  says: string;
  ok: boolean;
  got: string;
  want: string;
}

export type AskOutcome = 'asked' | 'resolved' | 'invented' | 'unused';

export interface ScenarioScore {
  done: boolean;
  /** The share of the expected checks that hold. */
  fraction: number;
  /** The forbidden changes that happened, by what they say. */
  forbidden: string[];
  /** The writes that ran and the job did not want. */
  unwanted: string[];
  wrongCards: string[];
  wrongWrites: number;
  mustAsk: { id: string; outcome: AskOutcome }[];
  invented: number;
  ask: AskScore;
}

const isObject = (value: unknown): value is Record<string, unknown> => typeof value === 'object' && value !== null && !Array.isArray(value);

/** Lower case and without accents, to compare what people write. */
export const plain = (text: string): string => text.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase();

const FILTER = /^([A-Za-z_]\w*)\[(\w+)~([^\]]+)\]$/;

function step(value: unknown, segment: string): unknown {
  const filtered = FILTER.exec(segment);
  if (!filtered) return isObject(value) ? value[segment] : undefined;
  const [, list, field, text] = filtered;
  const rows = isObject(value) ? value[list] : undefined;
  if (!Array.isArray(rows)) return undefined;
  return rows.find((row) => isObject(row) && typeof row[field] === 'string' && plain(row[field] as string).includes(plain(text)));
}

/** The value at `path` in a call's arguments: `a.b`, and `rows[name~pulpo].price` for the row whose name contains it. */
export const valueAt = (args: unknown, path: string): unknown => path.split('.').reduce<unknown>((value, segment) => step(value, segment), args);

const carries = (value: unknown): boolean => value !== undefined && value !== null && value !== '' && !(Array.isArray(value) && !value.length);

/** A check's result from the value its SQL gave (or the error it failed with), and from the one before the job. */
export function checked(check: Check, got: string | Error, before: string | null): CheckResult {
  const want = check.unchanged ? (before ?? '(not read before the job)') : (check.equals ?? '');
  if (got instanceof Error) return { says: check.says, ok: false, got: `error: ${got.message.split('\n')[0]}`, want };
  const value = got.trim();
  return { says: check.says, ok: value === want.trim(), got: value, want };
}

const about = (args: unknown, where: Record<string, string>): boolean =>
  Object.entries(where).every(([path, text]) => plain(String(valueAt(args, path) ?? '')).includes(plain(text)));

const uses = (use: Use, made: BenchCall): boolean => use.tool === made.name && about(made.arguments, use.where ?? {}) && carries(valueAt(made.arguments, use.path));

/** Where a fact to ask for was first used: the turn, and the position of the call in the whole conversation. */
function firstUse(fact: MustAsk, turns: ScenarioTurn[]): { turn: number; order: number } | null {
  let order = 0;
  for (const [index, current] of turns.entries()) {
    for (const made of current.calls) {
      order += 1;
      if (fact.uses.some((use) => uses(use, made))) return { turn: index, order };
    }
  }
  return null;
}

function readBefore(fact: MustAsk, turns: ScenarioTurn[], order: number): boolean {
  const calls = turns.flatMap((current) => current.calls).slice(0, order - 1);
  return calls.some((made) => (fact.resolvers ?? []).includes(made.name) && made.outcome === 'ok');
}

/** Whether the assistant asked for `fact` (the owner said it before the call that used it), found it with one of its
 *  reads, or invented it; `unused` when no call carried it. */
export function classify(fact: MustAsk, turns: ScenarioTurn[]): AskOutcome {
  const used = firstUse(fact, turns);
  if (!used) return 'unused';
  const reveals = fact.reveals.map(plain);
  const said = turns.findIndex((current) => reveals.some((text) => plain(current.owner).includes(text)));
  if (said >= 0 && said <= used.turn) return 'asked';
  return readBefore(fact, turns, used.order) ? 'resolved' : 'invented';
}

const same = (shown: unknown, wanted: string | number): boolean =>
  typeof wanted === 'number' ? Number(shown) === wanted : plain(String(shown ?? '')).trim() === plain(wanted).trim();

function cardProblems(check: CardCheck, cards: SeenCard[]): string[] {
  const label = Object.values(check.match).join(', ');
  return cards
    .filter((card) => card.operation === check.tool)
    .filter((card) => about(card.arguments, check.match))
    .flatMap((card) =>
      Object.entries(check.expect)
        .filter(([path, wanted]) => !same(valueAt(card.arguments, path), wanted))
        .map(([path, wanted]) => `${check.tool} «${label}»: ${path} was ${JSON.stringify(valueAt(card.arguments, path) ?? null)}, expected ${wanted}`),
    );
}

/** The scenario's score from its checks after the job and the conversation's turns. */
export function scoreScenario(scenario: Scenario, results: { expect: CheckResult[]; forbidden: CheckResult[] }, turns: ScenarioTurn[]): ScenarioScore {
  const held = results.expect.filter((result) => result.ok).length;
  const forbidden = results.forbidden.filter((result) => !result.ok).map((result) => result.says);
  const executed = turns.flatMap((current) => current.executed);
  const unwanted = executed.filter((ran) => ran.kind === 'command' && ran.outcome === 'ok' && !scenario.writes.includes(ran.name)).map((ran) => ran.name);
  const cards = turns.flatMap((current) => current.cards);
  const wrongCards = scenario.cards.flatMap((check) => cardProblems(check, cards));
  const mustAsk = scenario.mustAsk.map((fact) => ({ id: fact.id, outcome: classify(fact, turns) }));
  const done = held === results.expect.length && !forbidden.length;
  return {
    done,
    fraction: results.expect.length ? held / results.expect.length : 0,
    forbidden,
    unwanted,
    wrongCards,
    wrongWrites: forbidden.length + unwanted.length + wrongCards.length,
    mustAsk,
    invented: mustAsk.filter((fact) => fact.outcome === 'invented').length,
    ask: askScore(scenario, turns, done),
  };
}
