// @vitest-environment happy-dom
// hub#358 — the card where an administrator says what kind of device this is (Settings › Hub).
//
// hub#357 shipped the door (`PUT /api/device/mode`, admin session) with no key: nothing in the
// product could turn it. This is the key, and it is a security control wearing the clothes of a
// convenience setting, so the tests are about the guards and about the WORDS:
//
//   - **Only an administrator writes**, and not by hiding the control: the handler stops before
//     calling the runtime, exactly like `RolesPanel.setActive`. The runtime revalidates anyway;
//     this is a mirror, not the authority.
//   - **The screen shows what the server confirmed**, never the choice that was clicked. A refused
//     write that repainted the card would leave the owner believing the pinpad is off when it is on
//     — or, far worse, the other way round.
//   - **The reason survives.** `hub.device.unknown_device` is fixed by signing in online on the
//     device once; flattening it to "could not be saved" turns a solvable state into a mystery.
//   - **The copy states the CONSEQUENCE**, not the name of the mode. "Personal" tells the owner of
//     a bar nothing; "it stays signed in — only use it on a device only you use" does.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';

const { DeviceModeError } = vi.hoisted(() => ({
  DeviceModeError: class DeviceModeError extends Error {
    readonly code?: string;
    constructor(message: string, code?: string) {
      super(message);
      this.name = 'DeviceModeError';
      this.code = code;
    }
  },
}));

vi.mock('../lib/device-mode', async () => {
  const { ref } = await import('vue');
  return {
    deviceMode: ref<'shared' | 'personal'>('shared'),
    deviceModeReady: ref(false),
    loadDeviceMode: vi.fn(async () => 'shared' as const),
    setDeviceMode: vi.fn(),
    DeviceModeError,
  };
});

// A real `ref`, not a plain object: the template unwraps refs and a stand-in that does not would
// make `v-if="!isAdmin"` always false — the guard would look wired while rendering nothing.
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import DeviceModeCard from './DeviceModeCard.vue';
import { deviceMode, loadDeviceMode, setDeviceMode } from '../lib/device-mode';
import { isAdmin } from '../lib/session';

// Read from the vitest root (`apps/web`): under happy-dom `import.meta.url` is not a `file:` URL.
const en = readFileSync(`${process.cwd()}/src/i18n/locales/en.ts`, 'utf8');
const es = readFileSync(`${process.cwd()}/src/i18n/locales/es.ts`, 'utf8');

// Real strings: the consequence reaching the reader IS the feature here, so a mute i18n would hide
// exactly what these tests are for.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      deviceMode: {
        title: 'This device',
        intro: 'How this device asks who is using it.',
        shared: 'Shared — a till several people use',
        sharedConsequence: 'It asks for a PIN, and each sale is attributed to whoever made it.',
        personal: 'Personal — only you use this device',
        personalConsequence:
          'It stays signed in and never asks for a PIN: anyone who picks it up is already you. Only for a device nobody else uses.',
        adminOnly: 'Only an administrator can change how this device signs people in.',
        saveError: 'The device could not be changed. Please try again.',
        saved: 'Saved.',
      },
    },
  },
});

function mountCard() {
  return mount(DeviceModeCard, { global: { plugins: [i18n] } });
}

beforeEach(() => {
  (isAdmin as unknown as { value: boolean }).value = true;
  deviceMode.value = 'shared';
  vi.mocked(loadDeviceMode).mockClear().mockResolvedValue('shared');
  vi.mocked(setDeviceMode).mockReset();
});

describe('reading', () => {
  it('asks the hub what this device is, instead of assuming', async () => {
    mountCard();
    await flushPromises();

    expect(vi.mocked(loadDeviceMode)).toHaveBeenCalled();
  });

  it('shows the consequence of each option, not the name of the mode', async () => {
    const wrapper = mountCard();
    await flushPromises();

    const text = wrapper.html();
    // A bar owner does not know what "personal" means. They know what "anyone who picks it up is
    // already you" means, and that is the sentence that decides whether they should click it.
    expect(text).toContain('anyone who picks it up is already you');
    expect(text).toContain('each sale is attributed to whoever made it');
  });
});

describe('writing', () => {
  it('marks the device in front of the administrator, naming no other device', async () => {
    vi.mocked(setDeviceMode).mockResolvedValue('personal');
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('personal');

    // No device id: "this device is mine", from the device itself. Naming another device from here
    // would be a way to switch off a pinpad you are not standing in front of.
    expect(vi.mocked(setDeviceMode)).toHaveBeenCalledWith('personal');
  });

  it('does nothing when the device is already in that mode', async () => {
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('shared');

    expect(vi.mocked(setDeviceMode)).not.toHaveBeenCalled();
  });
});

describe('only an administrator', () => {
  it('refuses to write even if the change is triggered some other way', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('personal');

    // Hiding the control is not a guard. This is the same mirror as `RolesPanel.setActive`; the
    // runtime revalidates the session on every PUT regardless.
    expect(vi.mocked(setDeviceMode)).not.toHaveBeenCalled();
    expect(wrapper.html()).toContain('Only an administrator');
    // And the control looks the way it behaves: an employee who can click it and sees nothing
    // happen reads that as a broken product, not as a rule.
    expect(wrapper.findAllComponents({ name: 'IonRadio' }).every((r) => r.props('disabled'))).toBe(true);
  });

  it('leaves the control usable for an administrator', async () => {
    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.findAllComponents({ name: 'IonRadio' }).some((r) => r.props('disabled'))).toBe(false);
  });
});

describe('a refusal', () => {
  it('keeps the reason the runtime gave, because it says what to do about it', async () => {
    vi.mocked(setDeviceMode).mockRejectedValue(
      new DeviceModeError(
        'this hub does not know the device `laptop-9`: sign in online on it once',
        'hub.device.unknown_device',
      ),
    );
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('personal');
    await flushPromises();

    expect(wrapper.html()).toContain('sign in online on it once');
  });

  it('falls back to a generic message only when there is no reason to show', async () => {
    vi.mocked(setDeviceMode).mockRejectedValue(new TypeError('Failed to fetch'));
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('personal');
    await flushPromises();

    expect(wrapper.html()).toContain('could not be changed');
  });

  it('leaves the card showing the mode still in force, not the one that was clicked', async () => {
    vi.mocked(setDeviceMode).mockRejectedValue(new TypeError('Failed to fetch'));
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as { choose: (m: string) => Promise<void> }).choose('personal');
    await flushPromises();

    // The pinpad is still on. A card that painted the wish would tell the owner the opposite of
    // what the till in front of them is about to do.
    expect(deviceMode.value).toBe('shared');
    expect((wrapper.vm as unknown as { mode: string }).mode).toBe('shared');
  });
});

describe('the strings ship in both languages', () => {
  it('has the consequence copy in English and in Spanish', () => {
    for (const catalogue of [en, es]) {
      for (const key of [
        'sharedConsequence',
        'personalConsequence',
        'adminOnly',
        'saveError',
      ]) {
        expect(catalogue).toContain(key);
      }
    }
  });
});
