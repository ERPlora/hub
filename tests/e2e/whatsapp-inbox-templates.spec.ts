// flow: WHATSAPP_INBOX-F27 WHATSAPP_INBOX-F28 WHATSAPP_INBOX-F29 WHATSAPP_INBOX-F30 WHATSAPP_INBOX-F31
// The WhatsApp templates in Settings, in a hidden Chrome (apps/whatsapp_inbox/WORKBOOK.md): the owner of
// hub `a` sees the templates Meta holds (pushed as erplora.com will) with Meta's verdict and reason; the
// ones made in WhatsApp Manager that the Hub cannot fill are there but cannot be edited; «Add template»
// refuses what Meta would refuse under its field and keeps a new one «Not sent to Meta»; «Edit» keeps the
// approved one in use while the change waits; «Delete» asks first and leaves it «Being deleted at Meta».
// What the Hub hands over goes to the run's real erplora.com (WORKBOOK «Contrato con el SaaS», doors 8 and 9), where
// erplora.com's own test seed gave `a` a number (whatsapp-helpers.ts, `seedErplora`): erplora.com takes it to Meta,
// which refuses the seed's made-up permission, so each row says it was not accepted, with the reason, and is never
// shown as registered or deleted at Meta. Each flow's screen in three sizes (APP-WHATSAPP_INBOX-1-<flow>-390|834|1440). What it creates is
// deleted after the file.
// First, F27 and F28 as erplora.com itself brings them: its seed keeps `a`'s templates as it does after reading Meta's
// list (SEED_TEMPLATES: approved, in review, rejected with Meta's reason, and one made in WhatsApp Manager with a photo
// header and a named variable) and pushes them in `a`'s photo; the Hub shows each with Meta's verdict, and says of the
// WhatsApp Manager one that it cannot be sent or edited here, never offering it to send
// (FIX-HUB-WHATSAPP-INBOX-E2E-SEED-TEMPLATES-AND-CAP-UNUSED-<flow>-390|834|1440).
import { expect, type Page, test } from '@playwright/test';

import { A, login, psql, shot, shown } from './helpers';
import { FLOW_VIEWPORTS, noHorizontalScroll, rowAction, settled } from './service-helpers';
import {
  cleanUp,
  e2ePhone,
  flowShots,
  metaGraph,
  PREFIX,
  pushChannel,
  receive,
  SEED_TEMPLATES,
  seedErplora,
  template,
} from './whatsapp-helpers';

test.describe.configure({ mode: 'serial' });

test.beforeAll(async () => {
  // No channel pushed by another spec stands in front of erplora.com's photo (cleanUp drops it).
  cleanUp();
  // erplora.com takes `a`'s number (its test seed) and pushes its photo with the templates it holds: what the Hub
  // hands it reaches Meta.
  expect(seedErplora()).toEqual({ delivered: true, hub_error: '' });
  // erplora.com reaches Meta only through the run's Graph, or the run stops here (whatsapp-helpers.ts).
  await metaGraph();
});

test.afterAll(() => {
  cleanUp();
});

const TABLE = 'whatsapp-inbox-templates';
const rowOf = (page: Page, name: string) => shown(page).locator(`[data-testid=${TABLE}-row]`, { hasText: name });
const idOf = (name: string): string => psql(`select id from whatsapp_inbox_template where name = '${name}' and deleted_at is null`);

const TASK = 'FIX-HUB-WHATSAPP-INBOX-E2E-SEED-TEMPLATES-AND-CAP-UNUSED';

/** The screen in the three sizes (`${TASK}-<key>-390|834|1440`), with `ready` in sight. */
async function shots(page: Page, key: string, ready: (page: Page) => Promise<void>): Promise<void> {
  for (const viewport of FLOW_VIEWPORTS) {
    await page.setViewportSize({ width: viewport.width, height: viewport.height });
    await ready(page);
    await settled(page);
    await noHorizontalScroll(page, `${key} ${viewport.label}`);
    await page.screenshot({ path: shot(`${TASK}-${key}-${viewport.label}`) });
  }
  await page.setViewportSize({ width: 1280, height: 860 });
}

