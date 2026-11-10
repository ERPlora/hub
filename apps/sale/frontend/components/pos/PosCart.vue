<script setup lang="ts">
// The check column (WORKBOOK «Vender» — «Cuenta»; the phone's drawer): the bar (park, Tables' button in
// the `table` slot and the customer's in the `customer` slot, «Open checks» and its dropdown, «Close»),
// the heading (title and chips), the lines (they scroll; in the phone's drawer the heading scrolls with them, hub#630)
// and the foot (always in view). It paints what
// the page knows of the check and asks for everything; the page writes (`useTill`). With Kitchen (SALE-F20,
// `kitchen`), the tabs «Check» and «Current order»: the second one shows only what is pending and says how many
// items wait (also to a screen reader); while something waits, both carry the send bar above the foot, so the tab a
// check opens on offers it too (hub#1017); a send goes up (`send`, with its rush). With
// the right to see Kitchen's tickets (`kitchenTickets`), «Tickets · N» rides beside the head of what was sent
// (KITCHEN-F19, F20). Android's Back closes the open dropdown.
import { IonLabel, IonSegment, IonSegmentButton } from '@ionic/vue';
import { computed, shallowRef, watch } from 'vue';

import { useSystemBack } from '../../composables/pos/useSystemBack';
import { useT } from '../../composables/useT';
import type { OrderLineOut, OrderOut, OrderRow, SettingsOut } from '../../operations';
import CartFooter from './CartFooter.vue';
import CartHeading from './CartHeading.vue';
import CartLines from './CartLines.vue';
import CartToolbar from './CartToolbar.vue';
import KitchenSendBar from './KitchenSendBar.vue';
import KitchenTickets from './KitchenTickets.vue';
import OpenChecksPopover from './OpenChecksPopover.vue';

const props = defineProps<{
  order: OrderOut | null;
  /** The check's title, or the one typed before it exists. */
  label: string;
  /** The preview's total; `undefined` while it is on its way. */
  total: number | undefined;
  /** Why the server could not value the check; `null` when its preview is valid or pending. */
  previewError?: string | null;
  ticketDiscount: number;
  marks: readonly string[];
  staffNames: Readonly<Record<string, string>>;
  settings: SettingsOut;
  customerName: string | null;
  staffId: string | null;
  staffName: string | null;
  needsCustomer: boolean;
  busy: boolean;
  /** The cart is the phone's drawer. */
  drawer: boolean;
  /** Open checks besides this one. */
  openChecks: number;
  /** The number of the check's table (SALE-F19); `null` at none or without Tables. */
  tableNumber?: string | null;
  /** Kitchen on and the right to send to it (SALE-F20): the tabs «Check» and «Current order». */
  kitchen?: boolean;
  /** Kitchen on and the right to see its tickets (KITCHEN-F19): «Tickets · N» beside what was sent. */
  kitchenTickets?: boolean;
}>();
const emit = defineEmits<{
  park: [];
  close: [];
  rename: [label: string];
  staff: [];
  askCustomer: [];
  mark: [line: OrderLineOut];
  quantity: [line: OrderLineOut, quantity: string];
  lineDiscount: [line: OrderLineOut];
  note: [line: OrderLineOut];
  gift: [line: OrderLineOut];
  lineStaff: [line: OrderLineOut];
  voidLine: [line: OrderLineOut];
  ticketDiscount: [];
  prebill: [];
  charge: [];
  resume: [row: OrderRow];
  send: [rush: boolean];
}>();

const t = useT();
const checksOpen = shallowRef(false);
useSystemBack(checksOpen, () => (checksOpen.value = false));

const lines = computed(() => props.order?.lines ?? []);
const hasLines = computed(() => lines.value.length > 0);
const total = computed(() => (hasLines.value ? props.total : 0));
const blockedReason = computed(() => (props.needsCustomer ? t('sale.pos.customerRequiredCharge') : null));

