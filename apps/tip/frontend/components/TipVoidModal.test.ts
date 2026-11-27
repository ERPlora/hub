// «Void» a tip (TIP-F06): «Void the tip of <sale>», what voiding does, «Reason» and «Void» / «Cancel». It sends
// `tip.tip.void` with the reason as typed: the server asks for one when it is missing, under its field, and a
// refusal stays inside the window, in the server's words.
import { toastSuccess } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';

import { click, ionValue } from '../../../../base/frontend/__tests__/mount-in-shell';
import { MANAGER, mountTip } from '../__tests__/mount-tip';
import type { TipOut } from '../operations';
import TipVoidModal from './TipVoidModal.vue';

const TIP = { id: 't1', sale_number: '20261125-0007', pool: false, amount: 250 } as TipOut;

async function setup(tip: TipOut = TIP, locale: 'en' | 'es' = 'en') {
  const m = await mountTip(TipVoidModal, { props: { open: true, tip }, locale, session: MANAGER });
  const type = (text: string) => ionValue(m.inDoc('tip-void-reason'), text, 'ionInput');
  const submit = () => click(m.inDoc('tip-void-submit'));
  return { ...m, type, submit };
}

describe('TipVoidModal', () => {
  it('names the tip by its sale, says what voiding does and asks the reason', async () => {
    const s = await setup();
    expect(s.inDoc('tip-void')?.getAttribute('aria-label')).toBe('Void the tip of 20261125-0007');
    expect(s.inDoc('tip-void-explain')?.textContent).toBe(
      'The tip stays in the list as voided, with your reason. If it was in cash, it leaves the open drawer.',
    );
    const reason = s.inDoc('tip-void-reason') as unknown as Record<string, unknown>;
    expect([reason.label, reason.fill, s.inDoc('tip-void-reason')?.getAttribute('mode')]).toEqual(['Reason', 'outline', 'md']);
    expect([s.inDoc('tip-void-submit')?.textContent?.trim(), s.inDoc('tip-void-cancel')?.textContent?.trim()]).toEqual(['Void', 'Cancel']);
  });

  it('a tip of the pool is named as one', async () => {
    const s = await setup({ ...TIP, pool: true, sale_number: '' });
    expect(s.inDoc('tip-void')?.getAttribute('aria-label')).toBe('Void a tip of the pool');
  });

  it('voids it with the reason, says «Tip voided» and closes', async () => {
    const s = await setup();
    s.answer(200, { ...TIP, status: 'voided' });
    await s.type('Customer took it back');
    await s.submit();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/tip/tips/void', query: {}, body: { id: 't1', reason: 'Customer took it back' } }]);
    expect(toastSuccess).toHaveBeenCalledWith('Tip voided.');
    expect(s.wrapper.emitted('update:open')).toEqual([[false]]);
  });

  it('without a reason the server’s words go under the field, and the window stays open', async () => {
    const s = await setup();
    s.answer(422, { error: { code: 'validation_error', message: 'Check the fields.', fields: { reason: 'Write the reason.' } } });
    await s.submit();
    expect(s.sent()[0].body).toEqual({ id: 't1', reason: '' });
    expect((s.inDoc('tip-void-reason') as unknown as { errorText?: string }).errorText).toBe('Write the reason.');
    expect(s.wrapper.emitted('update:open')).toBeUndefined();
  });

  it('a refusal is read inside the window; one the server did not word says the window’s own sentence', async () => {
    const s = await setup();
    s.answer(409, { error: { code: 'tip.tip_voided', message: 'That tip is voided: it no longer changes.' } });
    await s.type('x');
    await s.submit();
    expect(s.inDoc('tip-void-error')?.textContent).toContain('That tip is voided: it no longer changes.');
    s.answer(500, { error: { code: 'internal_error', message: 'boom' } });
    await s.submit();
    expect(s.inDoc('tip-void-error')?.textContent).toContain('The tip could not be voided.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(TIP, 'es');
    expect(s.inDoc('tip-void')?.getAttribute('aria-label')).toBe('Anular la propina de 20261125-0007');
    expect(s.inDoc('tip-void-submit')?.textContent?.trim()).toBe('Anular');
  });
});
