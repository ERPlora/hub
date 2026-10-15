<script setup lang="ts">
// «Choose table» (SALE-F19; Tables' TABLE-F10, F12, F13), the product's table sheet of the till: the
// tables in service, searched on the server (its zone tabs became the search: each tile names its zone,
// as numbers repeat across zones), as tiles in their status colour — available green, occupied red,
// reserved amber, blocked grey — with the number, the zone, the seats, the status and the reservation's
// name and time. Only a free or reserved table can be tapped. A tap seats the check on screen there
// (`table.session.open` with its `order_id`, TABLE-F12); with no check yet, Tables opens one titled
// with the table (TABLE-F10) and the page puts it on the till; a check whose table was taken away is
// seated again (`table.session.restore`, TABLE-F24). The guests are not asked: the server takes the
// reservation's or the table's seats. «Remove from table» parks the check's seat (TABLE-F13): the table
// frees, the check stays open. A refusal stays in the sheet in the server's words.
// Sales does not require Tables: it talks to it only through operation names. The page mounts this only
// while someone is choosing, so nothing of Tables is followed otherwise.
import { InlineFeedback } from '@erplora/ui/components';
import { type OutputOf, useCommand, useLive } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton, IonSearchbar } from '@ionic/vue';
import { computed, shallowRef } from 'vue';

import { useLocale, useT } from '../../composables/useT';
import { refusal } from '../../lib/refusal';
import PosSheet from './PosSheet.vue';
import { shortTime } from './till';

type TableRow = OutputOf<'table.table.list'>['rows'][number];
type TableCheck = OutputOf<'table.session.by_order'>['rows'][number];
type Seated = OutputOf<'table.session.open'>;

const props = defineProps<{
  /** The check on screen; `null` before its first line (Tables then opens one). */
  orderId: string | null;
  /** The check's open table check with a table, if it has one. */
  seat: TableCheck | null;
  /** The check's parked table check (its table taken away), if it has one. */
  parked: TableCheck | null;
}>();
const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ seated: [check: Seated] }>();

const t = useT();
const locale = useLocale();
const session = useSession();

const term = shallowRef('');
const list = useLive('table.table.list', () => ({
  search: term.value,
  in_service: true,
  sort: 'number',
  limit: 40,
  offset: 0,
}));
const floor = useLive('table.floor.status', {});

const rows = computed(() => list.data.value?.rows ?? []);
const unset = computed(() => floor.data.value?.usable_tables === 0);
const loading = computed(() => !list.data.value || (list.status.value === 'loading' && !rows.value.length));
const empty = computed(() => (term.value ? t('sale.pos.table.noResults') : t('sale.pos.table.none')));
const canRemove = computed(() => !!props.seat && session.can('table.change_session'));

const open_ = useCommand('table.session.open');
const restore = useCommand('table.session.restore');
const park = useCommand('table.session.park');
const pending = shallowRef(false);
const failure = shallowRef<string | null>(null);

function onInput(event: CustomEvent<{ value?: string | null }>): void {
  term.value = (event.detail.value ?? '').trim();
}

const tappable = (row: TableRow) => row.status === 'available' || row.status === 'reserved';
const isCurrent = (row: TableRow) => props.seat?.table_id === row.id;

/** Whose reservation the table paints: its name, or «Deleted customer» once her data was erased. */
function holder(row: TableRow): string {
  if (!row.hold) return '';
  return row.hold.label || (row.hold.erased ? t('sale.pos.table.erasedCustomer') : '');
}

function holdTime(row: TableRow): string {
  return row.hold?.held_from ? shortTime(row.hold.held_from, locale.value) : '';
}

