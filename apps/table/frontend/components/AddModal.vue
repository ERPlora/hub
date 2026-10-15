<script setup lang="ts">
// The plan's «+» (WORKBOOK «Plano de sala»; TABLE-F01, F02): «Add», where each action owns its field —
// Zone («New zone…») with «Add zone» (the zone goes last and becomes the chosen one: `zone`), and «Table
// number» («Auto-numbered» when left empty: the first free number of the zone) with «Add table», off while
// there is no zone. The new table lands on the first free spot of the plan. A refusal stays here.
import { FormModal } from '@erplora/ui/components';
import { useCommand } from '@erplora/ui/sdk';
import { IonButton, IonInput } from '@ionic/vue';
import { computed, ref, watch } from 'vue';

const props = defineProps<{ zoneId: string | null }>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ zone: [id: string] }>();

const zoneName = ref('');
const number = ref('');
const createZone = useCommand('table.zone.create');
const createTable = useCommand('table.table.create');
const last = ref<'zone' | 'table'>('table');
const pending = computed(() => createZone.pending.value || createTable.pending.value);
const error = computed(() => (last.value === 'zone' ? createZone.error.value : createTable.error.value));

watch(open, (isOpen) => {
  if (!isOpen) return;
  zoneName.value = '';
  number.value = '';
  createZone.error.value = null;
  createTable.error.value = null;
});

const text = (value: unknown): string => (value === null || value === undefined ? '' : String(value));

async function addZone(): Promise<void> {
  last.value = 'zone';
  const name = zoneName.value.trim();
  if (!name) return;
  try {
    const zone = await createZone.run({ name });
    emit('zone', zone.id);
  } catch {
    return;
  }
  open.value = false;
}

async function addTable(): Promise<void> {
  last.value = 'table';
  if (!props.zoneId) return;
  try {
    await createTable.run({ zone_id: props.zoneId, ...(number.value.trim() ? { number: number.value.trim() } : {}) });
  } catch {
    return;
  }
  open.value = false;
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="table-add"
    :title="$t('table.add.title')"
    :pending="pending"
    :error="error"
  >
    <div class="table-add">
      <ion-input
        data-testid="table-add-zone-name"
        :value="zoneName"
        :label="$t('table.add.zone')"
        :placeholder="$t('table.add.zonePlaceholder')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="100"
        @ion-input="zoneName = text($event.detail.value)"
      />
      <div class="table-add__row">
        <ion-button
          fill="outline"
          data-testid="table-add-zone-submit"
          :disabled="pending || !zoneName.trim()"
          @click="addZone"
        >
          {{ $t('table.add.addZone') }}
        </ion-button>
      </div>
      <ion-input
        data-testid="table-add-table-number"
        :value="number"
        :label="$t('table.add.number')"
        :placeholder="$t('table.add.numberPlaceholder')"
        label-placement="floating"
        fill="outline"
        mode="md"
        :maxlength="20"
        @ion-input="number = text($event.detail.value)"
      />
      <div class="table-add__row">
        <ion-button
          data-testid="table-add-table-submit"
          :disabled="pending || !zoneId"
          @click="addTable"
        >
          {{ $t('table.add.addTable') }}
        </ion-button>
      </div>
    </div>
    <template #footer="{ cancel }">
      <ion-button
        fill="clear"
        data-testid="table-add-close"
        @click="cancel"
      >
        {{ $t('table.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.table-add {
  display: grid;
  gap: 12px;
}
.table-add__row {
  display: flex;
  justify-content: flex-end;
}
</style>
