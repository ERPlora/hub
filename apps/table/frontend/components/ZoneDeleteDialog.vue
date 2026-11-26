<script setup lang="ts">
// «Delete zone?» (WORKBOOK «Zonas», «Plano de sala»; TABLE-F06): an empty zone only says what deleting does;
// a zone with tables says they must be moved or deleted first, and «Delete zone» is off.
// Deleting (`table.zone.delete`) tells the page (`deleted`); a refusal stays in the dialog.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { watch } from 'vue';

import type { ZoneOut } from '../operations';

const props = defineProps<{ zone: ZoneOut; testid: string }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ deleted: [] }>();

const removal = useCommand('table.zone.delete');

watch(open, (isOpen) => {
  if (isOpen) removal.error.value = null;
});

async function remove(): Promise<void> {
  try {
    await removal.run({ id: props.zone.id });
  } catch {
    return; // The dialog says why.
  }
  emit('deleted');
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    :testid="testid"
    role="alertdialog"
    size="sm"
    submit-color="danger"
    :title="$t('table.zones.delete.title')"
    :submit-label="$t('table.zones.delete.confirm')"
    :cancel-label="$t('table.cancel')"
    :pending="removal.pending.value"
    :error="removal.error.value"
    :submit-disabled="zone.table_count > 0"
    @submit="remove"
  >
    <p v-if="zone.table_count > 0">{{ $t('table.zones.delete.impact', { count: zone.table_count }) }}</p>
    <p v-else>{{ $t('table.zones.delete.emptyImpact') }}</p>
  </FormModal>
</template>
