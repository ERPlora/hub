// THE interval editor (SCHEDULE-F02, F04, F05): one line per interval — «Opens», «Closes» and «Remove
// interval» — plus «+ Add interval» and the hint about split shifts and past-midnight intervals; the
// weekly day, the special day and the override share it, as in the old screen. The server's refusal of
// the intervals goes under them.
import { describe, expect, it } from 'vitest';

import { click, ionValue, mountSchedule } from '../__tests__/mount-schedule';
import IntervalsEditor from './IntervalsEditor.vue';

type Field = HTMLElement & { value?: unknown; type?: string; label?: string; disabled?: boolean };

async function setup(modelValue = [{ open_time: '10:00', close_time: '14:00' }], props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountSchedule(IntervalsEditor, { props: { modelValue, testid: 'day', ...props }, locale });
  await m.wrapper.setProps({ 'onUpdate:modelValue': (value: unknown) => m.wrapper.setProps({ modelValue: value }) });
  const emitted = () => (m.wrapper.emitted('update:modelValue') ?? []).map((e) => e[0]);
  const field = (testid: string) => m.find(testid).element as Field;
  return { ...m, emitted, field };
}

describe('IntervalsEditor', () => {
  it('paints one line per interval with its two time fields', async () => {
    const s = await setup([
      { open_time: '10:00', close_time: '14:00' },
      { open_time: '17:00', close_time: '20:00' },
    ]);
    expect(s.wrapper.findAll('[data-testid^="day-interval-"]')).toHaveLength(2);
    expect([s.field('day-open-1').value, s.field('day-close-1').value]).toEqual(['17:00', '20:00']);
    expect([s.field('day-open-0').type, s.field('day-open-0').label, s.field('day-close-0').label]).toEqual(['time', 'Opens', 'Closes']);
    expect(s.find('day-hint').text()).toBe(
      'Split shifts: one line per interval (10:00–14:00 and 17:00–20:00). A closing time earlier than the opening one runs past midnight (22:00–02:00).',
    );
  });

  it('a typed time changes that line only', async () => {
    const s = await setup([
      { open_time: '10:00', close_time: '14:00' },
      { open_time: '17:00', close_time: '20:00' },
    ]);
    await ionValue(s.field('day-close-1'), '21:00', 'ionInput');
    expect(s.emitted().at(-1)).toEqual([
      { open_time: '10:00', close_time: '14:00' },
      { open_time: '17:00', close_time: '21:00' },
    ]);
  });

  it('«+ Add interval» adds a blank line; «Remove interval» takes one, never the last', async () => {
    const s = await setup();
    expect(s.field('day-remove-0').disabled).toBe(true);
    await click(s.find('day-add').element);
    expect(s.emitted().at(-1)).toEqual([
      { open_time: '10:00', close_time: '14:00' },
      { open_time: '', close_time: '' },
    ]);
    expect(s.find('day-add').text()).toBe('+ Add interval');
    expect(s.field('day-remove-1').getAttribute('aria-label')).toBe('Remove interval');
    await click(s.find('day-remove-0').element);
    expect(s.emitted().at(-1)).toEqual([{ open_time: '', close_time: '' }]);
  });

  it('says the server’s refusal under the lines', async () => {
    const s = await setup(undefined, { error: 'Two intervals overlap.' });
    expect(s.find('day-error').text()).toBe('Two intervals overlap.');
  });

  it('speaks Spanish', async () => {
    const s = await setup(undefined, {}, 'es');
    expect([s.field('day-open-0').label, s.field('day-close-0').label, s.find('day-add').text()]).toEqual(['Abre', 'Cierra', '+ Añadir tramo']);
  });
});
