// «Duration (min)» of the booking panel (APPOINTMENT-F01, F04): one tap for 15, 30, 45, 60, 90 and 120 minutes, and
// «Other» to type it. It shows the length the panel holds (the services' sum unless changed); a length that is not one
// of the buttons comes with «Other» pressed and typed in. Once changed, «Use the sum» goes back to the services' sum.
import { describe, expect, it } from 'vitest';

import { ionValue, mountAppointment, settle } from '../__tests__/mount-appointment';
import DurationPicker from './DurationPicker.vue';

async function setup(props: Record<string, unknown> = {}, locale: 'en' | 'es' = 'en') {
  const m = await mountAppointment(DurationPicker, { props: { minutes: '30', sum: '30', touched: false, name: 'minutes', ...props }, locale });
  const choice = (id: string) => m.wrapper.find(`[data-testid=appointment-form-duration-${id}]`);
  const pressed = () => m.wrapper.findAll('[aria-pressed=true]').map((b) => b.text());
  const other = () => m.inDoc('appointment-form-minutes') as (HTMLElement & { value?: string; label?: string; errorText?: string }) | null;
  return { ...m, choice, pressed, other };
}

describe('DurationPicker', () => {
  it('offers the usual lengths and «Other» as one group named after the field, the length held pressed', async () => {
    const s = await setup();
    const group = s.wrapper.get('[role=group]');
    expect(s.wrapper.get(`#${group.attributes('aria-labelledby')}`).text()).toBe('Duration (min)');
    expect(group.findAll('button').map((b) => b.text())).toEqual(['15', '30', '45', '60', '90', '120', 'Other']);
    expect(s.choice('30').attributes('aria-label')).toBe('30 min');
    expect(s.pressed()).toEqual(['30']);
    expect(s.other()).toBeNull();
    expect(s.find('appointment-form-duration-sum').text()).toBe('Sum of the services: 30 min');
  });

  it('a tap chooses a length; «Other» opens the field to type it, and what is typed is the length', async () => {
    const s = await setup();
    await s.choice('60').trigger('click');
    expect(s.wrapper.emitted('type')).toEqual([['60']]);
    await s.choice('other').trigger('click');
    expect(s.pressed()).toEqual(['Other']);
    expect(s.other()?.label).toBe('Duration (min)');
    await ionValue(s.other()!, '50', 'ionInput');
    expect(s.wrapper.emitted('type')?.at(-1)).toEqual(['50']);
  });

  it('a length that is not a button comes with «Other» pressed and typed in, and stays open while typing', async () => {
    const s = await setup({ minutes: '75', sum: '75' });
    expect(s.pressed()).toEqual(['Other']);
    expect(s.other()?.value).toBe('75');
    await s.wrapper.setProps({ minutes: '6', touched: true });
    await s.wrapper.setProps({ minutes: '60' });
    await settle();
    expect(s.pressed()).toEqual(['Other']);
    expect(s.other()).not.toBeNull();
  });

  it('follows the services’ sum while untouched, onto a button or off it', async () => {
    const s = await setup({ minutes: '75', sum: '75' });
    await s.wrapper.setProps({ minutes: '30', sum: '30' });
    await settle();
    expect(s.pressed()).toEqual(['30']);
    expect(s.other()).toBeNull();
  });

  it('«Use the sum» shows once the length was changed away from the sum, and asks for it', async () => {
    const s = await setup({ minutes: '60', touched: true });
    expect(s.choice('use-sum').text()).toBe('Use the sum');
    await s.choice('use-sum').trigger('click');
    expect(s.wrapper.emitted('useSum')).toHaveLength(1);
    await s.wrapper.setProps({ minutes: '30', touched: false });
    expect(s.choice('use-sum').exists()).toBe(false);
  });

  it('nothing is pressed nor summed before any service', async () => {
    const s = await setup({ minutes: '', sum: '' });
    expect(s.pressed()).toEqual([]);
    expect(s.find('appointment-form-duration-sum').exists()).toBe(false);
  });

  it('a refused length opens its field with the reason under it; a charged appointment locks it all', async () => {
    const s = await setup({ errorText: 'Too long.' });
    expect(s.other()?.errorText).toBe('Too long.');
    const locked = await setup({ disabled: true, minutes: '50' });
    expect(locked.wrapper.findAll('button').every((b) => b.attributes('disabled') !== undefined)).toBe(true);
    expect((locked.other() as HTMLElement & { disabled?: boolean }).disabled).toBe(true);
  });

  it('speaks Spanish', async () => {
    const s = await setup({ minutes: '60', touched: true }, 'es');
    expect(s.choice('other').text()).toBe('Otra');
    expect(s.choice('other').attributes('aria-label')).toBe('Otra duración');
    expect(s.find('appointment-form-duration-sum').text()).toContain('Suma de los servicios: 30 min');
    expect(s.choice('use-sum').text()).toBe('Usar la suma');
  });
});
