// `useUnsavedChanges(inside, dirty)` (hub#1015; BASE-F05, INVENTORY-F01/F02): a window that holds what the person typed
// signs up with the system Back (`system-back.ts`, `holdUnsavedChanges`) for as long as it is mounted. While `dirty`
// says it holds something, Android's Back on it asks «Discard changes?» — «Keep editing» or «Discard changes» — and
// closes it only on «Discard changes»; with nothing typed Back closes it at once, as before. `inside` is an element of
// the window (its fields), which tells its overlay apart from any other open. The question is the ConfirmDialog of
// `@erplora/ui` (`useConfirm`), so Back on it closes the question and the person keeps editing.
import { useConfirm } from '@erplora/ui/components';
import { computed, getCurrentInstance, type MaybeRefOrGetter, onScopeDispose, ref, toValue, watch } from 'vue';

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

/** Called from `setup()`: the question belongs to the app of the window that asks it. */
export function useUnsavedChanges(inside: Inside, dirty: MaybeRefOrGetter<boolean>): void {
  const { t } = useBaseI18n();
  const { confirm } = useConfirm();
  const letGo = holdUnsavedChanges({
    inside: elementOf(inside, getCurrentInstance()),
    dirty: () => toValue(dirty),
    confirmDiscard: () =>
      confirm({
        title: t('base.unsavedChanges.title'),
        message: t('base.unsavedChanges.message'),
        tone: 'danger',
        confirmLabel: t('base.unsavedChanges.discard'),
        cancelLabel: t('base.unsavedChanges.keep'),
      }),
  });
  onScopeDispose(letGo);
}

/** A form is dirty when its current fields differ from the snapshot taken when it opened. */
export function useUnsavedForm(
  inside: Inside,
  current: MaybeRefOrGetter<unknown>,
  original: MaybeRefOrGetter<unknown>,
): void {
  const dirty = computed(() => JSON.stringify(toValue(current)) !== JSON.stringify(toValue(original)));
  useUnsavedChanges(inside, dirty);
}

/** Snapshots after the window's own opening reset; a closed window never holds Back. */
export function useUnsavedFormOnOpen(
  inside: Inside,
  current: MaybeRefOrGetter<unknown>,
  open: MaybeRefOrGetter<boolean>,
): void {
  const original = ref<string>();
  watch(
    () => toValue(open),
    (isOpen) => {
      if (isOpen) original.value = JSON.stringify(toValue(current));
    },
    { immediate: true, flush: 'post' },
  );
  const dirty = computed(() => toValue(open) && original.value !== undefined && JSON.stringify(toValue(current)) !== original.value);
  useUnsavedChanges(inside, dirty);
}