// ── «Check» and «Current order» (SALE-F20) ──
const tab = shallowRef<'check' | 'round'>('check');
/** Another check on screen starts on «Check»; the first line opening this one keeps the tab chosen. */
watch(
  () => props.order?.id,
  (_id, before) => {
    if (before) tab.value = 'check';
  },
);
/** What the next round sends: the lines not sent yet; a service never goes to the kitchen. */
const pending = computed(() => lines.value.filter((line) => !line.fired_at && !line.is_service));
const roundMode = computed(() => !!props.kitchen && tab.value === 'round');
const shownLines = computed(() => (roundMode.value ? pending.value : lines.value));
const roundLabel = computed(() => {
  const count = pending.value.length;
  if (!count) return t('sale.pos.kitchen.roundTab');
  return count === 1 ? t('sale.pos.kitchen.roundTabPendingOne') : t('sale.pos.kitchen.roundTabPending', { count });
});

function onTabChange(event: CustomEvent<{ value?: string | number }>): void {
  const next = String(event.detail.value ?? '');
  if (next === 'check' || next === 'round') tab.value = next;
}

function resume(row: OrderRow): void {
  checksOpen.value = false;
  emit('resume', row);
}

function park(): void {
  checksOpen.value = false;
  emit('park');
}
</script>

