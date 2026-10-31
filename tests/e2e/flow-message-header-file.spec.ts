// flow: FLOW-F32 FLOW-F31
// «Put a photo, a video or a PDF at the top of a WhatsApp» (apps/flow/WORKBOOK.md FLOW-F32; the old hub's HUB-F112),
// end to end as the owner of hub `a`, in each of the three sizes, against the real apps and the run's REAL erplora.com
// (only Meta is played: whatsapp-helpers.ts). A template made in WhatsApp Manager with a photo at the top (no file of
// its own in the Hub) is offered in «Send a message»: chosen, the step asks for the photo and says what WhatsApp takes;
// a file of another type is said under it and never uploaded; a JPEG is kept at once in the business's files and named
// in the step. Saved, allowed, on and run by hand, the WhatsApp is in the customer's conversation with that very photo.
// Opened again, the step names the photo it keeps. One screenshot per size (CLOSE-FLOW-<width>).
// What it creates is «E2E Fhf …», `e2e_…` templates, `e2e-…` files and `+3469900…` conversations, and goes.
import { expect, type Page, test } from '@playwright/test';

import { choose, confirmDialog, signedIn } from './flow-helpers';
import { psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, settled } from './service-helpers';
import { photo } from './website-helpers';
import { cleanUp as cleanUpInbox, e2ePhone, metaGraph, pushChannel, receive, restorePhoto, seedErplora, template } from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

const TASK = 'CLOSE-FLOW';
const TAG = 'E2E Fhf';
const RUN = Date.now().toString(36);
/** An approved template made in WhatsApp Manager: a photo at the top and no file of its own in the Hub. */
const PROMO = `e2e_promo_foto_${RUN}`;
const FILE_NAME = 'e2e-promo-otono.jpg';

function cleanUp(): void {
  const flows = `select id from flow_flow where name like '${TAG}%'`;
  psql([`delete from flow_flowrun where flow_id in (${flows})`, `delete from flow_flow where id in (${flows})`].join('; '));
  cleanUpInbox();
}

test.beforeAll(async () => {
  cleanUp();
  // erplora.com takes `a`'s number (connected); this Hub knows it, with this run's approved photo template.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  await metaGraph();
  pushChannel({ status: 'connected', templates: [template(PROMO, { header_format: 'IMAGE', header: '', body: '¡Hola {{1}}! Ven a ver la carta.', variables: 1 })] });
});
test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

/** The Hub's messages to `phone`: `kind|body|file name|kept file`, oldest first. */
const sentTo = (phone: string): string[] =>
  psql(
    `select m.kind || '|' || m.body || '|' || m.media_filename || '|' || coalesce(m.header_sample_id::text, '') from whatsapp_inbox_message m join whatsapp_inbox_conversation c on c.id = m.conversation_id where c.phone = '${phone}' and m.direction = 'outbound' order by m.created_at`,
  )
    .split('\n')
    .filter(Boolean);

async function openRun(page: Page, status: string): Promise<void> {
  const run = shown(page).locator('[data-testid^=flow-run-]').filter({ hasText: status }).first();
  await expect(run).toBeVisible();
}

for (const viewport of FLOW_VIEWPORTS) {
  test(`FLOW-F32: «Send a message» puts the photo chosen in the step at the top of the template at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(150_000);
    const phone = e2ePhone();
    receive(phone, 'Hola, ¿qué hay de nuevo?', `e2e.Ana ${RUN}`);
    const { context, page } = await signedIn(browser, '/flow/automations/new', viewport);
    try {
      const editor = shown(page);
      await editor.locator('[data-testid=flow-editor-name] input').fill(`${TAG} ${viewport.label} ${RUN}`);
      await editor.locator('[data-testid=flow-editor-add-message]').click();
      await editor.locator('[data-testid=flow-message-phone-s1-text-0]').fill(phone);
      await choose(page, 'flow-message-template-s1', PROMO);

      // A photo at the top with no file of its own: the step asks for it, with what WhatsApp takes.
      await expect(editor.locator('[data-testid=flow-message-file-empty-s1]')).toHaveText('No file chosen');
      await expect(editor.locator('[data-testid=flow-message-file-missing-s1]')).toContainText(
        'This template goes with a photo at the top: choose it, or WhatsApp will not send it.',
      );
      await expect(editor.locator('[data-testid=flow-message-file-rules-s1]')).toContainText('JPEG or PNG, up to 5 MB.');

      // A file of another type is said under it and never uploaded.
      const input = editor.locator('[data-testid=flow-message-file-input-s1]');
      await input.setInputFiles({ name: 'e2e-carta.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.7\n') });
      await expect(editor.locator('[data-testid=flow-message-file-error-s1]')).toHaveText('Choose a JPEG or PNG photo.');

      // The photo: kept at once in the business's files, and named in the step.
      const jpeg = await photo(page, 'Carta', 28 + FLOW_VIEWPORTS.indexOf(viewport) * 40);
      const kept = page.waitForResponse((response) => response.url().endsWith('/api/whatsapp_inbox/templates/samples'));
      await input.setInputFiles({ name: FILE_NAME, mimeType: 'image/jpeg', buffer: jpeg });
      const answer = await kept;
      expect(answer.status()).toBe(201);
      const sampleId = ((await answer.json()) as { id: string }).id;
      await expect(editor.locator('[data-testid=flow-message-file-name-s1]')).toContainText(`Photo: ${FILE_NAME}`);
      await expect(editor.locator('[data-testid=flow-message-file-choose-s1]')).toHaveText('Change file');
      await expect(editor.locator('[data-testid=flow-message-file-missing-s1]')).toHaveCount(0);
      await expect(editor.locator('[data-testid=flow-message-file-error-s1]')).toHaveCount(0);
      await editor.locator('[data-testid=flow-message-var-s1-0-text-0]').fill('Ana');
      await settled(page);
      await noHorizontalScroll(page, `FLOW-F32 ${viewport.label}`);
      await page.screenshot({ path: shot(`${TASK}-${viewport.label}`) });

      await editor.locator('[data-testid=flow-editor-save]').click();
      await page.waitForURL(/\/flow\/automations\/[0-9a-f-]+$/);
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-tab-permissions]').click();
      await shown(page).locator('[data-testid=flow-perm-grantall]').click();
      await shown(page).locator('[data-testid=flow-editor-enabled]').click();
      await shown(page).locator('[data-testid=flow-editor-save]').click();
      await expect(shown(page).locator('[data-testid=flow-editor-notice]')).toHaveText('Saved.');
      await shown(page).locator('[data-testid=flow-editor-run]').click();
      await confirmDialog(page, 'Run it now?');
      await shown(page).locator('[data-testid=flow-editor-tab-history]').click();
      await openRun(page, 'Finished well');

      // The template is in her conversation with that very photo at the top.
      await expect.poll(() => sentTo(phone).length).toBe(1);
      expect(sentTo(phone)[0]).toBe(`template|¡Hola Ana! Ven a ver la carta.|${FILE_NAME}|${sampleId}`);

      // Opened again, the step names the photo it keeps (read by its id).
      await page.reload();
      await shown(page).locator('[data-testid=flow-step-open-s1]').click();
      await expect(shown(page).locator('[data-testid=flow-message-file-name-s1]')).toContainText(`Photo: ${FILE_NAME}`);
      if (process.env.E2E_SAVE_STORAGE_STATE) await context.storageState({ path: process.env.E2E_SAVE_STORAGE_STATE });
    } finally {
      await context.close();
    }
  });
}
