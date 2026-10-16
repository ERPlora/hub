// The guide (WORKBOOK FLOW-F08): «How automations work», in five parts, inside the app; «Back to the
// automations» returns.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, mountFlow, settle } from '../__tests__/mount-flow';
import GuidePage from './GuidePage.vue';

describe('GuidePage', () => {
  it('says how automations work in five parts', async () => {
    const m = await mountFlow(GuidePage, { path: '/flow/guide' });
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('How automations work');
    expect(m.wrapper.findAll('[data-testid^="flow-guide-section-"]').map((section) => section.find('h2').text())).toEqual([
      'What an automation is',
      'Your first automation, step by step',
      'Permissions: why you have to say yes',
      'How to know whether it worked',
      'What it cannot do yet',
    ]);
    expect(m.wrapper.findAll('[data-testid="flow-guide-section-first"] li')).toHaveLength(5);
    expect(m.wrapper.findAll('[data-testid="flow-guide-section-limits"] li')).toHaveLength(4);
  });

  it('speaks Spanish and goes back to the automations', async () => {
    const m = await mountFlow(GuidePage, { path: '/flow/guide', locale: 'es' });
    expect(m.wrapper.findComponent(AppPage).props('title')).toBe('Cómo funcionan las automatizaciones');
    await click(m.find('flow-guide-back').element);
    await settle();
    expect(m.router.currentRoute.value.path).toBe('/flow/automations');
  });
});
