// «Book appointments» (apps/whatsapp_inbox/WORKBOOK.md WHATSAPP_INBOX-F14), turned on from WhatsApp's settings, and
// the WhatsApp of a customer who asks for an appointment answered by the assistant «Ask me first» (F21), end to end
// with its real dependencies: the Hub of this stack, its SaaS's gateway (`/internal/assistant/chat`) and, behind it,
// the e2e's provider (assistant-provider.ts, an OpenAI-compatible server on 127.0.0.1 that this spec starts): no
// mock between the Hub and the provider. The SaaS must be seeded with that provider (README «El asistente»).
// The owner turns the card on (its answer and its notice, in Automations' gallery too: FLOW-F33); the customer's
// message comes in as erplora.com pushes it; the worker's relay hands its event to Automations, whose run reads it,
// thanks her, makes her card and asks the assistant with only what the answer was granted; the booking it wants waits
// in «Waiting for your answer» with whom it is for. «Turn off» pauses both, never deleting them (F17).
// flow: WHATSAPP_INBOX-F14 WHATSAPP_INBOX-F17 WHATSAPP_INBOX-F21 FLOW-F33
import { execFile, execSync } from 'node:child_process';
import { promisify } from 'node:util';

import { expect, test } from '@playwright/test';

import { type Provider, startProvider } from './assistant-provider';
import { capture, HUB_DIR, psql, REPO_DIR, shown } from './helpers';
import { confirmDialog, parkedEvent, RELAY, signedIn } from './flow-helpers';
import { noHorizontalScroll, settled, VIEWPORTS } from './schedule-helpers';
import { STACK } from './stack';
import { cleanUp as inboxCleanUp, e2ePhone, pushChannel, receive } from './whatsapp-helpers';

const TASK = 'FIX-HUB-WHATSAPP-INBOX-RECIPES-USE-ASSISTANT-STEP';
const ANSWER = 'whatsapp_inbox/appointment_from_whatsapp';
const NOTICE = 'whatsapp_inbox/appointment_confirmed';
const THANKS = 'Thanks for writing! Let me check the diary and I will come straight back to you.';
const PROVIDER_PORT = Number(process.env.E2E_AI_PROVIDER_PORT ?? STACK.hubPort + 2);
const SAAS_DB = process.env.E2E_SAAS_DB ?? (STACK.hubPort === 8000 ? 'saas' : `saas_e2e_${STACK.hubPort + 1}`);

let provider: Provider;

function saasSql(sql: string): string {
  return execSync(`docker compose exec -T postgres psql -U hub -d ${SAAS_DB} -At -c "${sql}"`, { cwd: REPO_DIR, encoding: 'utf8' }).trim();
}

/** The inbox's answers and notices (with their runs and questions), the cards their runs made, the conversations and
 *  channel of the inbox's specs, and the month's messages of the business `a`: each size starts with the card off. */
function cleanUp(): void {
  const flows = "select id from flow_flow where recipe like 'whatsapp_inbox/%'";
  psql(
    [
      `delete from flow_question where flow_id in (${flows})`,
      `delete from flow_flowrun where flow_id in (${flows})`,
      `delete from flow_flow where id in (${flows})`,
    ].join('; '),
  );
  inboxCleanUp();
  psql("delete from customer_customer where source = 'whatsapp' and phone like '%69900%'");
  saasSql("delete from assistant_assistantusage where hub_id = (select id from hubs_hub where slug = 'a')");
}

const built = (ref: string): string =>
  psql(`select enabled::text || ' ' || (deleted_at is null)::text from flow_flow where recipe = '${ref}'`);

/** One tick of the worker's relay (this stack runs no worker): the outbox event `id` handed to Automations' reaction,
 *  and what it leaves for after its COMMIT made at once. It does not block this process: the provider the SaaS asks
 *  lives here, and must answer. */
async function relay(id: string): Promise<void> {
  await promisify(execFile)('uv', ['run', 'python', 'manage.py', 'shell', '-c', RELAY], {
    cwd: HUB_DIR,
    env: { ...process.env, FLOW_EVENT: id },
  });
}

test.beforeAll(async () => {
  provider = await startProvider(PROVIDER_PORT);
  const seeded = saasSql("select base_url from assistant_aiprovider where slug = 'e2e-local'");
  expect(seeded, `the SaaS ${SAAS_DB} is not seeded with this provider: README «El asistente»`).toBe(provider.url);
});

