// The transport of a turn of the assistant (BASE-G06, the old hub's SSE client; PLAN §14 «un solo camino»): ONE POST
// to `base.assistant.turn`'s route whose answer is a stream of `data: <json>` frames, read as they arrive with `fetch` +
// `ReadableStream` and closed when the turn ends — no EventSource and no second permanent stream (`/api/live` stays
// the tab's one). Same origin, with the SDK's own headers (CSRF, device). The SDK's client cannot read a stream (it
// waits for a JSON body): hence its own `fetch`, as `lib/access.ts`. A refusal of the Hub rejects with the envelope's
// `ApiError`; a network that is not there rejects as `fetch` does; aborting (`signal`) stops reading.
import { ApiError, createHeaderProvider, parseErrorEnvelope, readSpaConfig } from '@erplora/ui/sdk';

import { approvalPass } from './approval';
import type { AssistantCard } from './assistant-card';
import type { ChatMessage } from './assistant-history';

export const TURN_PATH = '/api/assistant/turn';

export interface PendingCall {
  call_id: string;
  name: string;
  arguments: string;
}

export interface Decision {
  call_id: string;
  accepted: boolean;
  typed?: string;
  stop?: boolean;
}

export interface TurnBody {
  messages: ChatMessage[];
  continuation?: string | null;
  pending?: PendingCall[];
  decision?: Decision;
  setup?: boolean;
}

export type TurnFrame =
  | { type: 'executed'; call_id: string; name: string; app: string; kind: 'query' | 'command' | ''; outcome: 'ok' | 'error' | 'refused' | 'cancelled'; code: string }
  | { type: 'confirm'; card: AssistantCard; call: PendingCall }
  | { type: 'text'; text: string }
  | { type: 'usage'; used: number; limit: number; resets_at: string | null; demo: boolean }
  | ({ type: 'error'; code: string; retriable?: boolean } & Record<string, unknown>)
  | { type: 'done'; append: ChatMessage[]; pending: PendingCall[]; continuation: string | null };

export interface TurnOptions {
  onFrame: (frame: TurnFrame) => void;
  signal?: AbortSignal;
  fetcher?: typeof fetch;
  doc?: Document;
}

function headers(doc: Document): Record<string, string> {
  const config = readSpaConfig(doc);
  const provider = createHeaderProvider(config, {
    storage: {
      getItem: (key) => {
        try {
          return globalThis.localStorage?.getItem(key) ?? null;
        } catch {
          return null;
        }
      },
      setItem: (key, value) => {
        try {
          globalThis.localStorage?.setItem(key, value);
        } catch {
          // A storage that refuses: the device id lives in memory (the SDK's own fallback).
        }
      },
    },
    cookies: () => doc.cookie,
    randomUUID: () => globalThis.crypto.randomUUID(),
    // A manager's approval (BASE-G118): the pass of the turn being repeated, in `X-Elevation-Token`.
    getElevationToken: approvalPass,
  });
  return { ...provider.apiHeaders('POST'), Accept: 'text/event-stream', 'Content-Type': 'application/json' };
}

function emit(chunk: string, onFrame: (frame: TurnFrame) => void): void {
  for (const line of chunk.split('\n')) {
    if (!line.startsWith('data:')) continue;
    try {
      onFrame(JSON.parse(line.slice(5).trim()) as TurnFrame);
    } catch {
      // A frame that cannot be read is skipped; the turn's `done` still closes it.
    }
  }
}

export async function postTurn(body: TurnBody, options: TurnOptions): Promise<void> {
  const doc = options.doc ?? document;
  // The SDK's client cannot read a streamed answer (see above): same origin and its headers, as its own calls.
  // eslint-disable-next-line no-restricted-globals -- see above
  const fetcher = options.fetcher ?? ((...args: Parameters<typeof fetch>) => fetch(...args));
  const response = await fetcher(TURN_PATH, {
    method: 'POST',
    credentials: 'same-origin',
    headers: headers(doc),
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (!response.ok) {
    const text = await response.text();
    let envelope: unknown = text;
    try {
      envelope = JSON.parse(text);
    } catch {
      // Not JSON (a proxy's page): the status alone says it.
    }
    throw parseErrorEnvelope(response.status, envelope);
  }
  if (!response.body) throw new ApiError(response.status, 'assistant.cut', 'The answer has no body.');
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let end = buffer.indexOf('\n\n');
    while (end !== -1) {
      emit(buffer.slice(0, end), options.onFrame);
      buffer = buffer.slice(end + 2);
      end = buffer.indexOf('\n\n');
    }
  }
  if (buffer.trim()) emit(buffer, options.onFrame);
}
