// The counts of a session (CASH_REGISTER-F06, F11; the old detail's «Counts» table): newest first, 50 a
// page, table or cards — When, Count type, Total counted, Notes. They re-run by themselves on a count.
import { DataTable } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { mountCash } from '../__tests__/mount-cash-register';
import { plain } from '../lib/money';
import SessionCounts from './SessionCounts.vue';

const OP = 'cash_register.count.list';

async function setup(locale: 'en' | 'es' = 'en') {
  const m = await mountCash(SessionCounts, { props: { sessionId: 's1' }, locale });
  await m.live();
  const cells = (i: number) =>
    m.wrapper.findAll('[data-testid="cash-register-session-counts-row"]')[i].findAll('[role="cell"]').map((c) => plain(c.text()).trim());
  return { ...m, cells };
}

describe('SessionCounts', () => {
  it('follows the session’s counts newest first', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{ session_id: 's1', sort: 'counted_at', dir: 'desc', limit: 50, offset: 0 }]);
    expect(s.wrapper.findComponent(DataTable as unknown as Component).props()).toMatchObject({ serverSide: true, pageSize: 50 });
  });

  it('paints the type, the total as money and the notes; empty says so', async () => {
    const s = await setup();
    await s.result(OP, {
      rows: [{ id: 'c1', session_id: 's1', type: 'closing', total: 10015, denominations: {}, notes: 'evening', counted_at: '2026-10-14T20:00:00Z', counted_by: 'ana' }],
      total: 1,
      limit: 50,
      offset: 0,
    });
    expect(s.cells(0).slice(1)).toEqual(['Closing', '€100.15', 'evening']);
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.find('cash-register-session-counts-empty').text()).toContain('No counts in this session.');
  });

  it('speaks Spanish', async () => {
    const s = await setup('es');
    await s.result(OP, { rows: [], total: 0, limit: 50, offset: 0 });
    expect(s.find('cash-register-session-counts-empty').text()).toContain('Sin arqueos en esta sesión.');
  });
});
