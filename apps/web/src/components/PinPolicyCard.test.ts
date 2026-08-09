// @vitest-environment happy-dom
// «Show PIN pad» (hub#628, redesign of hub#359's card) — Settings › Hub.
//
// The card turned into two controls over the same closed wire: a TOGGLE (is the pinpad offered at
// all) and an idle RANGE (how quickly a till nobody touches signs out and asks again:
// 1 · 5 · 10 · 15 · 30 · until you sign out). The mapping to `pin_policy` +
// `pin_inactivity_minutes` is lib/pinpad-dial; what these tests pin is the card's behaviour:
//
//   - **Only an administrator writes**, and not by hiding the control: the handler stops before
//     calling the runtime, exactly like `DeviceModeCard.choose`. The runtime revalidates anyway
//     (`PUT /api/settings` → `require_admin_session`); this is a mirror, not the authority.
//   - **The screen shows what the server confirmed**, never the option that was clicked. A refused
//     write that repainted the card would leave the owner believing the till stopped asking when
//     it did not — or, far worse, the other way round.
//   - **The copy states the CONSEQUENCE.** A bare OFF toggle tells a shopkeeper nothing. "Whoever
//     opened the till in the morning is the name on every sale" does — and so does the part people
//     forget: staff whose only credential is a PIN will not be able to sign in.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';

vi.mock('../lib/hub-settings', async () => {
  const { ref } = await import('vue');
  return {
    hubSettings: ref<{ pin_policy: string; pin_inactivity_minutes?: number } | null>(null),
    getHubSettings: vi.fn(async () => ({ pin_policy: 'per_shift' })),
    updateHubSettings: vi.fn(),
  };
});

// A real `ref`, not a plain object: the template unwraps refs and a stand-in that does not would
// make `v-if="!isAdmin"` always false — the guard would look wired while rendering nothing.
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));

import PinPolicyCard from './PinPolicyCard.vue';
import { getHubSettings, hubSettings, updateHubSettings } from '../lib/hub-settings';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';
import { UNTIL_SIGN_OUT_STOP } from '../lib/pinpad-dial';
import { isAdmin } from '../lib/session';

// Read from the vitest root (`apps/web`): under happy-dom `import.meta.url` is not a `file:` URL.
const en = readFileSync(`${process.cwd()}/src/i18n/locales/en.ts`, 'utf8');
const es = readFileSync(`${process.cwd()}/src/i18n/locales/es.ts`, 'utf8');

// Real-shaped strings: the consequence reaching the reader IS the feature here, so a mute i18n
// would hide exactly what these tests are for.
const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    en: {
      pinPolicy: {
        title: 'PIN pad',
        intro: 'Whether this hub shows the PIN pad and asks who is at the till.',
        showPinpad: 'Show PIN pad',
        onConsequence:
          'Staff pick their name and type their PIN, so every sale carries the name of whoever made it.',
        offConsequence:
          'Nobody types a PIN. Whoever opened the till in the morning is the name on every sale. Staff who only have a PIN and no account will not be able to sign in.',
        idleTitle: 'Ask again after inactivity',
        idleMinutes: '{n} min',
        idleUntilSignOut: 'Until you sign out',
        idleMinutesConsequence:
          'A till nobody has touched for {n} minutes signs the user out and shows the PIN pad.',
        idleUntilSignOutConsequence:
          'The till never locks itself: the session stays open until whoever signed in signs out.',
        adminOnly: 'Only an administrator can change whether this hub asks.',
        saveError: 'This could not be changed. Check the connection and try again.',
      },
    },
  },
});

function mountCard() {
  return mount(PinPolicyCard, { global: { plugins: [i18n] } });
}

type Card = {
  setPinpad: (on: boolean) => Promise<void>;
  chooseStop: (stop: number) => Promise<void>;
  policy: string;
  stop: number;
};

beforeEach(() => {
  (isAdmin as unknown as { value: boolean }).value = true;
  pinPolicy.value = STRICT_PIN_POLICY;
  hubSettings.value = null;
  vi.mocked(getHubSettings).mockClear();
  vi.mocked(updateHubSettings).mockReset();
});

describe('reading', () => {
  it('asks the hub where the dial points instead of assuming', async () => {
    mountCard();
    await flushPromises();

    expect(vi.mocked(getHubSettings)).toHaveBeenCalled();
  });

  it('with the pinpad on, shows the toggle on and the range at «until you sign out»', async () => {
    const wrapper = mountCard(); // per_shift: the strict default
    await flushPromises();

    expect(wrapper.findComponent({ name: 'IonToggle' }).props('checked')).toBe(true);
    expect(wrapper.findComponent({ name: 'IonRange' }).props('value')).toBe(UNTIL_SIGN_OUT_STOP);
    expect(wrapper.html()).toContain('Until you sign out');
    expect(wrapper.html()).toContain('never locks itself');
  });

  it('with an idle window, places the handle on the stored minutes and says what they do', async () => {
    pinPolicy.value = 'always';
    hubSettings.value = { pin_inactivity_minutes: 10 } as never;
    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.findComponent({ name: 'IonRange' }).props('value')).toBe(2); // 1·5·[10]
    expect(wrapper.html()).toContain('10 min');
    expect(wrapper.html()).toContain('signs the user out and shows the PIN pad');
  });

  it('with the pinpad off, hides the range and states the full price of OFF', async () => {
    pinPolicy.value = 'never';
    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.findComponent({ name: 'IonToggle' }).props('checked')).toBe(false);
    expect(wrapper.findComponent({ name: 'IonRange' }).exists()).toBe(false);
    // A shopkeeper does not know what "off" costs. These two sentences are what decides the click:
    expect(wrapper.html()).toContain('the name on every sale');
    expect(wrapper.html()).toContain('only have a PIN and no account will not be able to sign in');
  });
});