/** Why a table cannot be tapped, or the reservation in full («Marta (4) · 21:00»). */
function titleOf(row: TableRow): string | undefined {
  if (isCurrent(row)) return t('sale.pos.table.currentHint');
  if (row.status === 'occupied') return t('sale.pos.table.occupiedHint');
  if (row.status === 'blocked') return t('sale.pos.table.blockedHint');
  const name = holder(row);
  if (!name) return undefined;
  const party = row.hold?.party_size ? ` (${row.hold.party_size})` : '';
  const time = holdTime(row);
  return `${name}${party}${time ? ` · ${time}` : ''}`;
}

/** Runs a write of the sheet: closes it when it went, keeps it open with the refusal when not. */
async function write(run: () => Promise<unknown>, fallbackKey: string): Promise<void> {
  if (pending.value) return;
  failure.value = null;
  pending.value = true;
  try {
    await run();
    open.value = false;
  } catch (error) {
    const fallback = t(fallbackKey);
    failure.value = refusal(error, fallback)?.message ?? fallback;
  } finally {
    pending.value = false;
  }
}

function seatAt(row: TableRow): void {
  if (!tappable(row)) return;
  void write(async () => {
    const seated = props.parked
      ? await restore.run({ id: props.parked.id, table_id: row.id })
      : await open_.run(props.orderId ? { table_id: row.id, order_id: props.orderId } : { table_id: row.id });
    emit('seated', seated);
  }, 'sale.pos.table.seatFailed');
}

function remove(): void {
  const seat = props.seat;
  if (!seat) return;
  void write(() => park.run({ id: seat.id }), 'sale.pos.table.removeFailed');
}
</script>

<template>
  <PosSheet
    v-model:open="open"
    :title="$t('sale.pos.table.choose')"
    testid="pos-table"
    wide
  >
    <p
      v-if="unset"
      class="pos-sheet-hint"
      data-testid="pos-table-unset"
    >
      {{ $t('sale.pos.table.unset') }}
    </p>
    <template v-else>
      <ion-searchbar
        :placeholder="$t('sale.pos.table.search')"
        :debounce="250"
        :maxlength="100"
        @ion-input="onInput"
      />
      <InlineFeedback
        v-if="list.error.value"
        tone="danger"
        data-testid="pos-table-load-error"
      >
        {{ $t('sale.pos.table.loadFailed') }}
        <template #actions>
          <ion-button
            size="small"
            fill="outline"
            data-testid="pos-table-retry"
            @click="list.refresh()"
          >
            {{ $t('sale.live.retry') }}
          </ion-button>
        </template>
      </InlineFeedback>
      <p
        v-else-if="loading"
        class="pos-sheet-hint"
        data-testid="pos-table-loading"
      >
        {{ $t('sale.pos.table.loading') }}
      </p>
      <p
        v-else-if="!rows.length"
        class="pos-sheet-hint"
        data-testid="pos-table-empty"
      >
        {{ empty }}
      </p>
      <div
        v-else
        class="pos-table-grid"
      >
        <button
          v-for="row in rows"
          :key="row.id"
          type="button"
          class="pos-table-tile"
          :class="`pos-table-tile--${row.status}`"
          :data-testid="`pos-table-tile-${row.id}`"
          :disabled="!tappable(row) || pending"
          :aria-pressed="isCurrent(row) ? 'true' : 'false'"
          :title="titleOf(row)"
          @click="seatAt(row)"
        >
          <span class="pos-table-tile__number">{{ row.number }}</span>
          <span
            v-if="row.zone_name"
            class="pos-table-tile__zone"
          >{{ row.zone_name }}</span>
          <span class="pos-table-tile__pax">{{ $t('sale.pos.table.pax', { count: row.capacity }) }}</span>
          <span class="pos-table-tile__status">{{ $t(`sale.pos.table.status.${row.status}`) }}</span>
          <span
            v-if="holder(row)"
            class="pos-table-tile__hold"
          >
            <span class="pos-table-tile__holder">{{ holder(row) }}</span>
            <span
              v-if="holdTime(row)"
              class="pos-table-tile__time"
            >{{ holdTime(row) }}</span>
          </span>
        </button>
      </div>
    </template>
    <template
      v-if="canRemove || failure"
      #foot
    >
      <div class="pos-sheet-foot">
        <p
          v-if="failure"
          class="pos-sheet-error"
          role="alert"
          data-testid="pos-table-error"
        >
          {{ failure }}
        </p>
        <ion-button
          v-if="canRemove"
          fill="clear"
          color="danger"
          class="pos-table-remove"
          data-testid="pos-table-remove"
          :disabled="pending"
          @click="remove"
        >
          {{ $t('sale.pos.table.remove') }}
        </ion-button>
      </div>
    </template>
  </PosSheet>
