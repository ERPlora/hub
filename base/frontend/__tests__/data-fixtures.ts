// Rows of Settings › Data for its tests, shaped as base/schemas.py answers them.
import type { BlueprintSummary, ImportRow, Template } from '../operations';

export function template(key: string, fields: Partial<Template> = {}): Template {
  return {
    key,
    name: key.startsWith('hair') ? 'Hair salon' : 'Restaurant',
    description: `A ${key} ready to use`,
    language: key.split('.')[1] ?? 'es',
    country: 'ES',
    vertical: key.split('.')[0],
    version: '1',
    apps: [{ id: 'inventory', label: 'Inventory' }],
    contents: [{ key: 'inventory.product', label: 'Products', rows: 12 }],
    ...fields,
  };
}

export function summary(fields: Partial<BlueprintSummary> = {}): BlueprintSummary {
  return {
    name: 'Restaurant',
    language: 'es',
    country: 'ES',
    purpose: 'template',
    created_at: '',
    version: '1',
    source: 'catalog',
    apps: [
      {
        id: 'inventory',
        label: 'Inventory',
        status: 'on',
        datasets: [{ key: 'inventory.product', label: 'Products', rows: 12, personal: false, travels: true }],
      },
      {
        id: 'customer',
        label: 'Customers',
        status: 'on',
        datasets: [{ key: 'customer.customer', label: 'Customers', rows: 3, personal: true, travels: false }],
      },
      { id: 'kitchen', label: 'Kitchen', status: 'inactive', datasets: [] },
      { id: 'mystery', label: 'mystery', status: 'unknown', datasets: [] },
    ],
    dropped: [],
    ...fields,
  };
}

export function load(fields: Partial<ImportRow> = {}): ImportRow {
  return {
    id: '0192f0aa-0000-7000-8000-000000000001',
    name: 'Restaurant',
    source: 'catalog',
    template_key: 'restaurant.es',
    status: 'complete',
    created_at: '2026-10-24T08:00:00Z',
    created_by: 'Ana',
    rows: 14,
    undone: false,
    undoable: true,
    retry: false,
    retry_blocked: 'complete',
    report: {
      status: 'complete',
      dropped: [],
      apps: [
        {
          id: 'inventory',
          label: 'Inventory',
          status: 'applied',
          datasets: [
            { key: 'inventory.product', label: 'Products', rows: 12, status: 'applied', created: 12, already: 0, failed: 0, problems: [] },
          ],
        },
      ],
    },
    ...fields,
  };
}