describe('writing', () => {
  it('turning the pinpad OFF sends `never`, and only the dial', async () => {
    vi.mocked(updateHubSettings).mockResolvedValue({ pin_policy: 'never' } as never);
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).setPinpad(false);

    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ pin_policy: 'never' });
  });

  it('turning it back ON sends the runtime default, never a guess at old minutes', async () => {
    pinPolicy.value = 'never';
    vi.mocked(updateHubSettings).mockResolvedValue({ pin_policy: 'per_shift' } as never);
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).setPinpad(true);

    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ pin_policy: 'per_shift' });
  });

  it('a minute stop sends `always` plus the minutes of that stop', async () => {
    vi.mocked(updateHubSettings).mockResolvedValue({ pin_policy: 'always' } as never);
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).chooseStop(1);

    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({
      pin_policy: 'always',
      pin_inactivity_minutes: 5,
    });
  });

  it('the last stop sends `per_shift`: no idle lock', async () => {
    pinPolicy.value = 'always';
    hubSettings.value = { pin_inactivity_minutes: 5 } as never;
    vi.mocked(updateHubSettings).mockResolvedValue({ pin_policy: 'per_shift' } as never);
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).chooseStop(UNTIL_SIGN_OUT_STOP);

    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ pin_policy: 'per_shift' });
  });

  it('does nothing when the hub is already there', async () => {
    const wrapper = mountCard(); // per_shift = pinpad on, range at «until you sign out»
    await flushPromises();

    await (wrapper.vm as unknown as Card).setPinpad(true);
    await (wrapper.vm as unknown as Card).chooseStop(UNTIL_SIGN_OUT_STOP);

    expect(vi.mocked(updateHubSettings)).not.toHaveBeenCalled();
  });
});

describe('only an administrator', () => {
  it('refuses to write even if the change is triggered some other way', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).setPinpad(false);
    await (wrapper.vm as unknown as Card).chooseStop(0);

    // Hiding the control is not a guard. Deciding that sales stop carrying a name is
    // administration of the business; the runtime revalidates the session on every PUT regardless.
    expect(vi.mocked(updateHubSettings)).not.toHaveBeenCalled();
    expect(wrapper.html()).toContain('Only an administrator');
    // And the control looks the way it behaves: an employee who can click it and sees nothing
    // happen reads that as a broken product, not as a rule.
    expect(wrapper.findComponent({ name: 'IonToggle' }).props('disabled')).toBe(true);
    expect(wrapper.findComponent({ name: 'IonRange' }).props('disabled')).toBe(true);
  });

  it('leaves the controls usable for an administrator', async () => {
    const wrapper = mountCard();
    await flushPromises();

    expect(wrapper.findComponent({ name: 'IonToggle' }).props('disabled')).toBe(false);
    expect(wrapper.findComponent({ name: 'IonRange' }).props('disabled')).toBe(false);
  });
});

describe('a refusal', () => {
  it('leaves the card showing the position still in force, not the one that was clicked', async () => {
    vi.mocked(updateHubSettings).mockRejectedValue(new TypeError('Failed to fetch'));
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).setPinpad(false);
    await flushPromises();

    // The till is still asking. A card that painted the wish would tell the owner the opposite of
    // what the hub in front of them is about to do.
    expect(pinPolicy.value).toBe('per_shift');
    expect(wrapper.findComponent({ name: 'IonToggle' }).props('checked')).toBe(true);
    expect(wrapper.html()).toContain('could not be changed');
  });
});

describe('the strings ship in both languages', () => {
  it('has the consequence copy in English and in Spanish', () => {
    for (const catalogue of [en, es]) {
      for (const key of [
        'showPinpad',
        'onConsequence',
        'offConsequence',
        'idleTitle',
        'idleMinutes',
        'idleUntilSignOut',
        'idleMinutesConsequence',
        'idleUntilSignOutConsequence',
        'adminOnly',
        'saveError',
      ]) {
        // The KEY as it is declared (`key:` followed by its value), not the bare name. Found by
        // mutation: a bare `toContain('offConsequence')` also passes for `offConsequencePendiente`,
        // so a Spanish catalogue that lost the string to a rename would ship silently — and the
        // string that goes missing is the one that says what the owner is giving up.
        expect(catalogue, `${key} missing`).toMatch(new RegExp(`\\n\\s*${key}:\\s*\\n?\\s*'`));
      }
    }
  });
});
