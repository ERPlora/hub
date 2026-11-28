<script setup lang="ts">
// PRICING-F04, F05 and F16: the confirmations of a price list's three delicate actions: «Make {name} the
// general list?», «Deactivate {name}?» and «Delete {name}?», each saying its consequence. Confirming runs
// the command and closes, and a deletion says so (`deleted`, so its detail goes back to the lists); a refusal
// (the general list cannot be deactivated nor deleted…) stays in the dialog. `v-model:action` opens one.
import { ConfirmDialog } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { watch } from 'vue';

import { useT } from '../composables/useT';
import type { PriceListOut } from '../operations';

export type ListAction = 'default' | 'deactivate' | 'delete';

const props = defineProps<{ list: PriceListOut | null }>();
const action = defineModel<ListAction | null>('action', { default: null });
const emit = defineEmits<{ deleted: [] }>();

const t = useT();
const commands = {
  default: useCommand('pricing.price_list.set_default'),
  deactivate: useCommand('pricing.price_list.deactivate'),
  delete: useCommand('pricing.price_list.delete'),
};
const DIALOGS = [
  { id: 'default', texts: 'defaultConfirm', tone: 'primary' },
  { id: 'deactivate', texts: 'deactivateConfirm', tone: 'danger' },
  { id: 'delete', texts: 'deleteConfirm', tone: 'danger' },
] as const;

watch(action, () => {
  for (const command of Object.values(commands)) command.error.value = null;
});

async function confirm(): Promise<void> {
  const chosen = action.value;
  if (!props.list || !chosen) return;
  try {
    await commands[chosen].run({ id: props.list.id });
  } catch {
    return; // The dialog says why.
  }
  action.value = null;
  if (chosen === 'delete') emit('deleted');
}
</script>

<template>
  <ConfirmDialog
    v-for="dialog in DIALOGS"
    :key="dialog.id"
    :open="action === dialog.id"
    :testid="`pricing-list-${dialog.id}`"
    :tone="dialog.tone"
    :title="list ? t(`pricing.lists.${dialog.texts}.title`, { name: list.name }) : ''"
    :message="list ? t(`pricing.lists.${dialog.texts}.message`, { name: list.name }) : ''"
    :confirm-label="t(`pricing.lists.${dialog.texts}.confirm`)"
    :cancel-label="t('pricing.cancel')"
    :pending="commands[dialog.id].pending.value"
    :error="commands[dialog.id].error.value"
    @update:open="(open: boolean) => { if (!open) action = null }"
    @confirm="confirm"
    @cancel="action = null"
  />
</template>
