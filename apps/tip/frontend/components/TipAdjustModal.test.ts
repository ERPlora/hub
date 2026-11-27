// «Adjust» a tip (TIP-F06): the amount and the person it belongs to, as they are, and «Reason». It sends
// `tip.tip.update` with only what changed and the reason; an amount it cannot read is said under its field and nothing
// goes; the server's refusals stay inside the window.
import { Combo } from '@erplora/ui/components';
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, ionValue, page, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import { MANAGER, mountTip } from '../__tests__/mount-tip';
import type { TipOut } from '../operations';
import TipAdjustModal from './TipAdjustModal.vue';

const TIP = { id: 't1', sale_number: '20261125-0007', pool: false, amount: 250, member_id: 'm-bea', member_name: 'Bea Gil' } as TipOut;

async function setup(tip: TipOut = TIP, locale: 'en' | 'es' = 'en') {
  const m = await mountTip(TipAdjustModal, { props: { open: true, tip }, locale, session: MANAGER });
  await m.live();
  const combo = () => m.wrapper.findComponent(Combo);
  const field = (name: string) => m.inDoc(`tip-adjust-${name}`) as unknown as Record<string, unknown> & Element;
  const typeAmount = (text: string) => ionValue(m.inDoc('tip-adjust-amount'), text, 'ionInput');
  const typeReason = (text: string) => ionValue(m.inDoc('tip-adjust-reason'), text, 'ionInput');
  const submit = () => click(m.inDoc('tip-adjust-submit'));
  return { ...m, combo, field, typeAmount, typeReason, submit };
}

describe('TipAdjustModal', () => {
  it('names the tip by its sale and starts from its amount and its person', async () => {
    const s = await setup();
    expect(s.inDoc('tip-adjust')?.getAttribute('aria-label')).toBe('Adjust the tip of 20261125-0007');
    expect(s.field('amount').value).toBe('2.50');
    expect(s.combo().props('modelValue')).toEqual({ id: 'm-bea', label: 'Bea Gil' });
    expect(s.combo().props('label')).toBe('For');
    expect([s.field('reason').label, s.field('reason').fill, s.field('reason').getAttribute('mode')]).toEqual(['Reason', 'outline', 'md']);
  });

  it('an unassigned tip starts with nobody; the person is chosen among the active team', async () => {
    const s = await setup({ ...TIP, member_id: null, member_name: '' });
    expect(s.combo().props('modelValue')).toBeNull();
    s.answerBy({ '/api/staff/members': [200, page([{ id: 'm-carla', full_name: 'Carla Ruiz' }])] });
    const offered = await (s.combo().props('search') as (q: string) => Promise<unknown>)('car');
    expect(offered).toEqual([{ id: 'm-carla', label: 'Carla Ruiz' }]);
    expect(s.sent().at(-1)?.query).toMatchObject({ search: 'car', status: 'active' });
  });

  it('sends only what changed with the reason, says «Tip adjusted» and closes', async () => {
    const s = await setup();
    s.answer(200, { ...TIP, amount: 300 });
    await s.typeAmount('3');
    await s.typeReason('Charged 3 € more on the card');
    await s.submit();
    expect(s.sent().at(-1)).toEqual({
      method: 'POST',
      path: '/api/tip/tips/update',
      query: {},
      body: { id: 't1', amount: 300, reason: 'Charged 3 € more on the card' },
    });
    expect(toastSuccess).toHaveBeenCalledWith('Tip adjusted.');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('another person goes as the member it belongs to', async () => {
    const s = await setup();
    s.answer(200, TIP);
    s.combo().vm.$emit('update:modelValue', { id: 'm-carla', label: 'Carla Ruiz' });
    await settle();
    await s.typeReason('Her table');
    await s.submit();
    expect(s.sent().at(-1)?.body).toEqual({ id: 't1', member_id: 'm-carla', reason: 'Her table' });
  });

  it('an amount it cannot read is said under its field and nothing is sent', async () => {
    const s = await setup();
    await s.typeAmount('dos');
    await s.submit();
    expect(s.sent().filter((call) => call.path.startsWith('/api/tip'))).toEqual([]);
    expect(s.field('amount').errorText).toBe('Write the tip as an amount above zero.');
  });

  it('the server’s refusal of a field goes under it, and the window stays open', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'validation_error', message: 'Check the fields.', fields: { reason: 'Write the reason.' } } });
    await s.typeAmount('4');
    await s.submit();
    expect(s.field('reason').errorText).toBe('Write the reason.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('speaks Spanish', async () => {
    const s = await setup({ ...TIP, pool: true, sale_number: '' }, 'es');
    expect(s.inDoc('tip-adjust')?.getAttribute('aria-label')).toBe('Ajustar una propina del bote');
    expect(s.field('amount').value).toBe('2,50');
    expect(s.combo().props('label')).toBe('Para');
  });
});
