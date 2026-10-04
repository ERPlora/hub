// @vitest-environment happy-dom
// hub#2336 — with the marketplace down, the bell said «All caught up. No notifications.»: the same
// words as a hub whose apps are all current. When the check for new app versions could not be made,
// the bell now has a row saying so, with «Check again» (disabled and «Checking…» while it asks).
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { push, counts, notificationCount, unknown, checking, retry } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    push: vi.fn(),
    counts: ref<Record<string, number>>({}),
    notificationCount: ref(0),
    unknown: ref(false),
    checking: ref(false),
    retry: vi.fn(),
  };
});

vi.mock('../lib/management-link', async () => {
  const { ref } = await import('vue');
  return { canOpenManagement: ref(false), openManagement: vi.fn() };
});
vi.mock('../lib/viewport', async () => {
  const { ref } = await import('vue');
  return { isCompactViewport: ref(false) };
});
vi.mock('../lib/shell', async () => {
  const { ref } = await import('vue');
  return {
    assistantAvailable: ref(false),
    toggleAssistant: vi.fn(),
    notificationCount,
    notificationCountOf: (source: string) => counts.value[source] ?? 0,
    isLoading: ref(false),
    railCollapsed: ref(false),
  };
});
vi.mock('../lib/module-update-notice', () => ({
  MODULE_UPDATES_ROUTE: '/apps#mine',
  moduleUpdatesUnknown: unknown,
  moduleUpdatesChecking: checking,
  retryModuleUpdateNotice: retry,
}));
vi.mock('../lib/bell-counters', async () => {
  const { ref } = await import('vue');
  return { bellCounters: ref([]) };
});
vi.mock('../lib/nav', async () => {
  const { ref } = await import('vue');
  return { moduleNav: ref([]) };
});
vi.mock('../lib/icons', () => ({ resolveIcon: (name: string) => name }));
vi.mock('./HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span :data-icon="name" />' },
}));
vi.mock('vue-router', () => ({ useRouter: () => ({ push, back: vi.fn() }) }));

import AppTopbar from './AppTopbar.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const mountTopbar = (locale: 'en' | 'es' = 'en') =>
  mount(AppTopbar, {
    props: { title: 'Till' },
    global: {
      plugins: [createI18n({ legacy: false, locale, messages: { en, es } })],
      stubs: {
        IonPopover: {
          props: ['isOpen'],
          template: '<div class="popover-stub" :data-open="String(!!isOpen)"><slot /></div>',
        },
        IonContent: { template: '<div><slot /></div>' },
        IonLabel: { template: '<div><slot /></div>' },
        IonButton: {
          props: ['disabled'],
          emits: ['click'],
          template: '<button :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>',
        },
      },
    },
  });

const ROW = '[data-testid="topbar-module-updates-unknown"]';
const RETRY = '[data-testid="topbar-module-updates-retry"]';

beforeEach(() => {
  push.mockClear();
  retry.mockClear();
  counts.value = {};
  notificationCount.value = 0;
  unknown.value = false;
  checking.value = false;
});

describe('the bell says when it could not check for new app versions (hub#2336)', () => {
  it('🔴 paints a row saying so instead of «All caught up»', async () => {
    unknown.value = true;
    const wrapper = mountTopbar();
    await flushPromises();

    const row = wrapper.find(ROW);
    expect(row.exists()).toBe(true);
    expect(row.text()).toContain(en.topbar.moduleUpdatesUnknownTitle);
    expect(row.text()).toContain(en.topbar.moduleUpdatesUnknownBody);
    expect(row.find('[data-icon="cloud-offline-outline"]').exists()).toBe(true);
    expect(wrapper.html(), '«could not check» is not «all caught up»').not.toContain(en.topbar.noNotifications);
  });

  it('says it in Spanish', async () => {
    unknown.value = true;
    const wrapper = mountTopbar('es');
    await flushPromises();

    const text = wrapper.find(ROW).text();
    expect(text).toContain(es.topbar.moduleUpdatesUnknownTitle);
    expect(text).toContain(es.topbar.moduleUpdatesUnknownBody);
    expect(wrapper.find(RETRY).text()).toBe(es.topbar.moduleUpdatesRetry);
    expect(wrapper.html()).not.toContain(es.topbar.noNotifications);
  });

  it('🔴 «Check again» asks again', async () => {
    unknown.value = true;
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find(RETRY).text()).toBe(en.topbar.moduleUpdatesRetry);
    await wrapper.find(RETRY).trigger('click');

    expect(retry).toHaveBeenCalledTimes(1);
  });

  it('is «Checking…» and cannot be pressed while it asks', async () => {
    unknown.value = true;
    checking.value = true;
    const wrapper = mountTopbar();
    await flushPromises();

    const button = wrapper.find(RETRY);
    expect(button.text()).toBe(en.topbar.moduleUpdatesChecking);
    expect(button.attributes('disabled')).toBeDefined();
  });

  it('can be pressed again once the question is back', async () => {
    unknown.value = true;
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find(RETRY).attributes('disabled')).toBeUndefined();
  });

  // Next to the known count, both rows: «2 apps have a new version» is still true.
  it('sits next to the last known «apps have a new version» row', async () => {
    unknown.value = true;
    counts.value = { moduleUpdates: 2 };
    notificationCount.value = 2;
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find('[data-testid="topbar-module-updates"]').exists()).toBe(true);
    expect(wrapper.find(ROW).exists()).toBe(true);
  });

  it('is not there when the check answered', async () => {
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find(ROW).exists()).toBe(false);
    expect(wrapper.html()).toContain(en.topbar.noNotifications);
  });

  it('en and es carry every sentence, and they differ', () => {
    for (const key of [
      'moduleUpdatesUnknownTitle',
      'moduleUpdatesUnknownBody',
      'moduleUpdatesRetry',
      'moduleUpdatesChecking',
    ] as const) {
      expect(en.topbar[key], key).toBeTruthy();
      expect(es.topbar[key], key).toBeTruthy();
      expect(es.topbar[key], key).not.toBe(en.topbar[key]);
    }
  });
});
