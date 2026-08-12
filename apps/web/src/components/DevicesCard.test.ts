// @vitest-environment happy-dom
// hub#455 — the card where an owner disconnects a device they lost (Settings › Hub).
//
// The runtime could revoke a device since hub#15 and nothing in the product could ask it to. This
// is the gesture, and it is the one screen in the hub whose reason for existing is an emergency, so
// the tests are about what it SAYS as much as about what it does:
//
//   - **Recognising the right device is the whole task.** An opaque id decides nothing; the list
//     has to carry the name it signed in under, when it was last used and whether somebody is on it
//     right now — and it must mark the device the owner is holding, because that button signs them
//     out.
//   - **Nothing destructive happens on one tap.** Revoking is confirmed in place, with the
//     consequence spelled out, and the confirmation for the current device says something different
//     because the outcome is different.
//   - **The words are honest about the limits.** The session dies immediately, and the device can
//     be signed in on again by somebody with an account. Promising "this device can never come
//     back" would be a promise the runtime does not keep.
//   - **Only an administrator writes**, mirroring the runtime gate (ADR-0248), and the runtime
//     revalidates anyway.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { readFileSync } from 'node:fs';

const { DevicesError } = vi.hoisted(() => ({
  DevicesError: class DevicesError extends Error {
    constructor(message: string) {
      super(message);
      this.name = 'DevicesError';
    }
  },
}));

vi.mock('../lib/devices', () => ({
  DevicesError,
  listDevices: vi.fn(),
  renameDevice: vi.fn(),
  revokeDevice: vi.fn(),
}));
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true), logout: vi.fn() };
});
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', template: '<span />' },
}));
const replace = vi.fn(async () => undefined);
vi.mock('vue-router', () => ({ useRouter: () => ({ replace }) }));

import DevicesCard from './DevicesCard.vue';
import { listDevices, renameDevice, revokeDevice } from '../lib/devices';
import { isAdmin, logout } from '../lib/session';

// Read from the vitest root (`apps/web`): under happy-dom `import.meta.url` is not a `file:` URL.
const en = readFileSync(`${process.cwd()}/src/i18n/locales/en.ts`, 'utf8');
const es = readFileSync(`${process.cwd()}/src/i18n/locales/es.ts`, 'utf8');

/** The real `devices` block of a locale file. The words ARE the feature here. */
function block(source: string): Record<string, string> {
  const start = source.indexOf('\n  devices: {');
  const end = source.indexOf('\n  },', start);
  const body = source.slice(start, end);
  const entries: Record<string, string> = {};
  for (const match of body.matchAll(/^\s{4}(\w+):\s*\n?\s*'((?:[^'\\]|\\.)*)',?$/gm)) {
    entries[match[1]] = match[2].replace(/\\'/g, "'");
  }
  return entries;
}

const i18n = createI18n({
  legacy: false,
  locale: 'en',
  missingWarn: false,
  fallbackWarn: false,
  messages: { en: { devices: block(en) }, es: { devices: block(es) } },
});

function device(overrides: Record<string, unknown> = {}) {
  return {
    deviceId: 'dev_abc',
    // Two different facts (hub#494): what the BUSINESS calls it, and who signed in last. The second
    // one is chosen by the client and changes shift to shift, so it may only ever be a hint.
    name: 'Barra',
    label: 'Office laptop',
    trustedAt: '2026-08-01T08:00:00+00:00',
    mode: 'personal' as const,
    openSessions: 1,
    lastSignIn: '2026-08-07T10:00:00+00:00',
    signedInUntil: '2026-09-06T10:00:00+00:00',
    current: false,
    ...overrides,
  };
}

/**
 * Type into the name field the way `ion-input` reports it: a `ionInput` `CustomEvent` carrying
 * `detail.value` (same shape the other cards are driven with). `setValue` would be testing an
 * `<input>` this card does not use.
 */
function type(wrapper: ReturnType<typeof mount>, value: string): void {
  wrapper
    .get('[data-test="name-dev_abc"]')
    .element.dispatchEvent(new CustomEvent('ionInput', { detail: { value } }));
}

