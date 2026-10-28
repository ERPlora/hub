<script setup lang="ts">
// Printing → Devices (PRINTING-F18; WORKBOOK «Pantallas · Dispositivos»; the old hub's print hosts, hub#342):
// only the devices set up here print the queue, with anybody's session. The list, live, by name — Name (this
// device marked), Printers, Last seen and Set up by — and what the device the page runs on does. Whoever
// sets up the printers sets this device up («Print from this device»), edits any device and retires one after
// asking; everybody else reads. A device's own id is never shown (hub#2551): the server marks this one.
import { DataTable, type DataTableAction, type DataTableColumn, EmptyState, InlineFeedback, StatusPill, useConfirm } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { computed, shallowRef } from 'vue';

import DeviceModal from '../components/DeviceModal.vue';
import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { waited } from '../lib/format';
import { refusal } from '../lib/refusal';
import type { DeviceOut } from '../operations';
import { printingTabs } from '../tabs';

const session = useSession();
const canManage = computed(() => session.can('printing.manage_settings'));
const t = useT();
const { confirm } = useConfirm();
/** «3 min ago» turns by itself, without another result. */
const now = useNow();

const list = useLive('printing.device.list', { limit: 100 });
// The printers a device may print for: the business's active ones (the same subscription as Printers').
const printerList = useLive('printing.printer.list', { limit: 100 });
const retire = useCommand('printing.device.retire');

const rows = computed(() => list.data.value?.rows ?? []);
const activePrinters = computed(() => (printerList.data.value?.rows ?? []).filter((printer) => printer.is_active));
const thisDevice = computed(() => rows.value.find((row) => row.this_device) ?? null);
const blocked = computed(() => {
  const code = list.error.value?.code;
  return code === 'app_inactive' || code === 'permission_denied' ? code : null;
});
const tableError = computed(() => (list.status.value === 'error' && !blocked.value ? t('printing.devices.loadError') : undefined));

function printerNames(device: DeviceOut): string {
  return device.printers
    .map((printer) => (printer.is_active ? printer.name : t('printing.devices.inactive', { name: printer.name })))
    .join(', ');
}

/** What the device the page runs on does, and who sets it up when it prints nothing. */
const thisNote = computed(() => {
  if (thisDevice.value) return t('printing.devices.thisPrints', { printers: printerNames(thisDevice.value) });
  return canManage.value ? t('printing.devices.thisNotSetUp') : t('printing.devices.thisAskSomeone');
});

const columns = computed<DataTableColumn<DeviceOut>[]>(() => [
  { key: 'name', label: t('printing.devices.columns.name'), priority: 'high', cell: 'name' },
  { key: 'printers', label: t('printing.devices.columns.printers'), format: (_, row) => printerNames(row) },
  {
    key: 'last_seen_at',
    label: t('printing.devices.columns.lastSeen'),
    format: (_, row) =>
      row.last_seen_at ? t('printing.devices.lastSeen', { age: waited(row.last_seen_at, now.value, t) }) : t('printing.devices.never'),
  },
  { key: 'registered_by', label: t('printing.devices.columns.registeredBy'), priority: 'low' },
]);

const retiring = shallowRef<string | null>(null);
const actions = computed<DataTableAction<DeviceOut>[]>(() =>
  canManage.value
    ? [
        { id: 'edit', label: t('printing.devices.actions.edit'), icon: 'create-outline' },
        {
          id: 'retire',
          label: t('printing.devices.actions.retire'),
          icon: 'trash-outline',
          loading: (row: DeviceOut) => retiring.value === row.id,
        },
      ]
    : [],
);

const editing = shallowRef(false);
const target = shallowRef<DeviceOut | null>(null);

function setUp(): void {
  target.value = null;
  editing.value = true;
}

async function retireDevice(row: DeviceOut): Promise<void> {
  const yes = await confirm({
    title: t('printing.devices.retire.title', { name: row.name }),
    message: t('printing.devices.retire.message'),
    confirmLabel: t('printing.devices.retire.confirm'),
    cancelLabel: t('printing.devices.retire.back'),
    tone: 'danger',
  });
  if (!yes || retiring.value) return;
  retiring.value = row.id;
  try {
    await retire.run({ device_id: row.id });
    void toastSuccess(t('printing.devices.retire.done'));
  } catch {
    void toastError(refusal(retire.error.value, t('printing.devices.retire.failed'))?.message ?? t('printing.devices.retire.failed'));
  } finally {
    retiring.value = null;
  }
}

