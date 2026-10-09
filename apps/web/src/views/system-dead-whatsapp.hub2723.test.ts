// @vitest-environment happy-dom
// hub#2723 — a WhatsApp that WhatsApp refused, or accepted and then did not deliver, is in
// «Eventos caídos». The row must say so in the owner's words — what happened and why, and whether
// resending helps — instead of the raw error alone, and the one that cannot be resent must neither
// offer the button nor blame a withdrawn permission.
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { enableAutoUnmount, flushPromises, mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';

const { admin, route } = await vi.hoisted(async () => {
  const vue = await import('vue');
  return { admin: vue.ref(false), route: vue.reactive({ path: '/system', hash: '' }) };
});

const { fetchSystemInfo, fetchUsageSeries, fetchDeadLetters } = vi.hoisted(() => ({
  fetchSystemInfo: vi.fn(),
  fetchUsageSeries: vi.fn(),
  fetchDeadLetters: vi.fn(),
}));

vi.mock('../lib/session', async () => {
  const actual = await vi.importActual<typeof import('../lib/session')>('../lib/session');
  return { ...actual, isAdmin: admin, isAuthed: ref(true), user: ref({ id: 'someone' }) };
});
vi.mock('../lib/system', async () => {
  const actual = await vi.importActual<typeof import('../lib/system')>('../lib/system');
  return { ...actual, fetchSystemInfo };
});
vi.mock('../lib/system-usage', async () => {
  const actual = await vi.importActual<typeof import('../lib/system-usage')>('../lib/system-usage');
  return { ...actual, fetchUsageSeries };
});
vi.mock('../lib/module-loader', () => ({ loadInstalledManifests: vi.fn(async () => []) }));
vi.mock('../lib/runtime', async () => {
  const actual = await vi.importActual<typeof import('../lib/runtime')>('../lib/runtime');
  return { ...actual, listInstalledModules: vi.fn(async () => []), listModuleUpdates: vi.fn(async () => []) };
});
vi.mock('../lib/update-history', async () => {
  const actual = await vi.importActual<typeof import('../lib/update-history')>('../lib/update-history');
  return { ...actual, fetchUpdateHistory: vi.fn(async () => []) };
});
vi.mock('../lib/dead-letter', async () => {
  const actual = await vi.importActual<typeof import('../lib/dead-letter')>('../lib/dead-letter');
  return { ...actual, fetchDeadLetters, refreshDeadLetterCount: vi.fn(async () => {}) };
});
vi.mock('../lib/bell-counters', () => ({ loadBellCounterModuleIds: vi.fn(async () => new Set()) }));
vi.mock('../lib/open-external', () => ({ openExternal: vi.fn(async () => {}) }));
vi.mock('../lib/toast', () => ({
  toast: vi.fn(),
  toastInfo: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));
vi.mock('../components/AppPage.vue', () => ({
  default: { name: 'AppPage', template: '<div><slot /><slot name="footer" /></div>' },
}));
vi.mock('../components/PlanLimitsPanel.vue', () => ({
  default: { name: 'PlanLimitsPanel', template: '<div />' },
}));
vi.mock('../components/HubIcon.vue', () => ({ default: { name: 'HubIcon', template: '<span />' } }));
vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));

import SystemPage from './SystemPage.vue';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const STATE = {
  backend: 'cloud',
  shell: 'web',
  hubVersion: 'v1.4.0',
  cpu: { usedLabel: '0,4 cores', fraction: 0.42 },
  memory: { usedLabel: '256 MB', fraction: 0.5 },
  database: { engine: 'postgres', connections: 3, connectionsLimit: 20 },
  logs: [{ when: '2026-10-06T10:00:00Z', level: 'ERROR', message: 'sale.closed', meta: 'AEAT 4102' }],
};

async function mountSystem() {
  const i18n = createI18n({
    legacy: false,
    locale: 'en',
    fallbackLocale: 'en',
    missingWarn: false,
    fallbackWarn: false,
    messages: { en, es },
  });
  const wrapper = mount(SystemPage, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ok-') } },
    },
  });
  await flushPromises();
  return wrapper;
}

enableAutoUnmount(afterEach);

const row = (over: Record<string, unknown>) => ({
  id: 'ev-1',
  event_name: 'whatsapp_inbox.reminder.due',
  module_id: 'whatsapp_inbox',
  user_id: '',
  payload: { channel: 'whatsapp', to: '+34600111222' },
  last_error: 'host.notify: WhatsApp did not deliver it after accepting it: Meta 131047 (outside_window): Re-engagement message',
  attempts: 1,
  depth: 0,
  created_at: '2026-10-09T10:00:00Z',
  failure_kind: '',
  retryable: true,
  ...over,
});

beforeEach(() => {
  admin.value = true;
  route.path = '/system';
  route.hash = '#events';
  fetchSystemInfo.mockReset();
  fetchSystemInfo.mockResolvedValue(STATE);
  fetchUsageSeries.mockReset();
  fetchUsageSeries.mockResolvedValue(null);
  fetchDeadLetters.mockReset();
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => {
      throw new Error('the network is not part of this test');
    }),
  );
});

describe('a WhatsApp in «Eventos caídos» (hub#2723)', () => {
  it('accepted and not delivered: says so and why, offers no resend and blames no permission', async () => {
    fetchDeadLetters.mockResolvedValue([
      row({ failure_kind: 'whatsapp.undelivered.outside_window', retryable: false }),
    ]);
    const wrapper = await mountSystem();
    const text = wrapper.text();

    expect(fetchDeadLetters).toHaveBeenCalled();
    expect(text).toContain(
      en.system.whatsappUndelivered.replace('{reason}', en.system.whatsappReasons.outside_window),
    );
    expect(text).toContain(en.system.whatsappUndeliveredHint);
    expect(text).toContain('131047');
    expect(text).not.toContain(en.system.deadEventNotRetryable);
    expect(wrapper.findAll('.event-row__actions [name="refresh-outline"]')).toHaveLength(0);
  });

  it('refused with a reason: says WhatsApp refused it and why, and keeps the resend', async () => {
    fetchDeadLetters.mockResolvedValue([
      row({ failure_kind: 'whatsapp.refused.recipient_unreachable', retryable: true }),
    ]);
    const wrapper = await mountSystem();
    const text = wrapper.text();

    expect(text).toContain(
      en.system.whatsappRefused.replace('{reason}', en.system.whatsappReasons.recipient_unreachable),
    );
    expect(text).toContain(en.system.whatsappRefusedHint);
    expect(wrapper.findAll('.event-row__actions [name="refresh-outline"]')).toHaveLength(1);
  });

  it('any other row keeps the screen as it was', async () => {
    fetchDeadLetters.mockResolvedValue([
      row({ event_name: 'flow.step', failure_kind: 'flow.release_revoked', retryable: false, last_error: 'flow.release_revoked' }),
    ]);
    const wrapper = await mountSystem();
    const text = wrapper.text();

    expect(text).toContain(en.system.deadEventNotRetryable);
    expect(text).not.toContain(en.system.whatsappUndeliveredHint);
    expect(wrapper.find('.event-row__reason').exists()).toBe(false);
  });
});
