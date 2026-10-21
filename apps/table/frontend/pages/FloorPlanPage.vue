<script setup lang="ts">
// Tables → Floor plan (WORKBOOK «Pantallas · Plano de sala»; TABLE-F01 to F06, F09 to F17, F28, F32).
// One row on top: the zone strip (it scrolls sideways on a phone), «Service / Edit plan» for whoever
// draws the room, and — editing — «+» («Add zone or table») and the pencil («Edit zone»). Underneath, the
// live plan of the chosen zone: every table of the room (`table.table.list`, windows of 100) is read from
// the start, on the page's one stream, and the strip only picks the zone it paints (a query that waited for
// the zones would change when they came and throw the first stream away; a zone tap would reopen it). It
// changes by itself when somebody seats, moves, joins, splits, charges or voids.
// - Service: the zones and tables in service; a tap opens the table's window (TableSheet). Transfer and
//   Merge come back here to pick their destination on the plan: only the tables that may be picked answer,
//   with «Transfer 4 to…» / «Pick a free table» and «Cancel».
// - Edit plan: every zone and table (inactive ones greyed out); a tap opens «Edit table»; a drag (or the
//   arrows) saves the place at once (`table.table.move`), and a refused move goes back and says so.
import { EmptyState, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton, IonSpinner } from '@ionic/vue';
import { computed, ref, useTemplateRef, watch } from 'vue';

import AddModal from '../components/AddModal.vue';
import FloorCanvas from '../components/FloorCanvas.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TableFormModal from '../components/TableFormModal.vue';
import TableSheet from '../components/TableSheet.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import { useAllRows } from '../composables/useAllRows';
import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { paintedStatus, type PickMode, targetable } from '../lib/floor';
import type { SettingsOut, TableCheckOut, TableOut, ZoneOut } from '../operations';
import { tableTabs } from '../tabs';

type Mode = 'service' | 'edit';
interface Pick {
  mode: PickMode;
  table: TableOut;
  check: TableCheckOut;
}

const FACTORY: SettingsOut = {
  prompt_guests_on_seat: true,
  timer_warning_minutes: 60,
  timer_critical_minutes: 90,
  reserved_lead_minutes: 60,
  timezone: 'Europe/Madrid',
};

const session = useSession();
const t = useT();
const now = useNow();
const canDraw = computed(() => session.can('table.change_table') || session.can('table.add_table') || session.can('table.add_zone'));
const canAdd = computed(() => session.can('table.add_table') || session.can('table.add_zone'));
const canEditZone = computed(() => session.can('table.change_zone'));

const mode = ref<Mode>('service');
const editing = computed(() => mode.value === 'edit' && canDraw.value);

const { data: settingsData } = useLive('table.settings.get', {});
const settings = computed(() => settingsData.value ?? FACTORY);

const zonesLive = useLive('table.zone.list', { sort: 'sort_order', limit: 100 });
const zones = computed<ZoneOut[]>(() => (zonesLive.data.value?.rows ?? []).filter((zone) => editing.value || zone.is_active));
const activeZoneId = ref<string | null>(null);
const activeZone = computed(() => zones.value.find((zone) => zone.id === activeZoneId.value) ?? null);

watch(
  zones,
  (now) => {
    if (!now.some((zone) => zone.id === activeZoneId.value)) activeZoneId.value = now[0]?.id ?? null;
  },
  { immediate: true },
);

const plan = useAllRows('table.table.list', () => ({ sort: 'number' }));
/** The tables as the clock paints them now: a reservation enters its window or ends with no event. */
const painted = computed<TableOut[]>(() =>
  plan.rows.value.map((table) => {
    const status = paintedStatus(table, now.value, settings.value.reserved_lead_minutes);
    return status === table.status ? table : { ...table, status };
  }),
);
const tables = computed<TableOut[]>(() =>
  painted.value.filter((table) => (!activeZoneId.value || table.zone_id === activeZoneId.value) && (editing.value || table.in_service)),
);
// When the clock repaints a table, the server is asked again (it may know more: another reservation).
const drift = computed(() =>
  painted.value
    .filter((table, index) => table.status !== plan.rows.value[index]?.status)
    .map((table) => `${table.id}:${table.status}`)
    .join(','),
);
watch(drift, (now, before) => {
  if (now && now !== before) plan.refresh();
});
const blocked = computed(() => blockingError(zonesLive.error.value ?? plan.error.value));
const loading = computed(() => zonesLive.status.value === 'loading' || (zones.value.length > 0 && plan.status.value === 'loading'));
const loadFailed = computed(() => !blocked.value && (zonesLive.status.value === 'error' || plan.status.value === 'error'));

const failure = ref('');
const pick = ref<Pick | null>(null);
const canvas = useTemplateRef<InstanceType<typeof FloorCanvas>>('canvas');

