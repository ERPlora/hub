// @vitest-environment node
// flow: e2e-live-streams — FIX of the e2e harness (hub#814)
// A spec that proves a change arrived «over the stream already open» counts the `/api/live` the page opens, and it may
// only start counting once that stream is really the open one. A screen left behind keeps its subscriptions
// `RELEASE_GRACE_MS` and only then reopens the stream, so a second of quiet says nothing: with the machine loaded the
// reopening fell between the count and the assertion, and «Tus mesas» went red with nothing broken. And the stream
// reopened holds its frames until its opening pass ends: a change made during that pass reaches the screen in the pass,
// seconds later, and proves nothing about the events.
import { RELEASE_GRACE_MS, RESUBSCRIBE_DEBOUNCE_MS } from '@erplora/ui/sdk';
import type { Page } from '@playwright/test';
import { describe, expect, it, vi } from 'vitest';

import {
  liveStreamsPending,
  liveStreamsSettled,
  type LiveStream,
  QUIET_MS,
  RELEASE_WINDOW_MS,
  watchLiveStreams,
} from './live-streams';

const HOME = 'base.setup.status';
const TABLES = 'table.table.list';
const ZONES = 'table.zone.list';
const NOW = 1_000_000;

/** A stream of `ops`, every one of them answered unless the spec says how many were. */
function stream(ops: string[], ago = 5_000, answers = ops.length): LiveStream {
  return { at: NOW - ago, ops, answered: new Set(ops.slice(0, answers)) };
}

/** The address of a stream with the subscriptions as `encodeSubscriptions` of `@erplora/ui` writes them: each id, its op. */
function liveUrl(ops: string[], origin = 'http://a.localhost:8000'): string {
  const subscriptions = ops.map((op) => ({ id: op, op, params: {} }));
  return `${origin}/api/live?s=${Buffer.from(JSON.stringify(subscriptions)).toString('base64url')}`;
}

const base64 = (text: string) => Buffer.from(text).toString('base64');
const result = (id: string) => `event: result\ndata: ${JSON.stringify({ id, data: {}, rev: 1 })}\n\n`;

/** A page whose DevTools session only tells its listeners what a test makes the browser do. */
function fakeDevtools() {
  const listeners = new Map<string, (event: never) => void>();
  const send = vi.fn<(method: string, params?: unknown) => Promise<unknown>>(async () => ({ bufferedData: '' }));
  const session = {
    on(event: string, listener: (event: never) => void) {
      listeners.set(event, listener);
    },
    send,
  };
  const page = { context: () => ({ newCDPSession: async () => session }) } as unknown as Page;
  const emit = (event: string, payload: unknown) => listeners.get(event)?.(payload as never);
  return {
    page,
    send,
    open: (requestId: string, url: string) => emit('Network.requestWillBeSent', { requestId, request: { url } }),
    answer: (requestId: string) => emit('Network.responseReceived', { requestId }),
    data: (requestId: string, text: string) => emit('Network.dataReceived', { requestId, data: base64(text) }),
    /** Whatever the session handed over has been read. */
    read: () => new Promise((resolve) => setImmediate(resolve)),
  };
}

describe('liveStreamsPending', () => {
  it('is empty once the last stream is off the screen left, has answered everything and is a second old', () => {
    const streams = [stream([HOME, TABLES, ZONES], 9_000), stream([HOME], QUIET_MS + 1)];

    expect(liveStreamsPending(streams, [TABLES, ZONES], NOW)).toEqual([]);
  });

  // hub#814: the Tables stream opened long ago, so it has been quiet for seconds, and its grace has not ended yet.
  it('holds on while the last stream carries the screen left, however long the quiet', () => {
    const streams = [stream([HOME]), stream([HOME, TABLES, ZONES], 60_000)];

    expect(liveStreamsPending(streams, [TABLES, ZONES], NOW)).toEqual([
      `the last /api/live still carries ${TABLES}`,
      `the last /api/live still carries ${ZONES}`,
    ]);
  });

  it('holds on for the quiet after the reopening without the screen left', () => {
    const streams = [stream([HOME, TABLES], 9_000), stream([HOME], 10)];

    expect(liveStreamsPending(streams, [TABLES], NOW)).toEqual(['the last /api/live opened 10 ms ago']);
  });

  // hub#814 too: a change made during the opening pass reaches the screen in that pass, not through its events.
  it('holds on while the last stream has not answered all its subscriptions, however long the quiet', () => {
    expect(liveStreamsPending([stream([HOME, TABLES], 60_000, 1)], [], NOW)).toEqual([
      'the last /api/live answered 1 of its 2 subscriptions',
    ]);
  });

  it('holds on with no stream at all', () => {
    expect(liveStreamsPending([], [], NOW)).toEqual(['no /api/live yet']);
  });

  // An operation renamed, or a screen that no longer reads it: the wait must not pass for the wrong reason.
  it('says so when no stream ever carried the screen left', () => {
    expect(liveStreamsPending([stream([HOME])], [TABLES], NOW)).toEqual([`no /api/live ever carried ${TABLES}`]);
  });
});

