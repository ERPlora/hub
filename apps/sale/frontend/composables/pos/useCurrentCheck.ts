// `useCurrentCheck()`: the check this device has on screen, kept in localStorage so a reload of the
// till comes back to it (SALE-F17 step 5). Remembered when a check opens or is resumed; forgotten when
// it is charged whole, parked or voided. A storage that refuses (private mode, quota) only loses the
// reload: the screen keeps the check while it lives.
import { type Ref, shallowRef } from 'vue';

export const CURRENT_CHECK_KEY = 'erplora.sale.pos.currentCheck';

type CheckStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

export interface CurrentCheck {
  /** The id of the check on screen; `null` with none. */
  id: Readonly<Ref<string | null>>;
  remember(id: string): void;
  forget(): void;
}

function read(storage: CheckStorage | undefined): string | null {
  try {
    return storage?.getItem(CURRENT_CHECK_KEY) || null;
  } catch {
    return null;
  }
}

function write(storage: CheckStorage | undefined, id: string | null): void {
  try {
    if (id) storage?.setItem(CURRENT_CHECK_KEY, id);
    else storage?.removeItem(CURRENT_CHECK_KEY);
  } catch {
    // The storage refused: only a reload loses the check, the screen keeps it in `id`.
  }
}

export function useCurrentCheck(storage: CheckStorage | undefined = globalThis.localStorage): CurrentCheck {
  const id = shallowRef<string | null>(read(storage));
  return {
    id,
    remember(next) {
      id.value = next;
      write(storage, next);
    },
    forget() {
      id.value = null;
      write(storage, null);
    },
  };
}
