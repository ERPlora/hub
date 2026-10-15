// The two sections of the WhatsApp inbox, painted as the footer tabbar of both pages (AppPage `tabs`):
// the same entries, order, icons and paths as the app's menu (`navigation` in apps.py). Each tab follows
// its route; picking one replaces the address, so Back leaves the inbox instead of walking its tabs.
// Icons: registered ones only (`logo-whatsapp` is asked for in apps/whatsapp_inbox/UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const INBOX_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'inbox', icon: 'ion:chatbubbles-outline', to: '/whatsapp_inbox/inbox' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/whatsapp_inbox/settings' },
]);

/** The tabs with their labels in the reader's language (`inboxTabs($t)` in a template). */
export function inboxTabs(t: (key: string) => string): ShellTab[] {
  return INBOX_TABS.map((tab) => ({ ...tab, label: t(`whatsapp_inbox.tabs.${tab.id}`) }));
}
