// «Create your PIN» (`/pin/setup`, BASE-G54): after entering with the account on a till that works by PIN, the person
// without one chooses it (the business's digits), repeats it and enters; «Not now» goes on without it. Someone who
// already has one is never asked again.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import type { Profile } from '../operations';
import PinSetupPage from './PinSetupPage.vue';

const access = vi.hoisted(() => ({ leaveTo: vi.fn() }));
vi.mock('../lib/access', async (original) => ({ ...(await original<typeof import('../lib/access')>()), ...access }));

const PROFILE: Profile = {
  first_name: 'Ana',
  last_name: '',
  contact_email: '',
  avatar_url: '',
  language: '',
  theme_mode: '',
  palette: '',
  role: 'Employee',
  has_pin: false,
  pin_length: 4,
};

type Handler = (url: string, body: unknown) => Response;

async function setup(handler: Handler, locale: 'en' | 'es' = 'en') {
  const mounted = await mountBase(PinSetupPage, {
    path: '/pin/setup?next=%2Fsale%2Fpos',
    routes: ['/pin/setup'],
    locale,
    onApi: ({ url, init }) => handler(url, init.body ? JSON.parse(String(init.body)) : undefined),
  });
  await flush();
  const press = async (digits: string) => {
    for (const digit of digits) await mounted.wrapper.get(`[data-testid="pinpad-key-${digit}"]`).trigger('click');
    await flush();
  };
  return { ...mounted, press };
}

const profileThen = (onSet: Handler): Handler => (url, body) =>
  url.startsWith('/api/me/profile') ? Response.json(PROFILE) : onSet(url, body);

beforeEach(() => access.leaveTo.mockReset());
afterEach(() => {
  document.body.innerHTML = '';
});

describe('PinSetupPage', () => {
  it('asks for the business’s digits, then the same again, saves it and goes on', async () => {
    const set = vi.fn(() => Response.json({ set: true }));
    const { wrapper, press } = await setup(profileThen(set));
    expect(wrapper.get('[data-testid="pin-setup-title"]').text()).toBe('Create your PIN');
    expect(wrapper.get('[data-testid="pin-setup-step"]').text()).toBe('Choose a 4-digit PIN');
    await press('4826');
    expect(wrapper.get('[data-testid="pin-setup-step"]').text()).toBe('Confirm your PIN');
    await press('4826');
    expect(set).toHaveBeenCalledWith('/api/me/pin', { pin: '4826' });
    expect(access.leaveTo).toHaveBeenCalledWith('/sale/pos');
  });

  it('a repetition that differs starts again', async () => {
    const set = vi.fn(() => Response.json({ set: true }));
    const { wrapper, press } = await setup(profileThen(set));
    await press('4826');
    await press('4827');
    expect(set).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="pinpad-error"]').text()).toBe('The PINs do not match, try again');
    expect(wrapper.get('[data-testid="pin-setup-step"]').text()).toBe('Choose a 4-digit PIN');
  });

  it('a PIN the Hub refuses (too easy, taken) says why and starts again', async () => {
    const refuse = () =>
      Response.json({ error: { code: 'base.pin_weak', message: 'That PIN is too easy to guess.' } }, { status: 422 });
    const { wrapper, press } = await setup(profileThen(refuse));
    await press('1111');
    await press('1111');
    expect(wrapper.get('[data-testid="pinpad-error"]').text()).toBe('That PIN is too easy to guess.');
    expect(wrapper.get('[data-testid="pin-setup-step"]').text()).toBe('Choose a 4-digit PIN');
    expect(access.leaveTo).not.toHaveBeenCalled();
  });

  it('«Not now» goes on without a PIN', async () => {
    const { wrapper } = await setup(profileThen(() => Response.json({ set: true })));
    await wrapper.get('[data-testid="pin-setup-later"]').trigger('click');
    expect(access.leaveTo).toHaveBeenCalledWith('/sale/pos');
  });

  it('someone who already has a PIN is not asked for another one', async () => {
    await setup((url) => Response.json(url.startsWith('/api/me/profile') ? { ...PROFILE, has_pin: true } : {}));
    expect(access.leaveTo).toHaveBeenCalledWith('/sale/pos');
  });

  it('a business of six digits asks for six', async () => {
    const { wrapper } = await setup((url) => Response.json(url.startsWith('/api/me/profile') ? { ...PROFILE, pin_length: 6 } : {}));
    expect(wrapper.findAll('[data-testid="pinpad-dot"]')).toHaveLength(6);
  });

  it('a profile that cannot be read leaves «Not now» and says so', async () => {
    const { wrapper } = await setup(() => {
      throw new ApiError(503, 'x', 'x');
    });
    expect(wrapper.find('[data-testid="pin-setup-error"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="pin-setup-later"]').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await setup(profileThen(() => Response.json({ set: true })), 'es');
    expect(wrapper.get('[data-testid="pin-setup-step"]').text()).toBe('Elige un PIN de 4 dígitos');
    expect(wrapper.get('[data-testid="pin-setup-later"]').text()).toBe('Ahora no');
  });
});
