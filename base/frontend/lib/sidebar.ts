// The side menu's `visible` (APP-BASE-5; `ShellSidebarItem.visible`, which the shell runs once in its setup): an entry
// shows only to whoever may open its screen — the conventional menu (Square, Toast) never offers what the person
// cannot open — and «API» only while the business shows its API's documentation, as the old hub's menu did.
import { useSession } from '@erplora/ui/shell';
import { useLiveClient } from '@erplora/ui/sdk';
import { computed, shallowRef, watch } from 'vue';

/** `visible` of an entry whose screen asks `permission`: the person holds it, followed live. */
export function allowedTo(permission: string): () => () => boolean {
  return () => {
    const session = useSession();
    return () => session.can(permission);
  };
}

/**
 * `visible` of «API» (BASE-F90, F91): while the business shows its API's documentation (`base.api_doc.settings`,
 * live) and the person may read it. Asked only with a session — the live stream refuses whoever is not signed in,
 * and the shell runs this on the login screen too — and left when the session goes or the menu does.
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
  return () => enabled.value && session.can('base.view_home');
}