test('WHATSAPP_INBOX-F27, F28: the templates erplora.com brings from Meta show with Meta’s verdict, and the one made in WhatsApp Manager says what the Hub can do with it', async ({
  page,
}) => {
  const { approved, inReview, rejected, manager } = SEED_TEMPLATES;
  await login(page, A, '/whatsapp_inbox/settings');
  await shown(page).locator(`[data-testid=${TABLE}-search] input`).fill('e2e_seed_');

  // F27: each one with what Meta says of it, as erplora.com's photo brought it; the rejected one with Meta's reason.
  await expect(rowOf(page, approved)).toContainText('Approved');
  await expect(rowOf(page, inReview)).toContainText('In review');
  await expect(rowOf(page, rejected)).toContainText('Rejected');
  await expect(rowOf(page, rejected)).toContainText("Meta's reason: INVALID_FORMAT");
  await expect(rowOf(page, approved)).toContainText('Hola {{1}}, te esperamos el {{2}}.');
  await shots(page, 'F27', async (p) => {
    await expect(rowOf(p, rejected)).toContainText("Meta's reason: INVALID_FORMAT");
  });

  // F28: the one made in WhatsApp Manager (a photo header, a named variable) is there with its text and Meta's verdict,
  // and says it cannot be sent or edited here: no «Edit», and touching it opens nothing. The ones the Hub fills say nothing of it.
  const unfillable = "Can't be sent or edited here: it is managed in WhatsApp Manager.";
  await expect(rowOf(page, manager)).toContainText('Approved');
  await expect(rowOf(page, manager)).toContainText('Hola {{nombre}}, te damos la bienvenida al salón.');
  await expect(rowOf(page, manager)).toContainText(unfillable);
  await expect(rowOf(page, approved)).not.toContainText(unfillable);
  await expect(page.locator(`[data-testid=${TABLE}-row-${idOf(manager)}-edit]`)).toHaveCount(0);
  await rowOf(page, manager).click();
  await expect(page.locator('ion-modal[data-testid=whatsapp-inbox-template-editor]')).toBeHidden();
  await shots(page, 'F28', async (p) => {
    await expect(rowOf(p, manager)).toContainText(unfillable);
  });

  // F28: and «Template» in a conversation offers the approved one the Hub fills, never the WhatsApp Manager one.
  const phone = e2ePhone();
  receive(phone, '¿Tenéis hora el sábado?', `${PREFIX}Marta`);
  await page.goto('/whatsapp_inbox/inbox');
  await shown(page).locator('[data-testid=whatsapp-inbox-row]', { hasText: phone.slice(3) }).click();
  await shown(page).locator('[data-testid=whatsapp-inbox-detail] [data-testid=whatsapp-inbox-composer-template]').click();
  const picker = page.locator('ion-modal[data-testid=whatsapp-inbox-template-form]');
  await expect(picker).toContainText(approved);
  await expect(picker).not.toContainText(manager);
  await expect(picker).not.toContainText(inReview);
  await expect(picker).not.toContainText(rejected);
});

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
  // Meta» and handed to erplora.com, which takes it to Meta: Meta refuses the seed's made-up permission and
  // erplora.com says the number is not connected, so the row says «Not accepted» with it, never «In review».
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
  await expect(rowOf(page, made)).toContainText('Not accepted: WhatsApp is not connected.', { timeout: 30_000 });
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
  // erplora.com takes the change to Meta, which refuses the seed's permission: the row says the change was not
  // accepted, and the approved text is still the one in use.
  await expect(rowOf(page, approved)).toContainText('Approved');
  await expect(rowOf(page, approved)).toContainText('Not accepted: WhatsApp is not connected.', { timeout: 30_000 });
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
