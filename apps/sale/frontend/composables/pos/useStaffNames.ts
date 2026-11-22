// The names of the professionals on the check's lines (SALE-F16). One picked on this screen is named as it was
// picked; one the screen never picked (an appointment's line, a check built on another device or before a reload)
// is asked of Staff, once. Until Staff answers, and when it cannot (off, no permission, a member gone), the line
// says «the assigned professional».
import { useCommand } from '@erplora/ui/sdk';
import { shallowRef, watch } from 'vue';

import type { OrderLineOut } from '../../operations';

export function useStaffNames(lines: () => readonly OrderLineOut[]) {
  const names = shallowRef<Record<string, string>>({});
  const asked = new Set<string>();
  const member = useCommand('staff.member.detail');

  function remember(id: string | null, name: string | null): void {
    if (id && name) names.value = { ...names.value, [id]: name };
  }

  async function ask(id: string): Promise<void> {
    asked.add(id);
    try {
      remember(id, (await member.run({ id })).full_name);
    } catch {
      // The line keeps «the assigned professional»: it still says someone does it.
    }
  }

  watch(lines, (now) => {
    for (const { staff_id: id } of now) {
      if (id && !(id in names.value) && !asked.has(id)) void ask(id);
    }
  }, { immediate: true });

  return { names, remember };
}
