// What the tests of Reservations' two lists, the bookings and the waitlist, check alike of their layout: the column
// filters wait behind the table's funnel, so the list fills the page from the topbar to the tabbar.
import type { VueWrapper } from '@vue/test-utils';
import { expect, it } from 'vitest';

import { listFillProblems } from '../../../../frontend/testing/list-fill';

export function itFillsThePage(setup: () => Promise<{ wrapper: VueWrapper; prop: <T = unknown>(name: string) => T }>): void {
  it('keeps its column filters behind the table’s funnel: the list is not pushed down', async () => {
    const s = await setup();
    expect(s.prop('filterable')).toBe(true);
  });

  it('AppPage `fill` and its DataTable `fill`, only stacks between them: from the topbar to the tabbar', async () => {
    const s = await setup();
    expect(listFillProblems(s.wrapper)).toEqual([]);
  });
}
