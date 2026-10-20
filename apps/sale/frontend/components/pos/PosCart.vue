<script setup lang="ts">
// The check column (WORKBOOK «Vender» — «Cuenta»; the phone's drawer): the bar (park, Tables' button in
// the `table` slot and the customer's in the `customer` slot, «Open checks» and its dropdown, «Close»),
// the heading (title and chips), the lines (they scroll) and the foot (always in view). It paints what
// the page knows of the check and asks for everything; the page writes (`useTill`). With Kitchen (SALE-F20,
// `kitchen`), the tabs «Check» and «Current order»: the second one shows only what is pending, says how many
// items wait (also to a screen reader) and carries the send bar; a send goes up (`send`, with its rush).
import { computed, shallowRef, watch } from 'vue';

import { useT } from '../../composables/useT';
import type { OrderLineOut, OrderOut, OrderRow, SettingsOut } from '../../operations';
import CartFooter from './CartFooter.vue';
import CartHeading from './CartHeading.vue';
import CartLines from './CartLines.vue';
import CartToolbar from './CartToolbar.vue';
import KitchenSendBar from './KitchenSendBar.vue';
import OpenChecksPopover from './OpenChecksPopover.vue';

const props = defineProps<{
  order: OrderOut | null;
  /** The check's title, or the one typed before it exists. */
  label: string;
  /** The preview's total; `undefined` while it is on its way. */
  total: number | undefined;
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

const lines = computed(() => props.order?.lines ?? []);
const hasLines = computed(() => lines.value.length > 0);
const total = computed(() => (hasLines.value ? props.total : 0));
const blockedReason = computed(() => (props.needsCustomer ? t('sale.pos.customerRequiredCharge') : null));

// ── «Check» and «Current order» (SALE-F20) ──
const tab = shallowRef<'check' | 'round'>('check');
/** Another check on screen starts on «Check». */
watch(
  () => props.order?.id,
  () => (tab.value = 'check'),
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
    <div
      v-if="kitchen"
      class="pos-cart__tabs"
      role="tablist"
      data-testid="pos-cart-tabs"
    >
      <button
        type="button"
        role="tab"
        class="pos-cart__tab"
        :aria-selected="tab === 'check' ? 'true' : 'false'"
        data-testid="pos-cart-tab-check"
        @click="tab = 'check'"
      >
        {{ t('sale.pos.kitchen.accountTab') }}
      </button>
      <button
        type="button"
        role="tab"
        class="pos-cart__tab"
        :aria-selected="tab === 'round' ? 'true' : 'false'"
        :aria-label="roundLabel"
        data-testid="pos-cart-tab-round"
        @click="tab = 'round'"
      >
        {{ t('sale.pos.kitchen.roundTab') }}
        <span
          v-if="pending.length"
          class="pos-cart__badge"
          aria-hidden="true"
          data-testid="pos-cart-tab-round-badge"
        >{{ pending.length }}</span>
      </button>
    </div>
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
      />
    </div>
    <KitchenSendBar
      v-if="roundMode && pending.length"
      :pending="pending.length"
      :busy="busy"
      @send="emit('send', $event)"
    />
    <CartFooter
      :has-lines="hasLines"
      :total="total"
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
  background: var(--ion-background-color, #fff);
  border-left: 1px solid var(--ion-border-color, #e6e3db);
}
.pos-cart__body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}
.pos-cart__tabs {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.25rem;
  margin: 0 0.75rem 0.5rem;
  padding: 0.25rem;
  background: var(--ion-color-light, #f4f3ef);
  border-radius: 12px;
}
.pos-cart__tab {
  display: inline-flex;
  min-width: 0;
  min-height: 2.5rem;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  padding: 0.25rem 0.5rem;
  font: inherit;
  font-weight: 600;
  color: var(--ion-color-medium-shade, #636469);
  background: transparent;
  border: 0;
  border-radius: 9px;
  cursor: pointer;
}
.pos-cart__tab[aria-selected='true'] {
  color: var(--ion-text-color, #1c1b18);
  background: var(--ion-background-color, #fff);
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.08);
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
</style>
