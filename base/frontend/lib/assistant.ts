// The state of the assistant's panel (APP-BASE-9), one per tab: it outlives the panel's component (remounted when the
// person changes) and a turn goes on while the panel is closed.
// - A question (BASE-G111) goes out with the whole conversation; its answer arrives into ONE bubble, from every round.
// - The reads the model asks for go on by themselves (each round is one more request of the turn, BASE-G119); a write
//   stops on its card (BASE-G115, G116) until `decide` — yes, no, or «Cancel all» (`stop`).
// - «Stop» (`stop`) aborts the request: what was written stays. A failure ends the bubble with its code (BASE-G124),
//   and `retry` asks the same question again.
// - At the end, what the answer says is checked against what ran (BASE-G117), and the conversation is kept in the tab
//   for this person only (BASE-G120); another person starts empty, with the panel closed (gh:hub#2538).
import { ApiError } from '@erplora/ui/sdk';
import { reactive } from 'vue';

import type { AssistantUsage } from '../operations';
import type { AssistantCard } from './assistant-card';
import { type Executed, groundingNotices } from './assistant-grounding';
import {
  type Bubble,
  type ChatMessage,
  type ContentPart,
  clearThread,
  emptyThread,
  loadThread,
  saveThread,
  type Thread,
} from './assistant-history';
import { type Decision, type PendingCall, postTurn, type TurnBody, type TurnFrame, type TurnOptions } from './assistant-stream';

export const OPEN_KEY = 'erplora.assistant.open';

export interface Attachment {
  name: string;
  mime: string;
  /** Base64, without the `data:` prefix. */
  data: string;
}

export interface AssistantState {
  open: boolean;
  thread: Thread;
  /** A turn in flight, or a card waiting for its answer. */
  busy: boolean;
  /** The card of the write that waits; `more`: other actions wait behind it («Cancel all»). */
  confirm: { card: AssistantCard; call: PendingCall; more: boolean } | null;
  usage: AssistantUsage | null;
  /** What the person is writing and attaching, not sent yet. */
  draft: string;
  files: Attachment[];
}

export interface AssistantDeps {
  post?: (body: TurnBody, options: TurnOptions) => Promise<void>;
  storage?: Storage;
  openStorage?: Storage;
  id?: () => string;
}

interface Turn {
  bubble: Bubble;
  question: string;
  pending: PendingCall[];
  continuation: string | null;
  executed: Executed[];
  results: string[];
}

function readOpen(storage: Storage | undefined): boolean {
  try {
    return storage?.getItem(OPEN_KEY) === '1';
  } catch {
    return false;
  }
}

function contentOf(text: string, files: Attachment[]): string | ContentPart[] {
  if (files.length === 0) return text;
  const parts: ContentPart[] = text ? [{ type: 'text', text }] : [];
  for (const file of files) {
    if (file.mime.startsWith('image/')) {
      parts.push({ type: 'image_url', image_url: { url: `data:${file.mime};base64,${file.data}` }, filename: file.name });
    } else {
      parts.push({ type: 'input_file', filename: file.name, mime_type: file.mime, data: file.data });
    }
  }
  return parts;
}

/** The conversation as the gateway takes it: an image's file name is the panel's, not a field of its part. */
function forGateway(conversation: ChatMessage[]): ChatMessage[] {
  return conversation.map((message) =>
    Array.isArray(message.content)
      ? {
          ...message,
          content: message.content.map((part) => (part.type === 'image_url' ? { type: part.type, image_url: part.image_url } : part)),
        }
      : message,
  );
}

function isAbort(error: unknown): boolean {
  return error instanceof DOMException && error.name === 'AbortError';
}

