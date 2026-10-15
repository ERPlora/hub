<script setup lang="ts">
// PRICING-F04, F05: the confirmations of a price list's two delicate actions (the old module had none of
// them on screen): «Make {name} the general list?» and «Deactivate {name}?», each saying its
// consequence. Confirming runs the command and closes; a refusal (the general list cannot be
// deactivated…) stays in the dialog. `v-model:action` opens one or the other.
import { ConfirmDialog } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { watch } from 'vue';

import { useT } from '../composables/useT';
import type { PriceListOut } from '../operations';

export type ListAction = 'default' | 'deactivate';

const props = defineProps<{ list: PriceListOut | null }>();
const action = defineModel<ListAction | null>('action', { default: null });

const t = useT();
const setDefault = useCommand('pricing.price_list.set_default');
const deactivate = useCommand('pricing.price_list.deactivate');

watch(action, () => {
  setDefault.error.value = null;
  deactivate.error.value = null;
});

async function confirm(): Promise<void> {
  if (!props.list || !action.value) return;
  const command = action.value === 'default' ? setDefault : deactivate;
  try {
    await command.run({ id: props.list.id });
  } catch {
    return; // The dialog says why.
  }
  action.value = null;
}
</script>

<template>
  <ConfirmDialog
    :open="action === 'default'"
    testid="pricing-list-default"
    tone="primary"
    :title="list ? t('pricing.lists.defaultConfirm.title', { name: list.name }) : ''"
    :message="list ? t('pricing.lists.defaultConfirm.message', { name: list.name }) : ''"
    :confirm-label="t('pricing.lists.defaultConfirm.confirm')"
    :cancel-label="t('pricing.cancel')"
    :pending="setDefault.pending.value"
    :error="setDefault.error.value"
    @update:open="(open: boolean) => { if (!open) action = null }"
    @confirm="confirm"
    @cancel="action = null"
  />
  <ConfirmDialog
    :open="action === 'deactivate'"
    testid="pricing-list-deactivate"
    tone="danger"
    :title="list ? t('pricing.lists.deactivateConfirm.title', { name: list.name }) : ''"
    :message="list ? t('pricing.lists.deactivateConfirm.message', { name: list.name }) : ''"
    :confirm-label="t('pricing.lists.deactivateConfirm.confirm')"
    :cancel-label="t('pricing.cancel')"
    :pending="deactivate.pending.value"
    :error="deactivate.error.value"
    @update:open="(open: boolean) => { if (!open) action = null }"
    @confirm="confirm"
    @cancel="action = null"
  />
</template>