</template>

<style>
/* Not scoped: Ionic moves the sheet to ion-app. Every rule hangs from `ion-modal.pos-sheet`. */
ion-modal.pos-sheet .pos-table-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(5rem, 1fr));
  gap: 0.6rem;
  margin-top: 0.6rem;
}
ion-modal.pos-sheet .pos-table-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.1rem;
  min-width: 0;
  min-height: 44px;
  padding: 0.6rem 0.25rem;
  font: inherit;
  text-align: center;
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-background-color, #fff);
  border: 2px solid var(--pos-table-tone);
  border-radius: 12px;
  cursor: pointer;
  container-type: inline-size;
  transition: transform 0.05s;
  --pos-table-tone: var(--ion-color-medium, #868e96);
}
ion-modal.pos-sheet .pos-table-tile:active {
  transform: scale(0.96);
}
ion-modal.pos-sheet .pos-table-tile[disabled] {
  opacity: 0.35;
  cursor: not-allowed;
}
ion-modal.pos-sheet .pos-table-tile[aria-pressed='true'] {
  opacity: 1;
  outline: 3px solid var(--ion-color-primary, #0091ce);
  outline-offset: 1px;
}
ion-modal.pos-sheet .pos-table-tile--available {
  --pos-table-tone: var(--ion-color-success, #2f9e44);
}
ion-modal.pos-sheet .pos-table-tile--occupied {
  --pos-table-tone: var(--ion-color-danger, #d9480f);
}
ion-modal.pos-sheet .pos-table-tile--reserved {
  --pos-table-tone: var(--ion-color-warning, #f08c00);
}
ion-modal.pos-sheet .pos-table-tile__number,
ion-modal.pos-sheet .pos-table-tile__zone,
ion-modal.pos-sheet .pos-table-tile__pax {
  max-width: 100%;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
ion-modal.pos-sheet .pos-table-tile__number {
  font-size: 1.05rem;
  font-weight: 700;
}
ion-modal.pos-sheet .pos-table-tile__zone,
ion-modal.pos-sheet .pos-table-tile__pax {
  font-size: 0.75rem;
  color: var(--ion-color-medium, #8b897f);
}
/* The status on one line: the word scales with the tile, the ellipsis only for a longer language. */
ion-modal.pos-sheet .pos-table-tile__status {
  max-width: 100%;
  overflow: hidden;
  font-size: min(0.65rem, 15cqi);
  font-weight: 600;
  color: var(--pos-table-tone);
  text-transform: uppercase;
  white-space: nowrap;
  text-overflow: ellipsis;
}
/* The reservation: the name shrinks with an ellipsis, the time never does. */
ion-modal.pos-sheet .pos-table-tile__hold {
  display: flex;
  justify-content: center;
  gap: 0.2em;
  max-width: 100%;
  min-width: 0;
  font-size: 0.65rem;
  font-weight: 600;
  color: var(--ion-color-warning, #f08c00);
  white-space: nowrap;
}
ion-modal.pos-sheet .pos-table-tile__holder {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
ion-modal.pos-sheet .pos-table-tile__time {
  flex: none;
}
ion-modal.pos-sheet .pos-table-tile__time::before {
  content: '· ';
}
ion-modal.pos-sheet .pos-table-remove {
  align-self: flex-start;
  font-weight: 700;
  text-transform: none;
}
</style>
