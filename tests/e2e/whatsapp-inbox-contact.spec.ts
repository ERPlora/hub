// flow: WHATSAPP_INBOX-F05, WHATSAPP_INBOX-F09 — a customer's WhatsApp number reaches only whoever sees the customers'
// contact details (BASE-F119). The employee holds that permission (base/apps.py), so they still see «Phone» in the inbox
// and the number in the open conversation, find it by its digits and ask whose conversation a number is, at every
// width; nobody sorts the inbox by the number any more (the API answers 422). A role without the permission does not
// exist yet in a browser: what it gets (no number, a conversation without a name by its masked number) is held by the
// server's tests (apps/whatsapp_inbox/tests/test_queries_contact.py) and the pages' (Vitest). What the run creates is
// deleted after it.
import { expect, test } from '@playwright/test';

import { signedIn } from './flow-helpers';
import { A, api, capture, EMPLOYEE, shown } from './helpers';
import { FLOW_VIEWPORTS } from './service-helpers';
import { cleanUp, e2ePhone, keepPhoto, PREFIX, receive, restorePhoto } from './whatsapp-helpers';

const NAME = `${PREFIX}Ana ${Date.now().toString(36)}`;
const PHONE = e2ePhone();

type Row = { id: string; display_name: string; phone: string | null };

test.describe.configure({ mode: 'serial' });

test.beforeAll(() => {
  keepPhoto();
  receive(PHONE, 'Hola, ¿tenéis hora mañana?', NAME);
});

test.afterAll(() => {
  cleanUp();
  restorePhoto();
});

for (const viewport of FLOW_VIEWPORTS) {
  test(`the employee sees a customer's number in the inbox at ${viewport.label}px; nobody sorts by it`, async ({ browser }) => {
    const { context, page } = await signedIn(browser, '/whatsapp_inbox/inbox', viewport, EMPLOYEE);
    try {
      const found = await api<{ rows: Row[] }>(context, A, 'GET', `/whatsapp_inbox/conversations?search=${PHONE.slice(-6)}`);
      expect(found.data.rows.map((row) => [row.display_name, row.phone])).toEqual([[NAME, PHONE]]);
      const whose = await api<{ conversation_id: string | null }>(
        context,
        A,
        'GET',
        `/whatsapp_inbox/conversations/by_phone?phone=${encodeURIComponent(PHONE)}`,
      );
      expect([whose.status, whose.data.conversation_id]).toEqual([200, found.data.rows[0].id]);
      expect((await api(context, A, 'GET', '/whatsapp_inbox/conversations?sort=phone')).status).toBe(422);

      await shown(page).locator('[data-testid=whatsapp-inbox-search] input').fill(NAME);
      const row = shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: NAME });
      await expect(row).toBeVisible();
      if (viewport.width >= 1440) await expect(row).toContainText(PHONE);
      await capture(page, `whatsapp-inbox-contact-list-${viewport.label}`);

      await row.click();
      await expect(shown(page).locator('[data-testid=whatsapp-inbox-detail-phone]')).toHaveText(PHONE);
      await capture(page, `whatsapp-inbox-contact-panel-${viewport.label}`);
    } finally {
      await context.close();
    }
  });
}
