// @vitest-environment happy-dom
// hub#1678 — what a module raises on the bell has to be a row the owner can act on: its label,
// how many are waiting, and a tap that lands on the module's tab (the diary for appointments to
// confirm). A number on the badge with no row under it is a bell nobody can answer.
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

const { push, bellCounters, notificationCount } = await vi.hoisted(async () => {
  const { ref } = await import('vue');
  return {
    push: vi.fn(),
    bellCounters: ref<
      { key: string; label: string; icon?: string; count: number; path: string }[]
    >([]),
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
    notificationCountOf: () => 0,
    isLoading: ref(false),
    railCollapsed: ref(false),
  };
});
vi.mock('../lib/bell-counters', () => ({ bellCounters }));
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

const mountTopbar = () =>
  mount(AppTopbar, {
    props: { title: 'Till' },
    global: {
      plugins: [
        createI18n({ legacy: false, locale: 'en', messages: { en, es } }),
      ],
      stubs: {
        // Render the popover's content in place: what is under test is the rows, not Ionic.
        IonPopover: { template: '<div><slot /></div>' },
        IonContent: { template: '<div><slot /></div>' },
        IonLabel: { template: '<div><slot /></div>' },
      },
    },
  });

beforeEach(() => {
  push.mockClear();
  bellCounters.value = [];
  notificationCount.value = 0;
});

describe('module counters on the bell (hub#1678)', () => {
  it('paints one row per counter with its label and how many are waiting', async () => {
    bellCounters.value = [
      {
        key: 'appointments.to_confirm',
        label: 'Appointments to confirm',
        icon: 'calendar-outline',
        count: 2,
        path: '/m/appointments/agenda',
      },
    ];
    notificationCount.value = 2;
    const wrapper = mountTopbar();
    await flushPromises();

    const rows = wrapper.findAll('[data-testid="topbar-bell-counter"]');
    expect(rows).toHaveLength(1);
    expect(rows[0]!.text()).toContain('Appointments to confirm');
    expect(rows[0]!.text()).toContain('2');
    expect(rows[0]!.find('[data-icon="calendar-outline"]').exists()).toBe(true);
    expect(wrapper.text()).not.toContain(en.topbar.noNotifications);
  });

  it('takes the owner to the tab the module declared', async () => {
    bellCounters.value = [
      {
        key: 'appointments.to_confirm',
        label: 'Appointments to confirm',
        count: 1,
        path: '/m/appointments/agenda',
      },
    ];
    notificationCount.value = 1;
    const wrapper = mountTopbar();
    await flushPromises();

    await wrapper.find('[data-testid="topbar-bell-counter"]').trigger('click');

    expect(push).toHaveBeenCalledWith('/m/appointments/agenda');
  });

  it('falls back to a bell icon when the module names none', async () => {
    bellCounters.value = [
      { key: 'reservations.to_confirm', label: 'Bookings to confirm', count: 1, path: '/m/reservations' },
    ];
    notificationCount.value = 1;
    const wrapper = mountTopbar();
    await flushPromises();

    const row = wrapper.find('[data-testid="topbar-bell-counter"]');
    expect(row.find('[data-icon="notifications-outline"]').exists()).toBe(true);
  });
});
