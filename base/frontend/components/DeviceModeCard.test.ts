// «This device» of Settings › General (BASE-G72): whether the device in hand is shared (the PIN pad, a shift) or
// personal (the session stays open). The mark moves only when the Hub confirms; only an administrator changes it; a
// browser that is not a device of the business yet says how to make it one.
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { DeviceCurrent } from '../operations';
import DeviceModeCard from './DeviceModeCard.vue';

const SHARED: DeviceCurrent = { known: true, mode: 'shared', mode_set_by: '', mode_set_at: null };

async function card(data: DeviceCurrent | null = SHARED, options: Parameters<typeof mountBase>[1] = {}, answer?: () => Response) {
  const mounted = await mountBase(DeviceModeCard, { ...options, onApi: answer ?? (() => Response.json({ ...SHARED, mode: 'personal' })) });
  const call = await mounted.live();
  if (data) await mounted.result(call, 'base.device.current', data);
  const choose = async (mode: string) => {
    mounted.wrapper.get('[data-testid="device-mode"]').element.dispatchEvent(new CustomEvent('ionChange', { detail: { value: mode } }));
    await flush();
  };
  const sent = () => mounted.net.api.filter((c) => c.url.startsWith('/api/device/mode')).map((c) => JSON.parse(String(c.init.body)));
  return { ...mounted, call, choose, sent };
}

/** An Ionic control's state is a property of its element, not an attribute. */
const prop = (wrapper: { get: (s: string) => { element: Element } }, testid: string, name: string): unknown =>
  (wrapper.get(`[data-testid="${testid}"]`).element as unknown as Record<string, unknown>)[name];

afterEach(() => {
  document.body.innerHTML = '';
});

describe('DeviceModeCard', () => {
  it('says how the device asks, with both choices and what each one does', async () => {
    const { wrapper } = await card();
    expect(wrapper.text()).toContain('This device');
    // The choices are slotted into ion-radio, whose shadow root hides them from the card's text: read its labels.
    const choices = wrapper.findAll('ion-radio ion-label').map((label) => label.element.innerHTML);
    expect(choices[0]).toContain('Shared — a till or tablet several people use');
    expect(choices[1]).toContain('Personal — a device only you use');
    expect(prop(wrapper, 'device-mode', 'value')).toBe('shared');
  });

  it('an administrator changes it, and the mark is the Hub’s answer', async () => {
    const { wrapper, choose, sent } = await card();
    await choose('personal');
    expect(sent()).toEqual([{ mode: 'personal' }]);
    expect(prop(wrapper, 'device-mode', 'value')).toBe('personal');
  });

  it('a refusal leaves the mark where it was and says so', async () => {
    const refuse = () => Response.json({ error: { code: 'unexpected', message: 'boom' } }, { status: 500 });
    const { wrapper, choose } = await card(SHARED, {}, refuse);
    await choose('personal');
    expect(prop(wrapper, 'device-mode', 'value')).toBe('shared');
    expect(wrapper.get('[data-testid="device-mode-error"]').text()).toContain('Could not change this device.');
  });

  it('whoever does not run the hub sees it, disabled, and why', async () => {
    const { wrapper } = await card(SHARED, { session: EMPLOYEE });
    expect([prop(wrapper, 'device-mode-shared', 'disabled'), prop(wrapper, 'device-mode-personal', 'disabled')]).toEqual([true, true]);
    expect(wrapper.text()).toContain('Only an administrator can change how people enter on this device.');
  });

  it('a browser that is not a device of the business yet says how to become one', async () => {
    const { wrapper } = await card({ ...SHARED, known: false });
    expect(wrapper.get('[data-testid="device-mode-unknown"]').text()).toContain('enter once here with your account');
    expect(wrapper.find('[data-testid="device-mode"]').exists()).toBe(false);
  });

  it('a device that cannot be read says so', async () => {
    const { wrapper, call, client } = await card(null);
    call.push(errorFrame(subId(client, 'base.device.current'), 'unexpected'));
    await flush();
    expect(wrapper.get('[data-testid="device-mode-load-error"]').text()).toContain('Could not load this device.');
  });
});
