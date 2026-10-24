// The conversation (BASE-G120): only in this tab of the person's browser (`sessionStorage`, `HISTORY_KEY`), never on
// the Hub nor on erplora.com (no IndexedDB, CLAUDE.md); a reload brings it back, closing the tab loses it. It belongs to
// one person: another one on the same till (a switch by PIN) starts empty and the other's is removed (gh:hub#2538).
// An attachment's data travels once, with its question: kept, it is its name. A storage that refuses is ignored.
import type { GroundingNotice } from './assistant-grounding';

export const HISTORY_KEY = 'erplora.assistant.history';

export type ContentPart =
  | { type: 'text'; text: string }
  | { type: 'image_url'; image_url: { url: string }; filename?: string }
  | { type: 'input_file'; filename: string; mime_type: string; data: string };

export interface ToolCall {
  id: string;
  type: 'function';
  function: { name: string; arguments: string };
}

/** A message of the conversation, as the gateway reads it. */
export interface ChatMessage {
  role: 'user' | 'assistant' | 'tool';
  content: string | ContentPart[];
  tool_calls?: ToolCall[];
  tool_call_id?: string;
}

/** A bubble of the panel. */
export interface Bubble {
  id: string;
  role: 'user' | 'assistant';
  text: string;
  /** Names of the attached files (a user's bubble). */
  files: string[];
  notices: GroundingNotice[];
  /** False while it is being written. */
  done: boolean;
  /** Why it ended without an answer (a code of `assistant-errors.ts`). */
  error?: string;
  /** Numbers of the error's sentence (the allowance's). */
  details?: Record<string, unknown>;
  stopped?: boolean;
  /** The question that led to an answer (for «Report a problem»). */
  question?: string;
  /** What ran in the turn, for the receipts under the bubble. */
  executed?: { name: string; app: string; outcome: string }[];
}

export interface Thread {
  user: string;
  conversation: ChatMessage[];
  bubbles: Bubble[];
  /** The panel was opened to set up the business (BASE-G121): the checklist goes to the model. */
  setup: boolean;
}

export function emptyThread(user: string): Thread {
  return { user, conversation: [], bubbles: [], setup: false };
}

function kept(part: ContentPart): ContentPart {
  if (part.type === 'input_file') return { type: 'text', text: `[Attached: ${part.filename}]` };
  if (part.type === 'image_url') return { type: 'text', text: `[Attached: ${part.filename ?? 'image'}]` };
  return part;
}

/** The thread as it is kept: attachments by name. */
export function withoutData(conversation: ChatMessage[]): ChatMessage[] {
  return conversation.map((message) =>
    Array.isArray(message.content) ? { ...message, content: message.content.map(kept) } : message,
  );
}

export function loadThread(storage: Storage | undefined, user: string): Thread {
  let raw: string | null = null;
  try {
    raw = storage?.getItem(HISTORY_KEY) ?? null;
  } catch {
    return emptyThread(user);
  }
  if (!raw) return emptyThread(user);
  let parsed: Thread;
  try {
    parsed = JSON.parse(raw) as Thread;
  } catch {
    return emptyThread(user);
  }
  if (!parsed || parsed.user !== user || !Array.isArray(parsed.conversation) || !Array.isArray(parsed.bubbles)) {
    clearThread(storage);
    return emptyThread(user);
  }
  return {
    ...parsed,
    setup: Boolean(parsed.setup),
    bubbles: parsed.bubbles.map((bubble) => (bubble.done ? bubble : { ...bubble, done: true, error: bubble.error ?? 'assistant.cut' })),
  };
}

export function saveThread(storage: Storage | undefined, thread: Thread): void {
  try {
    storage?.setItem(HISTORY_KEY, JSON.stringify({ ...thread, conversation: withoutData(thread.conversation) }));
  } catch {
    // A storage that refuses (private mode, full): the thread lives on in memory until the tab closes.
  }
}

export function clearThread(storage: Storage | undefined): void {
  try {
    storage?.removeItem(HISTORY_KEY);
  } catch {
    // Nothing kept to remove.
  }
}
