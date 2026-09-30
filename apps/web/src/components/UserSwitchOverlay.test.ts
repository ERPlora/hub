// @vitest-environment happy-dom
// hub#456 (2/2) — **the lock screen that hands the till over**, seen from the counter.
//
// The rule it exists to keep is one sentence long: the person changes, the sale does not. So this
// suite is mostly about what the overlay does NOT do — it does not navigate, it does not close on a
// typo, it does not send twice — because every one of those, at a counter with a queue, costs the
// sale the whole feature is protecting.
//
// The swap itself is `lib/user-switch`'s contract and is pinned there (session minted before the
// old one is revoked, `logout()` never called, preferences re-read). Here the swap is a double: what
// is under test is the screen around it.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/runtime', async () => {
  const { ref } = await import('vue');
  return { pinUsers: ref<Array<{ id: string; name: string; role: string }>>([]) };
});

const switchUser = vi.fn(async (_name: string, _pin: string) => {});
vi.mock('../lib/user-switch', async () => {
  const actual = await vi.importActual<typeof import('../lib/user-switch')>('../lib/user-switch');
  return {
    ...actual,
    // The gate and the open/close state are the real ones — the overlay is wired to them, and a
    // double would hide exactly the wiring under test. Only the network hop is scripted.
    switchUser: (name: string, pin: string) => switchUser(name, pin),
  };
});

const toast = vi.fn();
vi.mock('../lib/toast', () => ({ toast: (...args: unknown[]) => toast(...args) }));

import UserSwitchOverlay from './UserSwitchOverlay.vue';
import { pinUsers } from '../lib/runtime';
import { closeUserSwitch, userSwitchOpen } from '../lib/user-switch';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en, es },
});

