// @vitest-environment node
// When a request of the page ended, as the page's own clock saw it (Resource Timing). In the dev stack Vite
// serves every module of the SPA one by one, and they fill Chrome's resource timing buffer (250 entries) before
// the first click: `performance.getEntriesByType('resource')` then never lists the request the spec measures
// (hub#34: `NaN` in delete-item, `null` in optimistic-add-line). Node implements the same buffer, so it plays
// the page here: the recorder, installed before the page loads, keeps the requests that came after it filled.
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { installResponseRecorder, lastResponseEnd, recordedResponses, recordedUrls } from './resource-timing';

/** Node's `performance.markResourceTiming`: how its own fetch adds an entry (`perf_hooks`). */
type MarkResourceTiming = (
  timingInfo: Record<string, unknown>,
  requestedUrl: string,
  initiatorType: string,
  global: unknown,
  cacheMode: string,
  bodyInfo: Record<string, unknown>,
  responseStatus: number,
  deliveryType: string,
) => void;

const ORIGIN = 'http://a.localhost:8040';
/** The buffer's size in Chrome and in Node unless a page changes it. */
const BUFFER_SIZE = 250;

/** One finished request of the page: it started at `start` and its response ended at `end` (page clock, ms). */
function request(path: string, initiatorType: string, start: number, end: number): void {
  const mark = (performance as unknown as { markResourceTiming: MarkResourceTiming }).markResourceTiming;
  const timing = {
    startTime: start,
    endTime: end,
    finalServiceWorkerStartTime: 0,
    redirectStartTime: 0,
    redirectEndTime: 0,
    postRedirectStartTime: 0,
    finalConnectionTimingInfo: null,
    encodedBodySize: 0,
    decodedBodySize: 0,
    finalNetworkRequestStartTime: start,
    finalNetworkResponseStartTime: end,
  };
  mark.call(performance, timing, `${ORIGIN}${path}`, initiatorType, globalThis, '', {}, 200, '');
}

/** What Vite's dev server makes the page load before anyone clicks: more modules than the buffer holds. */
function loadViteModules(count = BUFFER_SIZE + 50): void {
  for (let i = 0; i < count; i += 1) request(`/static/spa/@fs/module-${i}.js`, 'script', 1, 2);
}

/**
 * A clean page: no recorder, an empty buffer. Node finishes a full buffer's `resourcetimingbufferfull` on the next
 * `setImmediate`, and until then it puts every new entry aside: that tick comes first.
 */
async function freshPage(): Promise<void> {
  await new Promise((resolve) => setImmediate(resolve));
  performance.clearResourceTimings();
  const g = globalThis as unknown as { __e2eResponses?: { observer: PerformanceObserver } };
  g.__e2eResponses?.observer.disconnect();
  delete g.__e2eResponses;
}

beforeEach(freshPage);
afterEach(freshPage);

describe('installResponseRecorder + recordedResponses (in the page)', () => {
  it('keeps a request that ended after the modules filled the resource timing buffer', () => {
    installResponseRecorder();
    loadViteModules();
    request('/api/demo/items/delete', 'fetch', 100, 120);

    // The way the specs read it until now: the buffer is full and the request is not in it.
    const buffered = performance.getEntriesByType('resource');
    expect(buffered).toHaveLength(BUFFER_SIZE);
    expect(buffered.some((e) => e.name.endsWith('/api/demo/items/delete'))).toBe(false);

    const end = lastResponseEnd(recordedResponses(), '/api/demo/items/delete');
    expect(end).toEqual({ pageMs: 120, epochMs: performance.timeOrigin + 120 });
  });

  it('keeps every resource the page loads, module loads included', () => {
    installResponseRecorder();
    loadViteModules(2);
    request('/api/demo/items?limit=100', 'fetch', 5, 9);
    request('/api/demo/items/upload', 'xmlhttprequest', 10, 14);

    expect(recordedResponses()?.entries.map((e) => [e.url, e.initiatorType])).toEqual([
      [`${ORIGIN}/static/spa/@fs/module-0.js`, 'script'],
      [`${ORIGIN}/static/spa/@fs/module-1.js`, 'script'],
      [`${ORIGIN}/api/demo/items?limit=100`, 'fetch'],
      [`${ORIGIN}/api/demo/items/upload`, 'xmlhttprequest'],
    ]);
  });

  it('is still there on a second read', () => {
    installResponseRecorder();
    request('/api/demo/items/add_line', 'fetch', 10, 30);

    expect(lastResponseEnd(recordedResponses(), '/api/demo/items/add_line').pageMs).toBe(30);
    expect(lastResponseEnd(recordedResponses(), '/api/demo/items/add_line').pageMs).toBe(30);
  });

  it('reads nothing on a page where it was not installed', () => {
    request('/api/demo/items/delete', 'fetch', 100, 120);

    expect(recordedResponses()).toBeNull();
  });
});

