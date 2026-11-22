// WhatsApp inbox → Inbox and the customers' numbers (WHATSAPP_INBOX-F05, BASE-F119): the «Phone» column, never
// sortable, only for whoever sees the customers' contact details, and a search box that says what it looks into.
import { DataTable } from '@erplora/ui/components';
import type { SessionMe } from '@erplora/ui/shell';
import { describe, expect, it } from 'vitest';
import type { Component } from 'vue';

import { EMPLOYEE, mountInbox, OWNER, WITHOUT_CONTACT } from '../__tests__/mount-inbox';
import InboxPage from './InboxPage.vue';

type Column = { key: string; sortable?: boolean };

/** The table the page paints for `session`, in `locale`: its «Phone» column and its search hint. */
async function painted(session: SessionMe, locale: 'en' | 'es' = 'en') {
  const m = await mountInbox(InboxPage, { session, locale });
  await m.live();
  const prop = <T>(name: string) => (m.wrapper.findComponent(DataTable as unknown as Component).props() as Record<string, unknown>)[name] as T;
  const phone = prop<Column[]>('columns').filter((column) => column.key === 'phone');
  return { phone, placeholder: prop<string>('searchPlaceholder') };
}

describe('InboxPage: the customers’ numbers', () => {
  it.each([OWNER, EMPLOYEE])('whoever sees them has «Phone», not sortable', async (session) => {
    const s = await painted(session);
    expect(s.phone.map((column) => !!column.sortable)).toEqual([false]);
    expect(s.placeholder).toBe('Filter contact or phone…');
  });

  it('whoever does not has no «Phone» and a search by name, in both languages', async () => {
    expect(await painted(WITHOUT_CONTACT)).toEqual({ phone: [], placeholder: 'Filter contact…' });
    expect((await painted(WITHOUT_CONTACT, 'es')).placeholder).toBe('Filtrar contacto…');
  });
});
