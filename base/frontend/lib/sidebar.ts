// The Hub's side menu: the platform's entries in two groups — Home (the shell's, first), Employees, Files · Apps, System,
// API, Settings — and never a module (modules open from «My apps» and Home). The shell paints an entry only once its
// screen exists in the router, and only for whoever holds the permission that screen asks, as in Square or Toast.
import { type ShellSidebar, type ShellSidebarItem, useSession } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { computed, shallowRef, watch } from 'vue';

/** An entry of the Hub's side menu: the shell's, with the permission its screen asks in place of a `visible`. */
export interface HubSidebarItem extends Omit<ShellSidebarItem, 'visible'> {
  /** The permission of the operation its screen reads: only whoever holds it has the entry. */
  permission: string;
  /** A live condition besides the permission, called once in the shell's setup like `visible`. */
  shownWhile?: () => () => boolean;
}

export interface HubSidebar {
  groups: HubSidebarItem[][];
}

export const SIDEBAR: HubSidebar = {
  groups: [
    [
      { id: 'employees', labelKey: 'sidebar.employees', icon: 'ion:people-outline', to: '/employees', permission: 'base.view_home' },
      { id: 'files', labelKey: 'sidebar.files', icon: 'ion:folder-outline', to: '/files', permission: 'base.view_files' },
    ],
    [
      { id: 'apps', labelKey: 'sidebar.apps', icon: 'ion:storefront-outline', to: '/apps', permission: 'base.view_home' },
      { id: 'system', labelKey: 'sidebar.system', icon: 'ion:hardware-chip-outline', to: '/system', permission: 'base.administer_hub' },
      {
        id: 'api',
        labelKey: 'sidebar.api',
        icon: 'ion:code-slash-outline',
        to: '/api-docs',
        permission: 'base.view_home',
        shownWhile: useApiDocsShown,
      },
      { id: 'settings', labelKey: 'sidebar.settings', icon: 'ion:settings-outline', to: '/settings', permission: 'base.view_home' },
    ],
  ],
};

/** The side menu as the shell takes it: each entry shows while the person holds its permission, followed live. */
export function shellSidebar(sidebar: HubSidebar): ShellSidebar {
  return { groups: sidebar.groups.map((group) => group.map(shellItem)) };
}

function shellItem({ permission, shownWhile, ...item }: HubSidebarItem): ShellSidebarItem {
  return {
    ...item,
    visible: () => {
      const session = useSession();
      const alsoShown = shownWhile?.();
      return () => session.can(permission) && (alsoShown ? alsoShown() : true);
    },
  };
}

/**
 * Whether «API» shows (BASE-F90, F91): while the business shows its API's documentation (`base.api_doc.settings`, live).
 * Asked only with a session — the live stream refuses whoever is not signed in, and the shell runs this on the login
 * screen too — and left when the session goes or the menu does.
 */
export function useApiDocsShown(): () => boolean {
  const session = useSession();
  const client = useLiveClient();
  const enabled = shallowRef(false);
  watch(
    computed(() => session.user.value !== null),
    (signedIn, _before, onCleanup) => {
      enabled.value = false;
      if (!signedIn) return;
      const leave = client.stream.subscribe('base.api_doc.settings', {}, (event) => {
        if (event.type === 'result') enabled.value = (event.data as { docs_enabled?: boolean } | null)?.docs_enabled === true;
      });
      onCleanup(leave);
    },
    { immediate: true },
  );
  return () => enabled.value;
}
