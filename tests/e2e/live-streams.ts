// flow: e2e-live-streams — FIX of the e2e harness (hub#814)
// A new `/api/live` brings every result again, so what changes on a screen without one came over the stream already
// open, re-run by its events: that is what a spec proves by counting the streams of its page. It may only start counting
// once that stream is really the open one, and it can tell from what the browser sees, instead of hoping a pause was
// enough. The browser's DevTools read the stream as it arrives, with the page untouched.
import { type Browser, type BrowserContext, expect, type Page } from '@playwright/test';

import { createSseParser, type SseParser } from '../../packages/ui/src/sdk/sse-parser';
import { decodeSubs, saveSessionForTheSweep, shown, signedInSpanish } from './helpers';

/** A `/api/live` the page opened: when, the operations it carries and the subscriptions the Hub has answered so far. */
export interface LiveStream {
  at: number;
  ops: string[];
  answered: Set<string>;
}

/** The quiet that says the screen has declared every subscription, in ms. It says nothing about a screen left behind. */
export const QUIET_MS = 1_000;

/**
 * How long a screen left can still reopen the stream, in ms: the SDK keeps its subscriptions `RELEASE_GRACE_MS` (2 s) in
 * case it comes back and closes the stream `RESUBSCRIBE_DEBOUNCE_MS` (150 ms) later, both of `@erplora/ui/sdk`.
 */
export const RELEASE_WINDOW_MS = 2_500;

/** What a spec waits for the page at most, in ms: a sixth of the test's 180 s, and the wait ends when nothing is pending. */
const SETTLE_TIMEOUT_MS = 30_000;

/** Every `/api/live` the page opens from now on, in order. Call it before the page opens the first. */
export async function watchLiveStreams(page: Page): Promise<LiveStream[]> {
  const streams: LiveStream[] = [];
  const reading = new Map<string, { parser: SseParser; read: Promise<void> }>();
  const devtools = await page.context().newCDPSession(page);
  devtools.on('Network.requestWillBeSent', ({ requestId, request }) => {
    if (new URL(request.url).pathname !== '/api/live') return;
    const stream: LiveStream = { at: Date.now(), ops: operationsOf(request.url), answered: new Set() };
    streams.push(stream);
    reading.set(requestId, { parser: createSseParser(answerOf(stream)), read: Promise.resolve() });
  });
  // What already arrived comes with the request to read the rest, and each chunk after it, always in that order. A
  // stream the browser no longer has (the SDK has just closed it) has nothing left to answer, and a later one is the last.
  devtools.on('Network.responseReceived', ({ requestId }) => {
    const entry = reading.get(requestId);
    if (!entry) return;
    entry.read = devtools.send('Network.streamResourceContent', { requestId }).then(
      ({ bufferedData }) => entry.parser.push(Buffer.from(bufferedData, 'base64')),
      () => undefined,
    );
  });
  devtools.on('Network.dataReceived', ({ requestId, data }) => {
    const entry = reading.get(requestId);
    if (entry && data) entry.read = entry.read.then(() => entry.parser.push(Buffer.from(data, 'base64')));
  });
  await devtools.send('Network.enable');
  return streams;
}

/**
 * The owner on `a` in Spanish, on the Home, with every `/api/live` the page opens from then on: what the sign-in opened
 * says nothing about the screen, so the count starts with a Home loaded again.
 */
export async function spanishOwner(
  browser: Browser,
  viewport: { width: number; height: number },
): Promise<{ context: BrowserContext; page: Page; streams: LiveStream[] }> {
  const { context, page } = await signedInSpanish(browser, viewport, '/');
  const streams = await watchLiveStreams(page);
  await page.reload();
  await expect(shown(page).locator('[data-testid="home-my-apps"]')).toBeVisible();
  await saveSessionForTheSweep(context);
  return { context, page, streams };
}

function operationsOf(url: string): string[] {
  return decodeSubs(url).flatMap((subscription) => {
    const op = (subscription as { op?: unknown } | null)?.op;
    return typeof op === 'string' ? [op] : [];
  });
}

/** Notes on `stream` the subscription each frame answers: its `result` or its `error`, the two that carry an id. */
function answerOf(stream: LiveStream): Parameters<typeof createSseParser>[0] {
  return (frame) => {
    if (frame.type !== 'event' || (frame.event !== 'result' && frame.event !== 'error')) return;
    const { id } = JSON.parse(frame.data) as { id?: string };
    if (id) stream.answered.add(id);
  };
}

/**
 * What the page still owes before a spec may count its streams, in words; nothing when it is settled:
 * - The screen it left (`left`, the operations only that screen reads) is off the last stream. The SDK keeps them
 *   `RELEASE_GRACE_MS` in case the screen comes back, so a stream that opened long ago with them has been quiet for
 *   seconds and is about to be replaced (hub#814).
 * - The last stream has answered all its subscriptions. The Hub holds a stream's frames until its opening pass ends (10 s
 *   measured with the machine loaded), so a change made before that comes in the pass, seconds later, and says nothing
 *   about the events (hub#814).
 * - No other has followed for `QUIET_MS`.
 */
export function liveStreamsPending(streams: LiveStream[], left: string[] = [], now = Date.now()): string[] {
  const last = streams.at(-1);
  if (!last) return ['no /api/live yet'];
  const pending = left.flatMap((op) => {
    if (last.ops.includes(op)) return [`the last /api/live still carries ${op}`];
    return streams.some((stream) => stream.ops.includes(op)) ? [] : [`no /api/live ever carried ${op}`];
  });
  if (last.answered.size < last.ops.length) {
    pending.push(`the last /api/live answered ${last.answered.size} of its ${last.ops.length} subscriptions`);
  }
  const age = now - last.at;
  if (age <= QUIET_MS) pending.push(`the last /api/live opened ${age} ms ago`);
  return pending;
}

/** Waits until nothing is pending (`liveStreamsPending`), and fails saying what still was. */
export async function liveStreamsSettled(
  streams: LiveStream[],
  left: string[] = [],
  { timeout = SETTLE_TIMEOUT_MS } = {},
): Promise<void> {
  await expect.poll(() => liveStreamsPending(streams, left), { timeout }).toEqual([]);
}
