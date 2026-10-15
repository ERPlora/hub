<script setup lang="ts">
// The window of a table in «Service» (WORKBOOK «Plano de sala»; TABLE-F10 to F17, F21, F28, F32).
// - Free or reserved: the reservation it holds, the customer (Customers' search) and the guests prompt —
//   or, with the room's prompt off, «Seat» with the table's capacity (the reservation's party on a
//   reserved one). Seating opens the table's check (`table.session.open`); a table another device just
//   took says so and the window stays open to pick another.
// - Blocked: why it cannot be seated.
// - Occupied: with two checks (split), which one first; then its guests, since when, who serves and its
//   customer, and Charge (to the till with its check), Transfer and Merge (the page picks the destination
//   on the plan), Split check (the lines of its check in Sales, marked), Guests, Remove table (parks it)
//   and Close table (asks first; Sales refuses a check with something ordered and the reason shows here).
// The buttons a person may not use are not shown.
import { FormModal, InlineFeedback } from '@erplora/ui/components';
import { type ApiError, useCommand } from '@erplora/ui/sdk';
import { useSession } from '@erplora/ui/shell';
import { IonButton } from '@ionic/vue';
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import { useLocale, useT } from '../composables/useT';
import { clock, minutesSince } from '../lib/format';
import { holdName, type PickMode } from '../lib/floor';
import type { SettingsOut, TableCheckOut, TableOut } from '../operations';
import GuestsPrompt from './GuestsPrompt.vue';
import SplitLines from './SplitLines.vue';

const props = defineProps<{
  table: TableOut | null;
  settings: SettingsOut;
  now: Date;
}>();

const open = defineModel<boolean>('open', { default: false });
const emit = defineEmits<{ pick: [pick: { mode: PickMode; table: TableOut; check: TableCheckOut }] }>();

type Step = 'main' | 'guests' | 'split' | 'close';

const t = useT();
const locale = useLocale();
const session = useSession();
const router = useRouter();

const step = ref<Step>('main');
const checkId = ref<string | null>(null);
const customer = ref<CustomerSnapshot | null>(null);
const choosingCustomer = ref(false);
const failure = ref('');
/** Seated, but Customers could not put the customer picked on the check (TABLE-F32). */
const warning = ref('');
const marked = ref<string[]>([]);

const seat = useCommand('table.session.open');
const setGuests = useCommand('table.session.set_guests');
const park = useCommand('table.session.park');
const close = useCommand('table.session.close');
const split = useCommand('table.session.split');
const link = useCommand('customer.order.link');
const pending = computed(() =>
  [seat, setGuests, park, close, split, link].some((command) => command.pending.value),
);

watch(
  () => [open.value, props.table?.id] as const,
  ([isOpen]) => {
    if (!isOpen) return;
    step.value = 'main';
    checkId.value = props.table && props.table.checks.length === 1 ? props.table.checks[0].id : null;
    customer.value = null;
    failure.value = '';
    warning.value = '';
    marked.value = [];
  },
  { immediate: true },
);

const canSeat = computed(() => session.can('table.add_session'));
const canChange = computed(() => session.can('table.change_session'));
const canMove = computed(() => session.can('table.transfer_session'));

const free = computed(() => props.table?.status === 'available' || props.table?.status === 'reserved');
const check = computed(() => props.table?.checks.find((row) => row.id === checkId.value) ?? null);
const title = computed(() => (props.table ? t('table.sheet.title', { number: props.table.number }) : ''));
const startGuests = computed(() => (props.table?.hold?.reserving && props.table.hold.party_size) || props.table?.capacity || 1);

const holdLine = computed(() => {
  const hold = props.table?.hold;
  if (!hold) return '';
  const parts = [holdName(hold, t('table.erasedCustomer')), clock(hold.held_from, locale.value, props.settings.timezone)];
  if (hold.party_size) parts.push(t('table.pax', { count: hold.party_size }));
  return parts.filter(Boolean).join(' · ');
});

const since = computed(() => {
  if (!check.value) return '';
  const minutes = minutesSince(check.value.opened_at, props.now) ?? 0;
  return t('table.sheet.since', { time: clock(check.value.opened_at, locale.value, props.settings.timezone), minutes });
});

/** The customer of the chosen check, as the search paints it. */
const checkCustomer = computed<CustomerSnapshot | null>(() =>
  check.value?.customer_id
    ? {
        customer_id: check.value.customer_id,
        customer_name: check.value.customer_name ?? '',
        customer_tax_id: '',
        customer_address: '',
        customer_country: '',
      }
    : null,
);

