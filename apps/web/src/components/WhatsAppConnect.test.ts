// @vitest-environment happy-dom
// The «Channel» block a module embeds as `<erp-whatsapp-connect>` (hub#1600, ADR-0452): what the
// owner sees in each state, in the language of the till, with the runtime doors and Meta stubbed.
//
// Real catalogues (en + es), not inline strings: what these tests protect is that the sentence
// reaching a Spanish counter is Spanish — the family of hub#1241 — and that a refusal from the
// SaaS turns into a sentence a person can act on, never a code.
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';

vi.mock('../lib/whatsapp-connect', () => ({
  BUSINESS_APP_FEATURE: 'whatsapp_business_app_onboarding',
  WhatsAppConnectError: class WhatsAppConnectError extends Error {
    readonly code: string;
    readonly status: number;
    constructor(code: string, status: number) {
      super(code);
      this.code = code;
      this.status = status;
    }
  },
  fetchWhatsAppConfig: vi.fn(),
  fetchWhatsAppNumbers: vi.fn(),
  connectWhatsApp: vi.fn(),
  disconnectWhatsApp: vi.fn(),
  loadMetaSdk: vi.fn(),
  openEmbeddedSignup: vi.fn(),
}));
vi.mock('../lib/session', async () => {
  const { ref } = await import('vue');
  return { isAdmin: ref(true) };
});

import WhatsAppConnect from './WhatsAppConnect.vue';
import {
  WhatsAppConnectError,
  connectWhatsApp,
  disconnectWhatsApp,
  fetchWhatsAppConfig,
  fetchWhatsAppNumbers,
  loadMetaSdk,
  openEmbeddedSignup,
} from '../lib/whatsapp-connect';
import { isAdmin } from '../lib/session';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

const CONFIG = { configured: true, app_id: '1534856651538860', config_id: 'cfg_987', graph_version: 'v25.0' };
const NUMBER = { phone_number_id: 'phone_123', display_phone: '+34 612 345 678', is_active: true, is_on_biz_app: true };

function mountBlock(locale: 'en' | 'es' = 'es') {
  const i18n = createI18n({ legacy: false, locale, fallbackLocale: 'en', missingWarn: false, fallbackWarn: false, messages: { en, es } });
  return mount(WhatsAppConnect, {
    global: {
      plugins: [i18n],
      config: { compilerOptions: { isCustomElement: (tag: string) => tag.startsWith('ion-') || tag.startsWith('ok-') } },
    },
  });
}

beforeEach(() => {
  (isAdmin as unknown as { value: boolean }).value = true;
  vi.mocked(fetchWhatsAppConfig).mockReset().mockResolvedValue(CONFIG);
  vi.mocked(fetchWhatsAppNumbers).mockReset().mockResolvedValue([]);
  vi.mocked(connectWhatsApp).mockReset();
  vi.mocked(disconnectWhatsApp).mockReset().mockResolvedValue(undefined);
  vi.mocked(loadMetaSdk).mockReset().mockResolvedValue({ init: vi.fn(), login: vi.fn() });
  vi.mocked(openEmbeddedSignup).mockReset();
});

