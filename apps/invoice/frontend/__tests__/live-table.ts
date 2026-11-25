// The DataTable of a mounted list page of Invoicing: its props, its rows and the events it emits.
import { DataTable } from '@erplora/ui/components';
import type { Component } from 'vue';

import { flush, type MountedInvoice } from './mount-invoice';

export function liveTable(m: MountedInvoice, rowTestid: string) {
  const table = () => m.wrapper.findComponent(DataTable as unknown as Component);
  const prop = <T = unknown>(name: string) => (table().props() as Record<string, unknown>)[name] as T;
  const rows = () => m.wrapper.findAll(`[data-testid="${rowTestid}"]`);
  async function emit(name: string, ...args: unknown[]) {
    table().vm.$emit(name, ...args);
    await flush();
  }
  return { table, prop, rows, emit };
}
