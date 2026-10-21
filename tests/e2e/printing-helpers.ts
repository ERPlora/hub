// Helpers of the printing specs (apps/printing/WORKBOOK.md): the screenshots of a flow in the three sizes the
// migration asks for (`APP-PRINTING-<KEY>-390`, `-834`, `-1440` in `.artifacts/`), the device's side of the
// queue by the API (claim, then confirm or fail: what `/ws/print` will do for the app of the device) and letting
// go of the devices a spec printed from (PRINTING-F18: the owner's claim sets the device up).
import { type BrowserContext, expect, type Page } from '@playwright/test';

import { A, api, psql, shot } from './helpers';

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
    // The table refits to its box and a sheet slides to its new size: a frame, then every animation that
    // ends (a spinner never does), not a fixed wait.
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.evaluate(() =>
      Promise.all(
        document
          .getAnimations()
          .filter((animation) => Number.isFinite(Number(animation.effect?.getComputedTiming().endTime)))
          .map((animation) => animation.finished.catch(() => undefined)),
      ),
    );
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

/**
 * Lets go of the devices a spec printed from (PRINTING-F18): the printers named `like` leave every device, and
 * the devices it used — by their own `ids` (the hub keeps their SHA-256, never the id) or by `names` (`like`
 * patterns) — go, their jobs' mark first. Run after the spec's jobs are deleted and before its printers are: a
 * device names the printers it reaches.
 */
export function forgetDevices(like: string, { ids = [], names = [] }: { ids?: readonly string[]; names?: readonly string[] } = {}): void {
  psql(`delete from printing_printdevice_printers where printer_id in (select id from printing_printer where name like '${like}')`);
  const which = [...ids.map((id) => `key = encode(sha256('${id}'::bytea), 'hex')`), ...names.map((name) => `name like '${name}'`)];
  if (which.length === 0) return;
  const where = which.join(' or ');
  psql(`update printing_printjob set print_device_id = null where print_device_id in (select id from printing_printdevice where ${where})`);
  psql(`delete from printing_printdevice_printers where printdevice_id in (select id from printing_printdevice where ${where})`);
  psql(`delete from printing_printdevice where ${where}`);
}
