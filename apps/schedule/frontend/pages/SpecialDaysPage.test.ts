// Schedules → Special days (WORKBOOK «Pantallas · Días especiales»): two tables one under the other,
// each with its title — «Special days» and «Overrides» —, under «Schedules» with the three tabs.
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { mountSchedule } from '../__tests__/mount-schedule';
import OverridesList from '../components/OverridesList.vue';
import SpecialDaysList from '../components/SpecialDaysList.vue';
import SpecialDaysPage from './SpecialDaysPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

describe('SpecialDaysPage', () => {
  it('holds the special days, then the overrides, under «Schedules» with its tabs', async () => {
    const m = await mountSchedule(SpecialDaysPage, { path: '/schedule/special-days' });
    await m.live();
    const page = m.wrapper.findComponent(AppPage);
    expect(page.props('title')).toBe('Schedules');
    expect((page.props('tabs') as Array<{ id: string }>).map((t) => t.id)).toEqual(['hours', 'special_days', 'settings']);
    expect(m.wrapper.findComponent(SpecialDaysList).exists()).toBe(true);
    expect(m.wrapper.findComponent(OverridesList).exists()).toBe(true);
    const headings = m.wrapper.findAll('h3').map((h) => h.text());
    expect(headings).toEqual(['Special days', 'Overrides']);
    expect(m.params('schedule.special_day.list')).toHaveLength(1);
    expect(m.params('schedule.override.list')).toHaveLength(1);
  });
});
