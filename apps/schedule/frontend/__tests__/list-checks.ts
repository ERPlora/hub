// What the tests of Schedule's two lists, temporary changes and special days, check alike: an employee only reads
// them, and one that does not load says which list before the cause. Each list's test passes its own setup.
import type { OpName } from '@erplora/ui/sdk';
import { expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, type MountOptions, type mountSchedule } from './mount-schedule';

/** A list of Schedule as its test sets it up: mounted, live, with its DataTable's props and a page to show. */
export type ScheduleList = Awaited<ReturnType<typeof mountSchedule>> & {
  prop: <T = unknown>(name: string) => T;
  show: (data: unknown) => Promise<void>;
};

export function itOnlyReadsForAnEmployee(setup: (options: MountOptions) => Promise<ScheduleList>, firstPage: unknown): void {
  it('an employee only reads', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(firstPage);
    expect([s.prop('addable'), s.prop('rowClickable'), s.prop('actions')]).toEqual([false, false, []]);
  });
}

/** The list of `op`, which names itself in Spanish as `title` when it does not load. */
export function itNamesTheListThatDoesNotLoad(setup: (options: MountOptions) => Promise<ScheduleList>, op: OpName, title: string): void {
  it('a list that does not load names itself, then the cause, never the generic text', async () => {
    const s = await setup({ locale: 'es' });
    s.net.lastStream().push(errorFrame(s.subId(op), 'boom'));
    await flush();
    const box = s.wrapper.find('.data-table__error');
    expect(box.find('.data-table__error-title').text()).toBe(title);
    expect(box.find('.data-table__error-reason').text()).toBe('msg boom');
    expect(box.text()).not.toContain('No se han podido cargar los datos');
  });
}
