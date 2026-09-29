// @vitest-environment happy-dom
// **Printers are found from the menu: Settings › Printing** (hub#2243).
//
// The side menu is the hub itself and never lists apps (the apps live in the top-bar launcher and
// in «My apps» on Home). So the menu's way to the printers is Settings — where Square (Hardware ›
// Printers), Toast, Lightspeed, Loyverse, Clover, SumUp, Shopify POS and Odoo all put them. Ours
// was there, but behind a tab called «Receipts»/«Tiques»: someone looking for their printer read
// Hub · Business · Receipts · Permissions · Data and found no word that said «printer».
//
// This test reads the tab through the REAL catalogues (en + es): the tab that holds the printers
// row says Printing / Impresión, and it is that very tab which paints the row.
import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { ref } from 'vue';
import { createI18n } from 'vue-i18n';
import en from '../i18n/locales/en';
import es from '../i18n/locales/es';

// Same reasons as `settings-receipt-template.test.ts`: the icon registry imports virtual ids this
// environment denies, and the screen's collaborators are stubbed so this tests the SCREEN.
vi.mock('../lib/icons', () => ({
  resolveIcon: () => '',
  manifestIcon: () => '',
  iconRegistry: () => ({}),
  moduleIconRegistry: () => ({}),
}));
vi.mock('../components/HubIcon.vue', () => ({
  default: { name: 'HubIcon', props: ['name'], template: '<span class="hub-icon" :data-icon="name" />' },
}));

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  useRoute: () => ({ hash: '#tickets', query: {} }),
}));
vi.mock('../lib/nav', () => ({ moduleNav: ref([{ path: '/m/printing' }]) }));
vi.mock('../lib/hub-settings', () => ({
  hubSettings: ref({}),
  getHubSettings: vi.fn().mockResolvedValue({}),
  updateHubSettings: vi.fn(),
}));
vi.mock('../lib/session', () => ({ isAdmin: ref(true) }));
vi.mock('../lib/api-docs', () => ({ apiDocsEnabled: ref(false) }));
vi.mock('../lib/device', () => ({ isTauri: () => false }));
vi.mock('../lib/toast', () => ({ toastSuccess: vi.fn(), toastError: vi.fn() }));
vi.mock('../lib/money', () => ({ publishHubCurrency: vi.fn() }));

/** A stub that DOES paint what it wraps — the footer slot included, which is where the tabs live. */
const PASSTHROUGH = { template: '<div><slot /><slot name="footer" /></div>' };

async function mountSettings(locale: 'en' | 'es') {
  const i18n = createI18n({ legacy: false, locale, messages: { en, es } });
  const SettingsPage = (await import('./SettingsPage.vue')).default;
  return mount(SettingsPage, {
    shallow: true,
    global: {
      plugins: [i18n],
      stubs: {
        AppPage: PASSTHROUGH,
        IonCard: PASSTHROUGH,
        IonCardContent: PASSTHROUGH,
        IonFooter: PASSTHROUGH,
        IonToolbar: PASSTHROUGH,
        IonSegment: PASSTHROUGH,
        IonSegmentButton: PASSTHROUGH,
        IonLabel: PASSTHROUGH,
        IonItem: PASSTHROUGH,
        // The mocked icon above, painted for real: it carries the icon name as `data-icon`.
        HubIcon: false,
      },
    },
  });
}

describe('Settings › Printing — the menu way to the printers (hub#2243)', () => {
  it.each([
    ['en', 'Printing'],
    ['es', 'Impresión'],
  ] as const)('in %s the tab that holds the printers is called «%s»', async (locale, label) => {
    const wrapper = await mountSettings(locale);

    const tab = wrapper.find('[data-testid="settings-tab-tickets"]');
    expect(tab.exists(), 'the tab is painted').toBe(true);
    expect(tab.text()).toBe(label);
    // The mark says the same as the word: a printer, not a ticket stub.
    expect(tab.find('.hub-icon').attributes('data-icon')).toBe('print-outline');

    // And it is THIS tab (the route lands on #tickets) that paints the printers row.
    expect(wrapper.find('.receipt-template').text()).toContain(
      locale === 'en' ? en.settings.receiptTemplate : es.settings.receiptTemplate,
    );
  });
});
