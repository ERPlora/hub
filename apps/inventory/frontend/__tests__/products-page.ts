import { DataTable } from '@erplora/ui/components';
import type { Component } from 'vue';

import ProductsPage from '../pages/ProductsPage.vue';
import { flush, mountInventory, ok, product, UNITS, type ApiCall, type MountOptions } from './mount-inventory';

/** The API of the page: units, the hub's stock setting; anything else answers `answer`. */
export function api(answer: (call: ApiCall) => Response = () => ok({})) {
  return (call: ApiCall): Response => {
    const path = call.url.split('?')[0];
    if (path === '/api/inventory/units') return ok(UNITS);
    if (path === '/api/inventory/config') return ok({ allow_sell_without_stock: false, low_stock_threshold: 10, track_stock: true });
    return answer(call);
  };
}

export async function setup(options: MountOptions = {}, answer?: (call: ApiCall) => Response) {
  const m = await mountInventory(ProductsPage, { path: '/inventory/products', api: api(answer), ...options });
  const call = await m.live();
  const testid = (id: string) => m.wrapper.find(`[data-testid="${id}"]`);
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll('[data-testid="inventory-products-row"]');
  async function act(actionId: string, row: unknown = product()) {
    table().vm.$emit('action', { actionId, row });
    await flush();
  }
  async function onNewStream(data: unknown) {
    await m.clock.advance(150);
    await m.result(m.net.lastStream(), 'inventory.product.list', data);
  }
  /** What the table's funnel applies (`v-model:filters`): the filters by name, as typed. */
  async function filter(values: Record<string, string>) {
    table().vm.$emit('update:filters', values);
    await flush();
  }
  return { ...m, call, testid, table, prop, rows, act, onNewStream, filter, show: (data: unknown, rev?: number) => m.result(call, 'inventory.product.list', data, rev) };
}