function onAction({ actionId, row }: { actionId: string; row: DeviceOut }): void {
  if (!canManage.value) return;
  if (actionId === 'edit') {
    target.value = row;
    editing.value = true;
  } else if (actionId === 'retire') void retireDevice(row);
}
</script>

<template>
  <AppPage
    :title="$t('printing.title')"
    content-layout="fill"
    :tabs="printingTabs($t)"
    :tabs-label="$t('printing.tabs.label')"
  >
    <div class="printing-devices page-fill">
      <div class="printing-devices__head">
        <h2
          class="printing-devices__heading"
          data-testid="printing-devices-heading"
        >
          {{ $t('printing.devices.heading') }}
        </h2>
        <p
          class="printing-devices__intro"
          data-testid="printing-devices-intro"
        >
          {{ $t('printing.devices.intro') }}
        </p>
      </div>
      <InlineFeedback
        v-if="blocked"
        tone="warning"
        data-testid="printing-devices-blocked"
        :heading="blocked === 'app_inactive' ? $t('printing.live.appInactive') : $t('printing.live.noPermission')"
      />
      <template v-else>
        <InlineFeedback
          v-if="list.status.value !== 'loading' && !tableError"
          :tone="thisDevice ? 'success' : 'info'"
          :icon="thisDevice ? 'checkmark-circle-outline' : 'information-circle-outline'"
          data-testid="printing-devices-this"
        >
          {{ thisNote }}
        </InlineFeedback>
        <DataTable
          testid="printing-devices"
          fill
          :rows="rows"
          :page-size="100"
          :page-size-options="[]"
          :column-picker="false"
          :views="['table', 'cards']"
          :card-title="(row: DeviceOut) => row.name"
          card-title-column="name"
          :card-icon="() => 'lucide:smartphone'"
          :loading="list.status.value === 'loading'"
          :error="tableError"
          :addable="canManage && !thisDevice"
          :actions="actions"
          :max-inline-actions="2"
          :entity-label="{ one: $t('printing.devices.entity.one'), many: $t('printing.devices.entity.many') }"
          :labels="{ add: $t('printing.devices.add'), loading: $t('printing.devices.loading'), retry: $t('printing.live.retry') }"
          :columns="columns"
          @add="setUp"
          @action="onAction"
          @retry="list.refresh()"
        >
          <template #name="{ row }">
            <span
              class="printing-devices__name"
              :data-testid="`printing-devices-name-${row.id}`"
            >
              <span class="printing-devices__label">{{ row.name }}</span>
              <StatusPill
                v-if="row.this_device"
                size="sm"
                tone="success"
                :label="t('printing.devices.thisDevice')"
              />
            </span>
          </template>
          <template #empty>
            <EmptyState
              data-testid="printing-devices-empty"
              icon="file-tray-outline"
              :heading="$t('printing.devices.empty')"
            />
          </template>
        </DataTable>
      </template>
    </div>

    <DeviceModal
      v-if="canManage"
      v-model:open="editing"
      :device="target"
      :printers="activePrinters"
    />
  </AppPage>
</template>

<style scoped>
/* A `.page-fill` stack (polish.css): the list fills the page between the topbar and the tabbar. */
.printing-devices {
  gap: 12px;
}
.printing-devices__head {
  display: grid;
  gap: 4px;
  padding-inline: 0.25rem;
}
.printing-devices__heading {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 600;
}
.printing-devices__intro {
  margin: 0;
  color: var(--ion-color-medium-shade, var(--ion-color-medium));
}
/* The name wraps inside its column (a long one is never cut), the «This device» pill under it. */
.printing-devices__name {
  display: inline-grid;
  justify-items: start;
  gap: 2px;
  min-width: 0;
  max-width: 100%;
}
.printing-devices__label {
  white-space: normal;
  overflow-wrap: anywhere;
}
</style>
