// The test helper of the date and time fields picks in DateField and TimeField as their picker does: the page's
// v-model takes the value and the form around the field hears a native `input`, as FormModal listens for; it reads
// what a field holds, and it says so when the element is no such field.
import { DateField, TimeField } from '@erplora/ui/components';
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { defineComponent, h, ref } from 'vue';

import { createShellI18n } from '../../../packages/ui/src/shell/i18n';
import { pick, picked } from './date-time-fields';

function mountForm() {
  const day = ref('2026-10-19');
  const time = ref('');
  const heard: string[] = [];
  const Form = defineComponent({
    setup: () => () =>
      h('form', { onInput: (event: Event) => heard.push((event.target as HTMLElement).dataset.testid ?? '') }, [
        h(DateField, { testid: 'thing-day', label: 'Day', modelValue: day.value, 'onUpdate:modelValue': (v: string) => (day.value = v) }),
        h(TimeField, { testid: 'thing-time', label: 'Time', modelValue: time.value, 'onUpdate:modelValue': (v: string) => (time.value = v) }),
        h('ion-input', { 'data-testid': 'thing-notes' }),
      ]),
  });
  const wrapper = mount(Form, { attachTo: document.body, global: { plugins: [createShellI18n({ locale: 'en' })] } });
  const field = (testid: string) => wrapper.element.querySelector(`[data-testid="${testid}"]`);
  return { wrapper, day, time, heard, field };
}

describe('pick and picked: the date and time fields in a component test', () => {
  it('picks a day and a time as their picker does, and the form hears each', async () => {
    const s = mountForm();
    expect([picked(s.field('thing-day')), picked(s.field('thing-time'))]).toEqual(['2026-10-19', '']);
    await pick(s.field('thing-day'), '2026-11-02');
    await pick(s.field('thing-time'), '09:30');
    expect([s.day.value, s.time.value]).toEqual(['2026-11-02', '09:30']);
    expect([picked(s.field('thing-day')), picked(s.field('thing-time'))]).toEqual(['2026-11-02', '09:30']);
    expect(s.heard).toEqual(['thing-day', 'thing-time']);
    s.wrapper.unmount();
  });

  it('empties a field as Clear does', async () => {
    const s = mountForm();
    await pick(s.field('thing-day'), '');
    expect(s.day.value).toBe('');
    s.wrapper.unmount();
  });

  it('says so when the element is no date or time field', async () => {
    const s = mountForm();
    await expect(pick(s.field('thing-notes'), '2026-11-02')).rejects.toThrow(/thing-notes is no date or time field/);
    expect(() => picked(null)).toThrow(/no date or time field/);
    s.wrapper.unmount();
  });
});
