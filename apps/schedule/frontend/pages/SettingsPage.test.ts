// Schedules → Settings (SCHEDULE-F08, F09; WORKBOOK «Pantallas · Ajustes»): read-only «Business
// timezone» with its name and the note, then «Week starts» (Monday or Sunday) and «Save»
// (`schedule.settings.update`) for whoever may change the settings. «Week starts» only shows once the
// settings were read (never a value that was not read); a failure says so with «Retry». An employee reads.
import { InlineFeedback } from '@erplora/ui/components';
import { AppPage } from '@erplora/ui/shell';
import { describe, expect, it, vi } from 'vitest';

import { EMPLOYEE, errorFrame, flush, ionValue, type MountOptions, mountSchedule, settle } from '../__tests__/mount-schedule';
import SettingsPage from './SettingsPage.vue';

vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

const OP = 'schedule.settings.get';
const SETTINGS = { week_starts_on: 1, hours_confirmed: false, timezone: 'Europe/Madrid' };

type Control = HTMLElement & { value?: unknown; label?: string; disabled?: boolean };

async function setup(options: MountOptions = {}) {
  const m = await mountSchedule(SettingsPage, { path: '/schedule/settings', ...options });
  await m.live();
  const control = () => m.find('schedule-settings-week-start').element as Control;
  return { ...m, control, show: (data: unknown) => m.result(OP, data) };
}

describe('SettingsPage', () => {
  it('follows schedule.settings.get under «Schedules»; «Loading…» until it answers', async () => {
    const s = await setup();
    expect(s.params(OP)).toEqual([{}]);
    expect(s.wrapper.findComponent(AppPage).props('title')).toBe('Schedules');
    expect(s.find('schedule-settings-loading').text()).toBe('Loading…');
    expect(s.find('schedule-settings-week-start').exists()).toBe(false);
  });

  it('shows the business timezone, read only, and «Week starts» with Monday and Sunday', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    expect(s.find('schedule-settings-timezone').text()).toContain('Business timezone');
    expect(s.find('schedule-settings-timezone').text()).toContain('Europe/Madrid');
    expect(s.find('schedule-settings-timezone').text()).toContain("It is the Hub's, and the single clock the schedule is read with.");
    expect([s.control().label, s.control().value]).toEqual(['Week starts', 1]);
    const options = s.wrapper.findAll('[data-testid="schedule-settings-week-start"] ion-select-option').map((o) => o.text());
    expect(options).toEqual(['Monday', 'Sunday']);
  });

  it('«Save» sends the day the week starts on and says it saved', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(200, { ...SETTINGS, week_starts_on: 7 });
    await ionValue(s.control(), 7);
    await s.find('schedule-settings-submit').trigger('click');
    await settle();
    expect(s.sent()).toEqual([{ method: 'POST', path: '/api/schedule/settings', query: {}, body: { week_starts_on: 7 } }]);
    expect(s.find('schedule-settings-saved').text()).toBe('Saved');
  });

  it('a refused save is said, and what was chosen stays', async () => {
    const s = await setup();
    await s.show(SETTINGS);
    s.answer(422, { error: { code: 'invalid_payload', message: 'Invalid payload', fields: { week_starts_on: 'Ensure this value is less than or equal to 7.' } } });
    await ionValue(s.control(), 7);
    await s.find('schedule-settings-submit').trigger('click');
    await settle();
    expect(s.find('schedule-settings-save-error').text()).toContain('Ensure this value is less than or equal to 7.');
    expect(s.control().value).toBe(7);
  });

  it('a failure to read says so with «Retry», and no value to save', async () => {
    const s = await setup();
    s.net.lastStream().push(errorFrame(s.subId(OP), 'boom'));
    await flush();
    expect(s.find('schedule-settings-load-error').text()).toContain('The settings could not be loaded.');
    expect(s.find('schedule-settings-retry').exists()).toBe(true);
    expect(s.find('schedule-settings-week-start').exists()).toBe(false);
  });

  it('an employee reads, without «Save»', async () => {
    const s = await setup({ session: EMPLOYEE });
    await s.show(SETTINGS);
    expect(s.control().disabled).toBe(true);
    expect(s.find('schedule-settings-submit').exists()).toBe(false);
    expect(s.wrapper.findAllComponents(InlineFeedback)).toHaveLength(0);
  });

  it('speaks Spanish with the old words', async () => {
    const s = await setup({ locale: 'es' });
    await s.show(SETTINGS);
    expect(s.find('schedule-settings-timezone').text()).toContain('Zona horaria del negocio');
    expect(s.control().label).toBe('Semana empieza');
    expect(s.find('schedule-settings-submit').text()).toBe('Guardar');
  });
});
