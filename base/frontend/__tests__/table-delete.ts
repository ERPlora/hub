// Deleting a row from a list page's table, as its test does it: «Delete» on the row opens the page's ConfirmDialog, and
// confirming it sends the deletion. Each page's test checks what its dialog says and what it sent.
import { ConfirmDialog } from '@erplora/ui/components';
import type { VueWrapper } from '@vue/test-utils';

import { flush } from '../../../packages/ui/src/sdk/__tests__/live-harness';

/** A list page as its test sets it up: mounted, live, with its DataTable and a page of rows to show. */
export interface ListPageWithDelete {
  wrapper: VueWrapper;
  table: () => { vm: { $emit: (event: string, ...args: unknown[]) => void } };
  show: (data: unknown) => Promise<void>;
  answer: (status: number, body: unknown) => void;
  sent: () => unknown[];
}

/** Shows `firstPage` and presses «Delete» on its `row`: the confirmation the page opens. */
export async function askToDelete(s: ListPageWithDelete, firstPage: unknown, row: unknown) {
  await s.show(firstPage);
  s.table().vm.$emit('action', { actionId: 'delete', row });
  await flush();
  return s.wrapper.findComponent(ConfirmDialog);
}

/** Confirms `dialog`, the hub answering that `id` is deleted: the calls the page made. */
export async function confirmDeletion(
  s: ListPageWithDelete,
  dialog: { vm: { $emit: (event: string, ...args: unknown[]) => void } },
  id: string,
): Promise<unknown[]> {
  s.answer(200, { id });
  dialog.vm.$emit('confirm');
  await flush();
  return s.sent();
}
