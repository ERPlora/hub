// The sections of Tasks, painted as the footer tabbar of each task page (AppPage `tabs`): the two of
// the app's menu (`navigation` in apps.py), same order, icons and paths. Each tab follows its route;
// picking one replaces the address, so Back leaves Tasks.
import type { ShellTab } from '@erplora/ui/shell';

export const TASK_TABS: readonly Omit<ShellTab, 'label'>[] = Object.freeze([
  { id: 'tasks', icon: 'ion:checkmark-circle-outline', to: '/task/tasks' },
  { id: 'projects', icon: 'ion:file-tray-outline', to: '/task/projects' },
]);

/** The tabs in the reader's language. */
export function taskTabs(t: (key: string) => string): ShellTab[] {
  return TASK_TABS.map((tab) => ({ ...tab, label: t(`task.tabs.${tab.id}`) }));
}
