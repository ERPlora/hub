// flow: WHATSAPP_INBOX-F13
// A plan that includes no WhatsApp messages, through the run's REAL erplora.com, in a hidden Chrome (only Meta is
// played: whatsapp-helpers.ts, «The run's real erplora.com»). erplora.com's own test seed gives `a` its number; then
// `a`'s plan in erplora.com includes 0 WhatsApp messages a month (0 = none, ADR-0474: there is no «unlimited») and
// erplora.com pushes its photo here. The inbox says so above the list with «Upgrade plan» (erplora.com's plans), a
// customer's message still arrives through erplora.com (the cap only limits what is sent), the open conversation's
// «Send» says why instead of sending, and Settings → This month says the plan includes none, never «No limit».
// Captured in three sizes (FIX-HUB-WHATSAPP-INBOX-ZERO-LIMIT-SHOWN-UNLIMITED-390|834|1440, and -settings-…). The
// plan's figure goes back after the file; what it creates is named `e2e.…` and deleted.
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';

import { expect, type Page, test } from '@playwright/test';

import { A, login, REPO_DIR, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';
import { cleanUp, e2ePhone, meta, metaNow, notice, PREFIX, seedErplora } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'FIX-HUB-WHATSAPP-INBOX-ZERO-LIMIT-SHOWN-UNLIMITED';
// The run's erplora.com checkout and database, as whatsapp-helpers.ts finds them.
const SAAS_DIR = resolve(process.env.E2E_SAAS_DIR || join(REPO_DIR, 'saas'));
const SAAS_DB = process.env.E2E_SAAS_DB || `saas_e2e_${new URL(SAAS).port || '80'}`;

// In erplora.com: the WhatsApp messages a month of `a`'s plan become WA_LIMIT, and its photo is pushed to this Hub.
const SET_PLAN = `
import json, os
from django.db import transaction
from django.utils import timezone
from hubs import queries, services
from hubs.models import Hub
hub = Hub.objects.get(slug="a")
plan = queries.effective_plan(hub.id, timezone.now())
before = plan.whatsapp_messages_per_month
plan.whatsapp_messages_per_month = int(os.environ["WA_LIMIT"])
plan.save(update_fields=["whatsapp_messages_per_month"])
with transaction.atomic():
    services.bump_state(hub.id)
print(json.dumps({"before": before, "delivered": services.sync_hub(hub.id)}))
`;

function setPlan(limit: number): { before: number; delivered: boolean } {
  const out = execFileSync('uv', ['run', 'python', 'manage.py', 'shell', '-c', SET_PLAN], {
    cwd: SAAS_DIR,
    encoding: 'utf8',
    env: {
      ...process.env,
      DEBUG: 'True',
      DB_NAME: SAAS_DB,
      HUB_INTERNAL_URL: `http://127.0.0.1:${STACK.hubPort}`,
      WA_LIMIT: String(limit),
    },
  });
  return JSON.parse(out.trim().split('\n').at(-1) ?? '{}');
}

let before: number | undefined;

test.beforeAll(() => {
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  cleanUp();
  const set = setPlan(0);
  expect(set.delivered).toBe(true);
  before = set.before;
});

test.afterAll(() => {
  if (before !== undefined) expect(setPlan(before).delivered).toBe(true);
  cleanUp();
});

const notIncluded = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]');
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');

test('WHATSAPP_INBOX-F13: with a plan without WhatsApp messages the inbox says so, a message still arrives and «Send» explains it', async ({
  page,
}) => {
  await login(page, A, '/whatsapp_inbox/inbox');
  await expect(notIncluded(page)).toContainText('Your plan does not include WhatsApp messages.');
  await expect(notIncluded(page)).not.toContainText('next month');
  const upgrade = shown(page).locator('[data-testid=whatsapp-inbox-upgrade]');
  await expect(upgrade).toHaveText('Upgrade plan');
  await expect(upgrade).toHaveAttribute('href', `${SAAS}/store/plans`);
  await expect(upgrade).toHaveAttribute('target', '_blank');

  // What the customer writes arrives through erplora.com as always: the cap only limits what is sent.
  const phone = e2ePhone();
  const said = notice('messages', {
    contacts: [{ profile: { name: 'e2e. Lucía' }, wa_id: phone.slice(1) }],
    messages: [{ from: phone.slice(1), id: `${PREFIX}wamid.${Date.now()}.in`, timestamp: metaNow(), type: 'text', text: { body: '¿Tenéis hora el viernes?' } }],
  });
  expect(await meta(page.request, said)).toBe(200);
  const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
  await expect(row).toBeVisible({ timeout: 30_000 });
  await row.click();

  const blocked = panel(page).locator('[data-testid=whatsapp-inbox-composer-blocked]');
  await expect(blocked).toContainText('Your plan does not include WhatsApp messages: nothing can be sent.');
  await expect(blocked).toHaveAttribute('data-code', 'cap_reached');
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
  await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-upgrade]')).toHaveAttribute('href', `${SAAS}/store/plans`);

  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    // The reason «Send» gives, in sight in every size (on a phone it is below the conversation's header).
    await blocked.scrollIntoViewIfNeeded();
    await expect(blocked).toBeInViewport();
    await settled(page);
    await noHorizontalScroll(page, `inbox ${viewport.label}`);
    await page.screenshot({ path: shot(`${TASK}-${viewport.label}`) });
  }
});

test('WHATSAPP_INBOX-F13: Settings → This month says the plan includes none, never «No limit»', async ({ page }) => {
  await login(page, A, '/whatsapp_inbox/settings');
  const month = shown(page).locator('[data-testid=whatsapp-inbox-settings-month]');
  await expect(month).toContainText('Your plan does not include WhatsApp messages.');
  await expect(month).not.toContainText('No limit');
  await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-upgrade]')).toHaveAttribute('href', `${SAAS}/store/plans`);
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await month.scrollIntoViewIfNeeded();
    await settled(page);
    await noHorizontalScroll(page, `settings ${viewport.label}`);
    await page.screenshot({ path: shot(`${TASK}-settings-${viewport.label}`) });
  }
});
