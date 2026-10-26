// flow: WHATSAPP_INBOX-F13
// A plan that includes no WhatsApp messages, through the run's REAL erplora.com, in a hidden Chrome (only Meta is
// played: whatsapp-helpers.ts, «The run's real erplora.com»). erplora.com's own test seed gives `a` its number; then
// `a`'s plan in erplora.com includes 0 WhatsApp messages a month (0 = none, ADR-0474: there is no «unlimited») and
// erplora.com pushes its photo here. The inbox says so above the list with «Upgrade plan» (erplora.com's plans), a
// customer's message still arrives through erplora.com (the cap only limits what is sent), the open conversation's
// «Send» says why instead of sending, and Settings → This month says the plan includes none, never «No limit».
// Captured in three sizes (FIX-HUB-WHATSAPP-INBOX-ZERO-LIMIT-SHOWN-UNLIMITED-390|834|1440, and -settings-…). The
// plan's figure goes back after the file; what it creates is named `e2e.…` and deleted.
// Then the month spent: erplora.com's seed sets `a`'s usage this month to its plan's allowance (`--used`), and pushes
// it. Settings → This month says it, the inbox too, a customer's message still arrives, and the next send is refused
// as `cap_reached` — by the Hub when it knows it, by erplora.com when the Hub's figure is behind — before Meta: the
// run's Graph never receives it and erplora.com's count stays at the allowance
// (FIX-HUB-WHATSAPP-INBOX-E2E-SEED-TEMPLATES-AND-CAP-UNUSED-F13-…). The month goes back to 0 after the file.
import { execFileSync } from 'node:child_process';
import { join, resolve } from 'node:path';

import { expect, type Page, test } from '@playwright/test';

import { A, api, login, psql, REPO_DIR, SAAS, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { STACK } from './stack';
import { messageSends } from './whatsapp-graph';
import {
  cleanUp,
  e2ePhone,
  erploraUsage,
  metaGraph,
  metaHandsOver,
  metaNow,
  notice,
  PREFIX,
  pushChannel,
  restorePhoto,
  seedErplora,
} from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'FIX-HUB-WHATSAPP-INBOX-ZERO-LIMIT-SHOWN-UNLIMITED';
const SPENT = 'FIX-HUB-WHATSAPP-INBOX-E2E-SEED-TEMPLATES-AND-CAP-UNUSED';
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

const notIncluded = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-cap-reached]');
const panel = (page: Page) => shown(page).locator('[data-testid=whatsapp-inbox-detail]');

/** A text of the customer `phone`, as Meta posts it to erplora.com. */
const said = (phone: string, name: string, body: string) =>
  notice('messages', {
    contacts: [{ profile: { name }, wa_id: phone.slice(1) }],
    messages: [{ from: phone.slice(1), id: `${PREFIX}wamid.${Date.now()}.in`, timestamp: metaNow(), type: 'text', text: { body } }],
  });

test.describe('a plan without WhatsApp messages', () => {
  let before: number | undefined;

  test.beforeAll(async () => {
    expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
    // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
    await metaGraph();
    cleanUp();
    const set = setPlan(0);
    expect(set.delivered).toBe(true);
    before = set.before;
  });

  test.afterAll(() => {
    if (before !== undefined) expect(setPlan(before).delivered).toBe(true);
    cleanUp();
    // After erplora.com's plan goes back (its push): `a`'s photo as before the seed.
    restorePhoto();
  });

  test('WHATSAPP_INBOX-F13: with a plan without WhatsApp messages the inbox says so, a message still arrives and «Send» explains it', async ({
    page,
  }) => {
    await login(page, A, '/whatsapp_inbox/inbox');
    await expect(notIncluded(page)).toContainText('Your plan does not include WhatsApp messages.');
    await expect(notIncluded(page)).not.toContainText('next month');
    const upgrade = shown(page).locator('[data-testid=whatsapp-inbox-upgrade]');
    await expect(upgrade).toHaveText('Upgrade plan');
    await expect(upgrade).toHaveAttribute('href', `${SAAS}/dashboard/store/plans`);
    await expect(upgrade).toHaveAttribute('target', '_blank');

    // What the customer writes arrives through erplora.com as always: the cap only limits what is sent.
    const phone = e2ePhone();
    await metaHandsOver(page.request, said(phone, 'e2e. Lucía', '¿Tenéis hora el viernes?'));
    const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.click();

    const blocked = panel(page).locator('[data-testid=whatsapp-inbox-composer-blocked]');
    await expect(blocked).toContainText('Your plan does not include WhatsApp messages: nothing can be sent.');
    await expect(blocked).toHaveAttribute('data-code', 'cap_reached');
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-upgrade]')).toHaveAttribute('href', `${SAAS}/dashboard/store/plans`);

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
    await expect(shown(page).locator('[data-testid=whatsapp-inbox-settings-upgrade]')).toHaveAttribute('href', `${SAAS}/dashboard/store/plans`);
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await month.scrollIntoViewIfNeeded();
      await settled(page);
      await noHorizontalScroll(page, `settings ${viewport.label}`);
      await page.screenshot({ path: shot(`${TASK}-settings-${viewport.label}`) });
    }
  });
});

