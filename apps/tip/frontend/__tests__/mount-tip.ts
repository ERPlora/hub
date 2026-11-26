// Test helper of the tips app's components: `mountInShell` with its catalogues over base's and Sales' (whose list
// notices and period its screens reuse) and the hub's business.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { business } from '../../../../base/frontend/__tests__/business';
import { type BusinessMountOptions, mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
import saleEn from '../../../sale/frontend/locale/en.json';
import saleEs from '../../../sale/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** Whoever charges at the till: records tips and sees their own. */
export const EMPLOYEE: SessionMe = {
  user: { id: 'u1', label: 'Ana' },
  permissions: ['sale.take_payment', 'tip.view_tip', 'tip.add_tip'],
  menu: [],
  apps: [],
  language: 'en',
};

/** Adjusts and voids tips, and reads the settings without changing them; with the menu that opens. */
export const MANAGER: SessionMe = withMenu('tip', { ...EMPLOYEE, permissions: [...EMPLOYEE.permissions, 'tip.manage'] });

/** Everything, the settings too. */
export const OWNER: SessionMe = withMenu('tip', { ...MANAGER, permissions: [...MANAGER.permissions, 'tip.manage_settings'] });

export async function mountTip(component: Component, options: BusinessMountOptions = {}) {
  return mountInShell(component, options, {
    path: '/sale/pos',
    session: EMPLOYEE,
    messages: overBase({ ...saleEn, ...en }, { ...saleEs, ...es }),
    business: business(),
    inDocFrom: 'component',
  });
}
