// @vitest-environment happy-dom
// The one visible half of hub#400: the entry that appears in the LEFT sidebar when the app on this
// counter is older than the one we publish.
//
// Three ways of showing nothing are asserted here as hard as the one way of showing something,
// because each is a different lie the till could tell: `unknown` painted as an offer would send
// someone to reinstall over a flaky wifi; an offer with nowhere to go is the mute button hub#480 is
// about; and an offer to a waiter is a task that is not theirs (ADR-0248 — it is filtered away, not
// shown disabled).
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

import type { AppUpdate } from '../lib/app-update';

const { appUpdate, appUpdateDestination, canUpdateApp } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    // Real `ref`s: a plain object would make every `v-if` a constant, and the guards would look
    // wired while none of them ever closed.
    appUpdate: ref<AppUpdate>({ state: 'attention', installed: '1.2.3', latest: '1.4.0' }),
    appUpdateDestination: ref<string | null>('https://erplora.com/app/download/windows/'),
    canUpdateApp: ref(true),
  };
});
vi.mock('../lib/app-update', () => ({ appUpdate, appUpdateDestination, canUpdateApp }));

const { openExternal, OpenExternalError, toastError, alertCreate } = vi.hoisted(() => {
  class OpenExternalError extends Error {}
  return {
    openExternal: vi.fn(async () => undefined),
    OpenExternalError,
    toastError: vi.fn(),
    alertCreate: vi.fn(),
  };
});
vi.mock('../lib/open-external', () => ({ openExternal, OpenExternalError }));
vi.mock('../lib/toast', () => ({ toastError, toastInfo: vi.fn(), toastSuccess: vi.fn() }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, alertController: { create: (...args: unknown[]) => alertCreate(...args) } };
});

vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));

import SidebarAppUpdate from './SidebarAppUpdate.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

/** An alert that answers `role` when dismissed. */
function alertAnswering(role: string): { present: ReturnType<typeof vi.fn> } {
  const present = vi.fn(async () => undefined);
  alertCreate.mockResolvedValue({ present, onDidDismiss: async () => ({ role }) });
  return { present };
}

const mountItem = (locale = 'en') =>
  mount(SidebarAppUpdate, {
    global: {
      plugins: [
        createI18n({ legacy: false, locale, missingWarn: false, fallbackWarn: false, messages: { en, es } }),
      ],
    },
  });

const entry = (wrapper: ReturnType<typeof mountItem>) =>
  wrapper.find('[data-testid="sidebar-app-update"]');

beforeEach(() => {
  vi.clearAllMocks();
  appUpdate.value = { state: 'attention', installed: '1.2.3', latest: '1.4.0' };
  appUpdateDestination.value = 'https://erplora.com/app/download/windows/';
  canUpdateApp.value = true;
  alertAnswering('confirm');
});

describe('the sidebar entry', () => {
  it('appears when a newer app is published', () => {
    expect(entry(mountItem()).exists()).toBe(true);
  });

  it('names the version that is waiting, in both languages', () => {
    // `.html()`, not `.text()`: Ionic's tags are unresolved custom elements here, and happy-dom
    // reports no `textContent` for those — a `.text()` assertion would pass on an empty string and
    // keep passing after the label disappeared.
    expect(mountItem('en').html()).toContain('Update ERPlora (1.4.0)');
    expect(mountItem('es').html()).toContain('Actualizar ERPlora (1.4.0)');
  });

  it('says nothing when this app is the one we publish', () => {
    appUpdate.value = { state: 'ok', installed: '1.4.0', latest: '1.4.0' };
    expect(entry(mountItem()).exists()).toBe(false);
  });

  it('says nothing when it could NOT check', () => {
    // The morning the bar has no internet. Not green, not an alarm: silence.
    appUpdate.value = { state: 'unknown', installed: '1.2.3', latest: null };
    expect(entry(mountItem()).exists()).toBe(false);
  });

  it('says nothing when there is nowhere to send this device', () => {
    // macOS: built locally, never published. A button that leads to a 404 is the mute failure.
    appUpdateDestination.value = null;
    expect(entry(mountItem()).exists()).toBe(false);
  });

  it('is filtered away for a session that does not administer, never shown blocked', () => {
    // ADR-0248: a task that is not yours goes away. A cashier mid-service is not who decides that
    // the till gets reinstalled, and a disabled button would only invite them to ask why.
    canUpdateApp.value = false;
    const wrapper = mountItem();
    expect(entry(wrapper).exists()).toBe(false);
    expect(wrapper.html()).not.toContain('1.4.0');
  });
});

describe('pressing it', () => {
  it('asks first, and only then hands the address to the user own browser', async () => {
    const wrapper = mountItem();

    await entry(wrapper).trigger('click');
    await Promise.resolve();
    await Promise.resolve();

    expect(alertCreate).toHaveBeenCalled();
    expect(openExternal).toHaveBeenCalledWith('https://erplora.com/app/download/windows/');
  });

  it('does nothing at all when the answer is no', async () => {
    alertAnswering('cancel');
    const wrapper = mountItem();

    await entry(wrapper).trigger('click');
    await Promise.resolve();
    await Promise.resolve();

    expect(openExternal).not.toHaveBeenCalled();
  });

  it('SAYS SO when the trip out could not be made', async () => {
    // ADR-0255 rule 5, and the reason hub#475 existed at all: a press that does nothing, with no
    // window and no error, is indistinguishable from a broken product.
    openExternal.mockRejectedValueOnce(new OpenExternalError('nope'));
    const wrapper = mountItem();

    await entry(wrapper).trigger('click');
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();

    expect(toastError).toHaveBeenCalled();
  });
});

describe('the catalogues', () => {
  it('warn that the app will have to be closed — nobody is updated behind their back', () => {
    // There is no signing key yet (hub#394), so there is no in-place updater: what actually happens
    // is a download the user runs themselves. Saying "updating…" would be a promise we do not keep.
    for (const catalogue of [en, es]) {
      const copy = catalogue as unknown as { appUpdate: Record<string, string> };
      expect(copy.appUpdate.available).toContain('{version}');
      expect(copy.appUpdate.confirmTitle.length).toBeGreaterThan(0);
      expect(copy.appUpdate.confirmBody.length).toBeGreaterThan(0);
      expect(copy.appUpdate.action.length).toBeGreaterThan(0);
      expect(copy.appUpdate.cancel.length).toBeGreaterThan(0);
      expect(copy.appUpdate.failed.length).toBeGreaterThan(0);
    }
  });

  it('does not promise an update that installs itself', () => {
    const english = (en as unknown as { appUpdate: Record<string, string> }).appUpdate;
    expect(english.confirmBody.toLowerCase()).toContain('download');
  });
});
