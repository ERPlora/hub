// Who serves the check on screen (SALE-F16) belongs to the check and is kept in the Hub, so a check left and opened
// again (from the floor plan, «Open checks» or another device) still says who serves it. Someone chosen before
// there is a check waits for it: the check opens with them.
import { useCommand } from '@erplora/ui/sdk';
import { toastError } from '@erplora/ui/shell';
import { computed, type Ref, shallowRef, watch } from 'vue';

import { refusal } from '../../lib/refusal';
import type { OrderOut } from '../../operations';
import { useT } from '../useT';

/** Who serves; `id: null` = «me», whoever holds the session. */
export interface Server {
  id: string | null;
  name: string | null;
}

interface CheckOnScreen {
  order: Readonly<Ref<OrderOut | null>>;
  orderId: Readonly<Ref<string | null>>;
  follow(next: OrderOut): void;
}

const ME: Server = { id: null, name: null };

export function useCheckStaff(till: CheckOnScreen) {
  const t = useT();
  const save = useCommand('sale.order.set_staff');
  const waiting = shallowRef<Server>(ME);
  /** Chosen for the check on screen, until the Hub answers: the lines added meanwhile are already theirs. */
  const saving = shallowRef<Server | null>(null);

  const staff = computed<Server>(() => {
    if (saving.value) return saving.value;
    const check = till.order.value;
    if (!check) return waiting.value;
    return check.staff_id ? { id: check.staff_id, name: check.staff_name || null } : ME;
  });

  watch(till.orderId, (id) => {
    if (!id) return;
    const chosen = waiting.value;
    waiting.value = ME;
    // A check the till did not open itself (Tables opens it when a table is picked first) knows nothing of who was
    // chosen before it existed: it is saved on it.
    if (chosen.id && till.order.value?.staff_id !== chosen.id) void choose(chosen);
  });

  async function choose(next: Server): Promise<void> {
    const id = till.orderId.value;
    if (!id) {
      waiting.value = next;
      return;
    }
    saving.value = next;
    try {
      till.follow(await save.run({ order_id: id, staff_id: next.id }));
    } catch (error) {
      const fallback = t('sale.pos.staffSaveFailed');
      toastError(refusal(error, fallback)?.message ?? fallback);
    } finally {
      saving.value = null;
    }
  }

  return {
    staff,
    choose,
    /** What a new check opens with: who was chosen before it existed. */
    opening: () => (waiting.value.id ? { staff_id: waiting.value.id } : {}),
    clear: () => (waiting.value = ME),
  };
}
