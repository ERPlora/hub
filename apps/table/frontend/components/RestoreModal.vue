<script setup lang="ts">
// «Seat again» a parked check (WORKBOOK «Sesiones»; TABLE-F24): the tables free right now — available or
// reserved, in service — read live, to pick one; «Seat» sits the check there (`table.session.restore`),
// where its check of Sales takes the table's title. With none free, it says so; a refusal stays here.
import { FormModal } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { IonSelect, IonSelectOption } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

import type { SessionOut } from '../operations';

const props = defineProps<{ session: SessionOut | null }>();
const open = defineModel<boolean>('open', { default: false });

const { data } = useLive('table.table.list', { in_service: true, sort: 'number', limit: 100 });
const free = computed(() => (data.value?.rows ?? []).filter((table) => table.status === 'available' || table.status === 'reserved'));
const tableId = ref('');
const restore = useCommand('table.session.restore');

watch(open, (isOpen) => {
  if (!isOpen) return;
  tableId.value = '';
  restore.error.value = null;
});

async function seat(): Promise<void> {
  if (!props.session || !tableId.value) return;
  try {
    await restore.run({ id: props.session.id, table_id: tableId.value });
  } catch {
    return; // The dialog says why.
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="table-restore"
    size="sm"
    :title="$t('table.sessions.restore.title')"
    :submit-label="$t('table.sessions.restore.confirm')"
    :cancel-label="$t('table.cancel')"
    :pending="restore.pending.value"
    :error="restore.error.value"
    :submit-disabled="!tableId"
    @submit="seat"
  >
    <p
      v-if="data && free.length === 0"
      data-testid="table-restore-none"
    >
      {{ $t('table.sessions.restore.noFree') }}
    </p>
    <ion-select
      v-else
      data-testid="table-restore-table"
      :value="tableId"
      :label="$t('table.sessions.restore.table')"
      label-placement="floating"
      fill="outline"
      mode="md"
      interface="popover"
      @ion-change="tableId = $event.detail.value ?? ''"
    >
      <ion-select-option
        v-for="table in free"
        :key="table.id"
        :value="table.id"
      >
        {{ table.number }} · {{ table.zone_name ?? $t('table.form.noZone') }}
      </ion-select-option>
    </ion-select>
  </FormModal>
</template>
