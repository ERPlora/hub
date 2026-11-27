// The period of a tips screen as the select of its toolbar: Today, 7 days and 30 days, the one in use shown, and the one
// picked handed to the page.
import { describe, expect, it } from 'vitest';

import { mountTip } from '../__tests__/mount-tip';
import PeriodSelect from './PeriodSelect.vue';

async function setup(locale: 'en' | 'es' = 'en') {
  return mountTip(PeriodSelect, { locale, props: { value: 'week', testid: 'tip-report-period' } });
}

describe('PeriodSelect', () => {
  it('offers today, 7 days and 30 days, with the one in use shown', async () => {
    const s = await setup();
    const select = s.find('tip-report-period');
    expect(select.attributes('aria-label')).toBe('Period');
    expect((select.element as HTMLIonSelectElement).value).toBe('week');
    expect(select.findAll('ion-select-option').map((option) => [(option.element as HTMLIonSelectOptionElement).value, option.text()])).toEqual([
      ['today', 'Today'],
      ['week', '7 days'],
      ['month', '30 days'],
    ]);
  });

  it('hands the one picked to the page', async () => {
    const s = await setup();
    s.find('tip-report-period').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: 'month' } }));
    expect(s.wrapper.emitted('pick')).toEqual([['month']]);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.find('tip-report-period').findAll('ion-select-option').map((option) => option.text())).toEqual(['Hoy', '7 días', '30 días']);
  });
});
