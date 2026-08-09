// @vitest-environment happy-dom
// hub#364 — the entry to management in the Hub topbar (PLAN step 8).
//
// The hard part of this button is not that it navigates: it is that it takes the user OUT of the
// product they are standing in. So the tests are about the guard and about the WORDS:
//
//   - **It is filtered, not walled** (ADR-0248): a cashier does not see it. There is no consequence
//     to warn them about — managing the plan is not their task, and the account it leads to may not
//     even exist for them. A wall is for what will refuse THEIR sale, and this refuses nothing.
//   - **The name says where it goes.** The only affordance an icon-only topbar action has is its
//     accessible name, and this one crosses a product boundary: it has to say `erplora.com` out
//     loud, in every language, or the till just teleports somewhere without warning.
//   - **It leaves through `openManagement`**, the one helper that knows how the door opens on each
//     surface: a new tab in a browser, the system browser in the installed app.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

// A real `ref`: the template unwraps it, and a plain object would make `v-if` a constant — the
// guard would look wired while it never actually closes.
const { canOpenManagement, openManagement } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return { canOpenManagement: ref(true), openManagement: vi.fn() };
});
vi.mock('../lib/management-link', () => ({ canOpenManagement, openManagement }));

vi.mock('../lib/shell', async () => {
  const { ref, computed } = await import('vue');
  return {
    assistantAvailable: computed(() => false),
    toggleAssistant: vi.fn(),
    notificationCount: computed(() => 0),
    isLoading: computed(() => false),
    railCollapsed: ref(false),
  };
});
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('../lib/icons', () => ({ resolveIcon: (name: string) => name }));
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn(), back: vi.fn() }) }));

import AppTopbar from './AppTopbar.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// The REAL catalogues: what reaches the reader IS the feature here, so a mute i18n would hide
// exactly what these tests exist for.
const mountTopbar = (locale = 'en') =>
  mount(AppTopbar, {
    props: { title: 'Till' },
    global: {
      plugins: [
        createI18n({
          legacy: false,
          locale,
          missingWarn: false,
          fallbackWarn: false,
          messages: { en, es },
        }),
      ],
    },
  });

const manageButton = (wrapper: ReturnType<typeof mountTopbar>) =>
  wrapper.findAll('ion-button').find((b) => b.attributes('data-testid') === 'topbar-manage');

beforeEach(() => {
  openManagement.mockClear();
  canOpenManagement.value = true;
});

describe('the entry to management', () => {
  it('is offered to a session that administers the hub', () => {
    expect(manageButton(mountTopbar())).toBeTruthy();
  });

  it('is not offered to a session that does not — it is filtered, not shown blocked', () => {
    canOpenManagement.value = false;

    expect(manageButton(mountTopbar())).toBeFalsy();
  });

  it('leaves through the helper that opens the door OUT of this window', async () => {
    const button = manageButton(mountTopbar());

    await button!.trigger('click');

    expect(openManagement).toHaveBeenCalledTimes(1);
  });

  it('says out loud that it leads to erplora.com, in every language', () => {
    for (const locale of ['en', 'es']) {
      const button = manageButton(mountTopbar(locale));
      const name = button!.attributes('aria-label');

      expect(name).toContain('erplora.com');
      expect(button!.attributes('title')).toBe(name);
    }
  });

  // The mark used to be `open-outline`, the shell's generic "this leads to the SaaS" (Billing,
  // Profile, ModuleView). In the topbar that is not enough: those three sit next to a sentence that
  // says where they go, and this one is icon-only among three other icon-only actions. A cloud names
  // the DESTINATION — the online account — instead of merely announcing that something opens.
  it('carries the cloud: the destination, not just the fact that it leaves', () => {
    const icon = manageButton(mountTopbar())!.find('[data-icon]');

    expect(icon.attributes('data-icon')).toBe('cloud-outline');
  });
});

describe('the catalogues', () => {
  it('name the destination in both languages', () => {
    expect(en.topbar.manage).toContain('erplora.com');
    expect(es.topbar.manage).toContain('erplora.com');
  });

  it('do not leak the words the plan banned from the till', () => {
    // PLAN step 8: in simple view the jargon does not appear — no "hub", no "organización",
    // no "entitlement". This string is read by the owner of a bar, not by us.
    for (const copy of [en.topbar.manage, es.topbar.manage]) {
      expect(copy.toLowerCase()).not.toContain('hub');
      expect(copy.toLowerCase()).not.toContain('organiz');
      expect(copy.toLowerCase()).not.toContain('entitlement');
    }
  });
});