export function createAssistant(deps: AssistantDeps = {}) {
  const post = deps.post ?? postTurn;
  const storage = deps.storage;
  const openStorage = deps.openStorage;
  const id = deps.id ?? (() => globalThis.crypto.randomUUID());
  const state = reactive<AssistantState>({
    open: readOpen(openStorage),
    thread: emptyThread(''),
    busy: false,
    confirm: null,
    usage: null,
    draft: '',
    files: [],
  });
  let controller: AbortController | null = null;
  let turn: Turn | null = null;
  let screenExists: (path: string) => boolean = () => true;

  const save = () => saveThread(storage, state.thread);

  function setOpen(open: boolean): void {
    state.open = open;
    try {
      openStorage?.setItem(OPEN_KEY, open ? '1' : '0');
    } catch {
      // A storage that refuses: the panel stays as it is until the page reloads.
    }
  }

  function abort(): void {
    controller?.abort();
    controller = null;
  }

  function reset(user: string): void {
    abort();
    turn = null;
    state.thread = emptyThread(user);
    state.busy = false;
    state.confirm = null;
    state.draft = '';
    state.files = [];
  }

  /** The person of the session: another one than the thread's starts empty, with the panel closed. */
  function forUser(user: string): void {
    if (state.thread.user === user) return;
    const changed = state.thread.user !== '';
    reset(user);
    state.thread = loadThread(storage, user);
    if (changed) setOpen(false);
  }

  function finish(error?: string, details?: Record<string, unknown>, stopped = false): void {
    if (!turn) return;
    const { bubble } = turn;
    bubble.done = true;
    if (error) {
      bubble.error = error;
      if (details) bubble.details = details;
    }
    if (stopped) bubble.stopped = true;
    bubble.executed = turn.executed
      .filter((row) => row.kind === 'command')
      .map((row) => ({ name: row.name, app: row.app ?? '', outcome: row.outcome }));
    if (bubble.text) {
      bubble.notices = groundingNotices({
        answer: bubble.text,
        executed: turn.executed,
        results: turn.results,
        question: turn.question,
        screenExists,
      });
    }
    turn = null;
    controller = null;
    state.busy = false;
    state.confirm = null;
    save();
  }

  async function run(decision?: Decision): Promise<void> {
    if (!turn) return;
    state.busy = true;
    for (;;) {
      const current: Turn = turn;
      controller = new AbortController();
      let doneFrame: Extract<TurnFrame, { type: 'done' }> | null = null;
      let confirm: { card: AssistantCard; call: PendingCall } | null = null;
      let failure: { code: string; details: Record<string, unknown> } | null = null;
      const onFrame = (frame: TurnFrame) => {
        if (frame.type === 'text') current.bubble.text += frame.text;
        else if (frame.type === 'executed') current.executed.push({ name: frame.name, kind: frame.kind, outcome: frame.outcome, app: frame.app });
        else if (frame.type === 'usage') state.usage = { used: frame.used, limit: frame.limit, resets_at: frame.resets_at, demo: frame.demo };
        else if (frame.type === 'confirm') confirm = { card: frame.card, call: frame.call };
        else if (frame.type === 'error') {
          const { code, ...rest } = frame;
          const details: Record<string, unknown> = { ...rest };
          delete details.type;
          failure = { code, details };
        } else if (frame.type === 'done') doneFrame = frame;
      };
      const body: TurnBody = { messages: forGateway(state.thread.conversation), setup: state.thread.setup };
      if (current.continuation) body.continuation = current.continuation;
      if (current.pending.length) body.pending = current.pending;
      if (decision) body.decision = decision;
      decision = undefined;
      try {
        await post(body, { onFrame, signal: controller.signal });
      } catch (error) {
        if (turn !== current) return;
        if (isAbort(error)) return finish(undefined, undefined, true);
        const code = error instanceof ApiError ? error.code : 'assistant.unreachable';
        return finish(code, error instanceof ApiError ? (error.details ?? {}) : {});
      }
      if (turn !== current) return;
      const closed = doneFrame as Extract<TurnFrame, { type: 'done' }> | null;
      if (closed) {
        state.thread.conversation.push(...closed.append);
        for (const message of closed.append) {
          if (message.role === 'tool' && typeof message.content === 'string') current.results.push(message.content);
        }
        current.pending = closed.pending;
        current.continuation = closed.continuation;
      }
      const stopped = failure as { code: string; details: Record<string, unknown> } | null;
      if (stopped) return finish(stopped.code, stopped.details);
      const waiting = confirm as { card: AssistantCard; call: PendingCall } | null;
      if (waiting && waiting.card.blocked) {
        // Not done from the chat (a dangerous write that names no record): no card, the model hears it and says where.
        current.bubble.blocked = true;
        decision = { call_id: waiting.call.call_id, accepted: false, typed: '', stop: false };
        continue;
      }
      if (waiting) {
        state.confirm = { ...waiting, more: current.pending.length > 1 };
        save();
        return;
      }
      if (!closed) return finish('assistant.cut');
      if (current.pending.length === 0) return finish();
    }
  }

  async function ask(text: string, options: { setup?: boolean } = {}): Promise<void> {
    const question = text.trim();
    const files = [...state.files];
    if (state.busy || (!question && files.length === 0)) return;
    if (options.setup) state.thread.setup = true;
    state.thread.bubbles.push({ id: id(), role: 'user', text: question, files: files.map((file) => file.name), notices: [], done: true });
    state.thread.conversation.push({ role: 'user', content: contentOf(question, files) });
    state.draft = '';
    state.files = [];
    const bubble: Bubble = { id: id(), role: 'assistant', text: '', files: [], notices: [], done: false, question };
    state.thread.bubbles.push(bubble);
    // The reactive copy: what the frames write is what the panel paints.
    turn = { bubble: state.thread.bubbles.at(-1)!, question, pending: [], continuation: null, executed: [], results: [] };
    save();
    await run();
  }

  /** The person's answer to the card: yes (with what it typed), no, or «Cancel all» (`stop`). */
  async function decide(accepted: boolean, typed = '', stop = false): Promise<void> {
    if (!state.confirm || !turn) return;
    const { call } = state.confirm;
    state.confirm = null;
    await run({ call_id: call.call_id, accepted, typed, stop });
  }

  /** «Stop»: the request in flight is aborted (what was written stays); a card waiting is cancelled with the rest. */
  function stop(): void {
    if (state.confirm) {
      void decide(false, '', true);
      return;
    }
    abort();
  }

  /** Ask the last question again, after a failure. */
  async function retry(): Promise<void> {
    if (state.busy) return;
    const last = state.thread.bubbles.at(-1);
    if (!last || last.role !== 'assistant' || !last.error) return;
    const question = last.question ?? '';
    state.thread.bubbles.pop();
    if (state.thread.conversation.at(-1)?.role !== 'user') {
      state.thread.conversation.push({ role: 'user', content: question });
    }
    const bubble: Bubble = { id: id(), role: 'assistant', text: '', files: [], notices: [], done: false, question };
    state.thread.bubbles.push(bubble);
    turn = { bubble: state.thread.bubbles.at(-1)!, question, pending: [], continuation: null, executed: [], results: [] };
    await run();
  }

  function newConversation(): void {
    const user = state.thread.user;
    reset(user);
    clearThread(storage);
  }

  /** Forget everything of this tab (signing out). */
  function forget(): void {
    reset('');
    clearThread(storage);
  }

  function openForSetup(): void {
    state.thread.setup = true;
    setOpen(true);
    save();
  }

  return {
    state,
    forUser,
    setOpen,
    toggle: () => setOpen(!state.open),
    ask,
    decide,
    stop,
    retry,
    newConversation,
    forget,
    openForSetup,
    setScreenCheck(check: (path: string) => boolean) {
      screenExists = check;
    },
  };
}

export type Assistant = ReturnType<typeof createAssistant>;

function browserStorage(name: 'sessionStorage' | 'localStorage'): Storage | undefined {
  try {
    return globalThis[name];
  } catch {
    return undefined;
  }
}

let shared: Assistant | undefined;

/** The tab's assistant: the same for every component and every mount. */
export function useAssistant(): Assistant {
  shared ??= createAssistant({ storage: browserStorage('sessionStorage'), openStorage: browserStorage('localStorage') });
  return shared;
}

/** Puts `instance` as the tab's assistant (a test's own), or forgets it (`undefined`). */
export function installAssistant(instance: Assistant | undefined): void {
  shared = instance;
}

/** Signing out forgets the conversation of the tab (BASE-G120), even if the panel was never opened. */
export function forgetAssistant(): void {
  if (shared) shared.forget();
  else clearThread(browserStorage('sessionStorage'));
}
