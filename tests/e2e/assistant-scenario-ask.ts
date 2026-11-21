// Whether the assistant asks before acting, read from what went over the wire in a scenario (assistant-scenario.ts):
// its first move after the owner's opening, and the writes it put out before the owner said anything more. A job the
// owner says by halves («se han roto 3 botellas») is right only when the assistant asks first; one said whole is right
// when the job ends done, after asking for a missing fact or not. Pure, so Vitest proves it
// (assistant-scenario-ask.test.ts).
import type { Said } from './assistant-scenario.ts';
import type { ScenarioTurn } from './assistant-scenario-score.ts';

/** `writes`: the opening's turn showed a card or tried a write; `asks`: it did not, and its answer asks something. */
export type FirstMove = 'asks' | 'writes' | 'neither';

export interface AskScore {
  said: Said | null;
  firstMove: FirstMove | null;
  /** The writes the assistant put out before the owner's second message, by operation. */
  writesBeforeClear: string[];
  /** Null when the scenario does not say how the job is said. */
  right: boolean | null;
}

/** The operations of a turn that write: every write shows a card, or is refused before it as a command. */
const writesOf = (turn: ScenarioTurn): Set<string> =>
  new Set([...turn.cards.map((card) => card.operation), ...turn.executed.filter((ran) => ran.kind === 'command').map((ran) => ran.name)]);

export function firstMove(turns: ScenarioTurn[]): FirstMove | null {
  const [opening] = turns;
  if (!opening) return null;
  if (writesOf(opening).size) return 'writes';
  return /[?¿]/.test(opening.assistant) ? 'asks' : 'neither';
}

/** Until the owner writes again, nothing the opening left unsaid is clear: only the opening's turn counts. */
export function writesBeforeClear(turns: ScenarioTurn[]): string[] {
  const [opening] = turns;
  if (!opening) return [];
  const writes = writesOf(opening);
  return opening.calls.filter((call) => writes.has(call.name)).map((call) => call.name);
}

export function askScore(scenario: { said?: Said }, turns: ScenarioTurn[], done: boolean): AskScore {
  const said = scenario.said ?? null;
  const move = firstMove(turns);
  const right = said === null ? null : said === 'half' ? move === 'asks' : done;
  return { said, firstMove: move, writesBeforeClear: writesBeforeClear(turns), right };
}