describe('liveStreamsSettled', () => {
  it('returns at once when nothing is pending', async () => {
    await expect(liveStreamsSettled([{ at: 0, ops: [HOME], answered: new Set([HOME]) }])).resolves.toBeUndefined();
  });

  it('fails naming what it waited for', async () => {
    const streams: LiveStream[] = [{ at: Date.now(), ops: [HOME, TABLES], answered: new Set([HOME, TABLES]) }];

    await expect(liveStreamsSettled(streams, [TABLES], { timeout: 50 })).rejects.toThrow(`still carries ${TABLES}`);
  });
});

describe('watchLiveStreams', () => {
  it('notes every /api/live with its operations, in the order the page opens them, and nothing else', async () => {
    const browser = fakeDevtools();
    const streams = await watchLiveStreams(browser.page);

    browser.open('1', liveUrl([HOME, TABLES]));
    browser.open('2', 'http://a.localhost:8000/api/table/tables?s=x');
    browser.open('3', 'http://a.localhost:8000/static/api/live.js');
    browser.open('4', liveUrl([HOME]));

    expect(streams.map(({ ops }) => ops)).toEqual([[HOME, TABLES], [HOME]]);
  });

  it('takes an address without subscriptions as a stream of nothing', async () => {
    const browser = fakeDevtools();
    const streams = await watchLiveStreams(browser.page);

    browser.open('1', 'http://a.localhost:8000/api/live');
    browser.open('2', 'http://a.localhost:8000/api/live?s=not-json');

    expect(streams.map(({ ops }) => ops)).toEqual([[], []]);
  });

  it('notes each answer on its own stream, its results and its errors, not the rest of the frames', async () => {
    const browser = fakeDevtools();
    const streams = await watchLiveStreams(browser.page);

    browser.open('1', liveUrl([HOME, TABLES]));
    browser.open('2', liveUrl([ZONES]));
    browser.answer('1');
    browser.answer('2');
    await browser.read();
    browser.data('1', `event: hello\ndata: {"stream":"x"}\n\nevent: heartbeat\ndata: {}\n\n${result(HOME)}`);
    browser.data('1', `event: error\ndata: ${JSON.stringify({ id: TABLES, error: { code: 'x' } })}\n\n`);
    await browser.read();

    expect(streams.map(({ answered }) => [...answered])).toEqual([[HOME, TABLES], []]);
  });

  it('reads what arrived before it asked for the stream first, and a frame split across chunks', async () => {
    const browser = fakeDevtools();
    browser.send.mockImplementation(async (method) =>
      method === 'Network.streamResourceContent' ? { bufferedData: base64(`${result(HOME)}event: res`) } : {},
    );
    const streams = await watchLiveStreams(browser.page);

    browser.open('1', liveUrl([HOME, TABLES]));
    browser.answer('1');
    browser.data('1', `ult\ndata: ${JSON.stringify({ id: TABLES, data: {}, rev: 1 })}\n\n`);
    await browser.read();

    expect(browser.send).toHaveBeenCalledWith('Network.streamResourceContent', { requestId: '1' });
    expect([...streams[0].answered]).toEqual([HOME, TABLES]);
  });

  it('gives up reading a stream the browser no longer has, and keeps watching the next', async () => {
    const browser = fakeDevtools();
    browser.send.mockImplementation(async (method) => {
      if (method === 'Network.streamResourceContent') throw new Error('Request is not in flight');
      return {};
    });
    const streams = await watchLiveStreams(browser.page);

    browser.open('1', liveUrl([HOME]));
    browser.answer('1');
    await browser.read();
    browser.open('2', liveUrl([TABLES]));

    expect(streams.map(({ ops }) => ops)).toEqual([[HOME], [TABLES]]);
    expect(streams[0].answered.size).toBe(0);
  });
});

describe('RELEASE_WINDOW_MS', () => {
  it('covers what the SDK takes to let go of a screen and reopen the stream', () => {
    expect(RELEASE_WINDOW_MS).toBeGreaterThan(RELEASE_GRACE_MS + RESUBSCRIBE_DEBOUNCE_MS);
  });
});
