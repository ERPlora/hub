// «Record tip» (TIP-F03, TIP-F04, TIP-F05): of a sale, by its number, with the payment method the tip was paid by and
// the amount; or «To the pool, no ticket», only the amount of cash counted from the jar. It sends `tip.tip.add`; an
// amount it cannot read is said under its field, and the server's refusals stay inside the window.
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, flush, ionValue } from '../../../../base/frontend/__tests__/mount-in-shell';
import { MANAGER, mountTip } from '../__tests__/mount-tip';
import type { SettingsOut } from '../operations';
import TipFormModal from './TipFormModal.vue';

const SETTINGS: SettingsOut = {
  enabled: true,
  allow_custom: true,
  preselected: 0,
  methods: [
    { method_id: 'm-cash', method_name: 'Cash', method_type: 'cash', suggestions: [] },
    { method_id: 'm-card', method_name: 'Card', method_type: 'card', suggestions: [] },
  ],
};

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountTip(TipFormModal, { props: { open: true }, locale, session: MANAGER });
  await m.live();
  await m.result('tip.settings.get', SETTINGS);
  const field = (name: string) => m.inDoc(`tip-form-${name}`) as unknown as Record<string, unknown> & Element;
  const type = (name: string, text: string) => ionValue(m.inDoc(`tip-form-${name}`), text, 'ionInput');
  const pick = (name: string, value: string) => ionValue(m.inDoc(`tip-form-${name}`), value);
  async function target(value: 'sale' | 'pool') {
    m.inDoc('tip-form-target')?.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  const submit = () => click(m.inDoc('tip-form-submit'));
  const posted = () => m.sent().filter((call) => call.method === 'POST');
  return { ...m, field, type, pick, target, submit, posted };
}

describe('TipFormModal', () => {
  it('is «Record tip», of a sale to begin with: its number, the payment methods of Sales and the amount', async () => {
    const s = await setup();
    expect(s.inDoc('tip-form')?.getAttribute('aria-label')).toBe('Record tip');
    expect(s.field('target').value).toBe('sale');
    expect([s.field('sale').label, s.field('sale').fill, s.field('sale').getAttribute('mode')]).toEqual(['Sale number', 'outline', 'md']);
    expect([s.field('method').label, s.field('method').fill, s.field('method').getAttribute('mode')]).toEqual(['Payment method', 'outline', 'md']);
    const options = [...(s.inDoc('tip-form-method')?.querySelectorAll('ion-select-option') ?? [])];
    expect(options.map((option) => [option.getAttribute('value') ?? (option as unknown as { value: string }).value, option.textContent?.trim()])).toEqual([
      ['m-cash', 'Cash'],
      ['m-card', 'Card'],
    ]);
    expect(s.field('amount').label).toBe('Amount');
  });

  it('records the tip of a sale by its number, says «Tip recorded» and closes', async () => {
    const s = await setup();
    s.answer(201, { id: 't1' });
    await s.type('sale', ' 20261125-0007 ');
    await s.pick('method', 'm-card');
    await s.type('amount', '2,50');
    await s.submit();
    expect(s.posted()).toEqual([
      { method: 'POST', path: '/api/tip/tips', query: {}, body: { sale: '20261125-0007', method_id: 'm-card', amount: 250 } },
    ]);
    expect(toastSuccess).toHaveBeenCalledWith('Tip recorded.');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('to the pool asks only the amount, says where that cash goes, and sends it as the pool’s', async () => {
    const s = await setup();
    s.answer(201, { id: 't2' });
    await s.target('pool');
    expect([s.inDoc('tip-form-sale'), s.inDoc('tip-form-method')]).toEqual([null, null]);
    expect(s.inDoc('tip-form-pool-hint')?.textContent?.trim()).toBe(
      "Cash counted from the jar: it enters the open drawer and is split with the day's rules.",
    );
    await s.type('amount', '12');
    await s.submit();
    expect(s.posted().map((call) => call.body)).toEqual([{ pool: true, amount: 1200 }]);
  });

  it('an amount that is no tip is said under its field and nothing is sent', async () => {
    const s = await setup();
    await s.type('amount', '0');
    await s.submit();
    expect(s.posted()).toEqual([]);
    expect(s.field('amount').errorText).toBe('Write the tip as an amount above zero.');
  });

  it('a refusal is read inside the window, which stays open', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'tip.sale_voided', message: 'That sale is voided: it takes no tip.' } });
    await s.type('sale', '20261125-0001');
    await s.pick('method', 'm-cash');
    await s.type('amount', '1');
    await s.submit();
    expect(s.inDoc('tip-form-error')?.textContent).toContain('That sale is voided: it takes no tip.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('opened again, it starts empty: the tip just recorded is not left written to be saved twice', async () => {
    const s = await setup();
    s.answer(201, { id: 't1' });
    await s.type('sale', '20261125-0007');
    await s.pick('method', 'm-card');
    await s.type('amount', '2,50');
    await s.submit();
    await s.wrapper.setProps({ open: false });
    await s.wrapper.setProps({ open: true });
    await flush();
    expect([s.field('sale').value, s.field('method').value, s.field('amount').value]).toEqual(['', '', '']);
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    expect(s.inDoc('tip-form')?.getAttribute('aria-label')).toBe('Anotar propina');
    // happy-dom reads an upgraded Ionic element's text as empty: its markup says it.
    expect(s.inDoc('tip-form-target-pool')?.innerHTML.replace(/<[^>]+>/g, '').trim()).toBe('Al bote, sin tique');
    expect(s.field('sale').label).toBe('Número de venta');
  });
});
