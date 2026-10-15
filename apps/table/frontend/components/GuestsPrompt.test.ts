// The guests prompt (WORKBOOK «Plano de sala»; TABLE-F10, F14): «Guests at table N · 4 pax», «−» and «+»
// (never below 1), quick taps from 1 to 8 that seat at once, «Above the table capacity (4)» when there are
// more — it warns, it does not stop — and «Back» / «Seat N». Correcting an occupied table says «Save».
import { describe, expect, it } from 'vitest';

import { click, mountTable } from '../__tests__/mount-table';
import GuestsPrompt from './GuestsPrompt.vue';

async function prompt(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountTable(GuestsPrompt, { props: { number: '4', capacity: 4, initial: 4, mode: 'seat', ...props }, locale });
  const el = (name: string) => m.wrapper.find(`[data-testid="table-guests-${name}"]`).element as HTMLElement & { disabled?: boolean };
  const confirmed = () => (m.wrapper.emitted('confirm') ?? []).map(([n]) => n);
  return { ...m, el, confirmed };
}

describe('GuestsPrompt', () => {
  it('asks the guests at the table with its capacity, from the number given', async () => {
    const p = await prompt({ initial: 3 });
    expect(p.el('title').textContent?.trim()).toBe('Guests at table 4 · 4 pax');
    expect(p.el('value').textContent?.trim()).toBe('3');
    expect(p.el('confirm').textContent?.trim()).toBe('Seat 3');
  });

  it('counts with «−» and «+», never below one, and warns above the capacity without stopping', async () => {
    const p = await prompt({ initial: 1 });
    await click(p.el('fewer'));
    expect(p.el('value').textContent?.trim()).toBe('1');
    expect(p.el('fewer').disabled).toBe(true);
    for (let i = 0; i < 4; i += 1) await click(p.el('more'));
    expect(p.el('value').textContent?.trim()).toBe('5');
    expect(p.el('over').textContent?.trim()).toBe('Above the table capacity (4)');
    await click(p.el('confirm'));
    expect(p.confirmed()).toEqual([5]);
  });

  it('a quick tap seats at once', async () => {
    const p = await prompt();
    await click(p.el('quick-2'));
    expect(p.confirmed()).toEqual([2]);
  });

  it('correcting the guests: a quick tap only sets them, «Save» saves', async () => {
    const p = await prompt({ mode: 'edit', initial: 3 });
    await click(p.el('quick-6'));
    expect(p.confirmed()).toEqual([]);
    expect(p.el('confirm').textContent?.trim()).toBe('Save');
    await click(p.el('confirm'));
    expect(p.confirmed()).toEqual([6]);
  });

  it('«Back» goes back, and nothing is sent twice while it runs', async () => {
    const p = await prompt({ pending: true });
    expect(p.el('confirm').disabled).toBe(true);
    await click(p.el('back'));
    expect(p.wrapper.emitted('back')).toHaveLength(1);
  });

  it('speaks Spanish', async () => {
    const p = await prompt({ initial: 2 }, 'es');
    expect(p.el('title').textContent?.trim()).toBe('Comensales en la mesa 4 · 4 pax');
    expect(p.el('confirm').textContent?.trim()).toBe('Sentar 2');
  });
});