describe('lastResponseEnd', () => {
  const recorded = (...entries: { path: string; startTime: number; responseEnd: number; initiatorType?: string }[]) => ({
    timeOrigin: 1_000_000,
    entries: entries.map(({ path, initiatorType = 'fetch', ...times }) => ({ url: `${ORIGIN}${path}`, initiatorType, ...times })),
  });

  it('takes the last request to the path, on both clocks', () => {
    const end = lastResponseEnd(
      recorded(
        { path: '/api/demo/items/add_line', startTime: 10, responseEnd: 50 },
        { path: '/api/demo/items/add_line', startTime: 60, responseEnd: 90 },
      ),
      '/api/demo/items/add_line',
    );

    expect(end).toEqual({ pageMs: 90, epochMs: 1_000_090 });
  });

  it('matches the whole path', () => {
    const entries = recorded(
      { path: '/api/demo/items/delete', startTime: 10, responseEnd: 20 },
      { path: '/api/demo/items/delete_line', startTime: 30, responseEnd: 40 },
      { path: '/api/demo/items', startTime: 50, responseEnd: 60 },
    );

    expect(lastResponseEnd(entries, '/api/demo/items/delete').pageMs).toBe(20);
    expect(lastResponseEnd(entries, '/api/demo/items').pageMs).toBe(60);
  });

  it('counts the query: a GET with one is not the POST to the bare path', () => {
    const entries = recorded(
      { path: '/api/demo/items', startTime: 10, responseEnd: 20 },
      { path: '/api/demo/items?limit=100', startTime: 30, responseEnd: 40 },
    );

    expect(lastResponseEnd(entries, '/api/demo/items').pageMs).toBe(20);
    expect(lastResponseEnd(entries, '/api/demo/items?limit=100').pageMs).toBe(40);
  });

  it('counts only fetch and XHR requests, not a module at that path', () => {
    const fetched = { path: '/api/demo/items/add_line', startTime: 10, responseEnd: 20 };
    const module = { path: '/api/demo/items/add_line', startTime: 30, responseEnd: 40, initiatorType: 'script' };
    const xhr = { path: '/api/demo/items/add_line', startTime: 50, responseEnd: 60, initiatorType: 'xmlhttprequest' };

    expect(lastResponseEnd(recorded(fetched, module), '/api/demo/items/add_line').pageMs).toBe(20);
    expect(lastResponseEnd(recorded(fetched, module, xhr), '/api/demo/items/add_line').pageMs).toBe(60);
  });

  it('with `since`, only a request that started at or after it', () => {
    const entries = recorded(
      { path: '/api/demo/items/add_line', startTime: 10, responseEnd: 50 },
      { path: '/api/demo/items/add_line', startTime: 200, responseEnd: 260 },
    );

    expect(lastResponseEnd(entries, '/api/demo/items/add_line', { since: 100 }).pageMs).toBe(260);
    expect(() => lastResponseEnd(entries, '/api/demo/items/add_line', { since: 300 })).toThrow(/\/api\/demo\/items\/add_line/);
  });

  it('fails, naming the path and the page, when no request to it ended (never a NaN or a null)', () => {
    const entries = recorded(
      { path: '/api/demo/items', startTime: 10, responseEnd: 20 },
      { path: '/api/demo/items/delete', startTime: 30, responseEnd: 0 },
    );

    expect(() => lastResponseEnd(entries, '/api/demo/items/delete', { where: `${ORIGIN}/demo/items` })).toThrow(
      /\/api\/demo\/items\/delete.*http:\/\/a\.localhost:8040\/demo\/items/,
    );
  });

  it('fails, naming the missing recorder, on a page without it', () => {
    expect(() => lastResponseEnd(null, '/api/demo/items/delete')).toThrow(/recordResponses/);
  });
});

describe('recordedUrls', () => {
  it('lists every resource, also the ones loaded after the modules filled the buffer', () => {
    installResponseRecorder();
    loadViteModules();
    request('/static/spa/@fs/outfitkit/index.js', 'script', 100, 110);

    // The way no-outfitkit read it until now: past the buffer, the module is not there.
    expect(performance.getEntriesByType('resource').some((e) => e.name.includes('outfitkit'))).toBe(false);

    const urls = recordedUrls(recordedResponses());
    expect(urls).toHaveLength(BUFFER_SIZE + 51);
    expect(urls.at(-1)).toBe(`${ORIGIN}/static/spa/@fs/outfitkit/index.js`);
  });

  it('fails, naming the missing recorder and the page, on a page without it', () => {
    expect(() => recordedUrls(null, { where: `${ORIGIN}/demo/items` })).toThrow(/http:\/\/a\.localhost:8040\/demo\/items.*recordResponses/);
  });
});
