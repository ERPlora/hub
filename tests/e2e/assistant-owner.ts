// The simulated owner of a scenario (assistant-scenario.ts): a fixed model, the same for every assistant under test,
// plays the business owner from its persona and facts only, in plain words, and says when the job looks done or it gives
// up. It goes through OpenRouter (`QA_OWNER_MODEL`, Sonnet by default) with the least randomness the API allows; the key
// is read from QA_OPENROUTER_API_KEY and never written anywhere. Its tokens and cost are kept apart from the
// assistant's. Pure but for the fetch it is given, so Vitest proves it (assistant-owner.test.ts).
import type { Scenario } from './assistant-scenario.ts';

export const OWNER_DEFAULT = 'anthropic/claude-sonnet-5.5';
const OPENROUTER = 'https://openrouter.ai/api/v1';
const KEY_ENV = 'QA_OPENROUTER_API_KEY';
const DONE = '[DONE]';
const GIVE_UP = '[GIVE UP]';

export interface OwnerChoice {
  model: string;
  baseUrl: string;
  /** The NAME of the variable that holds the key. */
  keyEnv: string;
}

/** One line of the conversation as the owner saw it: what it wrote, or what the assistant answered and the cards the
 *  owner confirmed on the screen. */
export interface Exchange {
  who: 'owner' | 'assistant';
  text: string;
  cards?: string[];
}

export interface OwnerReply {
  /** The owner's next message, or null when it ends the conversation. */
  say: string | null;
  end: 'done' | 'gave_up' | null;
  tokensIn: number;
  tokensOut: number;
  /** USD, as OpenRouter counts it; null when it did not say. */
  costUsd: number | null;
}

export interface OwnerDeps {
  fetcher: (url: string, init: RequestInit) => Promise<Response>;
  choice: OwnerChoice;
  key: string;
  /** How long the owner's model may take to answer (2 minutes by default). */
  timeoutMs?: number;
}

type Env = Record<string, string | undefined>;

/** The owner's model: `QA_OWNER_MODEL` or Sonnet, through OpenRouter; a run without the key stops here. */
export function ownerChoice(env: Env): OwnerChoice {
  if (!env[KEY_ENV]?.trim()) throw new Error(`${KEY_ENV} is not set: export it from the root .env before a scenario run (tests/e2e/README.md).`);
  return { model: env.QA_OWNER_MODEL?.trim() || OWNER_DEFAULT, baseUrl: OPENROUTER, keyEnv: KEY_ENV };
}

const bullets = (facts: string[]): string => (facts.length ? facts.map((fact) => `- ${fact}`).join('\n') : '- (nothing)');

/** The owner's instructions: who it is, what it wants, its facts by when it says them, and how it talks and ends. */
export function ownerSystem(scenario: Scenario): string {
  const language = scenario.language === 'es' ? 'Spanish (from Spain)' : 'English';
  const { owner } = scenario;
  return [
    'You are role-playing the owner of a small business who is using the AI assistant built into the business software, from the counter, during a busy day.',
    `Who you are: ${owner.persona}`,
    `What you want done: ${owner.goal}`,
    `What you say up front, in your first messages:\n${bullets(owner.upFront)}`,
    `What you know but say only if the assistant asks you about it:\n${bullets(owner.ifAsked)}`,
    'How you talk:',
    `- Write only in ${language}, in short plain messages, like a busy owner typing on a tablet.`,
    '- Never mention tools, fields, ids, codes, SKUs, tax keys, JSON or the database: talk about your business, as someone who knows nothing about software.',
    '- Answer a question only with the facts above. If you were not told something, say you do not know; if it is a technical detail of the program, the assistant may decide it.',
    '- Never invent facts, prices, quantities, names or new tasks, and never do the assistant\'s work for it.',
    '- The screen sometimes shows a card to confirm an action: you always confirm it, and the conversation tells you so.',
    '- If the assistant asks whether to go ahead, say yes.',
    'How you end:',
    `- When the assistant has done everything you wanted, reply exactly ${DONE} and nothing else.`,
    `- If it keeps failing or refusing the same thing after you asked twice, reply exactly ${GIVE_UP} and nothing else.`,
    '- If something you wanted is still missing, ask for it.',
  ].join('\n');
}

function seen(exchange: Exchange): string {
  if (exchange.who === 'owner') return `YOU: ${exchange.text}`;
  const cards = (exchange.cards ?? []).map((card) => `\n[On the screen you confirmed: ${card}]`).join('');
  return `ASSISTANT: ${exchange.text || '(no answer)'}${cards}`;
}

/** The request for the owner's next message: the whole conversation so far, in one message, as the owner saw it. */
export function ownerRequest(choice: OwnerChoice, scenario: Scenario, transcript: Exchange[]) {
  const conversation = transcript.map(seen).join('\n\n');
  return {
    url: `${choice.baseUrl}/chat/completions`,
    body: {
      model: choice.model,
      temperature: 0,
      max_tokens: 400,
      usage: { include: true },
      messages: [
        { role: 'system', content: ownerSystem(scenario) },
        { role: 'user', content: `The conversation so far:\n\n${conversation}\n\nWrite your next message to the assistant, or ${DONE} or ${GIVE_UP}.` },
      ],
    },
  };
}

interface Completion {
  choices?: { message?: { content?: string } }[];
  usage?: { prompt_tokens?: number; completion_tokens?: number; cost?: number };
  error?: { message?: string };
}

/** The owner's reply from the API's answer: what it says, or how it ends, and what it spent. */
export function parseOwnerReply(answer: Completion): OwnerReply {
  if (answer.error) throw new Error(`the owner's model failed: ${answer.error.message ?? JSON.stringify(answer.error)}`);
  const text = (answer.choices?.[0]?.message?.content ?? '').trim();
  if (!text) throw new Error('the owner\'s model said nothing');
  const usage = answer.usage ?? {};
  let end: OwnerReply['end'] = null;
  if (text.includes(DONE)) end = 'done';
  else if (text.includes(GIVE_UP)) end = 'gave_up';
  return {
    say: end ? null : text,
    end,
    tokensIn: usage.prompt_tokens ?? 0,
    tokensOut: usage.completion_tokens ?? 0,
    costUsd: typeof usage.cost === 'number' ? usage.cost : null,
  };
}

/** Asks the owner's model for its next message. A failure says the status and what the API said, never the key. */
export async function askOwner(deps: OwnerDeps, scenario: Scenario, transcript: Exchange[]): Promise<OwnerReply> {
  const request = ownerRequest(deps.choice, scenario, transcript);
  const response = await deps.fetcher(request.url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${deps.key}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(request.body),
    signal: AbortSignal.timeout(deps.timeoutMs ?? 120_000),
  });
  const body = await response.text();
  if (!response.ok) throw new Error(`the owner's model answered ${response.status}: ${body.slice(0, 300)}`);
  return parseOwnerReply(JSON.parse(body) as Completion);
}
