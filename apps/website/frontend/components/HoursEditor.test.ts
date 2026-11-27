// HoursEditor: the week, Monday first; each day open or closed, with up to three intervals of two times.
import { TimeField } from '@erplora/ui/components';
import { describe, expect, it } from 'vitest';

import { pick, picked } from '../../../../base/frontend/__tests__/date-time-fields';
import { iconOnly, iconOnlyNamed } from '../../../../base/frontend/__tests__/icon-only';
import { ionChecked, mountWebsite, settle } from '../__tests__/mount-website';
import { defaultHours } from '../lib/hours';
import type { DayHours } from '../operations';
import HoursEditor from './HoursEditor.vue';

async function editor(props: Record<string, unknown> = {}) {
  const { wrapper } = await mountWebsite(HoursEditor, { props: { modelValue: defaultHours(), ...props } });
  const last = (): DayHours[] => {
    const emitted = wrapper.emitted('update:modelValue') ?? [];
    return emitted.at(-1)?.[0] as DayHours[];
  };
  return { wrapper, last };
}

describe('HoursEditor', () => {
  it('lists the seven days with their hours; a closed day says so', async () => {
    const { wrapper } = await editor();
    const rows = wrapper.findAll('[data-testid^="website-hours-day-"]');
    expect(rows.map((row) => row.attributes('data-testid'))).toEqual([
      'website-hours-day-mon',
      'website-hours-day-tue',
      'website-hours-day-wed',
      'website-hours-day-thu',
      'website-hours-day-fri',
      'website-hours-day-sat',
      'website-hours-day-sun',
    ]);
    // Text inside Ionic's elements (ion-toggle, ion-note) is read from the markup: happy-dom leaves it out of text().
    expect(rows[0].get('strong').element.textContent).toBe('Monday');
    expect(rows[0].findAll('ion-input')).toHaveLength(2);
    expect(rows[6].html()).toContain('Closed');
    expect(rows[0].html()).not.toContain('Closed');
    expect(rows[6].findAll('ion-input')).toHaveLength(0);
  });

  it('each time is the app’s own picker, shown in the app’s clock', async () => {
    const { wrapper } = await editor();
    const opens = wrapper.get('[data-testid="website-hours-mon-0-opens"]').element as HTMLElement & { value?: string; readonly?: boolean };
    expect([picked(opens), opens.value, opens.readonly]).toEqual(['09:00', expect.stringMatching(/^09:00\sAM$/), true]);
    // An open day's interval needs both times: no «Clear», an interval goes with its own ✕.
    const times = wrapper.findAllComponents(TimeField);
    expect([times.length, times.every((field) => field.props('required'))]).toEqual([wrapper.findAll('ion-input').length, true]);
  });

  it('opens and closes a day', async () => {
    const { wrapper, last } = await editor();
    await ionChecked(wrapper.get('[data-testid="website-hours-open-sun"]').element, true);
    expect(last()[6]).toEqual({ day: 'sun', intervals: [{ opens: '09:00', closes: '18:00' }] });
    await ionChecked(wrapper.get('[data-testid="website-hours-open-mon"]').element, false);
    expect(last()[0]).toEqual({ day: 'mon', intervals: [] });
  });

  it('«Add hours» and «Remove» of a day are their icons alone, named and titled by their labels', async () => {
    const { wrapper } = await editor();
    expect([iconOnly(wrapper.get('[data-testid="website-hours-add-mon"]')), iconOnly(wrapper.get('[data-testid="website-hours-mon-0-remove"]'))]).toEqual([
      iconOnlyNamed('Add hours'),
      iconOnlyNamed('Remove these hours'),
    ]);
  });

  it('changes a time and adds and removes intervals, three at most', async () => {
    const { wrapper, last } = await editor();
    await pick(wrapper.get('[data-testid="website-hours-mon-0-closes"]').element, '14:00');
    expect(last()[0].intervals).toEqual([{ opens: '09:00', closes: '14:00' }]);
    await wrapper.setProps({ modelValue: last() });
    await wrapper.get('[data-testid="website-hours-add-mon"]').trigger('click');
    expect(last()[0].intervals).toHaveLength(2);
    await wrapper.setProps({ modelValue: last() });
    await wrapper.get('[data-testid="website-hours-add-mon"]').trigger('click');
    await wrapper.setProps({ modelValue: last() });
    await settle();
    expect(wrapper.find('[data-testid="website-hours-add-mon"]').exists()).toBe(false);
    await wrapper.get('[data-testid="website-hours-mon-1-remove"]').trigger('click');
    expect(last()[0].intervals).toHaveLength(2);
  });

  it('shows the server’s refusal and, disabled, changes nothing', async () => {
    const { wrapper } = await editor({ error: 'The opening and the closing time cannot be the same.', disabled: true });
    expect(wrapper.get('[data-testid="website-hours-error"]').text()).toContain('cannot be the same');
    const times = wrapper.findAllComponents(TimeField);
    expect([times.length > 0, times.every((field) => field.props('disabled'))]).toEqual([true, true]);
    await wrapper.get('[data-testid="website-hours-add-mon"]').trigger('click');
    expect(wrapper.emitted('update:modelValue')).toBeUndefined();
  });
});
