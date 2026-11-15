// What the tests of Tasks' two lists, projects and tasks, check alike of their table's filters: they wait behind the
// toolbar's funnel, out of sight until it is pressed. Each list's test passes its own setup.
import type { VueWrapper } from '@vue/test-utils';
import { expect, it } from 'vitest';

import { flush } from './mount-task';

/** A list of Tasks as its test sets it up: mounted, live, with its DataTable's props and a page to show. */
export interface TaskList {
  wrapper: VueWrapper;
  prop: <T = unknown>(name: string) => T;
  show: (data: unknown) => Promise<void>;
}

/** The table whose test ids start with `id`, and one of its filters, `filter`. */
export function itKeepsTheFiltersBehindTheFunnel(setup: () => Promise<TaskList>, firstPage: unknown, id: string, filter: string): void {
  it('keeps the filters behind the toolbar funnel until it is pressed', async () => {
    const s = await setup();
    await s.show(firstPage);
    expect(s.prop('filterable')).toBe(true);
    expect(s.wrapper.find(`[data-testid="${id}-filters-toggle"]`).exists()).toBe(true);
    expect(s.wrapper.find(`[data-testid="${id}-filter-${filter}"]`).exists()).toBe(false);
    await s.wrapper.find(`[data-testid="${id}-filters-toggle"]`).trigger('click');
    await flush();
    expect(s.wrapper.find(`[data-testid="${id}-filters-panel"] [data-testid="${id}-filter-${filter}"]`).exists()).toBe(true);
  });
}
