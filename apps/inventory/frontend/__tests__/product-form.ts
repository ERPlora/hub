import { Combo, type ComboOption } from '@erplora/ui/components';

import type { Business } from '../../../../base/frontend/operations/business';
import {
  business,
  category,
  flush,
  mountInventory,
  ok,
  page,
  TAX_CATEGORIES,
  UNITS,
  type ApiCall,
} from './mount-inventory';
import ProductFormModal from '../components/ProductFormModal.vue';
import { typeText } from './ionic-controls';

export type Control = HTMLElement & {
  value?: unknown;
  errorText?: string;
  disabled?: boolean;
  label?: string;
  helperText?: string;
  checked?: boolean;
};

export const CATEGORIES = page([category(), category({ id: 'c2', name: 'Food', slug: 'food' })], 2, 100);

export const JAPANESE: Partial<Business> = { country: 'JP', country_name: 'Japan', currency: 'JPY', currency_label: 'JPY · Japanese Yen', currency_decimals: 0 };

export const searches = (categories: unknown) => (call: ApiCall) =>
  ok(call.url.startsWith('/api/tax/categories') ? TAX_CATEGORIES : categories);

function controls(el: (id: string) => Control | null) {
  const type = (id: string, value: string) => typeText(el, id, value);
  async function pick(id: string, value: unknown) {
    const field = el(id)!;
    field.value = value;
    field.dispatchEvent(new CustomEvent('ionChange', { detail: { value } }));
    await flush();
  }
  async function check(id: string, checked: boolean) {
    const field = el(id)!;
    field.checked = checked;
    field.dispatchEvent(new CustomEvent('ionChange', { detail: { checked } }));
    await flush();
  }
  return { type, pick, check };
}

export async function setup(
  props: Record<string, unknown> = {},
  options: { locale?: 'en' | 'es'; categories?: unknown; taxes?: unknown; api?: (call: ApiCall) => Response | Promise<Response>; business?: Business | null } = {},
) {
  const m = await mountInventory(ProductFormModal, {
    props: { open: true, product: null, units: UNITS.rows, ...props },
    locale: options.locale,
    attach: true,
    business: options.business,
    api: options.api ?? searches(options.categories ?? CATEGORIES),
  });
  const call = await m.live();
  await m.result(call, 'tax.category.list', options.taxes ?? TAX_CATEGORIES);
  await m.result(call, 'inventory.category.list', options.categories ?? CATEGORIES);
  const el = (id: string) => document.querySelector<Control>(`[data-testid="${id}"]`);
  const { type, pick, check } = controls(el);
  async function choose(id: string, key: string) {
    const combo = m.wrapper.findAllComponents(Combo).find((c) => c.props('testid') === id);
    if (!combo) throw new Error(`${id} is not a Combo`);
    const option = (await (combo.props('search') as (q: string) => Promise<ComboOption[]>)('')).find((o) => o.id === key);
    if (!option) throw new Error(`${id} offers no ${key}`);
    combo.vm.$emit('update:modelValue', option);
    await flush();
  }
  async function submit() {
    el('inventory-product-form-submit')!.click();
    await flush();
  }
  async function fillRequired() {
    await type('inventory-product-name', 'Coffee');
    await type('inventory-product-sku', 'CAF-1');
    await type('inventory-product-price', '2,20');
    await choose('inventory-product-tax', 'product.generic');
  }
  const sent = (path: string) => m.body(m.calls(path).at(-1)!) as Record<string, unknown>;
  const chips = () => [...document.querySelectorAll('[data-testid^="inventory-product-categories-chip-"]')].map((c) => c.textContent?.trim());
  const answer = (fields: Partial<Business>, rev = 1) => m.result(call, 'base.business.get', business(fields), rev);
  return { ...m, el, type, pick, choose, check, submit, fillRequired, sent, chips, answer };
}
