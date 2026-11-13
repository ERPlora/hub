// Test helper of the invoice app's pages and components: `mountInShell` with its catalogues over base's, the invoices
// and its people.
// Dialogs: a test that opens one mocks `@ionic/vue`'s IonModal with FormModal's `ionModalStub` (imported
// from its own file in the mock factory: this helper loads @ionic/vue, the factory must not).
// `platformNotice` paints a page as the hub does: base's blocking strip over it (`chrome.notice`, frontend/main.ts).
import { type SessionMe, SHELL_CONFIG_KEY } from '@erplora/ui/shell';
import type { OpName } from '@erplora/ui/sdk';
import type { Component } from 'vue';

import { memoryRouter, mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import BlockingStrip from '../../../../base/frontend/components/BlockingStrip.vue';
import type { Business, SetupStatus } from '../../../../base/frontend/operations';
import { ComposableHost } from './composable-host';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** The business of the hub (`base.business.get`): one in Spain, in euros, unless a test says another
 *  (flow business-currency: what a person types is read in the business's money). */
export function business(fields: Partial<Business> = {}): Business {
  return {
    name: 'Peluquería Ana',
    country: 'ES',
    country_name: 'Spain',
    timezone: 'Europe/Madrid',
    language: 'es',
    language_name: 'Spanish',
    currency: 'EUR',
    currency_label: 'EUR · Euro',
    currency_decimals: 2,
    demo: false,
    settings_url: 'https://erplora.com/businesses/1/settings',
    ...fields,
  };
}

export const POLISH: Partial<Business> = { country: 'PL', country_name: 'Poland', currency: 'PLN', currency_label: 'PLN · Polish Zloty' };
export const JAPANESE: Partial<Business> = { country: 'JP', country_name: 'Japan', currency: 'JPY', currency_label: 'JPY · Japanese Yen', currency_decimals: 0 };

/** Every permission of the invoice app (owner, admin: apps.py `role_permissions`) and what its screens
 *  read from the other apps (Customers' cards for the recipient, Taxes' categories). */
export const INVOICE_PERMISSIONS = [
  'invoice.view_invoice',
  'invoice.add_invoice',
  'invoice.rectify_invoice',
  'invoice.manage_series',
  'invoice.manage_issuer',
];
const READS = ['customer.view', 'customer.manage', 'tax.view', 'sale.view_sale'];

/** The owner (and the admin): every permission of the app. */
export const OWNER: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: [...INVOICE_PERMISSIONS, ...READS],
  menu: [],
  apps: [],
  language: 'en',
};

/** The manager: everything but the issuer. */
export const MANAGER: SessionMe = {
  ...OWNER,
  permissions: ['invoice.view_invoice', 'invoice.add_invoice', 'invoice.rectify_invoice', 'invoice.manage_series', ...READS],
};

/** The employee: looks, prints, issues by hand and marks paid. */
export const EMPLOYEE: SessionMe = {
  ...OWNER,
  permissions: ['invoice.view_invoice', 'invoice.add_invoice', ...READS],
};

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** The page behind a session with the hub's chrome: base's blocking strip over it, in base's words too. */
  platformNotice?: boolean;
}

export async function mountInvoice(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/invoice/invoices',
    session: OWNER,
    messages: overBase(en, es),
    router: memoryRouter(options.platformNotice ? { auth: true } : {}),
    provide: options.platformNotice ? { [SHELL_CONFIG_KEY as symbol]: { homePath: '/', chrome: { notice: BlockingStrip } } } : {},
    inDocFrom: 'component',
  });
}

export type MountedInvoice = Awaited<ReturnType<typeof mountInvoice>>;

/** Invoicing's ⛔ «Your business details» as `base.setup.status` tells it (apps.py `setup`; also to whoever
 *  may not set it up, with `actionable: false`), in the person's language. */
export function issuerStatus(fields: { configured: boolean; actionable: boolean; locale?: 'en' | 'es' }): SetupStatus {
  const pending = fields.configured ? 0 : 1;
  return {
    total: 1,
    pending,
    unavailable: 0,
    blocking_pending: pending,
    items: [
      {
        key: 'invoice.business_identity',
        app: 'invoice',
        state: fields.configured ? 'done' : 'pending',
        level: 'legal',
        required: true,
        actionable: fields.actionable,
        title: fields.locale === 'es' ? 'Los datos de tu negocio' : 'Your business details',
        description: '',
        icon: 'ion:storefront-outline',
        route: '/invoice/issuer',
        order: 40,
      },
    ],
  };
}

/** What the hub answers every live question of a screen about its issuer (the platform's strip and, if the screen
 *  asks, `invoice.issuer.get`): set up or missing, for the person mounted (`actionable` by `invoice.manage_issuer`). */
export async function answerIssuer(m: MountedInvoice, configured: boolean, options: { locale?: 'en' | 'es'; actionable?: boolean; rev?: number } = {}) {
  const status = issuerStatus({ configured, actionable: options.actionable ?? true, locale: options.locale });
  const asked = (op: OpName) => m.client.stream.subscriptions(op).length > 0;
  if (asked('base.setup.status')) await m.result('base.setup.status', status, {}, options.rev);
  if (asked('invoice.issuer.get')) await m.result('invoice.issuer.get', { configured }, {}, options.rev);
}

/** The red notices on the screen, whatever their words: base's strip and any danger notice of the page's own. */
export function redNotices(m: MountedInvoice): number {
  return m.wrapper.findAll('[data-testid="blocking-strip"], [data-tone="danger"]').length;
}

/** How many times `needle` is said in `text`. */
export function said(text: string, needle: string): number {
  return text.split(needle).length - 1;
}

/** Mounts `use` (a composable call) inside a component of the invoice app's harness. */
export function mountComposable(use: () => void, options: Omit<MountOptions, 'props'> = {}) {
  return mountInvoice(ComposableHost, { ...options, props: { use } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
