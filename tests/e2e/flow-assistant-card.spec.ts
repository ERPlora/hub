// The assistant's card for an automation (FLOW-F17, BASE-F97): a draft says its name, when it starts and each step in
// the words of the Automations list and editor, never the codes of its definition (hub#2300). End to end with the
// stack's SaaS gateway and the e2e's provider (assistant-provider.ts, `E2E-ASK <tool> <JSON>`): the SaaS must be seeded
// with it (README of this folder, «El asistente»). The owner, in Spanish, asks for the case of the issue: a task to
// review the closing every time the till closes; cancelled, no draft is left. What this file creates carries
// `E2EFac` and goes away; the apps it turns on are turned off again.
// flow: FLOW-F17 BASE-F97

import { expect, test } from '@playwright/test';

import { cardSpec } from './assistant-card-helpers';
import { askForACard, cancelAtComputerSize, card, openPanelAtTheDesk, ownerIn } from './assistant-panel';
import { capture, psql, THREE_SIZES as VIEWPORTS, untilStill } from './helpers';

const KEY = 'FIX-HUB-FLOW-ASSISTANT-CARD-SAYS-ITS-CODES';
const TAG = 'E2EFac';
/** The apps the draft names: Automations, the till whose closing starts it and the task it leaves. */
const NEEDED = ['flow', 'cash_register', 'task'];

function cleanup(): void {
  psql(`delete from flow_draft where name like '${TAG}%'`);
}

cardSpec(NEEDED, cleanup);

test('flow-assistant-card — a draft says when it starts and its steps in words, never its codes', async ({ browser }) => {
  const [context, page] = await ownerIn(browser, 'es');
  const draft = {
    name: `${TAG} Repasar el cierre de caja`,
    definition: {
      trigger: { kind: 'event', event: 'cash_register.session.closed' },
      steps: [{ id: 's1', kind: 'command', operation: 'task.task.create', params: { title: 'Repasar el cierre', priority: 'medium' } }],
    },
    notes: [],
  };
  await openPanelAtTheDesk(page);
  await askForACard(page, `E2E-ASK flow__draft__propose ${JSON.stringify(draft)}`);
  for (const vp of VIEWPORTS) {
    await page.setViewportSize({ width: vp.width, height: vp.height });
    await expect(card(page)).toContainText(`Proponer en Automatizaciones: ${draft.name} · Cuando se cierra una caja · Crear una tarea`);
    for (const code of ['cash_register.session.closed', 'task.task.create', 'command', 'medium']) await expect(card(page)).not.toContainText(code);
    await untilStill(page);
    await capture(page, `${KEY}-${vp.label}`);
  }
  await cancelAtComputerSize(page);
  expect(psql(`select count(*) from flow_draft where name like '${TAG}%'`).trim()).toBe('0');
  await context.close();
});
