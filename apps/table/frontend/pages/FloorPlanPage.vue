<script setup lang="ts">
import { EmptyState, FloorCards, FloorSkeleton, FloorSummary, FloorZoneTabs, InlineFeedback, zoneColor } from '@erplora/ui/components';
import { type ApiError, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, HubIcon, useSession } from '@erplora/ui/shell';
import { IonButton, IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, ref, useTemplateRef, watch } from 'vue';
import { useRouter } from 'vue-router';

import AddModal from '../components/AddModal.vue';
import FloorCanvas from '../components/FloorCanvas.vue';
import PageNotices, { blockingError } from '../components/PageNotices.vue';
import TableFormModal from '../components/TableFormModal.vue';
import TableSheet from '../components/TableSheet.vue';
import ZoneFormModal from '../components/ZoneFormModal.vue';
import { useAllRows } from '../composables/useAllRows';
import { useFloorViews } from '../composables/useFloorViews';
import { useIsPhone } from '../composables/useIsPhone';
import { useNow } from '../composables/useNow';
import { useT } from '../composables/useT';
import { paintedStatus, type PickMode, targetable } from '../lib/floor';
import { zoneSummary, zoneTabs } from '../lib/floor-summary';
import type { SettingsOut, TableCheckOut, TableOut, ZoneOut } from '../operations';
import { useAppTabs } from '../../../../base/frontend/lib/app-tabs';

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
const sections = useAppTabs('table');
const router = useRouter();
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
const isPhone = useIsPhone();

// Every table of the room is read from the start and the zone strip only picks the zone painted: a query that
// waited for the zones would change when they came and drop its first stream, and a zone tap would reopen it.
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
const inService = computed(() => tables.value.filter((table) => table.in_service));
const asCards = computed(() => isPhone.value && !editing.value);
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
const tabs = computed(() => zoneTabs(zones.value, painted.value, t));
const hint = computed(() => {
  if (editing.value) return t('table.floor.hint');
  return tables.value.length && !pick.value ? t('table.floor.serviceHint') : '';
});
const summary = computed(() => zoneSummary(activeZone.value, inService.value, t));
const cards = useFloorViews(
  () => (asCards.value ? tables.value : []),
  () => ({ now: now.value, settings: settings.value, timeZone: settings.value.timezone, pick: pickable.value }),
);

// Dialogs
const sheetId = ref<string | null>(null);
const sheetOpen = ref(false);
const sheetIntent = ref<'check' | 'actions'>('actions');
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

function onCard(id: string, handle: (table: TableOut) => void): void {
  const table = tables.value.find((row) => row.id === id);
  if (table) handle(table);
}

function openSheet(table: TableOut, intent: 'check' | 'actions'): void {
  sheetId.value = table.id;
  sheetIntent.value = intent;
  sheetOpen.value = true;
}

function openCheck(orderId: string): void {
  void router.push({ path: '/sale/pos', query: { order: orderId } });
}

// A tap on an occupied table goes to its check in Sales, as restaurant tills do; a split one asks which check.
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
  const [only, ...others] = table.checks;
  if (only?.order_id && !others.length) openCheck(only.order_id);
  else openSheet(table, others.length ? 'check' : 'actions');
}

