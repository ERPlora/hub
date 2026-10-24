// «Access» (`/login`, BASE-G52, G55, G56, G57, G58): the door of a browser without a session. On a shared device of the
// hub of a business that asks, the PIN pad (faces, PIN, badge) and «Account»; elsewhere only «Enter with your account»
// (erplora.com's sign-in for this hub). What happened (the session ended, another device's entry ended it) on top.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import type { AccessDoor } from '../operations';
import LoginPage from './LoginPage.vue';

const access = vi.hoisted(() => ({ enterWith: vi.fn(), leaveTo: vi.fn() }));
vi.mock('../lib/access', async (original) => ({ ...(await original<typeof import('../lib/access')>()), ...access }));

const ANA = { id: 'c-ana', name: 'Ana López', initials: 'AL' };
const BEA = { id: 'c-bea', name: 'Bea', initials: 'B' };
const PIN_DOOR: AccessDoor = { pin: true, pin_length: 4, people: [ANA, BEA], wait: 0, plan_url: 'https://erplora.example/store/plans' };
const NO_PIN: AccessDoor = { ...PIN_DOOR, pin: false, people: [] };

function answering(...doors: (AccessDoor | Response)[]) {
  let call = 0;
  return () => {
    const next = doors[Math.min(call++, doors.length - 1)];
    return next instanceof Response ? next : Response.json(next);
  };
}

async function login(doors: (AccessDoor | Response)[], path = '/login?next=%2Fsale%2Fpos', locale: 'en' | 'es' = 'en') {
  const mounted = await mountBase(LoginPage, { path, routes: ['/login'], session: null, status: 'live', onApi: answering(...doors), locale });
  await flush();
  const press = async (digits: string) => {
    for (const digit of digits) await mounted.wrapper.get(`[data-testid="pinpad-key-${digit}"]`).trigger('click');
    await flush();
  };
  const doorCalls = () => mounted.net.api.filter((call) => call.url.startsWith('/api/access/door')).length;
  return { ...mounted, press, doorCalls };
}

beforeEach(() => {
  access.enterWith.mockReset();
  access.leaveTo.mockReset();
});

afterEach(() => {
  vi.useRealTimers();
  document.body.innerHTML = '';
});

