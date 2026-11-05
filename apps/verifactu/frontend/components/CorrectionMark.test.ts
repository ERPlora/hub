// Whether a rejection (or an acceptance with errors) is corrected (VERIFACTU-F24), the same in the Records list and in
// the record's detail: «Corrected», a link to the record that corrects it, or «Pending correction»; nothing for a record
// a correction does not answer.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { flush, mountVerifactu } from '../__tests__/mount-verifactu';
import CorrectionMark from './CorrectionMark.vue';

async function setup(props: Record<string, unknown>, locale: 'en' | 'es' = 'en') {
  return mountVerifactu(CorrectionMark, { props: { correctedById: null, ...props }, locale });
}

describe('CorrectionMark', () => {
  it('a corrected one links to the record that corrects it', async () => {
    const s = await setup({ status: 'corrected', correctedById: 'r9' });
    const link = s.find('verifactu-correction-corrected');
    expect(link.element.tagName).toBe('A');
    expect(link.attributes('href')).toBe('/verifactu/records/r9');
    expect(link.attributes('aria-label')).toBe('Corrected: open the record that corrects it');
    const pill = s.wrapper.findComponent(StatusPill);
    expect([pill.props('label'), pill.props('tone')]).toEqual(['Corrected', 'success']);
    expect(s.find('verifactu-correction-pending').exists()).toBe(false);
  });

  it('opening it goes to the record that corrects it and never reaches what holds it (the row it sits in)', async () => {
    const s = await setup({ status: 'corrected', correctedById: 'r9' });
    const push = vi.spyOn(s.router, 'push');
    const outer = vi.fn();
    const holder = s.wrapper.element.parentElement as HTMLElement;
    holder.addEventListener('click', outer);
    holder.addEventListener('keydown', outer);
    const link = s.find('verifactu-correction-corrected');
    // A clickable row opens its own record on Enter and Space: the link's keys stay the link's.
    await link.trigger('keydown', { key: 'Enter' });
    await link.trigger('keydown', { key: ' ' });
    await link.trigger('click');
    await flush();
    expect(push).toHaveBeenCalledWith('/verifactu/records/r9');
    expect(outer).not.toHaveBeenCalled();
  });

  it('one left to correct says so, in amber', async () => {
    const s = await setup({ status: 'pending' });
    const pill = s.wrapper.findComponent(StatusPill);
    expect([pill.attributes('data-testid'), pill.props('label'), pill.props('tone')]).toEqual([
      'verifactu-correction-pending',
      'Pending correction',
      'warning',
    ]);
    expect(s.find('verifactu-correction-corrected').exists()).toBe(false);
  });

  it('a record no correction answers shows nothing', async () => {
    const s = await setup({ status: 'not_applicable' });
    expect(s.wrapper.findComponent(StatusPill).exists()).toBe(false);
    expect(s.wrapper.find('a').exists()).toBe(false);
  });

  it('in Spanish, «Subsanado» and «Pendiente de subsanar»', async () => {
    const corrected = await setup({ status: 'corrected', correctedById: 'r9' }, 'es');
    expect(corrected.wrapper.findComponent(StatusPill).props('label')).toBe('Subsanado');
    expect(corrected.find('verifactu-correction-corrected').attributes('aria-label')).toBe(
      'Subsanado: abrir el registro que lo subsana',
    );
    const pending = await setup({ status: 'pending' }, 'es');
    expect(pending.wrapper.findComponent(StatusPill).props('label')).toBe('Pendiente de subsanar');
  });

  it('takes the size of the pills beside it', async () => {
    const s = await setup({ status: 'pending', size: 'sm' });
    expect(s.wrapper.findComponent(StatusPill).props('size')).toBe('sm');
  });
});
