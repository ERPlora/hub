// The guide (WORKBOOK FLOW-F08): «How automations work» in five parts, with its texts inside the app,
// and «Back to the automations». What it says it cannot do is what this Hub cannot do (flows#16): no
// message, call or question steps, and — while the events of other apps are not delivered to it
// (FLOW-F21, phase 2) — no starting on its own when something happens.
import { describe, expect, it } from 'vitest';

import { click, mountFlow, settle } from '../__tests__/mount-flow';
import GuidePage from './GuidePage.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountFlow(GuidePage, { path: '/flow/guide', locale });
  await settle();
  return m;
}

describe('GuidePage', () => {
  it('has its five parts', async () => {
    const m = await setup();
    for (const part of ['what', 'first', 'permissions', 'worked', 'limits']) expect(m.find(`flow-guide-section-${part}`).exists(), part).toBe(true);
    expect(m.find('flow-guide-section-first').findAll('li')).toHaveLength(5);
  });

  it('says what it cannot do yet, as it is today', async () => {
    const section = (await setup()).find('flow-guide-section-limits');
    expect(section.findAll('li')).toHaveLength(4);
    const limits = section.text();
    expect(limits).toContain('The assistant writes drafts');
    expect(limits).toContain('Sending messages or asking the assistant: they come in a later version.');
    // What it already does is no limit: starting on its own when something happens (FLOW-F21), calling another
    // system (F27) and asking a person first (F28).
    expect(limits).not.toContain('Starting on its own');
    expect(limits).not.toContain('calling another system');
    const spanish = (await setup('es')).find('flow-guide-section-limits').text();
    expect(spanish).toContain('Enviar mensajes o pedírselo al asistente: llegan en una versión posterior.');
    expect(spanish).not.toContain('Arrancar sola');
  });

  it('«Back to the automations» goes back', async () => {
    const m = await setup();
    await click(m.find('flow-guide-back').element);
    await settle();
    expect(m.router.currentRoute.value.path).toBe('/flow/automations');
  });
});