async function mountCard() {
  const wrapper = mount(DevicesCard, {
    global: {
      plugins: [i18n],
      stubs: { 'ok-inline-feedback': true },
      renderStubDefaultSlot: true,
    },
  });
  await flushPromises();
  return wrapper;
}

beforeEach(() => {
  vi.mocked(listDevices).mockReset().mockResolvedValue([device()]);
  vi.mocked(revokeDevice).mockReset().mockResolvedValue({
    wasKnown: true,
    sessionsClosed: 1,
    wasCurrent: false,
  });
  vi.mocked(renameDevice).mockReset().mockResolvedValue('Cocina');
  vi.mocked(logout).mockReset();
  replace.mockClear();
  (isAdmin as unknown as { value: boolean }).value = true;
});

describe('the list', () => {
  it('shows the signals that let a person point at the device they lost', async () => {
    const wrapper = await mountCard();

    const text = wrapper.html();
    expect(text).toContain('Office laptop');
    // Somebody is on it right now: the fact that turns "I think I left it somewhere" into "cut it
    // off". The id is shown too, because two tills can carry the same name.
    expect(text).toContain('dev_abc');
    expect(text.toLowerCase()).toContain('in use');
  });

  it('marks the device the owner is holding', async () => {
    vi.mocked(listDevices).mockResolvedValue([device({ current: true })]);

    const wrapper = await mountCard();

    expect(wrapper.html()).toContain(i18n.global.t('devices.thisDevice'));
  });

  it('names a device that never told the hub what it is called', async () => {
    vi.mocked(listDevices).mockResolvedValue([device({ name: '', label: '  ' })]);

    const wrapper = await mountCard();

    // A blank row would look like a rendering fault, and the owner needs SOMETHING to tap.
    expect(wrapper.html()).toContain(i18n.global.t('devices.unnamed'));
  });

  it('leads with the name the business chose, and demotes who signed in last to a hint', async () => {
    const wrapper = await mountCard();

    const html = wrapper.html();
    // The heading is the one field an administrator wrote. Before hub#494 the row was titled with
    // `label` — the name of the PERSON who last signed in online, rewritten on every login and
    // chosen by the client: three tablets, three rows saying "Marta", next to the button that
    // disconnects one of them.
    expect(wrapper.get('.name').text()).toContain('Barra');
    expect(wrapper.get('.name').text()).not.toContain('Office laptop');
    // The person is still worth showing — it is a real memory aid — but said as what it is.
    expect(html).toContain('Office laptop');
    expect(html).toContain(i18n.global.t('devices.lastSignedInBy', { who: 'Office laptop' }));
  });

  it('a device nobody has named yet says so instead of borrowing the person name', async () => {
    vi.mocked(listDevices).mockResolvedValue([device({ name: '' })]);

    const wrapper = await mountCard();

    expect(wrapper.get('.name').text()).toContain(i18n.global.t('devices.unnamed'));
    expect(wrapper.get('.name').text()).not.toContain('Office laptop');
  });

  it('says when it was last used instead of claiming somebody is on it', async () => {
    vi.mocked(listDevices).mockResolvedValue([
      device({ openSessions: 0, mode: 'shared', signedInUntil: '' }),
    ]);

    const wrapper = await mountCard();

    const html = wrapper.html();
    expect(html).not.toContain(i18n.global.t('devices.inUse'));
    expect(html).toContain('Last used');
    // And the mode reads as its consequence, not as its name: "shared" means nothing to a landlord,
    // "asks for a PIN" does.
    expect(html).toContain(i18n.global.t('devices.modeShared'));
    expect(html).not.toContain(i18n.global.t('devices.modePersonal'));
  });

  it('a device nobody has used since it was added says exactly that', async () => {
    vi.mocked(listDevices).mockResolvedValue([
      device({ openSessions: 0, lastSignIn: '', signedInUntil: '' }),
    ]);

    const wrapper = await mountCard();

    expect(wrapper.html()).toContain('never used since');
  });

  it('says the list is empty rather than showing nothing at all', async () => {
    vi.mocked(listDevices).mockResolvedValue([]);

    const wrapper = await mountCard();

    expect(wrapper.html()).toContain(i18n.global.t('devices.empty'));
  });

  it('a failed read says so instead of looking like a business with no devices', async () => {
    vi.mocked(listDevices).mockRejectedValue(new DevicesError('boom'));

    const wrapper = await mountCard();

    // The distinction matters: "no devices" would tell somebody hunting a stolen tablet that there
    // is nothing to revoke.
    expect(wrapper.html()).toContain('boom');
    expect(wrapper.html()).not.toContain(i18n.global.t('devices.empty'));
  });
});

