// «PIN pad» of Settings › General (BASE-G151, G62): whether the business asks who is at the till, when it asks again
// (after 1, 5, 10, 15 or 30 idle minutes, or until signing out) and how many digits a PIN has. Each control saves on
// its own, at once, only its own key, and the card paints what the Hub confirms. Off and on again is the factory
// choice (per shift), never the minutes of before.
import { afterEach, describe, expect, it } from 'vitest';

import { EMPLOYEE, errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { AccessSettings } from '../operations';
import PinPolicyCard from './PinPolicyCard.vue';

const FACTORY: AccessSettings = { pin_policy: 'per_shift', pin_inactivity_minutes: 5, pin_length: 4, can_change: true };

async function card(data: AccessSettings | null = FACTORY, options: Parameters<typeof mountBase>[1] = {}, refuse = false) {
  const mounted = await mountBase(PinPolicyCard, {
    ...options,
    onApi: ({ init }) =>
      refuse
        ? Response.json({ error: { code: 'unexpected', message: 'boom' } }, { status: 500 })
        : Response.json({ ...(data ?? FACTORY), ...JSON.parse(String(init.body)) }),
  });
  const call = await mounted.live();
  if (data) await mounted.result(call, 'base.access.settings', data);
  const sent = () =>
    mounted.net.api.filter((c) => c.url.startsWith('/api/access/settings/update')).map((c) => JSON.parse(String(c.init.body)));
  const fire = async (testid: string, detail: Record<string, unknown>) => {
    mounted.wrapper.get(`[data-testid="${testid}"]`).element.dispatchEvent(new CustomEvent('ionChange', { detail }));
    await flush();
  };
  return { ...mounted, call, sent, fire };
}

/** An Ionic control's state is a property of its element, not an attribute. */
const prop = (wrapper: { get: (s: string) => { element: Element } }, testid: string, name: string): unknown =>
  (wrapper.get(`[data-testid="${testid}"]`).element as unknown as Record<string, unknown>)[name];

afterEach(() => {
  document.body.innerHTML = '';
});

describe('PinPolicyCard', () => {
  it('on: what it means, when it asks again and the digits', async () => {
    const { wrapper } = await card();
    expect(prop(wrapper, 'pin-policy-show', 'checked')).toBe(true);
    expect(wrapper.text()).toContain('Staff choose their name and type their PIN');
    expect(prop(wrapper, 'pin-policy-again', 'value')).toBe('shift');
    expect(wrapper.text()).toContain('The PIN pad asks again when the session ends');
    expect(prop(wrapper, 'pin-policy-digits', 'value')).toBe('4');
  });

  it('a stop of minutes asks always, after those idle minutes, and says what happens', async () => {
    const { wrapper, sent, fire } = await card();
    await fire('pin-policy-again', { value: '10' });
    expect(sent()).toEqual([{ pin_policy: 'always', pin_inactivity_minutes: 10 }]);
    expect(wrapper.text()).toContain('A till nobody touches for 10 minutes closes the session and shows the PIN pad');
  });

  it('«Until signing out» is per shift', async () => {
    const { sent, fire } = await card({ ...FACTORY, pin_policy: 'always', pin_inactivity_minutes: 15 });
    await fire('pin-policy-again', { value: 'shift' });
    expect(sent()).toEqual([{ pin_policy: 'per_shift' }]);
  });

  it('off: nobody types a PIN, and the consequence is spelled out; on again is the factory choice', async () => {
    const { wrapper, sent, fire } = await card({ ...FACTORY, pin_policy: 'always', pin_inactivity_minutes: 15 });
    await fire('pin-policy-show', { checked: false });
    expect(wrapper.text()).toContain('Nobody types a PIN.');
    expect(wrapper.find('[data-testid="pin-policy-again"]').exists()).toBe(false);
    await fire('pin-policy-show', { checked: true });
    expect(sent()).toEqual([{ pin_policy: 'never' }, { pin_policy: 'per_shift' }]);
  });

  it('the digits save on their own', async () => {
    const { wrapper, sent, fire } = await card();
    await fire('pin-policy-digits', { value: '6' });
    expect(sent()).toEqual([{ pin_length: 6 }]);
    expect(prop(wrapper, 'pin-policy-digits', 'value')).toBe('6');
    expect(wrapper.text()).toContain('Everyone types the same number of digits');
  });

  it('a refusal keeps what the Hub has and says so', async () => {
    const { wrapper, fire } = await card(FACTORY, {}, true);
    await fire('pin-policy-digits', { value: '6' });
    expect(prop(wrapper, 'pin-policy-digits', 'value')).toBe('4');
    expect(wrapper.get('[data-testid="pin-policy-error"]').text()).toContain('Could not change it.');
  });

  it('whoever does not run the hub sees it, disabled, and why', async () => {
    const { wrapper } = await card({ ...FACTORY, can_change: false }, { session: EMPLOYEE });
    expect(prop(wrapper, 'pin-policy-show', 'disabled')).toBe(true);
    expect(wrapper.text()).toContain('Only an administrator can change whether it asks.');
  });

  it('settings that cannot be read say so', async () => {
    const { wrapper, call, client } = await card(null);
    call.push(errorFrame(subId(client, 'base.access.settings'), 'unexpected'));
    await flush();
    expect(wrapper.find('[data-testid="pin-policy-load-error"]').exists()).toBe(true);
  });
});
