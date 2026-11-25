// Test helper of Online orders' pages and components: `mountInShell` with the app's catalogues, an owner who sees and
// regenerates the tables' QR codes, and the rows `online_order.qr_code.list` answers.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, type MountOptions } from '../../../../base/frontend/__tests__/mount-in-shell';
import en from '../locale/en.json';
import es from '../locale/es.json';
import type { TableCodeOut } from '../operations';

/** Owner, admin or manager: both permissions of the app (apps.py `role_permissions`), and Tables' to read and add tables. */
export const OWNER: SessionMe = withMenu('online_order', {
  user: { id: '1', label: 'Ana' },
  permissions: ['online_order.view_qr_code', 'online_order.change_qr_code', 'table.view_table', 'table.add_table'],
  menu: [],
  apps: [],
  language: 'en',
});

/** Someone who sees the codes but may not regenerate them. */
export const VIEWER: SessionMe = withMenu('online_order', {
  ...OWNER,
  permissions: ['online_order.view_qr_code', 'table.view_table'],
});

export function codeRow(overrides: Partial<TableCodeOut> = {}): TableCodeOut {
  const number = overrides.number ?? '4';
  const code = overrides.code === undefined ? `code-${number}` : overrides.code;
  return {
    table_id: `t${number}`,
    table: `${number} (Terrace)`,
    number,
    zone_name: 'Terrace',
    code,
    url: code ? `http://tenant-a.localhost/p/tenant-a/order/${code}` : null,
    issued_at: code ? '2026-11-20T10:30:00Z' : null,
    ...overrides,
  };
}

export async function mountOnlineOrder(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, { path: '/online_order/qr-codes', session: OWNER, messages: { en, es } });
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