function onActions(table: TableOut): void {
  if (pick.value) return;
  failure.value = '';
  openSheet(table, 'actions');
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
    :tabs="sections"
    :tabs-label="$t('table.tabs.label')"
    content-layout="fill"
  >
    <PageNotices
      testid="table-floor"
      :status="zonesLive.status.value === 'reconnecting' ? 'reconnecting' : plan.status.value"
      :error="zonesLive.error.value ?? plan.error.value"
    />
    <div
      v-if="!blocked"
      class="table-floor"
      :style="{ '--zone-color': zoneColor(activeZone?.color) }"
    >
      <div class="table-floor__bar">
        <FloorZoneTabs
          v-if="zones.length"
          data-testid="table-floor-zones"
          :zones="tabs"
          :active="activeZoneId"
          :label="$t('table.floor.zones')"
          @change="(id: string) => (activeZoneId = id)"
        />
        <span
          v-else
          class="table-floor__spacer"
        />
        <ion-segment
          v-if="canDraw"
          class="table-floor__mode"
          data-testid="table-floor-mode"
          scrollable
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
            class="table-floor__action"
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
            class="table-floor__action"
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
        <HubIcon name="ion:swap-horizontal-outline" />
        <div>
          <strong>{{ pick.mode === 'transfer' ? $t('table.floor.transferTitle', { number: pick.table.number }) : $t('table.floor.mergeTitle', { number: pick.table.number }) }}</strong>
          <span>{{ pick.mode === 'transfer' ? $t('table.floor.pickFree') : $t('table.floor.pickOccupied') }}</span>
        </div>
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

      <FloorSkeleton
        v-if="loading"
        data-testid="table-floor-loading"
        :label="$t('table.floor.loading')"
        :variant="asCards ? 'cards' : 'plan'"
      />
      <EmptyState
        v-else-if="!zones.length"
        data-testid="table-floor-empty-zones"
        icon="grid-outline"
        :message="$t('table.floor.emptyZones')"
      />
      <template v-else>
        <FloorSummary
          v-bind="summary"
          data-testid="table-floor-summary"
          :label="$t('table.floor.summary.label')"
        />
        <template v-if="asCards">
          <FloorCards
            v-if="tables.length"
            data-testid="table-floor-cards"
            :tables="cards"
            :label="$t('table.floor.cardsLabel')"
            @select="(id: string) => onCard(id, onSelect)"
            @actions="(id: string) => onCard(id, onActions)"
          />
          <EmptyState
            v-else
            data-testid="table-floor-empty-tables"
            icon="grid-outline"
            :message="$t('table.floor.emptyService')"
          />
        </template>
        <FloorCanvas
          v-else
          ref="canvas"
          :tables="tables"
          :now="now"
          :time-zone="settings.timezone"
          :settings="settings"
          :editable="editing && !pick"
          :pick="pickable"
          @select="onSelect"
          @actions="onActions"
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
          v-if="hint"
          class="table-floor__hint"
          data-testid="table-floor-hint"
        >
          {{ hint }}
        </p>
      </template>
    </div>

    <TableSheet
      v-model:open="sheetOpen"
      :table="sheetTable"
      :settings="settings"
      :now="now"
      :intent="sheetIntent"
      @pick="onPick"
      @check="openCheck"
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
.table-floor {
  display: flex;
  flex: 1 1 0;
  min-height: 0;
  flex-direction: column;
}
.table-floor__bar {
  display: flex;
  flex: none;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.table-floor__spacer {
  flex: 1;
}
.table-floor__mode {
  flex: none;
}
.table-floor__action {
  width: var(--ep-touch-min);
  min-width: var(--ep-touch-min);
  min-height: var(--ep-touch-min);
  margin: 0;
  --color: var(--ep-text-muted);
}
@media (min-width: 641px) {
  .table-floor__bar {
    flex-wrap: nowrap;
  }
}
@media (max-width: 640px) {
  .table-floor {
    flex: 1 0 auto;
  }
  .table-floor__bar > :first-child {
    flex-basis: 100%;
  }
  .table-floor__mode {
    flex: 1;
  }
}
.table-floor__pick {
  display: flex;
  flex: none;
  align-items: center;
  gap: 10px;
  margin: 8px 0;
  padding: 8px 8px 8px 14px;
  border: 1px solid color-mix(in srgb, var(--ion-color-primary) 20%, var(--ion-border-color));
  border-radius: var(--ep-radius);
  background: var(--ep-primary-tint);
}
.table-floor__pick > ion-icon {
  color: var(--ep-primary-text);
  font-size: 20px;
}
.table-floor__pick div {
  flex: 1;
}
.table-floor__pick strong {
  display: block;
  font-size: 12px;
}
.table-floor__pick span {
  color: var(--ep-text-muted);
  font-size: 10px;
}
.table-floor__pick ion-button {
  margin: 0;
  --color: var(--ep-primary-text);
}
.table-floor__empty {
  position: absolute;
  inset: 0;
}
.table-floor__hint {
  flex: none;
  margin: 7px 4px 0;
  color: var(--ep-text-muted);
  font-size: 10px;
  text-align: center;
}
</style>
