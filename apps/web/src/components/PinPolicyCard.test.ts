// @vitest-environment happy-dom
// hub#359 — the card where an owner says how often the hub asks who is selling (Settings › Hub).
//
// This is the key to the one door in the product that can stop sales carrying a name, so the tests
// are about the guards and about the **words**:
//
//   - **Only an administrator writes**, and not by hiding the control: the handler stops before
//     calling the runtime, exactly like `DeviceModeCard.choose` and `RolesPanel.setActive`. The
//     runtime revalidates anyway (`PUT /api/settings` → `require_admin_session`); this is a mirror,
//     not the authority.
//   - **The screen shows what the server confirmed**, never the option that was clicked. A refused
//     write that repainted the card would leave the owner believing the till stopped asking when it
//     did not — or, far worse, the other way round.
//   - **The copy states the CONSEQUENCE.** "Never" tells a shopkeeper nothing. "Whoever opened the
//     till in the morning is the name on every sale until the shift ends" does — and so does the
//     part people forget: staff whose only credential is a PIN will not be able to sign in.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';

vi.mock('../lib/hub-settings', async () => {
  const { ref } = await import('vue');
  return {
    hubSettings: ref<{ pin_policy: string } | null>(null),
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
import { getHubSettings, updateHubSettings } from '../lib/hub-settings';
import { STRICT_PIN_POLICY, pinPolicy } from '../lib/pin-policy';
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
        title: 'Asking who is selling',
        intro: 'How often this hub asks which person is at the till.',
        always: 'Every hour',
        alwaysConsequence: 'The till forgets who was using it after an hour.',
        perShift: 'Once per shift',
        perShiftConsequence: 'Somebody signs in when they start and the till remembers them.',
        never: 'Never',
        neverConsequence:
          'Whoever opened the till in the morning is the name on every sale until the shift ends. Staff who only have a PIN will not be able to sign in.',
        adminOnly: 'Only an administrator can change how often this hub asks.',
        saveError: 'This could not be changed. Check the connection and try again.',
      },
    },
  },
});

function mountCard() {
  return mount(PinPolicyCard, { global: { plugins: [i18n] } });
}

type Card = { choose: (p: string) => Promise<void>; policy: string };

beforeEach(() => {
  (isAdmin as unknown as { value: boolean }).value = true;
  pinPolicy.value = STRICT_PIN_POLICY;
  vi.mocked(getHubSettings).mockClear();
  vi.mocked(updateHubSettings).mockReset();
});

describe('reading', () => {
  it('asks the hub where the dial points instead of assuming', async () => {
    mountCard();
    await flushPromises();

    expect(vi.mocked(getHubSettings)).toHaveBeenCalled();
  });

  it('shows the consequence of each option, not the name of the position', async () => {
    const wrapper = mountCard();
    await flushPromises();

    const text = wrapper.html();
    // A shopkeeper does not know what "never" costs. They know what "whoever opened the till is the
    // name on every sale" means, and that is the sentence that decides whether they should click it.
    expect(text).toContain('the name on every sale until the shift ends');
    // Including the part that is easy to leave out and expensive to discover on a Saturday.
    expect(text).toContain('only have a PIN will not be able to sign in');
    expect(text).toContain('The till forgets who was using it after an hour');
  });
});

describe('writing', () => {
  it('sends only the dial, leaving the rest of the settings alone', async () => {
    vi.mocked(updateHubSettings).mockResolvedValue({ pin_policy: 'never' } as never);
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).choose('never');

    expect(vi.mocked(updateHubSettings)).toHaveBeenCalledWith({ pin_policy: 'never' });
  });

  it('does nothing when the hub is already there', async () => {
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).choose('per_shift');

    expect(vi.mocked(updateHubSettings)).not.toHaveBeenCalled();
  });
});

describe('only an administrator', () => {
  it('refuses to write even if the change is triggered some other way', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).choose('never');

    // Hiding the control is not a guard. Deciding that sales stop carrying a name is
    // administration of the business; the runtime revalidates the session on every PUT regardless.
    expect(vi.mocked(updateHubSettings)).not.toHaveBeenCalled();
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
  it('leaves the card showing the position still in force, not the one that was clicked', async () => {
    vi.mocked(updateHubSettings).mockRejectedValue(new TypeError('Failed to fetch'));
    const wrapper = mountCard();
    await flushPromises();

    await (wrapper.vm as unknown as Card).choose('never');
    await flushPromises();

    // The till is still asking. A card that painted the wish would tell the owner the opposite of
    // what the hub in front of them is about to do.
    expect(pinPolicy.value).toBe('per_shift');
    expect((wrapper.vm as unknown as Card).policy).toBe('per_shift');
    expect(wrapper.html()).toContain('could not be changed');
  });
});

describe('the strings ship in both languages', () => {
  it('has the consequence copy in English and in Spanish', () => {
    for (const catalogue of [en, es]) {
      for (const key of [
        'always',
        'alwaysConsequence',
        'perShift',
        'perShiftConsequence',
        'never',
        'neverConsequence',
        'adminOnly',
        'saveError',
      ]) {
        // The KEY as it is declared (`key:` followed by its value), not the bare name. Found by
        // mutation: a bare `toContain('neverConsequence')` also passes for
        // `neverConsequencePendiente`, so a Spanish catalogue that lost the string to a rename
        // would ship silently — and the string that goes missing is the one that says what the
        // owner is giving up.
        expect(catalogue, `${key} missing`).toMatch(new RegExp(`\\n\\s*${key}:\\s*\\n?\\s*'`));
      }
    }
  });
});
