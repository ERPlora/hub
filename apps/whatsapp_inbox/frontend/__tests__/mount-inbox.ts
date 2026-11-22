// Test helper of the WhatsApp inbox's pages and components: `mountInShell` with its catalogues over Customers' (for its
// CustomerSearch), the inbox and its people.
import type { SessionMe } from '@erplora/ui/shell';
import { vi } from 'vitest';
import type { Component } from 'vue';

import { withMenu } from '../../../../base/frontend/__tests__/app-menu';
import { mountInShell, settle } from '../../../../base/frontend/__tests__/mount-in-shell';
import customerEn from '../../../customer/frontend/locale/en.json';
import customerEs from '../../../customer/frontend/locale/es.json';
import en from '../locale/en.json';
import es from '../locale/es.json';

/** An administrator: every permission of the inbox (apps.py `role_permissions`), and Customers'; not the owner, so it
 *  does not buy (no «Upgrade plan»). */
export const ADMIN: SessionMe = withMenu('whatsapp_inbox', {
  user: { id: '1', label: 'Ana' },
  permissions: [
    'whatsapp_inbox.view',
    'whatsapp_inbox.reply',
    'whatsapp_inbox.assign',
    'whatsapp_inbox.configure',
    'whatsapp_inbox.erase',
    'customer.view',
    'customer.manage',
  ],
  menu: [],
  apps: [],
  language: 'en',
});

/** The owner: all the administrator has, and the business is theirs, so it is the only one offered «Upgrade plan». */
export const OWNER: SessionMe = withMenu('whatsapp_inbox', { ...ADMIN, permissions: [...ADMIN.permissions, 'base.own_business'] });

/** A manager: reads, answers and assigns anybody; no settings, no erasing. */
export const MANAGER: SessionMe = withMenu('whatsapp_inbox', {
  ...ADMIN,
  permissions: ['whatsapp_inbox.view', 'whatsapp_inbox.reply', 'whatsapp_inbox.assign', 'customer.view', 'customer.manage'],
});

/** An employee: reads, answers and takes conversations for themselves. */
export const EMPLOYEE: SessionMe = withMenu('whatsapp_inbox', {
  ...ADMIN,
  // The person of the business's database (base.HubUser), as base.session.me says it.
  user: { id: '01a16000-0000-7000-8000-0000000000b2', label: 'Luis' },
  permissions: ['whatsapp_inbox.view', 'whatsapp_inbox.reply', 'customer.view', 'customer.manage'],
});

export interface MountOptions {
  props?: Record<string, unknown>;
  path?: string;
  locale?: 'en' | 'es';
  session?: SessionMe;
  stubs?: Record<string, Component | boolean>;
  /** Answers the API calls from before the mount: what a component asks as it mounts gets it. */
  api?: (call: { url: string; init: RequestInit }) => Response;
}

export async function mountInbox(component: Component, options: MountOptions = {}) {
  return mountInShell(component, options, {
    path: '/whatsapp_inbox/inbox',
    session: OWNER,
    messages: { en: { ...customerEn, ...en }, es: { ...customerEs, ...es } },
    inDocFrom: 'component',
  });
}

/** What `base.saas_pass.create` signs in these tests. */
export const SIGNED = 'https://erplora.com/hub-pass/?pass=abc%3A123';

/** Clicks «Upgrade plan» in a browser (`useSaasPass`) and says where its new tab was sent. */
export async function followUpgrade(link: Element): Promise<string> {
  const tab = { opener: {} as unknown, location: { href: 'about:blank' } };
  const open = vi.spyOn(window, 'open').mockReturnValue(tab as unknown as Window);
  try {
    link.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
    await settle();
    return tab.location.href;
  } finally {
    open.mockRestore();
  }
}

export * from '../../../../base/frontend/__tests__/mount-in-shell';