const pickable = computed(() => {
  const current = pick.value;
  return current ? (table: TableOut) => targetable(current.mode, current.table, table) : null;
});

// Dialogs
const sheetId = ref<string | null>(null);
const sheetOpen = ref(false);
const sheetTable = computed(() => painted.value.find((table) => table.id === sheetId.value) ?? null);
const formTable = ref<TableOut | null>(null);
const formOpen = ref(false);
const addOpen = ref(false);
const zoneOpen = ref(false);

function onModeChange(event: CustomEvent<{ value?: string | number }>): void {
  const value = String(event.detail.value ?? 'service') as Mode;
  if (value !== 'service' && value !== 'edit') return;
  mode.value = value;
  pick.value = null;
  failure.value = '';
}

function onZoneChange(event: CustomEvent<{ value?: string | number }>): void {
  const value = event.detail.value;
  if (value !== undefined && value !== null) activeZoneId.value = String(value);
}

const transfer = useCommand('table.session.transfer');
const merge = useCommand('table.session.merge');
const move = useCommand('table.table.move');

function refusal(error: unknown, fallback: string): string {
  const apiError = error as ApiError | null;
  if (apiError?.code === 'table.table_not_available') return t('table.floor.taken');
  return apiError?.message || fallback;
}

async function finishPick(target: TableOut): Promise<void> {
  const current = pick.value;
  if (!current) return;
  failure.value = '';
  try {
    if (current.mode === 'transfer') {
      await transfer.run({ id: current.check.id, to_table_id: target.id });
    } else if (target.id === current.table.id) {
      const other = target.checks.find((check) => check.id !== current.check.id);
      if (!other) return;
      await merge.run({ id: current.check.id, into_session_id: other.id });
    } else {
      await merge.run({ id: current.check.id, into_table_id: target.id });
    }
  } catch (error) {
    failure.value = refusal(error, current.mode === 'transfer' ? t('table.floor.transferError') : t('table.floor.mergeError'));
    return;
  }
  pick.value = null;
}

function onSelect(table: TableOut): void {
  if (pick.value) {
    void finishPick(table);
    return;
  }
  failure.value = '';
  if (editing.value) {
    formTable.value = table;
    formOpen.value = true;
    return;
  }
  sheetId.value = table.id;
  sheetOpen.value = true;
}

async function onMove({ table, x, y }: { table: TableOut; x: number; y: number }): Promise<void> {
  failure.value = '';
  try {
    await move.run({ id: table.id, position_x: x, position_y: y });
  } catch {
    canvas.value?.revert(table.id);
    failure.value = t('table.floor.positionError');
  }
}

function onPick(next: Pick): void {
  failure.value = '';
  pick.value = next;
}

function onZoneSaved(zone: ZoneOut): void {
  activeZoneId.value = zone.id;
}
</script>