function refused(error: unknown): void {
  const apiError = error as ApiError | null;
  failure.value = apiError?.code === 'table.table_not_available' ? t('table.floor.taken') : (apiError?.message ?? t('table.sheet.error'));
}

async function attempt(work: () => Promise<unknown>, done = true): Promise<boolean> {
  failure.value = '';
  try {
    await work();
  } catch (error) {
    refused(error);
    return false;
  }
  if (done) open.value = false;
  return true;
}

async function seatWith(guests: number | null): Promise<void> {
  const table = props.table;
  if (!table) return;
  const picked = customer.value;
  failure.value = '';
  try {
    const seated = await seat.run({
      table_id: table.id,
      ...(guests === null ? {} : { guests_count: guests }),
      ...(picked ? { customer_id: picked.customer_id } : {}),
    });
    if (picked && !seated.customer_id) {
      // Seated all the same: the window stays to say the customer is not on the check.
      warning.value = t('table.sheet.customerError');
      return;
    }
  } catch (error) {
    refused(error);
    return;
  }
  open.value = false;
}

async function onCheckCustomer(next: CustomerSnapshot | null): Promise<void> {
  const orderId = check.value?.order_id;
  if (!orderId) return;
  await attempt(() => link.run({ order_id: orderId, customer_id: next?.customer_id ?? null }), false);
}

function charge(): void {
  const orderId = check.value?.order_id;
  if (!orderId) return;
  open.value = false;
  void router.push({ path: '/sale/pos', query: { order: orderId } });
}

function pick(mode: PickMode): void {
  if (!props.table || !check.value) return;
  emit('pick', { mode, table: props.table, check: check.value });
  open.value = false;
}

function saveGuests(guests: number): void {
  const id = check.value?.id;
  if (!id) return;
  void attempt(() => setGuests.run({ id, guests_count: guests }));
}

function parkCheck(): void {
  const id = check.value?.id;
  if (id) void attempt(() => park.run({ id }));
}

function closeCheck(): void {
  const current = check.value;
  if (current) void attempt(() => close.run({ id: current.id, order_id: current.order_id }));
}

// The lines of the check in Sales, read only while splitting.
const orderId = computed(() => check.value?.order_id ?? '');
const splitting = computed(() => step.value === 'split' && !!check.value?.order_id);

function toggle(lineId: string): void {
  marked.value = marked.value.includes(lineId) ? marked.value.filter((id) => id !== lineId) : [...marked.value, lineId];
}

function splitCheck(): void {
  const id = check.value?.id;
  if (id) void attempt(() => split.run({ id, line_ids: marked.value }));
}
</script>

