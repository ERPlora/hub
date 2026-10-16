// What the page loaded and when its requests ended, on the page's own clock (Resource Timing): for the specs that
// time a click against the server's answer, or check which modules a screen loaded. `recordResponses(page)` before
// the page loads; after, `responseEnd(page, path)` or `resourceUrls(page)`. Nothing else in the e2e reads the
// resource buffer (`resource-timing-reads.test.ts`).
import type { BrowserContext, Page } from '@playwright/test';

/** A resource of the page whose response ended (a module, a fetch…). Times on the page's clock (`performance.now()`), ms. */
export interface RecordedResponse {
  url: string;
  initiatorType: string;
  startTime: number;
  responseEnd: number;
}

/** What the recorder kept on a page: its resources and the page's `performance.timeOrigin`. */
export interface RecordedResponses {
  timeOrigin: number;
  entries: RecordedResponse[];
}

/** When the response ended: on the page's clock and as ms since 1970 (comparable with `Date.now()` in any tab). */
export interface ResponseEnd {
  pageMs: number;
  epochMs: number;
}

/** The recorder a page keeps on `globalThis.__e2eResponses`. */
interface Recorder {
  observer: PerformanceObserver;
  entries: RecordedResponse[];
  keep: (list: PerformanceEntryList) => void;
}

/**
 * In the page, before any of its scripts (`addInitScript`): keeps every resource whose response ends. A
 * `PerformanceObserver` sees every entry; `performance.getEntriesByType('resource')` stops at the buffer (250 entries
 * in Chrome), which the dev stack's Vite modules fill before the first click. Self-contained: Playwright sends its
 * source to the page.
 */
export function installResponseRecorder(): void {
  const entries: RecordedResponse[] = [];
  const keep = (list: PerformanceEntryList): void => {
    for (const entry of list as PerformanceResourceTiming[]) {
      entries.push({
        url: entry.name,
        initiatorType: entry.initiatorType,
        startTime: entry.startTime,
        responseEnd: entry.responseEnd,
      });
    }
  };
  const observer = new PerformanceObserver((list) => keep(list.getEntries()));
  observer.observe({ type: 'resource', buffered: true });
  const recorder: Recorder = { observer, entries, keep };
  (globalThis as unknown as { __e2eResponses: Recorder }).__e2eResponses = recorder;
}

/**
 * In the page: what the recorder kept, `null` where it was not installed. The entries its observer has not been
 * handed yet (its callback runs later, in a task) are taken first. Self-contained, like the recorder.
 */
export function recordedResponses(): RecordedResponses | null {
  const recorder = (globalThis as unknown as { __e2eResponses?: Recorder }).__e2eResponses;
  if (!recorder) return null;
  recorder.keep(recorder.observer.takeRecords());
  return { timeOrigin: performance.timeOrigin, entries: [...recorder.entries] };
}

const noRecorder = (call: string, where: string): Error =>
  new Error(`${call}: ${where} has no response recorder; call recordResponses(page) before it loads`);

/** A request of the page: a fetch or an XHR (not a module, a stylesheet or an image). */
const isRequest = (e: RecordedResponse): boolean => e.initiatorType === 'fetch' || e.initiatorType === 'xmlhttprequest';

/** The URL's path with its query: `/api/demo/items` (the POST) is not `/api/demo/items?limit=100` (a GET). */
const pathOf = (url: string): string => {
  const { pathname, search } = new URL(url);
  return pathname + search;
};

/**
 * When the last fetch or XHR request to `path` (path and query, exactly) ended; with `since` (page clock, ms), only
 * one that started at or after it. Never `NaN` nor `null`: without that request, or without the recorder, it throws
 * saying which path, on which page (`where`) and what was missing.
 */
export function lastResponseEnd(
  recorded: RecordedResponses | null,
  path: string,
  options: { since?: number; where?: string } = {},
): ResponseEnd {
  const where = options.where ?? 'the page';
  if (recorded === null) throw noRecorder(`responseEnd(${path})`, where);
  const since = options.since ?? Number.NEGATIVE_INFINITY;
  const requests = recorded.entries.filter(isRequest);
  const ended = requests.filter(
    (e) => pathOf(e.url) === path && e.startTime >= since && Number.isFinite(e.responseEnd) && e.responseEnd > 0,
  );
  const last = ended.at(-1);
  if (!last) {
    const after = options.since === undefined ? '' : ` that started at or after ${options.since} ms`;
    throw new Error(
      `responseEnd(${path}): no request to ${path}${after} ended on ${where} ` +
        `(${requests.length} fetch/XHR responses recorded there)`,
    );
  }
  return { pageMs: last.responseEnd, epochMs: recorded.timeOrigin + last.responseEnd };
}

/** Every resource the page loaded since it loaded, in order; without the recorder it throws, naming the page. */
export function recordedUrls(recorded: RecordedResponses | null, options: { where?: string } = {}): string[] {
  if (recorded === null) throw noRecorder('resourceUrls', options.where ?? 'the page');
  return recorded.entries.map((e) => e.url);
}

/** Installs the recorder in every page `target` loads from now on (a page: each of its navigations). */
export async function recordResponses(target: Page | BrowserContext): Promise<void> {
  await target.addInitScript(installResponseRecorder);
}

/** When the last request of `page` to `path` ended (`lastResponseEnd`), read in the page. */
export async function responseEnd(page: Page, path: string, options: { since?: number } = {}): Promise<ResponseEnd> {
  return lastResponseEnd(await page.evaluate(recordedResponses), path, { ...options, where: page.url() });
}

/** Every resource `page` loaded since its last navigation (`recordedUrls`), read in the page. */
export async function resourceUrls(page: Page): Promise<string[]> {
  return recordedUrls(await page.evaluate(recordedResponses), { where: page.url() });
}
