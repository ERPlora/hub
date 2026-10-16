// The sections of Printing, painted as the footer tabbar of each of its pages (AppPage `tabs`): the same
// entries, order and paths as the app's menu (`navigation` in apps.py). Each tab follows its route.
// Icons: registered ones only (`lucide:receipt` stands in for `ion:print-outline`, asked for in
// apps/printing/UI-REQUESTS.md).
import type { ShellTab } from '@erplora/ui/shell';

export const PRINTING_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'printers', icon: 'lucide:receipt', to: '/printing/printers' },
  { id: 'jobs', icon: 'ion:list-outline', to: '/printing/jobs' },
  { id: 'settings', icon: 'ion:settings-outline', to: '/printing/settings' },
]);

/** The tabs with their labels in the reader's language (`printingTabs($t)` in a template). */
export function printingTabs(t: (key: string) => string): ShellTab[] {
  return PRINTING_TABS.map((tab) => ({ ...tab, label: t(`printing.tabs.${tab.id}`) }));
}