<template>
  <FormModal
    v-model:open="open"
    testid="table-sheet"
    :title="title"
    :pending="pending"
  >
    <template v-if="table">
      <InlineFeedback
        v-if="failure"
        tone="danger"
        data-testid="table-sheet-error"
      >
        {{ failure }}
      </InlineFeedback>
      <InlineFeedback
        v-if="warning"
        tone="warning"
        data-testid="table-sheet-warning"
      >
        {{ warning }}
      </InlineFeedback>

      <!-- Free or reserved: seat a party -->
      <template v-if="free && canSeat">
        <p
          v-if="holdLine"
          class="table-sheet__hold"
          data-testid="table-sheet-hold"
        >
          {{ $t('table.sheet.reservation') }}: {{ holdLine }}
        </p>
        <div class="table-sheet__customer">
          <span>{{ $t('table.sheet.customer') }}</span>
          <CustomerSearch
            v-model="customer"
            v-model:open="choosingCustomer"
          />
        </div>
        <GuestsPrompt
          v-if="settings.prompt_guests_on_seat"
          :number="table.number"
          :capacity="table.capacity"
          :initial="startGuests"
          :pending="pending"
          @confirm="seatWith"
          @back="open = false"
        />
        <ion-button
          v-else
          expand="block"
          data-testid="table-sheet-seat"
          :disabled="pending"
          @click="seatWith(null)"
        >
          {{ $t('table.sheet.seatNow') }}
        </ion-button>
      </template>

      <!-- Blocked -->
      <InlineFeedback
        v-else-if="table.status === 'blocked'"
        tone="warning"
        data-testid="table-sheet-blocked"
      >
        {{ $t('table.sheet.blocked') }}
      </InlineFeedback>

      <!-- Occupied -->
      <template v-else-if="table.status === 'occupied'">
        <div
          v-if="!check"
          class="table-sheet__checks"
        >
          <p>{{ $t('table.sheet.chooseCheck') }}</p>
          <ion-button
            v-for="(row, index) in table.checks"
            :key="row.id"
            expand="block"
            fill="outline"
            :data-testid="`table-sheet-check-${row.id}`"
            @click="checkId = row.id"
          >
            {{ $t('table.sheet.check', { n: index + 1 }) }} · {{ $t('table.pax', { count: row.guests_count }) }}{{ row.customer_name ? ` · ${row.customer_name}` : '' }}
          </ion-button>
        </div>
        <template v-else-if="step === 'main'">
          <div
            class="table-sheet__summary"
            data-testid="table-sheet-summary"
          >
            <p>{{ $t('table.guestsCount', { count: check.guests_count }) }} · {{ since }}</p>
            <p v-if="check.waiter_name">
              {{ $t('table.servedBy', { name: check.waiter_name }) }}
            </p>
          </div>
          <div
            v-if="check.order_id && canChange"
            class="table-sheet__customer"
          >
            <span>{{ $t('table.sheet.customer') }}</span>
            <CustomerSearch
              v-model:open="choosingCustomer"
              :model-value="checkCustomer"
              @update:model-value="onCheckCustomer"
            />
          </div>
          <div
            class="table-sheet__actions"
            role="group"
            :aria-label="$t('table.sheet.actions.label')"
          >
            <ion-button
              v-if="check.order_id"
              data-testid="table-sheet-action-charge"
              @click="charge"
            >
              {{ $t('table.sheet.actions.charge') }}
            </ion-button>
            <ion-button
              v-if="canMove"
              fill="outline"
              data-testid="table-sheet-action-transfer"
              @click="pick('transfer')"
            >
              {{ $t('table.sheet.actions.transfer') }}
            </ion-button>
            <ion-button
              v-if="canMove"
              fill="outline"
              data-testid="table-sheet-action-merge"
              @click="pick('merge')"
            >
              {{ $t('table.sheet.actions.merge') }}
            </ion-button>
            <template v-if="canChange">
              <ion-button
                fill="outline"
                data-testid="table-sheet-action-split"
                @click="step = 'split'"
              >
                {{ $t('table.sheet.actions.split') }}
              </ion-button>
              <ion-button
                fill="outline"
                data-testid="table-sheet-action-guests"
                @click="step = 'guests'"
              >
                {{ $t('table.sheet.actions.guests') }}
              </ion-button>
              <ion-button
                fill="outline"
                data-testid="table-sheet-action-park"
                :disabled="pending"
                @click="parkCheck"
              >
                {{ $t('table.sheet.actions.park') }}
              </ion-button>
              <ion-button
                fill="outline"
                color="danger"
                data-testid="table-sheet-action-close"
                @click="step = 'close'"
              >
                {{ $t('table.sheet.actions.close') }}
              </ion-button>
            </template>
          </div>
        </template>
        <GuestsPrompt
          v-else-if="step === 'guests'"
          mode="edit"
          :number="table.number"
          :capacity="table.capacity"
          :initial="check.guests_count"
          :pending="pending"
          @confirm="saveGuests"
          @back="step = 'main'"
        />
        <div
          v-else-if="step === 'close'"
          class="table-sheet__close"
        >
          <p data-testid="table-sheet-close-impact">
            {{ $t('table.sessions.close.impact', { number: table.number, count: check.guests_count }) }}
          </p>
          <div class="table-sheet__row">
            <ion-button
              fill="clear"
              @click="step = 'main'"
            >
              {{ $t('table.back') }}
            </ion-button>
            <ion-button
              color="danger"
              data-testid="table-sheet-close-confirm"
              :disabled="pending"
              @click="closeCheck"
            >
              {{ $t('table.sessions.close.confirm') }}
            </ion-button>
          </div>
        </div>
        <SplitLines
          v-else-if="splitting"
          :order-id="orderId"
          :marked="marked"
          :pending="pending"
          @toggle="toggle"
          @confirm="splitCheck"
          @back="step = 'main'"
        />
      </template>
    </template>
    <template #footer="{ cancel }">
      <ion-button
        fill="clear"
        data-testid="table-sheet-done"
        @click="cancel"
      >
        {{ $t('table.close') }}
      </ion-button>
    </template>
  </FormModal>
</template>

<style scoped>
.table-sheet__hold {
  margin: 0 0 0.6rem;
  font-weight: 600;
  color: var(--ion-color-warning-shade, #b06c00);
}
.table-sheet__customer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
  margin-bottom: 0.6rem;
}
.table-sheet__summary p {
  margin: 0 0 0.3rem;
}
.table-sheet__actions {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(9rem, 1fr));
  gap: 0.5rem;
  margin-top: 0.6rem;
}
.table-sheet__actions ion-button,
.table-sheet__checks ion-button {
  min-height: 44px;
  margin: 0;
}
.table-sheet__row {
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
</style>
