// Test helper of the tips app's components: `mountInShell` with its catalogues over base's and the hub's business.
import type { SessionMe } from '@erplora/ui/shell';
import type { Component } from 'vue';

import { business } from '../../../../base/frontend/__tests__/business';
import { type BusinessMountOptions, mountInShell, overBase } from '../../../../base/frontend/__tests__/mount-in-shell';
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

export async function mountTip(component: Component, options: BusinessMountOptions = {}) {
  return mountInShell(component, options, {
    path: '/sale/pos',
    session: EMPLOYEE,
    messages: overBase(en, es),
    business: business(),
    inDocFrom: 'component',
  });
}
