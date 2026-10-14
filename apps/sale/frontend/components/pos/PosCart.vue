<script setup lang="ts">
// The check column (WORKBOOK «Vender» — «Cuenta»; the phone's drawer): the bar (park, the customer
// button in the `customer` slot, «Open checks» and its dropdown, «Close»), the heading (title and
// chips), the lines (they scroll) and the foot (always in view). It paints what the page knows of the
// check and asks for everything; the page writes (`useTill`).
import { computed, shallowRef } from 'vue';

import { useT } from '../../composables/useT';
import type { OrderLineOut, OrderOut, OrderRow, SettingsOut } from '../../operations';
import CartFooter from './CartFooter.vue';
import CartHeading from './CartHeading.vue';
import CartLines from './CartLines.vue';
import CartToolbar from './CartToolbar.vue';
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
  /** A refusal for the open-checks dropdown (a check that could not be resumed). */
  checksNotice: string | null;
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
}>();

const t = useT();
const checksOpen = shallowRef(false);

const lines = computed(() => props.order?.lines ?? []);
const hasLines = computed(() => lines.value.length > 0);
const total = computed(() => (hasLines.value ? props.total : 0));
const blockedReason = computed(() => (props.needsCustomer ? t('sale.pos.customerRequiredCharge') : null));

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
      <slot name="customer" />
    </CartToolbar>
    <OpenChecksPopover
      v-if="checksOpen"
      :current-id="order?.id ?? null"
      :parking-enabled="settings.enable_parked_tickets"
      :has-lines="hasLines"
      :notice="checksNotice"
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
      @rename="emit('rename', $event)"
      @staff="emit('staff')"
      @ask-customer="emit('askCustomer')"
    />
    <div class="pos-cart__body">
      <CartLines
        :lines="lines"
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
</style>
