// `useLeaveGuard(dirty)`: leaving the editor with unsaved changes asks first (WORKBOOK FLOW-F14), by the
// back arrow or any other way out of the route (`onBeforeRouteLeave`). `mayLeave` is the question.
import { useConfirm } from '@erplora/ui/components';
import { inject, type Ref } from 'vue';
import { matchedRouteKey, onBeforeRouteLeave } from 'vue-router';

import { useT } from './useT';

export function useLeaveGuard(dirty: Readonly<Ref<boolean>>) {
  const t = useT();
  const { confirm } = useConfirm();

  async function mayLeave(): Promise<boolean> {
    if (!dirty.value) return true;
    return confirm({
      title: t('flow.editor.leaveTitle'),
      message: t('flow.editor.leaveMessage'),
      tone: 'warning',
      confirmLabel: t('flow.editor.leaveYes'),
      cancelLabel: t('flow.editor.leaveNo'),
    });
  }

  // Only inside a route (a page under the router's outlet, which Ionic's provides too).
  if (inject(matchedRouteKey, null)?.value) onBeforeRouteLeave(() => mayLeave());

  return { mayLeave };
}