<template>
  <aside
    id="pos-cart-drawer"
    class="pos-cart"
    :class="{ 'pos-cart--drawer': drawer }"
    data-testid="pos-cart"
  >
    <CartToolbar
      :parking-enabled="settings.enable_parked_tickets"
      :has-lines="hasLines"
      :open-checks="openChecks"
      :checks-open="checksOpen"
      :drawer="drawer"
      @park="park"
      @toggle-checks="checksOpen = !checksOpen"
      @close="emit('close')"
    >
      <slot name="table" />
      <slot name="customer" />
    </CartToolbar>
    <OpenChecksPopover
      v-if="checksOpen"
      :current-id="order?.id ?? null"
      :parking-enabled="settings.enable_parked_tickets"
      :has-lines="hasLines"
      @resume="resume"
      @park="park"
      @close="checksOpen = false"
    />
    <!-- What sits between the bar and the foot. The side column keeps its heading and scrolls the lines; the phone's
         drawer, and a column too low for a whole line beside them (hub#820), scroll it all as one, so «Charge» stays in
         view above the tab bar (hub#630). The
         send bar rides here too: outside, it took all of this when low, tabs and lines included (hub#787). -->
    <div class="pos-cart__scroll">
      <CartHeading
        :label="label"
        :customer-name="customerName"
        :staff-id="staffId"
        :staff-name="staffName"
        :needs-customer="needsCustomer"
        :table-number="tableNumber ?? null"
        @rename="emit('rename', $event)"
        @staff="emit('staff')"
        @ask-customer="emit('askCustomer')"
      />
      <ion-segment
        v-if="kitchen"
        class="pos-cart__tabs"
        :value="tab"
        data-testid="pos-cart-tabs"
        @ion-change="onTabChange"
      >
        <ion-segment-button
          value="check"
          class="pos-cart__tab"
          :aria-selected="tab === 'check' ? 'true' : 'false'"
          data-testid="pos-cart-tab-check"
        >
          <ion-label>{{ t('sale.pos.kitchen.accountTab') }}</ion-label>
        </ion-segment-button>
        <ion-segment-button
          value="round"
          class="pos-cart__tab"
          :aria-selected="tab === 'round' ? 'true' : 'false'"
          :aria-label="roundLabel"
          data-testid="pos-cart-tab-round"
        >
          <ion-label>{{ t('sale.pos.kitchen.roundTab') }}</ion-label>
          <span
            v-if="pending.length"
            class="pos-cart__badge"
            aria-hidden="true"
            data-testid="pos-cart-tab-round-badge"
          >{{ pending.length }}</span>
        </ion-segment-button>
      </ion-segment>
      <div class="pos-cart__body">
        <p
          v-if="roundMode && pending.length"
          class="pos-cart__hint"
          data-testid="pos-cart-round-hint"
        >
          {{ t('sale.pos.kitchen.roundHint') }}
        </p>
        <div
          v-if="roundMode && !pending.length"
          class="pos-cart__all-sent"
          role="status"
          data-testid="pos-cart-round-empty"
        >
          <strong>{{ t('sale.pos.kitchen.allSent') }}</strong>
          <span>{{ t('sale.pos.kitchen.allSentHint') }}</span>
        </div>
        <CartLines
          v-else
          :lines="shownLines"
          :marks="marks"
          :staff-names="staffNames"
          :allow-discounts="settings.allow_discounts"
          :busy="busy"
          @mark="emit('mark', $event)"
          @quantity="(line, quantity) => emit('quantity', line, quantity)"
          @discount="emit('lineDiscount', $event)"
          @note="emit('note', $event)"
          @gift="emit('gift', $event)"
          @staff="emit('lineStaff', $event)"
          @void="emit('voidLine', $event)"
        >
          <template
            v-if="kitchenTickets && order"
            #sent
          >
            <KitchenTickets :order-id="order.id" />
          </template>
        </CartLines>
      </div>
      <KitchenSendBar
        v-if="kitchen && pending.length"
        :pending="pending.length"
        :busy="busy"
        @send="emit('send', $event)"
      />
    </div>
    <CartFooter
      :has-lines="hasLines"
      :total="total"
      :preview-error="previewError"
      :discount-percent="order?.discount_percent ?? '0'"
      :discount-amount="order?.discount_amount ?? 0"
      :ticket-discount="ticketDiscount"
      :allow-discounts="settings.allow_discounts"
      :blocked-reason="blockedReason"
      @discount="emit('ticketDiscount')"
      @prebill="emit('prebill')"
      @charge="emit('charge')"
    />
  </aside>
</template>

<style scoped>
.pos-cart {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: var(--ion-card-background);
  border-left: 1px solid var(--ep-border);
}
/* A scroll container: its automatic minimum height is 0, so it gives way to the bar and the foot. It is also what the
   send bar measures to know whether it can stay pinned (KitchenSendBar, hub#787). */
.pos-cart__scroll {
  display: flex;
  flex: 1;
  flex-direction: column;
  overflow-y: auto;
  container: pos-cart-middle / size;
}
.pos-cart__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
/* The phone's drawer: one scroll for the heading, the tabs and the lines, so the bar and the foot always fit. */
.pos-cart--drawer .pos-cart__body {
  flex: 1 0 auto;
  overflow: visible;
}
/* A side column too low for a whole line beside the heading (83 px), the tabs (64 with their words in two lines, and
   their 8 px of margin) and the send bar (67): the same, or the lines get a slit, 0 px under the red strip of a small
   tablet (hub#787) and 14 to 105 px on a tablet on its side or a laptop of 720 or 768 (hub#820). Measured: a line is
   115 px, so 21rem is the most that still leaves it whole (337 px leave 115); the lowest column where it fits, 343 px,
   keeps its heading and tabs in place. The send bar stays pinned down to 13rem (KitchenSendBar). */
@container pos-cart-middle (max-height: 21rem) {
  .pos-cart__body {
    flex: 1 0 auto;
    overflow: visible;
  }
}
.pos-cart__tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem;
  margin: 0 0.75rem 0.5rem;
  padding: 0.25rem;
  background: var(--ep-surface-muted);
  border-radius: 12px;
}
.pos-cart__tab {
  min-width: 0;
  min-height: 2.5rem;
  font-weight: 600;
  text-transform: none;
  --background: transparent;
  --background-checked: var(--ion-card-background);
  --color: var(--ion-color-medium-shade);
  --color-checked: var(--ep-primary-text);
  --border-radius: 9px;
  --indicator-color: transparent;
  --indicator-box-shadow: var(--ep-shadow-xs);
  --padding-start: 0.5rem;
  --padding-end: 0.5rem;
}
.pos-cart__badge {
  min-width: 1.35rem;
  padding: 0 0.35rem;
  font-size: 0.75rem;
  line-height: 1.35rem;
  color: var(--ion-color-primary-contrast, #fff);
  background: var(--ion-color-primary, #0091ce);
  border-radius: 999px;
}
.pos-cart__hint {
  margin: 0.25rem 0.75rem 0.5rem;
  font-size: 0.8125rem;
  color: var(--ion-color-medium-shade, #636469);
}
.pos-cart__all-sent {
  display: grid;
  gap: 0.35rem;
  padding: 2.5rem 1rem;
  text-align: center;
  color: var(--ion-color-medium-shade, #636469);
}
/* A phone on its side: «All sent» reads over the foot instead of being cut by it (hub#800). */
@media (max-height: 500px) {
  .pos-cart__all-sent {
    padding: 0.5rem 1rem;
  }
}
</style>
