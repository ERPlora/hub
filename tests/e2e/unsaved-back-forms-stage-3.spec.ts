// flow: BASE-F05 and one create form per app of hub#1032 (hub#1020's third and last stage; the walks are
// `expectBackAsksOnDirtyForm` and, for its own ways out, `expectWaysOutAskOnDirtyForm`, hub#1156). The other windows of
// the stage are covered by their component tests.
import { test } from '@playwright/test';

import { expectBackAsksOnDirtyForm, expectWaysOutAskOnDirtyForm, type UnsavedFormCase } from './unsaved-back-helpers';

const CASES: UnsavedFormCase[] = [
  { app: 'invoice', flow: 'INVOICE-F03', route: '/invoice/invoices', add: 'invoice-list-add', form: 'invoice-create', field: 'invoice-create-notes' },
  { app: 'printing', flow: 'PRINTING-F03', route: '/printing/printers', add: 'printing-printers-add', form: 'printing-printer', field: 'printing-printer-name' },
  { app: 'schedule', flow: 'SCHEDULE-F04', route: '/schedule/special-days', add: 'schedule-special-days-add', form: 'schedule-special-day-form', field: 'schedule-special-day-form-name' },
  { app: 'task', flow: 'TASK-F01', route: '/task/tasks', add: 'task-tasks-add', form: 'task-form', field: 'task-form-title' },
  { app: 'tax', flow: 'TAX-F02', route: '/tax/categories', add: 'tax-categories-add', form: 'tax-category-form', field: 'tax-category-form-name' },
  { app: 'whatsapp_inbox', flow: 'WHATSAPP_INBOX-F29', route: '/whatsapp_inbox/settings', add: 'whatsapp-inbox-templates-add', form: 'whatsapp-inbox-template-editor', field: 'whatsapp-inbox-template-editor-name' },
  { app: 'base', flow: 'BASE-F86', route: '/employees#apikeys', add: 'api-keys-new', form: 'api-key-form', field: 'api-key-form-name' },
];

for (const item of CASES) {
  test(`${item.flow} ${item.app}: Android Back asks before discarding a dirty form and closes a clean one`, async ({ page }) => {
    await expectBackAsksOnDirtyForm(page, item, 'HUB-1032');
  });

  test(`${item.flow} ${item.app}: Cancel, ×, Escape and a tap outside ask before discarding a dirty form and close a clean one (hub#1156)`, async ({ page }) => {
    await expectWaysOutAskOnDirtyForm(page, item, 'HUB-1156');
  });
}
