// Helpers of the printing specs (apps/printing/WORKBOOK.md): the screenshots of a flow in the three sizes the
// migration asks for (`APP-PRINTING-<KEY>-390`, `-834`, `-1440` in `.artifacts/`) and the device's side of the
// queue by the API (claim, then confirm or fail: what `/ws/print` will do for the app of the device).
import { type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, shot } from './helpers';

/** Phone, tablet and desktop: 390×844, 834×1112 and 1440×900. */
export const FLOW_VIEWPORTS = [
  { label: '390', width: 390, height: 844 },
  { label: '834', width: 834, height: 1112 },
  { label: '1440', width: 1440, height: 900 },
] as const;

/** Screenshots of `key` (a flow, `PRINTING-F01`) in the three sizes, each once `ready` says the page is painted. */
export async function flowShots(page: Page, key: string, ready: (page: Page) => Promise<void>, restore = { width: 1280, height: 860 }): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    // The table refits to its box: a frame, not a fixed wait.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.screenshot({ path: shot(`APP-PRINTING-${key}-${viewport.label}`) });
  }
  await page.setViewportSize(restore);
}

interface Claimed {
  job: { id: string; attempts: number } | null;
}

/** The device's side: takes the next job of `printerId` as `device`; `null` when nothing waits. */
export async function claim(context: BrowserContext, printerId: string, device = 'e2e device'): Promise<{ id: string; attempts: number } | null> {
  const res = await api<Claimed>(context, A, 'POST', '/printing/jobs/claim', { printers: [printerId], device });
  expect(res.status, JSON.stringify(res.data)).toBe(200);
  return res.data.job;
}

/** The device says the job did not come out, with `error`. */
export async function fail(context: BrowserContext, job: { id: string; attempts: number }, error: string, device = 'e2e device'): Promise<void> {
  const res = await api(context, A, 'POST', '/printing/jobs/fail', { job_id: job.id, error, device, attempt: job.attempts });
  expect(res.status, JSON.stringify(res.data)).toBe(200);
}