describe('revoking', () => {
  it('never disconnects on a single tap: it asks, and says what will happen', async () => {
    const wrapper = await mountCard();

    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    expect(revokeDevice).not.toHaveBeenCalled();
    expect(wrapper.html()).toContain(i18n.global.t('devices.confirm'));
    // The honest limits, in the confirmation and not in a tooltip: the session dies now, and the
    // device is not banned — somebody with an account can sign in on it again.
    expect(wrapper.html()).toContain(i18n.global.t('devices.consequence'));
  });

  it('warns differently when the device being cut off is the one in your hands', async () => {
    vi.mocked(listDevices).mockResolvedValue([device({ current: true })]);
    const wrapper = await mountCard();

    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    expect(wrapper.html()).toContain(i18n.global.t('devices.confirmCurrent'));
  });

  it('backing out of the confirmation calls nothing', async () => {
    const wrapper = await mountCard();
    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    await wrapper.get('[data-test="cancel-dev_abc"]').trigger('click');

    expect(revokeDevice).not.toHaveBeenCalled();
    expect(wrapper.html()).not.toContain(i18n.global.t('devices.confirm'));
  });

  it('confirming disconnects that device and reloads the list', async () => {
    const wrapper = await mountCard();
    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    await wrapper.get('[data-test="confirm-dev_abc"]').trigger('click');
    await flushPromises();

    expect(revokeDevice).toHaveBeenCalledWith('dev_abc');
    // Reloaded, never patched locally: what the hub says is the truth, and the counts on the other
    // rows may have moved too.
    expect(vi.mocked(listDevices).mock.calls.length).toBe(2);
    // And the confirmation closes. Leaving it open over a fresh list would put a "remove?" question
    // in front of whatever row landed there next.
    expect(wrapper.html()).not.toContain(i18n.global.t('devices.confirm'));
  });

  it('cutting off your own device sends you to the login instead of leaving a dead session', async () => {
    vi.mocked(listDevices).mockResolvedValue([device({ current: true })]);
    vi.mocked(revokeDevice).mockResolvedValue({
      wasKnown: true,
      sessionsClosed: 1,
      wasCurrent: true,
    });
    const wrapper = await mountCard();
    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    await wrapper.get('[data-test="confirm-dev_abc"]').trigger('click');
    await flushPromises();

    // The session it was using is gone server-side; keeping the screen up would mean every next tap
    // fails with an authentication error nobody can act on.
    expect(logout).toHaveBeenCalled();
    expect(replace).toHaveBeenCalledWith('/login');
  });

  it('cutting off ANOTHER device leaves you exactly where you were', async () => {
    const wrapper = await mountCard();
    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    await wrapper.get('[data-test="confirm-dev_abc"]').trigger('click');
    await flushPromises();

    // The other half of the branch above, and the one that would be caught late: signing the owner
    // out every time they tidy up an old tablet would make the screen unusable.
    expect(logout).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('a refusal keeps the reason on screen and does not pretend it worked', async () => {
    vi.mocked(revokeDevice).mockRejectedValue(new DevicesError('sesión inválida o caducada'));
    const wrapper = await mountCard();
    await wrapper.get('[data-test="revoke-dev_abc"]').trigger('click');

    await wrapper.get('[data-test="confirm-dev_abc"]').trigger('click');
    await flushPromises();

    expect(wrapper.html()).toContain('sesión inválida o caducada');
  });

  it('an employee is told who can do this, instead of finding a dead button', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;

    const wrapper = await mountCard();

    expect(wrapper.html()).toContain(i18n.global.t('devices.adminOnly'));
    expect(wrapper.find('[data-test="revoke-dev_abc"]').exists()).toBe(false);
    // The mirror stops here too, exactly like `DeviceModeCard.choose`; the runtime revalidates.
    expect(revokeDevice).not.toHaveBeenCalled();
  });

  it('the guard is in the handler, not only in the missing button', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = await mountCard();

    // Reached the way anything that is not the button would reach it. Hiding a control is a
    // courtesy; the handler refusing is the mirror of the runtime's own gate (ADR-0248).
    (wrapper.vm as unknown as { ask: (id: string) => void }).ask('dev_abc');
    await (wrapper.vm as unknown as { revoke: (d: unknown) => Promise<void> }).revoke(device());
    await flushPromises();

    expect(revokeDevice).not.toHaveBeenCalled();
    expect(wrapper.html()).not.toContain(i18n.global.t('devices.confirm'));
  });
});

