// `useUnsavedChanges(inside, dirty)` (hub#1015; BASE-F05, INVENTORY-F01/F02): a window that holds what the person typed
// signs up with the system Back (`system-back.ts`, `holdUnsavedChanges`) for as long as it is mounted. While `dirty`
// says it holds something, Android's Back on it asks «Discard changes?» — «Keep editing» or «Discard changes» — and
// closes it only on «Discard changes»; with nothing typed Back closes it at once, as before. `inside` is an element of
// the window (its fields), which tells its overlay apart from any other open. The question is the ConfirmDialog of
// `@erplora/ui` (`useConfirm`), so Back on it closes the question and the person keeps editing.
import { useConfirm } from '@erplora/ui/components';
import { type MaybeRefOrGetter, onScopeDispose, toValue } from 'vue';

import { useBaseI18n } from './i18n';
import { holdUnsavedChanges } from './system-back';

/** Called from `setup()`: the question belongs to the app of the window that asks it. */
export function useUnsavedChanges(inside: MaybeRefOrGetter<Element | null | undefined>, dirty: MaybeRefOrGetter<boolean>): void {
  const { t } = useBaseI18n();
  const { confirm } = useConfirm();
  const letGo = holdUnsavedChanges({
    inside: () => toValue(inside),
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
