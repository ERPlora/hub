// @vitest-environment happy-dom
// hub#364 — the entry to management in the Hub topbar (PLAN step 8).
//
// The hard part of this button is not that it navigates: it is that it takes the user OUT of the
// product they are standing in. So the tests are about the guard and about the WORDS:
//
//   - **It is filtered, not walled** (ADR-0248): a cashier does not see it. There is no consequence
//     to warn them about — managing the plan is not their task, and the account it leads to may not
//     even exist for them. A wall is for what will refuse THEIR sale, and this refuses nothing.
//   - **The name says where it goes, and it is READ.** This crosses a product boundary, so it has
//     to say `erplora.com` — out loud in the accessible name, and on screen in the entry itself
//     (hub#1400: at the till it used to be icon-only, so you had to guess the pictogram).
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

// What the eye reads on the button. NOT `wrapper.text()`: `ion-label` is a REGISTERED custom
// element here (importing `@ionic/vue` defines it), and happy-dom hands those back with an empty
// `textContent` — which is exactly what `text()` reads, so it answers '' however loudly the button
// is labelled. `innerHTML` carries what was painted. Reading the label ELEMENT keeps the assertion
// honest in the other direction too: go back to icon-only and there is no `ion-label` inside the
// button at all, so this returns '' and the tests below fail.
const visibleWords = (button: ReturnType<typeof manageButton>) => {
  const label = button!.find('ion-label');
  return label.exists() ? label.element.innerHTML.trim() : '';
};

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
  // Profile, ModuleView). In the topbar that is not enough: a cloud names the DESTINATION — the
  // online account — instead of merely announcing that something opens.
  it('carries the cloud: the destination, not just the fact that it leaves', () => {
    const icon = manageButton(mountTopbar())!.find('[data-icon]');

    expect(icon.attributes('data-icon')).toBe('cloud-outline');
  });

  // hub#1400. This used to be icon-only on the wide viewport — the very screen people work on — and
  // laballed only in the phone overflow. So on a phone you could read it and at the till you had to
  // guess the pictogram. ADR-0251 argued it out ("the accessible name says erplora.com out loud"),
  // but the accessible name is not what somebody looking at the screen reads.
  it('can be READ at the till: the entry carries visible text, not only an icon', () => {
    const button = manageButton(mountTopbar());

    expect(visibleWords(button)).toContain('erplora.com');
  });

  it('puts the words in both languages, because the entry is what is read', () => {
    for (const locale of ['en', 'es']) {
      expect(visibleWords(manageButton(mountTopbar(locale)))).toContain('erplora.com');
    }
  });

  // The visible word and the accessible name are not the same string on purpose: the short one is
  // what fits in a topbar next to three other actions, the long one is the whole sentence. WCAG
  // 2.5.3 only asks that the name CONTAIN what is written, which is why the short one is the brand.
  it('keeps the icon beside the words instead of standing in for them', () => {
    const icon = manageButton(mountTopbar())!.find('[data-icon]');

    expect(icon.attributes('slot')).toBe('start');
  });
});

describe('the catalogues', () => {
  // The short label is the BRAND, so it is the same word in every language — what changes around it
  // is the sentence the accessible name reads out. Naming the destination is what the market does
  // with a link to a sibling product (Shopify POS → "Shopify admin", Square → "Dashboard").
  it('carry a short label that is the destination itself', () => {
    expect(en.topbar.manageShort).toBe('erplora.com');
    expect(es.topbar.manageShort).toBe('erplora.com');
  });

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