describe('what the owner sees', () => {
  it('renders nothing at all when the SaaS has no Meta app configured', async () => {
    vi.mocked(fetchWhatsAppConfig).mockResolvedValue({ configured: false, app_id: '', config_id: '', graph_version: 'v25.0' });
    const wrapper = mountBlock();
    await flushPromises();
    expect(wrapper.text().trim()).toBe('');
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
  });

  it('offers to connect, in Spanish, when no number is connected', async () => {
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.text()).toContain('Conectar WhatsApp');
    expect(wrapper.text()).not.toContain('Connect WhatsApp');
    expect(wrapper.text()).toContain('WhatsApp Business');
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(true);
  });

  it('and in English for an English till', async () => {
    const wrapper = mountBlock('en');
    await flushPromises();
    expect(wrapper.text()).toContain('Connect WhatsApp');
  });

  it('shows the connected number, marks the Business-app one, and offers to disconnect', async () => {
    vi.mocked(fetchWhatsAppNumbers).mockResolvedValue([NUMBER]);
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.text()).toContain('+34 612 345 678');
    expect(wrapper.text()).toContain(es.whatsappConnect.businessApp);
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="whatsapp-disconnect-button"]').exists()).toBe(true);
  });

  it('says the hub could not be reached instead of a blank block when the doors fail at mount', async () => {
    // A SaaS that is down at mount used to leave the block EMPTY: no button, no sentence — the
    // owner cannot tell «not available» from «broken». The refusal is painted, with its sentence.
    vi.mocked(fetchWhatsAppConfig).mockRejectedValue(new WhatsAppConnectError('unreachable', 0));
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.text()).toContain(es.whatsappConnect.errors.unreachable);
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
  });

  it('tells a cashier this is the owner’s when the runtime refuses the doors', async () => {
    // In production the runtime answers a cashier's session with 403 BEFORE any config arrives,
    // so the `isAdmin` branch below is never reached: this is the path a cashier actually walks.
    vi.mocked(fetchWhatsAppConfig).mockRejectedValue(new WhatsAppConnectError('forbidden', 403));
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.text()).toContain(es.whatsappConnect.errors.forbidden);
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
    expect(wrapper.find('[data-test="whatsapp-retry-button"]').exists()).toBe(false);
  });

  it('offers to retry after a failed mount and recovers when the doors answer', async () => {
    vi.mocked(fetchWhatsAppConfig).mockRejectedValueOnce(new WhatsAppConnectError('unreachable', 0)).mockResolvedValueOnce(CONFIG);
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.find('[data-test="whatsapp-retry-button"]').exists()).toBe(true);

    await wrapper.find('[data-test="whatsapp-retry-button"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(fetchWhatsAppConfig)).toHaveBeenCalledTimes(2);
    expect(wrapper.text()).not.toContain(es.whatsappConnect.errors.unreachable);
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(true);
  });

  it('tells a cashier this is the owner’s, without a button', async () => {
    (isAdmin as unknown as { value: boolean }).value = false;
    const wrapper = mountBlock('es');
    await flushPromises();
    expect(wrapper.text()).toContain(es.whatsappConnect.adminOnly);
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
  });
});

describe('connecting', () => {
  it('loads the SDK with the configuration the SaaS gave, opens the popup, posts the result and refreshes', async () => {
    const popup = { code: 'oauth-code', event: 'FINISH_WHATSAPP_BUSINESS_APP_ONBOARDING', waba_id: 'w', phone_number_id: 'phone_123', business_id: 'b' };
    vi.mocked(openEmbeddedSignup).mockResolvedValue(popup);
    vi.mocked(connectWhatsApp).mockResolvedValue({ phone_number_id: 'phone_123', display_phone: '+34 612 345 678', is_on_biz_app: true });
    vi.mocked(fetchWhatsAppNumbers).mockResolvedValueOnce([]).mockResolvedValueOnce([NUMBER]);
    const wrapper = mountBlock('es');
    await flushPromises();

    await wrapper.find('[data-test="whatsapp-connect-button"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(loadMetaSdk).mock.calls[0][0]).toMatchObject({ appId: '1534856651538860', graphVersion: 'v25.0', locale: 'es' });
    expect(vi.mocked(openEmbeddedSignup).mock.calls[0][1]).toBe('cfg_987');
    expect(vi.mocked(connectWhatsApp)).toHaveBeenCalledWith(popup);
    expect(wrapper.text()).toContain('+34 612 345 678');
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(false);
  });

  it('turns a refusal into a sentence the owner can act on', async () => {
    vi.mocked(openEmbeddedSignup).mockResolvedValue({ code: 'c', event: 'FINISH_ONLY_WABA', waba_id: 'w', phone_number_id: '', business_id: '' });
    vi.mocked(connectWhatsApp).mockRejectedValue(new WhatsAppConnectError('no_phone_number', 404));
    const wrapper = mountBlock('es');
    await flushPromises();

    await wrapper.find('[data-test="whatsapp-connect-button"]').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain(es.whatsappConnect.errors.no_phone_number);
    expect(wrapper.text()).not.toContain('no_phone_number');
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(true);
  });

  it('says so, quietly, when the person closes the popup', async () => {
    vi.mocked(openEmbeddedSignup).mockRejectedValue(new WhatsAppConnectError('cancelled', 0));
    const wrapper = mountBlock('es');
    await flushPromises();

    await wrapper.find('[data-test="whatsapp-connect-button"]').trigger('click');
    await flushPromises();

    expect(wrapper.text()).toContain(es.whatsappConnect.errors.cancelled);
    expect(vi.mocked(connectWhatsApp)).not.toHaveBeenCalled();
  });

  it('disconnects and shows the button again', async () => {
    vi.mocked(fetchWhatsAppNumbers).mockResolvedValueOnce([NUMBER]).mockResolvedValueOnce([]);
    const wrapper = mountBlock('es');
    await flushPromises();

    await wrapper.find('[data-test="whatsapp-disconnect-button"]').trigger('click');
    await flushPromises();

    expect(vi.mocked(disconnectWhatsApp)).toHaveBeenCalledWith('phone_123');
    expect(wrapper.find('[data-test="whatsapp-connect-button"]').exists()).toBe(true);
  });
});
