// flow: BILLING-G54 (the SaaS's BILLING-F16, «Impago del plan: reintentos, suspensión y vuelta»)
// A business whose plan stays unpaid past its grace is suspended by the SaaS, which says so in the photo it pushes
// (`state.status = "suspended"`). The Hub then answers 402 on every page and call of that host, with a session or
// without: a page that says why and takes the person to ERPlora (where the invoice is paid), the API the envelope
// `base.hub_suspended`. When the photo says it is paid again, the same session works as before. The photo is set
// here straight in this run's database (the SaaS's push is covered by its own tests and by `/internal`'s).
import { expect, test } from '@playwright/test';

import { api, B, collectProblems, hostPage, listReady, psql, SAAS, shot } from './helpers';

const SIZES = [
  { name: '390', width: 390, height: 844 },
  { name: '834', width: 834, height: 1112 },
  { name: '1440', width: 1440, height: 900 },
] as const;

const slug = new URL(B).hostname.split('.')[0];

function photoStatus(): string {
  return psql(`SELECT coalesce(state->>'status', '') FROM base_hub WHERE slug = '${slug}'`);
}

function setPhotoStatus(status: string): void {
  const next = status
    ? `(state - 'status') || jsonb_build_object('status', '${status}')`
    : `state - 'status'`;
  psql(`UPDATE base_hub SET state = ${next} WHERE slug = '${slug}'`);
}

test('BILLING-G54: a business suspended for an unpaid invoice answers 402 until it is paid, page and API', async ({
  browser,
}) => {
  const before = photoStatus();
  const { context, page } = await hostPage(browser, B, { next: '/demo/items' });
  const problems = await collectProblems(page);
  try {
    await listReady(page);

    setPhotoStatus('suspended');
    for (const size of SIZES) {
      await page.setViewportSize({ width: size.width, height: size.height });
      const answer = await page.goto('/demo/items');
      expect(answer?.status()).toBe(402);
      await expect(page.getByRole('heading', { level: 1 })).toHaveText('This business is suspended');
      await expect(page.getByRole('link', { name: 'Go to ERPlora' })).toHaveAttribute('href', `${SAAS}/launch`);
      await page.screenshot({ path: shot(`APP-BILLING-1-BILLING-G54-hub-${size.name}`), fullPage: true });
    }

    const envelope = await api<{ error: { code: string } }>(context, B, 'GET', '/me');
    expect([envelope.status, envelope.data.error.code]).toEqual([402, 'base.hub_suspended']);

    // Without a session, and its login included: nobody opens it until it is paid.
    const stranger = await browser.newContext();
    try {
      const door = await stranger.newPage();
      expect((await door.goto(`${B}/auth/callback?code=x&state=y`))?.status()).toBe(402);
      expect((await door.goto(`${B}/`))?.status()).toBe(402);
    } finally {
      await stranger.close();
    }

    // Paid: the SaaS's next photo says active, and the same session works again.
    setPhotoStatus('active');
    await page.setViewportSize({ width: 1440, height: 900 });
    expect((await page.goto('/demo/items'))?.status()).toBe(200);
    await listReady(page);

    const found = await problems();
    expect(found.csp).toEqual([]);
    expect(found.page).toEqual([]);
    // The one console error allowed is the browser's own line about the 402 asked for on purpose.
    expect(found.console.filter((line) => !/status of 402/.test(line))).toEqual([]);
  } finally {
    setPhotoStatus(before);
    await context.close();
  }
});
