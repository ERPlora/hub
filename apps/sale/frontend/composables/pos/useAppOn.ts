// What the till offers of another app: only while that app is on in the business and the person may read it.
import { useSession } from '@erplora/ui/shell';
import { computed, type ComputedRef } from 'vue';

export function useAppOn(label: string, permission: string): ComputedRef<boolean> {
  const session = useSession();
  return computed(() => !!session.me.value?.apps.some((app) => app.label === label && app.state === 'on') && session.can(permission));
}
