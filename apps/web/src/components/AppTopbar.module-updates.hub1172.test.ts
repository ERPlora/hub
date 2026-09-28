// @vitest-environment happy-dom
// hub#1172 — the owner learns that apps are behind from ANY screen: the bell carries one row
// («3 apps have a new version») whose tap lands on Apps → «My apps», where each update is one tap.
// Without the row, the badge would count something nobody can find under it.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { push, counts, notificationCount } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    push: vi.fn(),
    counts: ref<Record<string, number>>({}),
    notificationCount: ref(0),
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
        // Render the popover's content in place: what is under test is the rows, not Ionic.
        IonPopover: { template: '<div><slot /></div>' },
        IonContent: { template: '<div><slot /></div>' },
        IonLabel: { template: '<div><slot /></div>' },
      },
    },
  });

const ROW = '[data-testid="topbar-module-updates"]';

beforeEach(() => {
  push.mockClear();
  counts.value = {};
  notificationCount.value = 0;
});

describe('apps with a new version on the bell (hub#1172)', () => {
  it('paints one row saying how many apps have a new version', async () => {
    counts.value = { moduleUpdates: 3 };
    notificationCount.value = 3;
    const wrapper = mountTopbar();
    await flushPromises();

    const rows = wrapper.findAll(ROW);
    expect(rows).toHaveLength(1);
    expect(rows[0]!.text()).toContain('App updates available');
    expect(rows[0]!.text()).toContain('3 apps have a new version');
    expect(rows[0]!.find('[data-icon="cloud-download-outline"]').exists()).toBe(true);
    expect(wrapper.html()).not.toContain(en.topbar.noNotifications);
  });

  it('says it in the singular for one app', async () => {
    counts.value = { moduleUpdates: 1 };
    notificationCount.value = 1;
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find(ROW).text()).toContain('1 app has a new version');
  });

  it('is translated to Spanish', async () => {
    counts.value = { moduleUpdates: 2 };
    notificationCount.value = 2;
    const wrapper = mountTopbar('es');
    await flushPromises();

    const text = wrapper.find(ROW).text();
    expect(text).toContain('Actualizaciones de apps');
    expect(text).toContain('2 apps tienen una versión nueva');
  });

  it('takes the owner to «My apps»', async () => {
    counts.value = { moduleUpdates: 2 };
    notificationCount.value = 2;
    const wrapper = mountTopbar();
    await flushPromises();

    await wrapper.find(ROW).trigger('click');

    expect(push).toHaveBeenCalledWith('/apps#mine');
  });

  it('is not there when every app is up to date', async () => {
    const wrapper = mountTopbar();
    await flushPromises();

    expect(wrapper.find(ROW).exists()).toBe(false);
    expect(wrapper.html()).toContain(en.topbar.noNotifications);
  });
});