<template>
  <AppPage
    :title="$t('table.title')"
    :tabs="tableTabs($t, { settings: session.can('table.manage_settings') })"
    :tabs-label="$t('table.tabs.label')"
  >
    <PageNotices
      testid="table-floor"
      :status="zonesLive.status.value === 'reconnecting' ? 'reconnecting' : plan.status.value"
      :error="zonesLive.error.value ?? plan.error.value"
    />
    <div
      v-if="!blocked"
      class="table-floor"
    >
      <div class="table-floor__bar">
        <ion-segment
          v-if="zones.length"
          class="table-floor__zones"
          data-testid="table-floor-zones"
          scrollable
          :value="activeZoneId ?? undefined"
          :aria-label="$t('table.floor.zones')"
          @ion-change="onZoneChange"
        >
          <ion-segment-button
            v-for="zone in zones"
            :key="zone.id"
            :value="zone.id"
            :data-testid="`table-floor-zone-tab-${zone.id}`"
          >
            <ion-label>{{ zone.name }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <span
          v-else
          class="table-floor__spacer"
        />
        <ion-segment
          v-if="canDraw"
          class="table-floor__mode"
          data-testid="table-floor-mode"
          :value="mode"
          :aria-label="$t('table.floor.mode.label')"
          @ion-change="onModeChange"
        >
          <ion-segment-button
            value="service"
            data-testid="table-floor-mode-service"
          >
            <ion-label>{{ $t('table.floor.mode.service') }}</ion-label>
          </ion-segment-button>
          <ion-segment-button
            value="edit"
            data-testid="table-floor-mode-edit"
          >
            <ion-label>{{ $t('table.floor.mode.edit') }}</ion-label>
          </ion-segment-button>
        </ion-segment>
        <template v-if="editing">
          <ion-button
            v-if="canAdd"
            fill="clear"
            data-testid="table-floor-add"
            :aria-label="$t('table.floor.add')"
            :title="$t('table.floor.add')"
            @click="addOpen = true"
          >
            <HubIcon
              slot="icon-only"
              name="ion:add-outline"
            />
          </ion-button>
          <ion-button
            v-if="canEditZone"
            fill="clear"
            data-testid="table-floor-zone-edit"
            :aria-label="$t('table.floor.editZone')"
            :title="$t('table.floor.editZone')"
            :disabled="!activeZone"
            @click="zoneOpen = true"
          >
            <HubIcon
              slot="icon-only"
              name="ion:create-outline"
            />
          </ion-button>
        </template>
      </div>

      <div
        v-if="pick"
        class="table-floor__pick"
        data-testid="table-floor-pick"
      >
        <strong>{{ pick.mode === 'transfer' ? $t('table.floor.transferTitle', { number: pick.table.number }) : $t('table.floor.mergeTitle', { number: pick.table.number }) }}</strong>
        <span>{{ pick.mode === 'transfer' ? $t('table.floor.pickFree') : $t('table.floor.pickOccupied') }}</span>
        <ion-button
          fill="clear"
          data-testid="table-floor-pick-cancel"
          @click="pick = null"
        >
          {{ $t('table.cancel') }}
        </ion-button>
      </div>

      <InlineFeedback
        v-if="failure && !sheetOpen && !formOpen && !addOpen && !zoneOpen"
        tone="danger"
        dismissible
        data-testid="table-floor-error"
        @dismiss="failure = ''"
      >
        {{ failure }}
      </InlineFeedback>
      <InlineFeedback
        v-if="loadFailed"
        tone="danger"
        data-testid="table-floor-load-error"
        :heading="$t('table.floor.loadError')"
      >
        <ion-button
          fill="clear"
          size="small"
          @click="plan.refresh()"
        >
          {{ $t('table.live.retry') }}
        </ion-button>
      </InlineFeedback>

      <p
        v-if="loading"
        class="table-floor__loading"
        data-testid="table-floor-loading"
      >
        <ion-spinner name="crescent" />
        {{ $t('table.loading') }}
      </p>
      <EmptyState
        v-else-if="!zones.length"
        data-testid="table-floor-empty-zones"
        icon="grid-outline"
        :message="$t('table.floor.emptyZones')"
      />
      <template v-else>
        <FloorCanvas
          ref="canvas"
          :tables="tables"
          :now="now"
          :time-zone="settings.timezone"
          :editable="editing && !pick"
          :pick="pickable"
          @select="onSelect"
          @move="onMove"
        >
          <EmptyState
            v-if="!tables.length"
            class="table-floor__empty"
            data-testid="table-floor-empty-tables"
            icon="grid-outline"
            :message="editing ? $t('table.floor.emptyTables') : $t('table.floor.emptyService')"
          />
        </FloorCanvas>
        <p
          v-if="editing"
          class="table-floor__hint"
          data-testid="table-floor-hint"
        >
          {{ $t('table.floor.hint') }}
        </p>
      </template>
    </div>

    <TableSheet
      v-model:open="sheetOpen"
      :table="sheetTable"
      :settings="settings"
      :now="now"
      @pick="onPick"
    />
    <TableFormModal
      v-model:open="formOpen"
      :table="formTable"
      :zones="zonesLive.data.value?.rows ?? []"
      :can-delete="session.can('table.delete_table')"
    />
    <AddModal
      v-model:open="addOpen"
      :zone-id="activeZoneId"
      @zone="(id: string) => (activeZoneId = id)"
    />
    <ZoneFormModal
      v-model:open="zoneOpen"
      :zone="activeZone"
      variant="plan"
      :can-delete="session.can('table.delete_zone')"
      @saved="onZoneSaved"
    />
  </AppPage>
</template>

<style scoped>
.table-floor__bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.25rem;
  margin-bottom: 0.4rem;
}
.table-floor__zones {
  flex: 1;
  min-width: 0;
}
.table-floor__spacer {
  flex: 1;
}
.table-floor__mode {
  width: auto;
}
.table-floor__bar ion-button {
  min-height: 44px;
  --min-height: 44px;
}
.table-floor__pick {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin: 0.4rem 0;
  padding: 0.6rem 0.7rem;
  border-radius: var(--ep-radius, 12px);
  background: var(--ion-color-light, #f4f5f8);
}
.table-floor__pick span {
  margin-inline-end: auto;
  color: var(--ion-color-medium, #8b897f);
}
.table-floor__loading {
  display: flex;
  align-items: center;
  gap: 8px;
}
.table-floor__empty {
  position: absolute;
  inset: 0;
}
.table-floor__hint {
  margin: 0.5rem 0 0;
  font-size: 0.85rem;
  color: var(--ion-color-medium, #8b897f);
}
</style>