describe('LoginPage — the PIN pad of a shared till', () => {
  it('opens on «PIN» with the faces and the badge hint, and «Account» beside it', async () => {
    const { wrapper } = await login([PIN_DOOR]);
    expect(wrapper.get('[data-testid="access-heading"]').text()).toBe('Enter your business');
    expect(wrapper.find('[data-testid="access-tabs"]').exists()).toBe(true);
    expect(wrapper.text()).toContain('Enter your PIN');
    expect(wrapper.text()).toContain('…or pass your badge: no need to choose your name first.');
    expect(wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
    expect(wrapper.get('[data-testid="access-footer"]').text()).toBe('ERPlora · trusted device');
  });

  it('a right PIN enters as that person and goes where they were going, with a full load', async () => {
    access.enterWith.mockResolvedValue('/sale/pos');
    const { wrapper, press } = await login([PIN_DOOR]);
    await wrapper.findAll('[data-testid="pin-face"]')[0].trigger('click');
    await press('4826');
    expect(access.enterWith).toHaveBeenCalledWith('/auth/pin', { person: 'c-ana', pin: '4826', next: '/sale/pos' });
    expect(access.leaveTo).toHaveBeenCalledWith('/sale/pos');
  });

  it('a wrong PIN says so under the circles and reads the faces again (someone may have left)', async () => {
    access.enterWith.mockRejectedValue(new ApiError(401, 'base.pin_incorrect', 'Wrong PIN.'));
    const { wrapper, press, doorCalls } = await login([PIN_DOOR, { ...PIN_DOOR, people: [ANA] }]);
    await wrapper.findAll('[data-testid="pin-face"]')[1].trigger('click');
    await press('0000');
    expect(access.leaveTo).not.toHaveBeenCalled();
    expect(doorCalls()).toBe(2);
    expect(wrapper.text()).toContain('Wrong PIN.');
    expect(wrapper.get('[data-testid="pinpad"]').attributes('aria-label')).toBe('PIN of Ana López');
  });

  it('a network failure is the page’s own sentence, never a silent nothing', async () => {
    access.enterWith.mockRejectedValue(new TypeError('Failed to fetch'));
    const { wrapper, press } = await login([{ ...PIN_DOOR, people: [ANA] }]);
    await press('4826');
    expect(wrapper.get('[data-testid="pinpad-error"]').text()).toBe('Could not enter. Check the connection and try again.');
  });

  it('a badge burst enters as its owner, with no face chosen', async () => {
    access.enterWith.mockResolvedValue('/sale/pos');
    await login([PIN_DOOR]);
    for (const key of [...'0012345678', 'Enter']) document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    await flush();
    expect(access.enterWith).toHaveBeenCalledWith('/auth/badge', { badge: '0012345678', next: '/sale/pos' });
    expect(access.leaveTo).toHaveBeenCalledWith('/sale/pos');
  });

  it('an address that tried too many PINs hears how long to wait, and «Account» stays', async () => {
    const { wrapper } = await login([{ ...PIN_DOOR, people: [], wait: 170 }]);
    expect(wrapper.get('[data-testid="access-wait"]').text()).toBe('Too many wrong attempts. Wait 3 min and try again.');
    expect(wrapper.find('[data-testid="pin-face"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="access-tabs"]').exists()).toBe(true);
  });

  it('reads the faces again every minute and when the till comes back to the screen', async () => {
    vi.useFakeTimers({ toFake: ['setInterval', 'clearInterval'] });
    const { doorCalls } = await login([PIN_DOOR]);
    expect(doorCalls()).toBe(1);
    vi.advanceTimersByTime(60_000);
    await flush();
    expect(doorCalls()).toBe(2);
    window.dispatchEvent(new Event('focus'));
    await flush();
    expect(doorCalls()).toBe(3);
  });
});

describe('LoginPage — the account', () => {
  it('without a PIN pad, only «Enter with your account», to erplora.com’s sign-in for this hub', async () => {
    const { wrapper } = await login([NO_PIN]);
    expect(wrapper.find('[data-testid="access-tabs"]').exists()).toBe(false);
    expect(wrapper.find('[data-testid="pinpad"]').exists()).toBe(false);
    expect(wrapper.get('[data-testid="access-footer"]').text()).toBe('ERPlora · secure connection');
    await wrapper.get('[data-testid="access-account"]').trigger('click');
    expect(access.leaveTo).toHaveBeenCalledWith('/auth/login?account=1&next=%2Fsale%2Fpos');
  });

  it('«Account» on a till leads there too', async () => {
    const { wrapper } = await login([PIN_DOOR]);
    await wrapper.get('[data-testid="access-tab-account"]').trigger('click');
    await flush();
    await wrapper.get('[data-testid="access-account"]').trigger('click');
    expect(access.leaveTo).toHaveBeenCalledWith('/auth/login?account=1&next=%2Fsale%2Fpos');
  });

  it('a door that cannot be read leaves the account, and says so', async () => {
    const broken = new Response('{"error":{"code":"x","message":"x"}}', { status: 503 });
    const { wrapper } = await login([broken]);
    expect(wrapper.get('[data-testid="access-door-error"]').text()).toContain('Could not load the PIN pad');
    expect(wrapper.find('[data-testid="access-account"]').exists()).toBe(true);
  });

  it('a `next` of another origin never leaves the hub', async () => {
    const { wrapper } = await login([NO_PIN], '/login?next=%2F%2Fevil.example');
    await wrapper.get('[data-testid="access-account"]').trigger('click');
    expect(access.leaveTo).toHaveBeenCalledWith('/auth/login?account=1&next=%2F');
  });
});

describe('LoginPage — what happened', () => {
  it('the session ended', async () => {
    const { wrapper } = await login([PIN_DOOR], '/login?next=%2F&notice=ended');
    const notice = wrapper.get('[data-testid="access-notice"]');
    expect(notice.text()).toContain('Your session has ended');
    expect(notice.find('[data-testid="access-upgrade"]').exists()).toBe(false);
  });

  it('another device’s entry ended it: why, and «Upgrade plan» to erplora.com', async () => {
    const { wrapper } = await login([NO_PIN], '/login?next=%2F&notice=device_limit');
    const notice = wrapper.get('[data-testid="access-notice"]');
    expect(notice.text()).toContain('Session opened on another device');
    expect(notice.text()).toContain('Your plan covers one device at a time');
    expect(notice.get('[data-testid="access-upgrade"]').attributes('href')).toBe('https://erplora.example/store/plans');
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await login([PIN_DOOR], '/login?next=%2F&notice=ended', 'es');
    expect(wrapper.get('[data-testid="access-heading"]').text()).toBe('Entra en tu negocio');
    expect(wrapper.text()).toContain('Tu sesión ha terminado');
    expect(wrapper.text()).toContain('Elige tu usuario');
  });
});
