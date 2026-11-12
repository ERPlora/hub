// `useUnsavedChanges(inside, dirty)` (hub#1015; BASE-F05, INVENTORY-F01/F02): a window that holds what the person typed
// signs up with the system Back (`system-back.ts`, `holdUnsavedChanges`) for as long as it is mounted. While `dirty`
// says it holds something, Android's Back on it asks «Discard changes?» — «Keep editing» or «Discard changes» — and
// closes it only on «Discard changes»; with nothing typed Back closes it at once, as before. `inside` is an element of
// the window (its fields), which tells its overlay apart from any other open. The question is the ConfirmDialog of
// `@erplora/ui` (`useConfirm`), so Back on it closes the question and the person keeps editing. It gives back the same
// question for the window's own ways out (hub#1023): the `canDismiss` of its FormModal, which asks it on Cancel, the
// close button, Escape and the backdrop while `dirty`, and lets it close at once when nothing is typed. `useUnsavedForm`
// and `useUnsavedFormOnOpen` give back the same question (hub#1156, BASE-F05), for every form window to hand its FormModal.
// A window that is an `ion-modal` of its own (a sheet with its own close button) hands it to `useSheetWaysOut` (hub#1233).
// An edit window whose whole record arrives after the person started typing fills the form with `keepTouched`, which
// keeps what was typed and takes the record everywhere else.
import { useConfirm } from '@erplora/ui/components';
import { computed, getCurrentInstance, type MaybeRefOrGetter, onScopeDispose, type Ref, ref, toValue, watch } from 'vue';

import { useBaseI18n } from './i18n';
import { holdUnsavedChanges } from './system-back';

type Inside = MaybeRefOrGetter<Element | null | undefined> | string;

function elementOf(inside: Inside, instance: ReturnType<typeof getCurrentInstance>): () => Element | null | undefined {
  return () => {
    if (typeof inside !== 'string') return toValue(inside);
    const selector = `[data-testid="${inside}"]`;
    const node = instance?.vnode.el as Node | null | undefined;
    const root = node instanceof Element ? node : node?.parentElement;
    if (root) {
      if (root.matches(selector)) return root;
      const found = root.querySelector(selector);
      if (found) return found;
    }
    return document.querySelector(selector);
  };
}

/** Called from `setup()`: the question belongs to the app of the window that asks it. Resolves `true` when the window
 *  may close (nothing typed, or «Discard changes»): its FormModal's `canDismiss`. */
export function useUnsavedChanges(inside: Inside, dirty: MaybeRefOrGetter<boolean>): () => Promise<boolean> {
  const { t } = useBaseI18n();
  const { confirm } = useConfirm();
  const confirmDiscard = () =>
    confirm({
      title: t('base.unsavedChanges.title'),
      message: t('base.unsavedChanges.message'),
      tone: 'danger',
      confirmLabel: t('base.unsavedChanges.discard'),
      cancelLabel: t('base.unsavedChanges.keep'),
    });
  const letGo = holdUnsavedChanges({ inside: elementOf(inside, getCurrentInstance()), dirty: () => toValue(dirty), confirmDiscard });
  onScopeDispose(letGo);
  return async () => !toValue(dirty) || confirmDiscard();
}

/** A form is dirty when its current fields differ from the snapshot taken when it opened. Gives back its FormModal's
 *  `canDismiss`. */
export function useUnsavedForm(
  inside: Inside,
  current: MaybeRefOrGetter<unknown>,
  original: MaybeRefOrGetter<unknown>,
): () => Promise<boolean> {
  const dirty = computed(() => JSON.stringify(toValue(current)) !== JSON.stringify(toValue(original)));
  return useUnsavedChanges(inside, dirty);
}

/** Snapshots after the window's own opening reset; a closed window never holds Back. Gives back its FormModal's
 *  `canDismiss`. */
export function useUnsavedFormOnOpen(
  inside: Inside,
  current: MaybeRefOrGetter<unknown>,
  open: MaybeRefOrGetter<boolean>,
): () => Promise<boolean> {
  const original = ref<string>();
  watch(
    () => toValue(open),
    (isOpen) => {
      if (isOpen) original.value = JSON.stringify(toValue(current));
    },
    { immediate: true, flush: 'post' },
  );
  const dirty = computed(() => toValue(open) && original.value !== undefined && JSON.stringify(toValue(current)) !== original.value);
  return useUnsavedChanges(inside, dirty);
}

/** The form an edit window shows when its whole record arrives late: the window painted `shown` (what its row says) at
 *  once and the person typed `typed` in the meantime. Every field the person changed since `shown` keeps what was typed;
 *  every other field takes the record `loaded`. So what was typed is never lost, and Save, which sends what differs from
 *  the record, sends it. Fields are compared with `!==`, as plain values; none of the three objects is changed. */
export function keepTouched<T extends object>(loaded: T, shown: T, typed: T): T {
  const kept = { ...loaded };
  for (const field of Object.keys(loaded) as (keyof T)[]) {
    if (typed[field] !== shown[field]) kept[field] = typed[field];
  }
  return kept;
}

/** The ways out of a window that is an `ion-modal` of its own, not a FormModal (a sheet with its own close button,
 *  hub#1233), asking the question its guard gives back (`useUnsavedForm`, `useUnsavedFormOnOpen`) as FormModal asks it:
 *  `close`, for its close button, closes it only when it may; `canDismiss`, for its `ion-modal`, is asked on Ionic's own
 *  dismissals (Escape, a tap outside), never on closing from the page (`open = false`, no role: a pick, a delete).
 *  Ionic itself never asks who already asked, the system Back (role `handler`). One question at a time: a second way
 *  out while it is up waits for the same answer. */
export function useSheetWaysOut(
  mayClose: () => Promise<boolean>,
  open: Ref<boolean>,
): { canDismiss: (data?: unknown, role?: string) => Promise<boolean>; close: () => Promise<void> } {
  let asking: Promise<boolean> | null = null;
  const ask = (): Promise<boolean> =>
    (asking ??= mayClose().finally(() => {
      asking = null;
    }));
  return {
    canDismiss: (_data, role) => (role === undefined ? Promise.resolve(true) : ask()),
    close: async () => {
      if (await ask()) open.value = false;
    },
  };
}