test.describe('the month spent', () => {
  let allowance = 0;

  test.beforeAll(async () => {
    cleanUp();
    expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
    // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
    await metaGraph();
    // The allowance of `a`'s plan, as erplora.com's photo brought it: this month it is spent whole.
    allowance = Number(psql("select monthly_limit from whatsapp_inbox_channel where host = 'a'"));
    expect(allowance, 'a plan with WhatsApp messages').toBeGreaterThan(0);
    expect(seedErplora({ used: allowance })).toEqual({ delivered: true, hub_error: '' });
  });

  test.afterAll(() => {
    cleanUp();
    // The month back to 0, the photo pushed again: the next spec sends as always.
    expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
    // After that push: `a`'s photo as before the seed.
    restorePhoto();
  });

  /** The conversation open at `phone`'s, once her message has arrived through erplora.com; its id. */
  async function arrived(page: Page, phone: string, name: string, body: string): Promise<string> {
    await login(page, A, '/whatsapp_inbox/inbox');
    await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(phone.slice(3));
    // What the customer writes arrives through erplora.com as always: the cap only limits what is sent.
    await metaHandsOver(page.request, said(phone, name, body));
    const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) });
    await expect(row).toBeVisible({ timeout: 30_000 });
    await row.click();
    return psql(`select id from whatsapp_inbox_conversation where phone = '${phone}'`);
  }

  /** What the Hub sent from `phone`'s conversation: its status and code, one line each. */
  const sentFrom = (phone: string) =>
    psql(
      `select coalesce(string_agg(m.status || '|' || m.error_code, ','), '') from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone}' and m.origin = 'hub'`,
    );

  test('WHATSAPP_INBOX-F13: Settings → This month says the plan’s messages are spent, with «Upgrade plan»', async ({ page }) => {
    await login(page, A, '/whatsapp_inbox/settings');
    const month = shown(page).locator('[data-testid=whatsapp-inbox-settings-month]');
    await expect(month).toContainText(`${allowance} of ${allowance} messages sent`);
    await expect(month).toContainText('You have used all the messages of your plan this month.');
    await expect(month).not.toContainText('Your plan does not include WhatsApp messages.');
    const upgrade = shown(page).locator('[data-testid=whatsapp-inbox-settings-upgrade]');
    await expect(upgrade).toHaveText('Upgrade plan');
    await expect(upgrade).toHaveAttribute('href', `${SAAS}/dashboard/store/plans`);
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await month.scrollIntoViewIfNeeded();
      await expect(month).toBeInViewport();
      await settled(page);
      await noHorizontalScroll(page, `settings ${viewport.label}`);
      await page.screenshot({ path: shot(`${SPENT}-F13-settings-${viewport.label}`) });
    }
  });

  test('WHATSAPP_INBOX-F13: with the month spent a message still arrives and the send is refused before Meta', async ({ page, context }) => {
    const graph = await metaGraph();
    const asked = (await graph.seen()).calls.length;
    const phone = e2ePhone();
    const id = await arrived(page, phone, `${PREFIX}Nerea`, '¿Me cambiáis la cita?');
    await expect(notIncluded(page)).toContainText('You have used all the WhatsApp messages of your plan this month.');

    // «Send» explains it instead of sending.
    const blocked = panel(page).locator('[data-testid=whatsapp-inbox-composer-blocked]');
    await expect(blocked).toHaveAttribute('data-code', 'cap_reached');
    await expect(blocked).toContainText("This month's WhatsApp messages of your plan are spent: nothing can be sent until next month.");
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-send]')).toHaveJSProperty('disabled', true);
    await expect(panel(page).locator('[data-testid=whatsapp-inbox-composer-template]')).toHaveJSProperty('disabled', true);
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await blocked.scrollIntoViewIfNeeded();
      await expect(blocked).toBeInViewport();
      await settled(page);
      await noHorizontalScroll(page, `inbox ${viewport.label}`);
      await page.screenshot({ path: shot(`${SPENT}-F13-${viewport.label}`) });
    }
    await page.setViewportSize({ width: 1280, height: 860 });

    // The same send through the API is refused by the Hub, which keeps nothing and hands nothing to erplora.com.
    const refused = await api<{ error: { code: string } }>(context, A, 'POST', '/whatsapp_inbox/messages/send', {
      id,
      text: 'Sí, ¿te va el lunes?',
      client_message_id: crypto.randomUUID(),
    });
    expect(refused.status).toBe(409);
    expect(refused.data.error.code).toBe('whatsapp_inbox.cap_reached');
    expect(sentFrom(phone)).toBe('');
    expect(messageSends((await graph.seen()).calls.slice(asked))).toEqual([]);
    expect(erploraUsage()).toBe(allowance);
  });

  test('WHATSAPP_INBOX-F13: when the Hub’s figure is behind, erplora.com refuses the send for the cap before Meta and the bubble says why', async ({
    page,
  }) => {
    const graph = await metaGraph();
    const phone = e2ePhone();
    // The Hub still counts none sent this month (its figure behind erplora.com's, which is at the allowance).
    pushChannel({ status: 'connected', monthly_limit: allowance, monthly_usage: 0 });
    await arrived(page, phone, `${PREFIX}Olga`, '¿Abrís el domingo?');
    await expect(notIncluded(page)).toBeHidden();
    const asked = (await graph.seen()).calls.length;

    await panel(page).locator('[data-testid=whatsapp-inbox-composer-text] textarea').fill('No, el domingo cerramos.');
    await panel(page).locator('[data-testid=whatsapp-inbox-composer-send]').click();
    const reply = panel(page).locator('[data-testid=whatsapp-inbox-message][data-side=outbound]', { hasText: 'el domingo cerramos' });
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-status]')).toContainText('Not delivered', { timeout: 30_000 });
    // Said in the Hub's words: the cap is the plan's, never «Meta's reason».
    const why = reply.locator('[data-testid=whatsapp-inbox-message-error]');
    await expect(why).toHaveAttribute('data-code', 'whatsapp_inbox.cap_reached');
    await expect(why).toHaveText("This month's WhatsApp messages of your plan are spent: nothing can be sent until next month.");
    await expect(reply.locator('[data-testid=whatsapp-inbox-message-retry]')).toHaveCount(0);
    expect(sentFrom(phone)).toBe('failed|whatsapp_inbox.cap_reached');
    // Refused before Meta: the run's Graph never received it, and erplora.com counted nothing more.
    expect(messageSends((await graph.seen()).calls.slice(asked))).toEqual([]);
    expect(erploraUsage()).toBe(allowance);
    for (const viewport of FLOW_VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await reply.scrollIntoViewIfNeeded();
      await expect(reply).toBeInViewport();
      await settled(page);
      await noHorizontalScroll(page, `refused ${viewport.label}`);
      await page.screenshot({ path: shot(`${SPENT}-F13-refused-${viewport.label}`) });
    }
  });
});
