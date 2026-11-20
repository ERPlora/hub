// One owner message of a scenario and everything the assistant did after it (assistant-scenario-score.ts), read from the
// streamed answers of `/api/assistant/turn` (`base.assistant.gateway.turn_frames`): the answer, every call with its
// arguments, every card with the fields it showed, what ran and the errors; and a card as the owner reads it on the
// screen, for the simulated owner (assistant-owner.ts). Pure, so Vitest proves it (assistant-scenario-turn.test.ts).
import { observe, parseFrames } from './assistant-battery.ts';
import { callsOf } from './assistant-bench.ts';
import type { ScenarioTurn, SeenCard } from './assistant-scenario-score.ts';

type Raw = Record<string, unknown>;

const parsedArguments = (raw: unknown): unknown => {
  if (typeof raw !== 'string') return raw ?? {};
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
};

function seenCard(frame: Raw): SeenCard {
  const card = (frame.card ?? {}) as Raw;
  const call = (frame.call ?? {}) as Raw;
  const fields = Array.isArray(card.fields) ? (card.fields as Raw[]) : [];
  const app = card.app_name ? ` (${String(card.app_name)})` : '';
  return {
    operation: String(card.operation ?? ''),
    title: `${String(card.action ?? card.operation ?? '')}${app}`,
    risk: String(card.risk ?? ''),
    arguments: parsedArguments(call.arguments),
    fields: fields.map((field) => ({ name: String(field.name ?? ''), label: String(field.label ?? ''), kind: String(field.kind ?? ''), value: field.value })),
  };
}

/** Every card the turn's answers showed, in order. */
export function cardsOf(bodies: string[]): SeenCard[] {
  return bodies.flatMap(parseFrames).filter((frame) => frame.type === 'confirm').map(seenCard);
}

/** The owner's message and what the assistant did after it, from the answers of its turn. */
export function scenarioTurn(owner: string, bodies: string[]): ScenarioTurn {
  const seen = observe(bodies);
  return { owner, assistant: seen.text.trim(), calls: callsOf(bodies), cards: cardsOf(bodies), executed: seen.executed, errors: seen.errors };
}

function shown(field: SeenCard['fields'][number], language: string): string | null {
  const { value } = field;
  if (field.kind === 'money' && typeof value === 'number') {
    const euros = (value / 100).toFixed(2);
    return `${language === 'es' ? euros.replace('.', ',') : euros} €`;
  }
  if (Array.isArray(value)) return value.every((item) => typeof item !== 'object') ? value.join(', ') : null;
  if (value === null || value === undefined || value === '' || typeof value === 'object') return null;
  return String(value);
}

/** The card as the owner reads it: what it does, its app and its plain values (an amount in euros). */
export function cardLine(card: SeenCard, language: string): string {
  const values = card.fields
    .map((field) => [field.label, shown(field, language)] as const)
    .filter((pair): pair is readonly [string, string] => pair[1] !== null)
    .map(([label, value]) => `${label}: ${value}`);
  return values.length ? `${card.title} — ${values.join('; ')}` : card.title;
}
