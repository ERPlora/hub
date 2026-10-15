<script setup lang="ts">
// «Drawers» (CASH_REGISTER-F02; the product only had the assistant for them): the business's drawers by
// name, whether each is active, live. Whoever may change the settings adds one («Add drawer»), renames one
// and deactivates or activates one — a drawer is never deleted: its sessions name it. A deactivated drawer
// is no longer offered when a session opens.
import { type DataTableAction, type DataTableColumn, DataTable, EmptyState } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { toastError, toastSuccess } from '@erplora/ui/shell';
import { computed, shallowRef } from 'vue';

import { useT } from '../composables/useT';
import { refusal } from '../lib/refusal';
import type { RegisterOut } from '../operations';
import RegisterModal from './RegisterModal.vue';

const props = defineProps<{ editable: boolean }>();

const t = useT();
const list = useLive('cash_register.register.list', { limit: 100 });
const update = useCommand('cash_register.register.update');

const rows = computed(() => list.data.value?.rows ?? []);
const tableError = computed(() => (list.status.value === 'error' ? t('cash_register.registers.loadError') : undefined));

const columns = computed<DataTableColumn<RegisterOut>[]>(() => [
  { key: 'name', label: t('cash_register.registers.columns.name'), priority: 'high' },
  {
    key: 'is_active',
    label: t('cash_register.registers.columns.active'),
    format: (_, row) => (row.is_active ? t('cash_register.registers.yes') : t('cash_register.registers.no')),
  },
]);

const actions = computed<DataTableAction<RegisterOut>[]>(() =>
  props.editable
    ? [
        { id: 'rename', label: t('cash_register.registers.rename'), icon: 'create-outline' },
        {
          id: 'toggle',
          label: (row) => (row.is_active ? t('cash_register.registers.deactivate') : t('cash_register.registers.activate')),
          icon: 'swap-horizontal-outline',
          loading: () => update.pending.value,
        },
      ]
    : [],
);

const editing = shallowRef(false);
const register = shallowRef<RegisterOut | null>(null);

function add(): void {
  register.value = null;
  editing.value = true;
}

async function toggle(row: RegisterOut): Promise<void> {
  try {
    await update.run({ register_id: row.id, is_active: !row.is_active });
  } catch {
    void toastError(refusal(update.error.value, t('cash_register.registers.toggleFailed'))?.message ?? t('cash_register.registers.toggleFailed'));
    return;
  }
  void toastSuccess(t(row.is_active ? 'cash_register.registers.deactivated' : 'cash_register.registers.activated'));
}

function onAction({ actionId, row }: { actionId: string; row: RegisterOut }): void {
  if (!props.editable) return;
  if (actionId === 'rename') {
    register.value = row;
    editing.value = true;
  } else if (actionId === 'toggle') void toggle(row);
}
</script>

<template>
  <section class="cash-registers">
    <h2
      class="cash-registers__heading"
      data-testid="cash-register-registers-heading"
    >
      {{ $t('cash_register.registers.heading') }}
    </h2>
    <DataTable
      testid="cash-register-registers"
      :rows="rows"
      :page-size="100"
      :page-size-options="[]"
      :column-picker="false"
      :loading="list.status.value === 'loading'"
      :error="tableError"
      :addable="editable"
      :actions="actions"
      :entity-label="{ one: $t('cash_register.registers.entity.one'), many: $t('cash_register.registers.entity.many') }"
      :labels="{ add: $t('cash_register.registers.add'), retry: $t('cash_register.live.retry') }"
      :columns="columns"
      @add="add"
      @action="onAction"
      @retry="list.refresh()"
    >
      <template #empty>
        <EmptyState
          data-testid="cash-register-registers-empty"
          icon="file-tray-outline"
          :heading="$t('cash_register.registers.empty')"
        />
      </template>
    </DataTable>
    <RegisterModal
      v-if="editable"
      v-model:open="editing"
      :register="register"
    />
  </section>
</template>

<style scoped>
.cash-registers {
  display: grid;
  gap: 8px;
}
.cash-registers__heading {
  margin: 0;
  padding-inline: 0.25rem;
  font-size: 1.05rem;
  font-weight: 600;
}
</style>
