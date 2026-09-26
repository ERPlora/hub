// Regression test for ERPlora/hub#2217 — «Use these details for my ERPlora invoice too» fired on
// its own the moment it was switched on, with the STORED details instead of the ones just typed.
// A new business typing its tax id and switching it on before «Save changes» got «Could not share
// the details with ERPlora», the switch stayed on anyway, and on the next visit it was off again.
//
// It is now a box of the Business form: ticking it calls nothing, «Save changes» stores it with the
// rest in ONE `PUT /api/settings`, and it is still ticked after a reload. Real runtime, real shell,
// the three widths of the UI contract.
import { request as pwRequest } from '@playwright/test';
import { test, expect } from '../bench-boot';
import { loginByPin, withSession } from './shell-visual-helpers';
import { VIEWPORTS } from './viewports';

// ONE test on purpose: the bench shares a single runtime between tests, so a second test would
// find the box already ticked by the first. The flow runs once; the reload is checked at each width.
test('Settings › Business: tick the ERPlora-invoice box, save once, still ticked after a reload (hub#2217)', async ({
  page,
}) => {
  await page.setViewportSize(VIEWPORTS[0]);
  const session = await loginByPin();
  // The bench database outlives a run (`hub_e2e_web`, fixed hub id): start from an unticked box
  // instead of assuming a hub nobody has saved before.
  const api = await pwRequest.newContext();
  const reset = await api.put(`${process.env.HUB_RUNTIME_URL}/api/settings`, {
    headers: { 'x-hub-session': session.token },
    data: { business_identity_for_erplora_billing: false },
  });
  expect(reset.ok(), `could not reset the box: ${reset.status()} ${await reset.text()}`).toBeTruthy();
  await api.dispose();
  await withSession(page, session);

  const calls: { method: string; url: string; body: string | null }[] = [];
  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/business/fiscal-identity') || (url.includes('/api/settings') && req.method() === 'PUT'))
      calls.push({ method: req.method(), url, body: req.postData() });
  });

  await page.goto('/settings#business');
  const box = page.getByTestId('settings-share-with-erplora');
  await expect(box).toBeVisible();
  await expect(box, 'the box shows the stored (unticked) value').toHaveJSProperty('checked', false);

  await page.getByTestId('settings-business-tax-id').locator('input').fill('B12345674');
  await page.getByTestId('settings-business-legal-name').locator('input').fill('Bar Manolo SL');
  await box.click();
  await expect(box).toHaveJSProperty('checked', true);

  // Ticking is not saving, and it is not sharing either.
  await page.waitForTimeout(300);
  expect(calls, 'ticking the box must not call anything').toEqual([]);

  const saved = page.waitForResponse((res) => res.url().includes('/api/settings') && res.request().method() === 'PUT');
  await page.getByTestId('settings-save-business').click();
  expect((await saved).status()).toBe(200);

  expect(calls, 'one save, and nothing else').toHaveLength(1);
  expect(JSON.parse(calls[0].body ?? '{}')).toMatchObject({
    business_tax_id: 'B12345674',
    business_legal_name: 'Bar Manolo SL',
    business_identity_for_erplora_billing: true,
  });
  await expect(page.getByText('Could not share the details with ERPlora')).toHaveCount(0);

  for (const viewport of VIEWPORTS) {
    await page.setViewportSize(viewport);
    await page.reload();
    await expect(
      page.getByTestId('settings-share-with-erplora'),
      `still ticked at ${viewport.width}px`,
    ).toHaveJSProperty('checked', true);
    if (process.env.HUB2217_SHOTS)
      await page.screenshot({ path: `${process.env.HUB2217_SHOTS}/billing-box-${viewport.width}.png`, fullPage: true });
  }
});