test.beforeEach(() => {
  cleanUp();
  pushChannel({ status: 'connected' });
});

test.afterAll(async () => {
  cleanUp();
  await provider?.close();
});

for (const viewport of VIEWPORTS) {
  test(`WHATSAPP_INBOX-F14 «Book appointments» turned on, and a WhatsApp asking for one waits for the owner's yes at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(180_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      // F14: the card says what it does; on, after a question, with its answer and its notice.
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]');
      await expect(card).toContainText('Book appointments');
      await expect(card).toContainText('Off');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-on]').click();
      await confirmDialog(page, 'Book appointments');
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-done]')).toHaveText(
        'Done. Write to yourself from another phone: “I want an appointment tomorrow”.',
      );
      await expect(card).toContainText('On');
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-confirm] ion-radio')).toHaveCount(2);
      expect(built(ANSWER)).toBe('true true');
      expect(built(NOTICE)).toBe('true true');
      // «Ask me first», and only Citas' free times, booking and moving among the assistant's tools: never cancelling.
      const step = JSON.parse(
        psql(`select steps from flow_flow where recipe = '${ANSWER}'`),
      ) as { kind: string; mode?: string; tools?: string[] }[];
      const assistant = step.find((each) => each.kind === 'assistant');
      expect(assistant?.mode).toBe('ask');
      expect(assistant?.tools).toEqual([
        'appointment.availability.slots',
        'appointment.appointment.create',
        'appointment.appointment.reschedule',
      ]);
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-off]').scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-settings-${viewport.label}`);

      // F21: she writes; the relay starts the answer, which thanks her, makes her card and asks the assistant.
      const phone = e2ePhone();
      const booking = { customer: phone, start: '2026-11-02T10:00:00+01:00', source: 'whatsapp' };
      const message = receive(phone, `E2E-ASK appointment__appointment__create ${JSON.stringify(booking)}`, 'E2E Lucía');
      const received = psql(
        `select id from live_outboxevent where name = 'whatsapp_inbox.message.received' and payload->>'id' = '${message.id}'`,
      );
      expect(received, 'whatsapp_inbox.message.received of the message in the outbox').not.toBe('');
      await relay(received);
      const flowId = psql(`select id from flow_flow where recipe = '${ANSWER}'`);
      const before = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').length;
      await relay(parkedEvent(flowId));

      // The assistant was offered only what the answer grants of the Hub's operations (`<app>__<entity>__<action>`;
      // the SaaS adds its own clock), and wanted to book: nothing is booked yet.
      const turns = provider.seen.filter((seen) => seen.path === '/v1/chat/completions').slice(before);
      expect(turns).toHaveLength(1);
      const tools = ((turns[0].body as { tools?: { function: { name: string } }[] }).tools ?? [])
        .map((tool) => tool.function.name)
        .filter((name) => name.includes('__'));
      expect(tools).toEqual([
        'appointment__availability__slots',
        'appointment__appointment__create',
        'appointment__appointment__reschedule',
      ]);
      expect(psql(`select status from flow_flowrun where flow_id = '${flowId}'`)).toBe('asking');
      expect(psql(`select count(*) from customer_customer where source = 'whatsapp' and phone like '%${phone.slice(-9)}'`)).toBe('1');
      expect(
        psql(`select body from whatsapp_inbox_message where conversation_id = '${message.conversation_id}' and direction = 'outbound'`),
      ).toBe(THANKS);

      // The owner finds the booking in «Waiting for your answer», with whom it is for.
      await page.goto('/flow/automations');
      const question = shown(page)
        .locator('[data-testid=flow-inbox] article')
        .filter({ hasText: 'The assistant wants to change something in «Appointments»' });
      await expect(question).toBeVisible();
      await expect(question).toContainText('From «WhatsApp → appointment booked»');
      await expect(question).toContainText(`Customer: ${phone}`);
      await question.scrollIntoViewIfNeeded();
      await noHorizontalScroll(page, viewport.label);
      await settled(page);
      await capture(page, `${TASK}-${viewport.label}`);

      // F17: off from the same card, both paused and kept.
      await page.goto('/whatsapp_inbox/settings');
      await shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments-off]').click();
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]')).toContainText('Off');
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments-on]')).toBeVisible();
      expect(built(ANSWER)).toBe('false true');
      expect(built(NOTICE)).toBe('false true');
    } finally {
      await context.close();
    }
  });
}
