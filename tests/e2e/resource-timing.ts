// When a request of the page ended, on the page's own clock (Resource Timing), for the specs that time a click
// against the server's answer. `recordResponses(page)` before the page loads, `responseEnd(page, path)` after.
import type { BrowserContext, Page } from '@playwright/test';

/** A fetch or XHR request of the page whose response ended. Times on the page's clock (`performance.now()`), ms. */
export interface RecordedResponse {
  path: string;
  initiatorType: string;
  startTime: number;
  responseEnd: number;
}

/** What the recorder kept on a page: its requests and the page's `performance.timeOrigin`. */
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
 * In the page, before any of its scripts (`addInitScript`): keeps every fetch and XHR request whose response
 * ends. A `PerformanceObserver` sees every entry; `performance.getEntriesByType('resource')` stops at the buffer
 * (250 entries in Chrome), which the dev stack's Vite modules fill before the first click. Self-contained: Playwright
 * sends its source to the page.
 */
export function installResponseRecorder(): void {
  const entries: RecordedResponse[] = [];
  const keep = (list: PerformanceEntryList): void => {
    for (const entry of list as PerformanceResourceTiming[]) {
      if (entry.initiatorType !== 'fetch' && entry.initiatorType !== 'xmlhttprequest') continue;
      entries.push({
        path: new URL(entry.name).pathname,
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

/**
 * When the last request to `path` (the URL's whole path, whatever its query) ended; with `since` (page clock, ms),
 * only one that started at or after it. Never `NaN` nor `null`: without that request, or without the recorder,
 * it throws saying which path, on which page (`where`) and what was missing.
 */
export function lastResponseEnd(
  recorded: RecordedResponses | null,
  path: string,
  options: { since?: number; where?: string } = {},
): ResponseEnd {
  const where = options.where ?? 'the page';
  if (recorded === null) {
    throw new Error(`responseEnd(${path}): ${where} has no response recorder; call recordResponses(page) before it loads`);
  }
  const since = options.since ?? Number.NEGATIVE_INFINITY;
  const ended = recorded.entries.filter(
    (e) => e.path === path && e.startTime >= since && Number.isFinite(e.responseEnd) && e.responseEnd > 0,
  );
  const last = ended.at(-1);
  if (!last) {
    const after = options.since === undefined ? '' : ` that started at or after ${options.since} ms`;
    throw new Error(
      `responseEnd(${path}): no request to ${path}${after} ended on ${where} ` +
        `(${recorded.entries.length} fetch/XHR responses recorded there)`,
    );
  }
  return { pageMs: last.responseEnd, epochMs: recorded.timeOrigin + last.responseEnd };
}

/** Installs the recorder in every page `target` loads from now on (a page: each of its navigations). */
export async function recordResponses(target: Page | BrowserContext): Promise<void> {
  await target.addInitScript(installResponseRecorder);
}

/** When the last request of `page` to `path` ended (`lastResponseEnd`), read in the page. */
export async function responseEnd(page: Page, path: string, options: { since?: number } = {}): Promise<ResponseEnd> {
  return lastResponseEnd(await page.evaluate(recordedResponses), path, { ...options, where: page.url() });
}
