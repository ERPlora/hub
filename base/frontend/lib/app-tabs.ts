// The tab bar of an app's pages is the part of the app's menu the person may open, as base.session.me sends it:
// already filtered by permission and translated. So nobody sees a tab they cannot open, and a tab says what the menu
// says. An app never writes its own list.
import { type SessionMenuSection, type ShellTab, useSession } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

/** The tabs of the app `app` for the person signed in; they follow the session as it changes. */
export function useAppTabs(app: string): ComputedRef<ShellTab[]> {
  const session = useSession();
  return computed(() => appTabs(session.menu.value, app));
}

/**
 * One tab per entry of `app` in `menu`, in its order. A tab is named by the last part of its path: the session's
 * entries carry no id, and that part is the one the `tab-<id>` test ids have always used.
 */
export function appTabs(menu: readonly SessionMenuSection[], app: string): ShellTab[] {
  const section = menu.find((candidate) => candidate.id === app);
  return (section?.items ?? []).map((item) => ({
    id: item.path.slice(item.path.lastIndexOf('/') + 1),
    label: item.label,
    icon: item.icon,
    to: item.path,
  }));
}
