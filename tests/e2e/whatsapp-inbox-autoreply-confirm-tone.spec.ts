// The questions of WhatsApp's settings that turn an automatic answer on (WHATSAPP_INBOX-F14) and update it to its
// improved version (F18) confirm in the primary colour of a normal action: neither deletes anything, and the danger red
// stays for what does.
// flow: WHATSAPP_INBOX-F14 WHATSAPP_INBOX-F18
import { expect, type Locator, type Page, test } from '@playwright/test';

import { signedIn } from './flow-helpers';
import { capture, psql, shown, THREE_SIZES } from './helpers';
import { noHorizontalScroll } from './schedule-helpers';

const TASK = 'WHATSAPP-INBOX-AUTOREPLY-CONFIRM-TONE';
const ANSWER = 'whatsapp_inbox/appointment_from_whatsapp';
const FLOWS = "select id from flow_flow where recipe like 'whatsapp_inbox/%'";

/** Each size starts with nothing of the inbox's automatic answers built. */
function cleanUp(): void {
  psql(
    [
      `delete from flow_question where flow_id in (${FLOWS})`,
      `delete from flow_flowrun where flow_id in (${FLOWS})`,
      `delete from flow_flow where id in (${FLOWS})`,
    ].join('; '),
  );
}

test.beforeEach(cleanUp);
test.afterAll(cleanUp);

/** The open question titled `title`, and its button that says yes. */
function question(page: Page, title: string): { dialog: Locator; yes: Locator } {
  const dialog = page.locator('ion-modal.ep-form-modal').filter({ hasText: title });
  return { dialog, yes: dialog.locator('.ep-form-modal__submit') };
}

async function asksInPrimary(yes: Locator, label: string): Promise<void> {
  await expect(yes).toBeInViewport();
  await expect(yes).toHaveText(label);
  await expect(yes).toHaveClass(/\bion-color-primary\b/);
  await expect(yes).not.toHaveClass(/\bion-color-danger\b/);
}

for (const viewport of THREE_SIZES) {
  test(`WHATSAPP_INBOX-F14 F18 «Turn on» and «Update» ask in the colour of a normal action at ${viewport.label}`, async ({ browser }) => {
    test.setTimeout(120_000);
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/settings', viewport);
    try {
      const card = shown(page).locator('[data-testid=whatsapp-inbox-autoreply-appointments]');
      await expect(card).toContainText('Off');
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-on]').click();
      const turnOn = question(page, 'Book appointments');
      await asksInPrimary(turnOn.yes, 'Turn on');
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${TASK}-turn-on-${viewport.label}`);
      await turnOn.yes.click();
      await expect(turnOn.dialog).toBeHidden();
      await expect(card).toContainText('On');

      // F18: a version older than the one the app brings today, as after an update of the app.
      psql(`update flow_flow set recipe_digest = 'e2e-older' where recipe = '${ANSWER}'`);
      await page.reload();
      await card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-update]').click();
      const update = question(page, 'Update the automatic answer');
      await asksInPrimary(update.yes, 'Update');
      await noHorizontalScroll(page, viewport.label);
      await capture(page, `${TASK}-update-${viewport.label}`);
      await update.yes.click();
      await expect(update.dialog).toBeHidden();
      await expect(card.locator('[data-testid=whatsapp-inbox-autoreply-appointments-updated]')).toHaveText(
        'Done: this automatic answer already works with the latest version.',
      );
    } finally {
      await context.close();
    }
  });
}