function mountOverlay() {
  // shallow: the `ion-*` are stubbed (this is the overlay's contract, not Ionic's) but their slots
  // are rendered — a real `ion-modal` reparents its content to <body> and there would be nothing to
  // look at. The `ok-*` are custom ELEMENTS, so they survive shallow and can be fired at.
  return mount(UserSwitchOverlay, {
    shallow: true,
    global: {
      plugins: [i18n],
      renderStubDefaultSlot: true,
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
}

const modal = (w: ReturnType<typeof mountOverlay>): VueWrapper =>
  w.getComponent('[data-testid="user-switch-modal"]') as VueWrapper;
const isOpen = (w: ReturnType<typeof mountOverlay>): unknown =>
  (modal(w).props() as Record<string, unknown>).isOpen;

/** The counter till's people, as the hub named them (`/api/hub/context` → `pin_users`). */
function seedPeople(): void {
  pinUsers.value = [
    { id: 'u1', name: 'Nacho', role: 'employee' },
    { id: 'u2', name: 'Sofía', role: 'manager' },
  ];
}

/** Tap the face, then type four digits on the pinpad. */
async function takeOverAs(
  w: ReturnType<typeof mountOverlay>,
  name: string,
  pin: string,
): Promise<void> {
  const card = w.findAll('[data-testid="user-switch-person"]').find((c) => c.text().includes(name));
  await card!.trigger('click');
  w.find('[data-testid="user-switch-pinpad"]').element.dispatchEvent(
    new CustomEvent('ok-complete', { detail: { value: pin } }),
  );
  await flushPromises();
}

beforeEach(() => {
  closeUserSwitch();
  pinUsers.value = [];
  switchUser.mockReset();
  switchUser.mockResolvedValue(undefined);
  toast.mockClear();
  i18n.global.locale.value = 'en';
});

describe('what is on screen', () => {
  it('is not there at all until somebody asks to hand the till over', () => {
    const w = mountOverlay();
    expect(isOpen(w)).toBe(false);
  });

  it('promises, in words, that the sale is still there', async () => {
    // The reassurance IS the feature. Without it a cashier mid-sale does not touch the button —
    // they finish the ticket under the wrong name, which is the behaviour hub#456 set out to end.
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    expect(isOpen(w)).toBe(true);
    expect(w.find('[data-testid="user-switch-lead"]').text()).toBe(en.userSwitch.lead);
  });

  it('offers the people the hub knows, so taking over is a tap', async () => {
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    const names = w.findAll('[data-testid="user-switch-person"]').map((c) => c.text());
    expect(names.some((n) => n.includes('Nacho'))).toBe(true);
    expect(names.some((n) => n.includes('Sofía'))).toBe(true);
  });

  it('falls back to typing a name when the hub named nobody', async () => {
    // A dead end here would leave a shift change with no way through but a sign-out — the very
    // trip this overlay replaces.
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    expect(w.findAll('[data-testid="user-switch-person"]')).toHaveLength(0);
    expect(w.find('[data-testid="user-switch-name"]').exists()).toBe(true);
  });
});

describe('handing over', () => {
  it('sends the name and the PIN to the runtime, and steps out of the way', async () => {
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '8317');

    expect(switchUser).toHaveBeenCalledWith('Sofía', '8317');
    expect(userSwitchOpen.value, 'the overlay closed onto the sale that was already there').toBe(
      false,
    );
  });

  it('says out loud who the till belongs to now', async () => {
    // The same reason the elevation dialog names the approver: the next lines of this sale are
    // being recorded under a name, and somebody should have read it.
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '8317');

    expect(toast).toHaveBeenCalled();
    expect(String(toast.mock.calls[0][0])).toContain('Sofía');
  });

  it('stays open on a refused PIN, and says so in one sentence', async () => {
    // A typo at a busy counter is the common case. Closing here would drop the person back onto a
    // till that is still not theirs, with nothing said.
    seedPeople();
    switchUser.mockRejectedValue(Object.assign(new Error('nope'), {}));
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '0000');

    expect(w.find('[data-testid="user-switch-error"]').text()).toBe(en.userSwitch.rejected);
    expect(userSwitchOpen.value).toBe(true);
  });

  it('names the gesture that fixes a device the hub never enrolled', async () => {
    seedPeople();
    switchUser.mockRejectedValue(Object.assign(new Error('nope'), { code: 'device_untrusted' }));
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '8317');

    expect(w.find('[data-testid="user-switch-error"]').text()).toBe(en.userSwitch.deviceNotEnrolled);
  });

  // hub#2285: the lock the pinpad names since hub#2283 is the same lock here — per name, and per
  // address with hub#2282 — so the overlay says the same thing: how many minutes to wait.
  it.each(['en', 'es'] as const)('says how many minutes a lock lasts, singular included (%s)', async (locale) => {
    i18n.global.locale.value = locale;
    const say = (minutes: number): string => i18n.global.t('login.pinTooManyAttempts', { minutes }, minutes);
    seedPeople();
    switchUser.mockRejectedValue(
      Object.assign(new Error('nope'), { code: 'too_many_attempts', retryAfterSecs: 240 }),
    );
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '0000');
    expect(w.find('[data-testid="user-switch-error"]').text()).toBe(say(4));

    switchUser.mockRejectedValue(
      Object.assign(new Error('nope'), { code: 'too_many_attempts', retryAfterSecs: 20 }),
    );
    // Same person, typing again: the overlay stays on her pinpad after a refusal.
    w.find('[data-testid="user-switch-pinpad"]').element.dispatchEvent(
      new CustomEvent('ok-complete', { detail: { value: '0000' } }),
    );
    await flushPromises();
    expect(w.find('[data-testid="user-switch-error"]').text()).toBe(say(1));
    expect(say(1)).not.toBe(say(2).replace('2', '1'));
  });

  it('is never sent twice for one tap', async () => {
    // `ok-complete` can fire twice on the fourth digit, and every attempt spends one of the five
    // tries the brute-force guard allows against that NAME (hub#329) — a lock that then holds at
    // the login pinpad too, on a till in the middle of service.
    seedPeople();
    let release: () => void = () => {};
    switchUser.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          release = resolve;
        }),
    );
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    const card = w.findAll('[data-testid="user-switch-person"]').find((c) => c.text().includes('Sofía'));
    await card!.trigger('click');
    const pad = w.find('[data-testid="user-switch-pinpad"]').element;
    pad.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '8317' } }));
    pad.dispatchEvent(new CustomEvent('ok-complete', { detail: { value: '8317' } }));
    await flushPromises();

    expect(switchUser).toHaveBeenCalledTimes(1);
    release();
  });
});

describe('changing your mind', () => {
  it('closes without touching the session', async () => {
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    await w.find('[data-testid="user-switch-cancel"]').trigger('click');

    expect(userSwitchOpen.value).toBe(false);
    expect(switchUser, 'nothing was sent').not.toHaveBeenCalled();
  });

  it('treats a dismissal by backdrop exactly the same', async () => {
    seedPeople();
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();

    modal(w).vm.$emit('didDismiss');
    await flushPromises();

    expect(userSwitchOpen.value).toBe(false);
    expect(switchUser).not.toHaveBeenCalled();
  });

  it('opens clean the next time: no face, no sentence left from the last attempt', async () => {
    seedPeople();
    switchUser.mockRejectedValue(new Error('nope'));
    userSwitchOpen.value = true;
    const w = mountOverlay();
    await flushPromises();
    await takeOverAs(w, 'Sofía', '0000');
    expect(w.find('[data-testid="user-switch-error"]').exists()).toBe(true);

    closeUserSwitch();
    await flushPromises();
    userSwitchOpen.value = true;
    await flushPromises();

    expect(w.find('[data-testid="user-switch-error"]').exists()).toBe(false);
    expect(w.find('[data-testid="user-switch-pinpad"]').exists(), 'back at the faces').toBe(false);
  });
});
