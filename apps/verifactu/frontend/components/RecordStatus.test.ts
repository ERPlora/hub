// A record's status, the same in the Records list and in the record's detail: its coloured pill and, by a rejection (or an
// acceptance with errors), whether it is corrected (VERIFACTU-F24): «Corrected», a link to the record that corrects it,
// or «Pending correction»; nothing more for a record no correction answers. The pills sit together, spaced, and wrap
// under each other when there is no room.
import { StatusPill } from '@erplora/ui/components';
import { describe, expect, it, vi } from 'vitest';

import { flush, mountVerifactu } from '../__tests__/mount-verifactu';
import type { RecordRowOut } from '../operations';
import RecordStatus from './RecordStatus.vue';

type Shown = Pick<RecordRowOut, 'status' | 'correction_status' | 'corrected_by_id'>;

async function setup(record: Partial<Shown>, props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const full: Shown = { status: 'rejected', correction_status: 'not_applicable', corrected_by_id: null, ...record };
  const m = await mountVerifactu(RecordStatus, { props: { record: full, testid: 'verifactu-x-status', ...props }, locale });
  const pills = () => m.wrapper.findAllComponents(StatusPill).map((pill) => [pill.props('label'), pill.props('tone')]);
  return { ...m, pills };
}

describe('RecordStatus', () => {
  it('its status pill, in its tone, under the testid it is given', async () => {
    const s = await setup({ status: 'accepted' });
    expect(s.pills()).toEqual([['Accepted', 'success']]);
    expect(s.find('verifactu-x-status').text()).toBe('Accepted');
  });

  it('a corrected one links to the record that corrects it, beside its status', async () => {
    const s = await setup({ correction_status: 'corrected', corrected_by_id: 'r9' });
    expect(s.pills()).toEqual([
      ['Rejected', 'danger'],
      ['Corrected', 'success'],
    ]);
    const link = s.find('verifactu-correction-corrected');
    expect(link.element.tagName).toBe('A');
    expect(link.attributes('href')).toBe('/verifactu/records/r9');
    expect(link.attributes('aria-label')).toBe('Corrected: open the record that corrects it');
    // Both in the one box that spaces them, the status first.
    expect(link.element.parentElement).toBe(s.find('verifactu-x-status').element.parentElement);
    expect(s.find('verifactu-correction-pending').exists()).toBe(false);
  });

  it('opening it goes to the record that corrects it and never reaches what holds it (the row it sits in)', async () => {
    const s = await setup({ correction_status: 'corrected', corrected_by_id: 'r9' });
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
    const s = await setup({ status: 'accepted_with_errors', correction_status: 'pending' });
    expect(s.pills()).toEqual([
      ['Accepted with errors', 'warning'],
      ['Pending correction', 'warning'],
    ]);
    expect(s.find('verifactu-correction-pending').text()).toBe('Pending correction');
    expect(s.find('verifactu-correction-corrected').exists()).toBe(false);
  });

  it('a record no correction answers shows only its status', async () => {
    const s = await setup({ status: 'pending' });
    expect(s.pills()).toEqual([['Pending', 'warning']]);
    expect(s.wrapper.find('a').exists()).toBe(false);
  });

  it('in Spanish, «Subsanado» and «Pendiente de subsanar»', async () => {
    const corrected = await setup({ correction_status: 'corrected', corrected_by_id: 'r9' }, {}, 'es');
    expect(corrected.pills().map(([label]) => label)).toEqual(['Rechazado', 'Subsanado']);
    expect(corrected.find('verifactu-correction-corrected').attributes('aria-label')).toBe('Subsanado: abrir el registro que lo subsana');
    const pending = await setup({ correction_status: 'pending' }, {}, 'es');
    expect(pending.pills().map(([label]) => label)).toEqual(['Rechazado', 'Pendiente de subsanar']);
  });

  it('every pill takes the size it is given', async () => {
    const s = await setup({ correction_status: 'pending' }, { size: 'sm' });
    expect(s.wrapper.findAllComponents(StatusPill).map((pill) => pill.props('size'))).toEqual(['sm', 'sm']);
  });
});
