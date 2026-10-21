// flow: WHATSAPP_INBOX-F27 WHATSAPP_INBOX-F28 WHATSAPP_INBOX-F29 WHATSAPP_INBOX-F30 WHATSAPP_INBOX-F31
// The WhatsApp templates in Settings, in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the owner of
// hub `a` sees the templates Meta holds (pushed as erplora.com will) with Meta's verdict and reason; the
// ones made in WhatsApp Manager that the Hub cannot fill are there but cannot be edited; «Add template»
// refuses what Meta would refuse under its field and keeps a new one «Not sent to Meta»; «Edit» keeps the
// approved one in use while the change waits; «Delete» asks first and leaves it «Being deleted at Meta».
// erplora.com does not serve its template doors yet (WORKBOOK «Contrato con el SaaS», doors 8 and 9): what
// the Hub hands over stays on its way, with the reason, and is never shown as registered or deleted at
// Meta. Each flow's screen in three sizes (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440). What it creates is
// deleted after the file.
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, shown } from './helpers';
import { rowAction } from './service-helpers';
import { cleanUp, flowShots, pushChannel, template } from './whatsapp-helpers';

test.afterAll(() => {
  cleanUp();
});

const TABLE = 'whatsapp-inbox-templates';
const rowOf = (page: Page, name: string) => shown(page).locator(`[data-testid=${TABLE}-row]`, { hasText: name });
const idOf = (name: string): string => psql(`select id from whatsapp_inbox_template where name = '${name}' and deleted_at is null`);

test('the owner sees Meta’s templates and makes, changes and deletes them from Settings', async ({ page }) => {
  const stamp = Date.now().toString(36);
  const approved = `e2e_aprobada_${stamp}`;
  const rejected = `e2e_rechazada_${stamp}`;
  const photo = `e2e_con_foto_${stamp}`;
  const named = `e2e_con_nombre_${stamp}`;
  const made = `e2e_nueva_${stamp}`;
  pushChannel({
    status: 'connected',
    templates: [
      template(approved, { body: 'Hola {{1}}, te esperamos mañana.', body_examples: ['Ana'] }),
      template(rejected, { status: 'REJECTED', rejected_reason: 'INVALID_FORMAT' }),
      template(photo, { header_format: 'IMAGE', header: '' }),
      template(named, { body: 'Hola {{nombre}}, te esperamos.' }),
    ],
  });

  await login(page, A, '/whatsapp_inbox/settings');
  await shown(page).locator(`[data-testid=${TABLE}-search] input`).fill(stamp);

  // F27: each template with what Meta says of it; a rejected one with Meta's reason.
  await expect(rowOf(page, approved)).toContainText('Approved');
  await expect(rowOf(page, rejected)).toContainText('Rejected');
  await expect(rowOf(page, rejected)).toContainText('INVALID_FORMAT');
  await flowShots(page, 'WHATSAPP_INBOX-F27', async (p) => {
    await expect(rowOf(p, rejected)).toBeVisible();
  });

  // F28: the ones made in WhatsApp Manager the Hub cannot fill (a photo header, named variables) are
  // brought, but cannot be edited here: touching them opens nothing.
  await expect(rowOf(page, photo)).toBeVisible();
  await expect(rowOf(page, named)).toBeVisible();
  const editor = page.locator('ion-modal[data-testid=whatsapp-inbox-template-editor]');
  await rowOf(page, photo).click();
  await rowOf(page, named).click();
  await expect(editor).toBeHidden();
  await flowShots(page, 'WHATSAPP_INBOX-F28', async (p) => {
    await expect(rowOf(p, named)).toBeVisible();
  });

  // F29: «Add template». What Meta would refuse is said under its field; a valid one is kept «Not sent to
  // Meta», and the row says erplora.com did not take it (its door does not exist yet), never «In review».
  await shown(page).locator(`[data-testid=${TABLE}-add]`).click();
  await expect(editor).toBeVisible();
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-name] input').fill(made);
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-body] textarea').fill('Hola {{nombre}}, tu cita es mañana.');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-submit]').click();
  await expect(editor.getByText('Number the variables 1, 2, 3… in order, without skipping any.')).toBeVisible();
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-body] textarea').fill('Hola {{1}}, tu cita es el {{2}}.');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-example-1] input').fill('Ana');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-example-2] input').fill('viernes');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-footer] input').fill('Peluquería e2e');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-button-add]').click();
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-button-0-text] input').fill('Confirmar');
  await flowShots(page, 'WHATSAPP_INBOX-F29', async () => {
    await expect(editor.locator('[data-testid=whatsapp-inbox-template-editor-example-2]')).toBeVisible();
  });
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-submit]').click();
  await expect(editor).toBeHidden();
  await expect(rowOf(page, made)).toContainText('Not sent to Meta');
  await expect(rowOf(page, made)).toContainText('erplora.com did not answer');
  await expect(rowOf(page, made)).not.toContainText('In review');

  // F30: «Edit» an approved one: it stays approved (and sendable) while the change waits for Meta.
  await rowAction(page, TABLE, idOf(approved), 'edit');
  await expect(editor).toBeVisible();
  await expect(editor).toContainText('Until Meta approves the changes, the approved one keeps being sent.');
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-body] textarea').fill('Hola {{1}}, recuerda tu cita de mañana.');
  await flowShots(page, 'WHATSAPP_INBOX-F30', async () => {
    await expect(editor.locator('[data-testid=whatsapp-inbox-template-editor-body]')).toBeVisible();
  });
  await editor.locator('[data-testid=whatsapp-inbox-template-editor-submit]').click();
  await expect(editor).toBeHidden();
  await expect(rowOf(page, approved)).toContainText('Approved');
  await expect(rowOf(page, approved)).toContainText('Changes not sent');
  await expect(rowOf(page, approved)).toContainText('Hola {{1}}, te esperamos mañana.');

  // F31: «Delete» asks first, naming it and what it costs; it then waits for Meta, «Being deleted at Meta».
  await rowAction(page, TABLE, idOf(rejected), 'delete');
  const confirm = page.locator('ion-modal[data-testid=whatsapp-inbox-template-delete]');
  await expect(confirm).toContainText(rejected);
  await expect(confirm).toContainText('An approved template takes days to be approved again.');
  await flowShots(page, 'WHATSAPP_INBOX-F31', async () => {
    await expect(confirm).toBeVisible();
  });
  await confirm.locator('[data-testid=whatsapp-inbox-template-delete-submit]').click();
  await expect(confirm).toBeHidden();
  await expect(rowOf(page, rejected)).toContainText('Being deleted at Meta');
});
