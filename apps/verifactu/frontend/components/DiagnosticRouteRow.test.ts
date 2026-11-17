import { describe, expect, it } from 'vitest';

import { mountVerifactu } from '../__tests__/mount-verifactu';
import DiagnosticRouteRow from './DiagnosticRouteRow.vue';

async function setup(diagnostic: { route: 'erplora' | 'own'; available: boolean }) {
  return mountVerifactu(DiagnosticRouteRow, { props: { diagnostic } });
}

describe('DiagnosticRouteRow', () => {
  it('omits the row for the unavailable ERPlora route', async () => {
    const s = await setup({ route: 'erplora', available: false });
    expect(s.wrapper.find('dt').exists()).toBe(false);
    expect(s.wrapper.find('dd').exists()).toBe(false);
  });

  it('shows the own certificate when it carries the records', async () => {
    const s = await setup({ route: 'own', available: false });
    expect(s.wrapper.text()).toContain('Filed through');
    expect(s.wrapper.text()).toContain('My certificate');
  });

  it('keeps the original labels when ERPlora is available', async () => {
    for (const [route, label] of [['erplora', 'ERPlora files for you'], ['own', 'My certificate']] as const) {
      const s = await setup({ route, available: true });
      expect(s.wrapper.text()).toContain('Filed through');
      expect(s.wrapper.text()).toContain(label);
    }
  });
});
