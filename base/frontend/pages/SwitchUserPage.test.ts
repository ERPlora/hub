// «Switch user» (`/switch-user`, BASE-G60): over the screen in use, the faces of the till (live: a PIN given or taken
// away shows at once, the old hub's HUB_SHELL-F04 trap), the PIN (or the badge) of whoever takes over, and back to the
// same screen with a full reload as them (gh:hub#2538, hub#2539: nothing of who left stays mounted); the sale is kept
// by its app. A refusal leaves whoever was in, in. «Cancel» changes nothing.
import { ApiError } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { errorFrame, flush, mountBase, subId } from '../__tests__/mount-base';
import type { AccessDoor } from '../operations';
import SwitchUserPage from './SwitchUserPage.vue';

const access = vi.hoisted(() => ({ enterWith: vi.fn(), replaceWith: vi.fn(), announceSwitch: vi.fn() }));
vi.mock('../lib/access', async (original) => ({ ...(await original<typeof import('../lib/access')>()), ...access }));

const ANA = { id: 'c-ana', name: 'Ana López', initials: 'AL' };
const BEA = { id: 'c-bea', name: 'Bea', initials: 'B' };
const FACES: AccessDoor = { pin: true, pin_length: 4, people: [ANA, BEA], wait: 0, plan_url: '' };

async function switchUser(faces: AccessDoor | null = FACES, locale: 'en' | 'es' = 'en') {
  const mounted = await mountBase(SwitchUserPage, { path: '/sale/pos', routes: ['/sale/pos', '/switch-user'], locale });
  await mounted.router.push('/switch-user');
  // vue-router's web history keeps where a page was opened from in the browser's state; the memory one of the tests
  // does not, so it is set as the browser would have it.
  window.history.replaceState({ back: '/sale/pos' }, '');
  await flush();
  const call = await mounted.live();
  if (faces) await mounted.result(call, 'base.access.faces', faces);
  const press = async (digits: string) => {
    for (const digit of digits) await mounted.wrapper.get(`[data-testid="pinpad-key-${digit}"]`).trigger('click');
    await flush();
  };
  return { ...mounted, call, press };
}

beforeEach(() => {
  access.enterWith.mockReset();
  access.replaceWith.mockReset();
  access.announceSwitch.mockReset();
});

afterEach(() => {
  document.body.innerHTML = '';
  window.history.replaceState(null, '');
});

describe('SwitchUserPage', () => {
  it('says the sale stays open and shows who can take over', async () => {
    const { wrapper } = await switchUser();
    expect(wrapper.get('[data-testid="switch-user-title"]').text()).toBe('Switch user');
    expect(wrapper.text()).toContain('The sale stays open. From now on it is in the name of whoever enters here.');
    expect(wrapper.text()).toContain('Who is taking over?');
    expect(wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
  });

  it('the PIN of whoever takes over reloads the screen in use as them, and tells who serves now', async () => {
    access.enterWith.mockResolvedValue('/sale/pos');
    const { wrapper, press } = await switchUser();
    await wrapper.findAll('[data-testid="pin-face"]')[1].trigger('click');
    await press('9071');
    expect(access.enterWith).toHaveBeenCalledWith('/auth/pin', { person: 'c-bea', pin: '9071', next: '/sale/pos' });
    expect(access.announceSwitch).toHaveBeenCalledWith('Bea');
    expect(access.replaceWith).toHaveBeenCalledWith('/sale/pos');
  });

  it('a badge takes over too', async () => {
    access.enterWith.mockResolvedValue('/sale/pos');
    await switchUser();
    for (const key of [...'0012345678', 'Enter']) document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
    await flush();
    expect(access.enterWith).toHaveBeenCalledWith('/auth/badge', { badge: '0012345678', next: '/sale/pos' });
    expect(access.replaceWith).toHaveBeenCalledWith('/sale/pos');
  });

  it('a wrong PIN leaves whoever was in, in, and says so', async () => {
    access.enterWith.mockRejectedValue(new ApiError(401, 'base.pin_incorrect', 'Wrong PIN.'));
    const { wrapper, press } = await switchUser();
    await wrapper.findAll('[data-testid="pin-face"]')[0].trigger('click');
    await press('0000');
    expect(access.replaceWith).not.toHaveBeenCalled();
    expect(wrapper.get('[data-testid="pinpad-error"]').text()).toBe('Wrong PIN.');
  });

  it('a PIN given meanwhile shows its face without reloading (live)', async () => {
    const { wrapper, call, result } = await switchUser({ ...FACES, people: [ANA] });
    expect(wrapper.find('[data-testid="pin-face"]').exists()).toBe(false);
    await result(call, 'base.access.faces', FACES, 2);
    expect(wrapper.findAll('[data-testid="pin-face"]')).toHaveLength(2);
  });

  it('«Cancel» goes back to the screen in use and changes nothing', async () => {
    const { wrapper, router } = await switchUser();
    await wrapper.get('[data-testid="switch-user-cancel"]').trigger('click');
    await flush();
    expect(router.currentRoute.value.path).toBe('/sale/pos');
    expect(access.enterWith).not.toHaveBeenCalled();
  });

  it('a grid that cannot be read says so, and «Cancel» stays', async () => {
    const { wrapper, call, client } = await switchUser(null);
    call.push(errorFrame(subId(client, 'base.access.faces'), 'unexpected'));
    await flush();
    expect(wrapper.get('[data-testid="switch-user-error"]').text()).toContain('Could not load who works here');
    expect(wrapper.find('[data-testid="switch-user-cancel"]').exists()).toBe(true);
  });

  it('speaks Spanish', async () => {
    const { wrapper } = await switchUser(FACES, 'es');
    expect(wrapper.get('[data-testid="switch-user-title"]').text()).toBe('Cambiar de usuario');
    expect(wrapper.text()).toContain('¿Quién se pone?');
    expect(wrapper.get('[data-testid="switch-user-cancel"]').text()).toBe('Cancelar');
  });
});