describe('the words', () => {
  it('says it in Spanish too, and without a word a shopkeeper does not use', async () => {
    const keys = [
      'title',
      'intro',
      'thisDevice',
      'unnamed',
      'empty',
      'confirm',
      'confirmCurrent',
      'consequence',
      'adminOnly',
      'inUse',
      'lastUsed',
      'revoke',
      'cancel',
      'loadError',
      // hub#494 — the words of naming a device.
      'rename',
      'nameLabel',
      'save',
      'lastSignedInBy',
      'renameError',
    ];
    for (const key of keys) {
      const spanish = i18n.global.t(`devices.${key}`, 1, { locale: 'es' });
      expect(spanish, key).toBeTruthy();
      expect(spanish, key).not.toBe(i18n.global.t(`devices.${key}`, 1, { locale: 'en' }));
      // ADR-0254 fixed the product's vocabulary: "tu negocio", "apps", "Mi plan". "Hub" is our word
      // for our thing, and this screen is read by somebody running a bar.
      expect(spanish.toLowerCase(), key).not.toMatch(/\bhubs?\b/);
    }
  });
});

describe('naming a device (hub#494)', () => {
  it('an administrator names it from the row, and the list comes back from the hub', async () => {
    const wrapper = await mountCard();

    await wrapper.get('[data-test="rename-dev_abc"]').trigger('click');
    type(wrapper, 'Cocina');
    await wrapper.get('[data-test="save-name-dev_abc"]').trigger('click');
    await flushPromises();

    expect(renameDevice).toHaveBeenCalledWith('dev_abc', 'Cocina');
    // Reloaded, not patched in place: what the row says is the hub's to decide, exactly as in the
    // revocation. A name that only changed on screen is the failure mode this whole card avoids.
    expect(listDevices).toHaveBeenCalledTimes(2);
  });

  it('only an administrator is offered the pencil', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;

    const wrapper = await mountCard();

    // Mirror of the runtime gate (ADR-0248), which revalidates anyway: a name that whoever holds a
    // device could write would be worth exactly what `label` is worth — nothing.
    expect(wrapper.find('[data-test="rename-dev_abc"]').exists()).toBe(false);
  });

  it('a refused rename says why instead of looking like a name that stuck', async () => {
    vi.mocked(renameDevice).mockRejectedValue(new DevicesError('sesión inválida o caducada'));
    const wrapper = await mountCard();

    await wrapper.get('[data-test="rename-dev_abc"]').trigger('click');
    type(wrapper, 'Cocina');
    await wrapper.get('[data-test="save-name-dev_abc"]').trigger('click');
    await flushPromises();

    expect(wrapper.html()).toContain('sesión inválida o caducada');
  });

  it('naming is never one tap away from disconnecting', async () => {
    const wrapper = await mountCard();

    await wrapper.get('[data-test="rename-dev_abc"]').trigger('click');
    await wrapper.get('[data-test="save-name-dev_abc"]').trigger('click');
    await flushPromises();

    // The two gestures share a row and nothing else: housekeeping must not be able to take a till
    // down because a control was where the other one used to be.
    expect(revokeDevice).not.toHaveBeenCalled();
  });
});
