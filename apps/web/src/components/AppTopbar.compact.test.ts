// @vitest-environment happy-dom
// The topbar on a phone — where the global actions stopped fitting beside the title.
//
// Ionic centres `ion-title` in `ios` mode, so the buttons of the `end` slot do not push the title
// aside: they sit ON it. With four of them (apps, management, assistant, notifications) the name of
// the screen was unreadable at 390px (reported by Ioan, 2026-08-09).
//
// The answer is the one every phone toolbar uses: below the tablet step the secondary actions
// collapse into a single OVERFLOW menu, and the title gets its width back. Two rules hold it
// together, and they are what these tests defend:
//
//   - **Nothing is lost on the way in.** Every action that the wide toolbar offers this session is a
//     row of the menu — same guard, same words. Hiding a button with CSS would have been shorter and
//     would have left all of them in the tab order and announced to a screen reader.
//   - **The apps launcher does NOT collapse.** It is the way into the installed modules — the till
//     itself — not a secondary action, and it already opens its own sheet.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { canOpenManagement, openManagement, isCompactViewport, toggleAssistant, assistantAvailable } =
  await vi.hoisted(async () => {
    const { ref } = await import('vue');
    return {
      canOpenManagement: ref(true),
      openManagement: vi.fn(),
      isCompactViewport: ref(true),
      toggleAssistant: vi.fn(),
      assistantAvailable: ref(true),
    };
  });

vi.mock('../lib/management-link', () => ({ canOpenManagement, openManagement }));
vi.mock('../lib/viewport', () => ({ isCompactViewport }));
vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantAvailable,
    toggleAssistant,
    notificationCount: ref(0),
    isLoading: ref(false),
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

const at = (wrapper: ReturnType<typeof mountTopbar>, testid: string) =>
  wrapper.find(`[data-testid="${testid}"]`);

beforeEach(() => {
  openManagement.mockClear();
  toggleAssistant.mockClear();
  canOpenManagement.value = true;
  assistantAvailable.value = true;
  isCompactViewport.value = true;
});

describe('on a phone', () => {
  it('leaves ONE action beside the title instead of the row that covered it', () => {
    const wrapper = mountTopbar();

    expect(at(wrapper, 'topbar-more').exists()).toBe(true);
    for (const collapsed of ['topbar-manage', 'topbar-assistant', 'topbar-notifications']) {
      expect(at(wrapper, collapsed).exists()).toBe(false);
    }
  });

  it('keeps the apps launcher out of the menu — it is the door to the till, not an extra', () => {
    expect(mountTopbar().find('ok-app-launcher').exists()).toBe(true);
  });

  it('hands the menu the same three actions the wide toolbar offers', () => {
    const wrapper = mountTopbar();

    for (const row of ['topbar-more-manage', 'topbar-more-assistant', 'topbar-more-notifications']) {
      expect(at(wrapper, row).exists()).toBe(true);
    }
  });

  it('opens management from the menu through the same door as the button', async () => {
    const wrapper = mountTopbar();

    await at(wrapper, 'topbar-more-manage').trigger('click');

    expect(openManagement).toHaveBeenCalledTimes(1);
  });

  it('opens the assistant from the menu', async () => {
    const wrapper = mountTopbar();

    await at(wrapper, 'topbar-more-assistant').trigger('click');

    expect(toggleAssistant).toHaveBeenCalledTimes(1);
  });

  it('does not smuggle past a guard what the toolbar would have filtered out', () => {
    canOpenManagement.value = false;
    assistantAvailable.value = false;

    const wrapper = mountTopbar();

    expect(at(wrapper, 'topbar-more-manage').exists()).toBe(false);
    expect(at(wrapper, 'topbar-more-assistant').exists()).toBe(false);
    // Notifications are for every session: nothing gates the bell.
    expect(at(wrapper, 'topbar-more-notifications').exists()).toBe(true);
  });

  it('names the menu in every language — it is icon-only, the name is all there is', () => {
    for (const locale of ['en', 'es']) {
      const button = at(mountTopbar(locale), 'topbar-more');

      expect(button.attributes('aria-label')).toBe(
        locale === 'en' ? en.topbar.more : es.topbar.more,
      );
      expect(button.attributes('aria-label')).toBeTruthy();
    }
  });
});

describe('on a screen with room', () => {
  beforeEach(() => {
    isCompactViewport.value = false;
  });

  it('shows the actions themselves and no menu — a phone pattern on a desktop is a step backwards', () => {
    const wrapper = mountTopbar();

    expect(at(wrapper, 'topbar-more').exists()).toBe(false);
    for (const action of ['topbar-manage', 'topbar-assistant', 'topbar-notifications']) {
      expect(at(wrapper, action).exists()).toBe(true);
    }
  });
});
