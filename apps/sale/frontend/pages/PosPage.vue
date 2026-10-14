<script setup lang="ts">
// Sales & POS → Sell (WORKBOOK «Vender»; SALE-F01, F05, F09, F13–F18, F20–F22). The till: the catalogue
// and the check side by side (23–24.5rem on a desktop); on a phone (narrower than 821px or 500px tall or
// less) the check is a drawer from the right that the cart button opens. The page wires the pieces:
// the till settings, the check and its writes (`useTill`), the live check and its preview (mounted
// only while there is one), the customer (the Customers app's search; linked to the check by
// `customer.order.link`, read back on resuming), who serves, the sheets, the pre-bill, the checkout
// sheet and the sale's document after a whole charge. Nothing about money is decided here.
import { InlineFeedback } from '@erplora/ui/components';
import { useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toast, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue';

import CustomerSearch, { type CustomerSnapshot } from '../../../customer/frontend/components/CustomerSearch.vue';
import CheckoutSheet from '../components/checkout/CheckoutSheet.vue';
import DocumentModal from '../components/document/DocumentModal.vue';
import CartFab from '../components/pos/CartFab.vue';
import CheckFollower from '../components/pos/CheckFollower.vue';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import DiscountSheet from '../components/pos/DiscountSheet.vue';
import LineNoteSheet from '../components/pos/LineNoteSheet.vue';
import OpenPriceSheet from '../components/pos/OpenPriceSheet.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import PrebillModal from '../components/pos/PrebillModal.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import { customerSnapshot, refusal, shortTime } from '../components/pos/till';
import VoidLineSheet from '../components/pos/VoidLineSheet.vue';
import { type OpenLine, useTill, type WriteResult } from '../composables/pos/useTill';
import { useLocale, useT } from '../composables/useT';
import type { OrderLineOut, OrderOut, OrderRow, PreviewOut, SaleOut } from '../operations';
import { saleTabs } from '../tabs';

const t = useT();
const locale = useLocale();
const session = useSession();

// ── The till settings: nothing is shown until they are read ─────────────────────────────────────
const settingsLive = useLive('sale.pos_settings.get', {});
const settings = computed(() => settingsLive.data.value);
const loadError = computed(() => {
  const error = settingsLive.error.value;
  if (!error || settings.value) return null;
  if (error.code === 'app_inactive') return t('sale.live.appInactive');
  if (error.code === 'permission_denied') return t('sale.live.noPermission');
  return t('sale.pos.loadFailed');
});

// ── The check ────────────────────────────────────────────────────────────────────────────────────
const customer = shallowRef<CustomerSnapshot | null>(null);
const choosingCustomer = shallowRef(false);
const staff = shallowRef<{ id: string | null; name: string | null }>({ id: null, name: null });
const staffNames = shallowRef<Record<string, string>>({});
const marks = shallowRef<string[]>([]);
const preview = shallowRef<PreviewOut | undefined>();
const charging = shallowRef(false);

const till = useTill({ settings: () => settings.value, onOpened: (id) => customer.value && void linkCustomer(id, customer.value) });
const order = computed(() => till.order.value);
const lines = computed(() => order.value?.lines ?? []);

const openChecksLive = useLive('sale.order.list', { status: 'open' as const, limit: 1, offset: 0 });
const openChecks = computed(() => Math.max(0, (openChecksLive.data.value?.total ?? 0) - (till.orderId.value ? 1 : 0)));

watch(
  () => till.orderId.value,
  () => (preview.value = undefined),
);
watch(lines, (now) => {
  const ids = new Set(now.map((line) => line.id));
  marks.value = now.length < 2 ? [] : marks.value.filter((id) => ids.has(id));
});

function onOrder(next: OrderOut): void {
  // While the checkout sheet is charging it, the charge itself says how it ended.
  if (charging.value && next.status !== 'open') return;
  till.follow(next);
}

function rememberName(id: string | null, name: string | null): void {
  if (id && name) staffNames.value = { ...staffNames.value, [id]: name };
}

/** The screen starts afresh: no check, no customer, «me» serving, nothing marked. */
function clearScreen(): void {
  customer.value = null;
  staff.value = { id: null, name: null };
  marks.value = [];
}

// ── The customer (the Customers app's search) ─────────────────────────────────────────────────────
const link = useCommand('customer.order.link');
const linkOf = useCommand('customer.order.customer');
const cardOf = useCommand('customer.customer.detail');

async function linkCustomer(orderId: string, snapshot: CustomerSnapshot | null): Promise<void> {
  try {
    await link.run({ order_id: orderId, customer_id: snapshot?.customer_id ?? null });
  } catch (error) {
    void toastError(refusal(error, t('sale.pos.customerLinkFailed')));
  }
}

function onCustomer(next: CustomerSnapshot | null): void {
  customer.value = next;
  if (till.orderId.value) void linkCustomer(till.orderId.value, next);
}

/** A resumed (or reloaded) check gets its customer back from the card linked to it. */
async function loadCustomer(orderId: string): Promise<void> {
  try {
    const linked = await linkOf.run({ order_id: orderId });
    if (!linked.customer_id || till.orderId.value !== orderId) return;
    const card = await cardOf.run({ id: linked.customer_id });
    if (till.orderId.value === orderId) customer.value = customerSnapshot(card, locale.value);
  } catch (error) {
    void toastError(refusal(error, t('sale.pos.customerLoadFailed')));
  }
}

function askCustomer(): void {
  void toast(t('sale.pos.customerRequiredCharge'), 'warning');
  choosingCustomer.value = true;
}

const needsCustomer = computed(() => !!settings.value?.require_customer && !customer.value);

// ── Sheets: one write at a time, its refusal read inside ─────────────────────────────────────────
const sheetError = shallowRef<string | null>(null);
const sheetPending = shallowRef(false);

/** Runs a sheet's write; closes the sheet when it went, keeps it open with the refusal when not. */
async function fromSheet(write: () => Promise<WriteResult>, close: () => void): Promise<boolean> {
  sheetError.value = null;
  sheetPending.value = true;
  try {
    const done = await write();
    if (!done.ok) {
      sheetError.value = done.message;
      return false;
    }
    close();
    return true;
  } finally {
    sheetPending.value = false;
  }
}

function openSheet(open: () => void): void {
  sheetError.value = null;
  open();
}

const pricing = shallowRef(false);
function openPrice(): void {
  if (!session.can('sale.sell_open_price')) {
    void toast(t('sale.pos.managerOnly'), 'warning');
    return;
  }
  openSheet(() => (pricing.value = true));
}
const addOpenLine = (line: OpenLine) =>
  fromSheet(
    () => till.addOpenLine(line, staff.value.id),
    () => (pricing.value = false),
  );

const noting = shallowRef<OrderLineOut | null>(null);
const saveNote = (note: string) =>
  noting.value &&
  fromSheet(
    () => till.setNote(noting.value as OrderLineOut, note),
    () => (noting.value = null),
  );

const discounting = shallowRef<OrderLineOut | 'ticket' | null>(null);
const discountLine = computed(() => (discounting.value && discounting.value !== 'ticket' ? discounting.value : null));
function applyDiscount(discount: { percent: string; amount: number }): void {
  const target = discounting.value;
  if (!target) return;
  void fromSheet(
    () => (target === 'ticket' ? till.setTicketDiscount(discount) : till.setLineDiscount(target, discount.percent)),
    () => (discounting.value = null),
  );
}

const voiding = shallowRef<OrderLineOut | null>(null);
const voidLine = (reason: string) =>
  voiding.value &&
  fromSheet(
    () => till.voidLine(voiding.value as OrderLineOut, reason),
    () => (voiding.value = null),
  );

// ── Who serves ───────────────────────────────────────────────────────────────────────────────────
const picking = shallowRef<{ mode: 'check' } | { mode: 'line'; line: OrderLineOut } | null>(null);
function chooseStaff(choice: { id: string | null; name: string | null }): void {
  const target = picking.value;
  picking.value = null;
  rememberName(choice.id, choice.name);
  if (target?.mode === 'line') void till.setLineStaff(target.line, choice.id);
  else staff.value = choice;
}

// ── Parking and switching checks ─────────────────────────────────────────────────────────────────
const parking = shallowRef(false);
const checksNotice = shallowRef<string | null>(null);
function park(label: string): void {
  void fromSheet(
    async () => {
      const done = await till.park(label);
      if (done.ok) {
        clearScreen();
        void toastSuccess(t('sale.pos.parkedToast', { name: label }));
      }
      return done;
    },
    () => (parking.value = false),
  );
}

const switchingTo = shallowRef<OrderRow | null>(null);
function switchTo(row: OrderRow): void {
  till.resume(row.id);
  clearScreen();
  void loadCustomer(row.id);
}

function resume(row: OrderRow): void {
  if (row.id === till.orderId.value) return;
  if (lines.value.length) openSheet(() => (switchingTo.value = row));
  else switchTo(row);
}

function leaveCurrent(choice: 'park' | 'discard'): void {
  const target = switchingTo.value;
  if (!target) return;
  void fromSheet(
    () => (choice === 'park' ? till.park(order.value?.label || shortTime(new Date(), locale.value)) : till.voidCheck()),
    () => {
      switchingTo.value = null;
      switchTo(target);
    },
  );
}

// ── Charging ─────────────────────────────────────────────────────────────────────────────────────
const documentOpen = shallowRef(false);
const documentSaleId = shallowRef<string | null>(null);

function charge(): void {
  if (!order.value || !lines.value.length) return;
  if (needsCustomer.value) {
    askCustomer();
    return;
  }
  charging.value = true;
}

function onCharged(sale: SaleOut): void {
  const whole = marks.value.length === 0 || marks.value.length >= lines.value.length;
  if (!whole) {
    marks.value = [];
    return;
  }
  till.release();
  clearScreen();
  cartOpen.value = false;
  documentSaleId.value = sale.id;
  documentOpen.value = true;
}

function toggleMark(line: OrderLineOut): void {
  marks.value = marks.value.includes(line.id) ? marks.value.filter((id) => id !== line.id) : [...marks.value, line.id];
}

const prebillOpen = shallowRef(false);

// ── Layout: the phone's drawer and its button ────────────────────────────────────────────────────
const PHONE = '(max-width: 820px), (max-height: 500px)';
const phone = shallowRef(false);
const cartOpen = shallowRef(false);
let media: MediaQueryList | undefined;
const onMedia = () => (phone.value = !!media?.matches);

const tillEl = useTemplateRef<HTMLElement>('tillEl');
const itemCount = computed(() =>
  Math.round(lines.value.reduce((sum, line) => sum + (line.unit === 'ud' ? Number(line.quantity) : 1), 0)),
);
const total = computed(() => (lines.value.length ? preview.value?.total : 0));

onMounted(() => {
  media = typeof window.matchMedia === 'function' ? window.matchMedia(PHONE) : undefined;
  onMedia();
  media?.addEventListener('change', onMedia);
  if (till.orderId.value) void loadCustomer(till.orderId.value);
});
onBeforeUnmount(() => media?.removeEventListener('change', onMedia));
</script>

<template>
  <AppPage
    :title="$t('sale.title')"
    :tabs="saleTabs($t)"
    :tabs-label="$t('sale.tabs.label')"
  >
    <InlineFeedback
      v-if="loadError"
      tone="danger"
      data-testid="pos-load-error"
    >
      {{ loadError }}
      <template #actions>
        <ion-button
          size="small"
          fill="outline"
          data-testid="pos-load-retry"
          @click="settingsLive.refresh()"
        >
          {{ $t('sale.live.retry') }}
        </ion-button>
      </template>
    </InlineFeedback>
    <div
      v-else-if="!settings"
      class="pos-loading"
      data-testid="pos-loading"
    >
      <ion-spinner />
    </div>
    <div
      v-else
      ref="tillEl"
      class="pos-till"
      :class="{ 'pos-till--cart-open': cartOpen }"
      data-testid="pos-till"
      @keydown.esc="cartOpen = false"
    >
      <div class="pos-till__body">
        <PosCatalog
          :show-products="settings.show_products"
          :can-open-price="session.can('sale.sell_open_price')"
          :target="tillEl"
          @add="till.addProduct($event, staff.id)"
          @open-price="openPrice"
        >
          <CartFab
            class="pos-till__fab"
            :count="itemCount"
            :total="total"
            :expanded="cartOpen"
            @open="cartOpen = true"
          />
        </PosCatalog>
        <div
          v-if="cartOpen"
          class="pos-till__backdrop"
          data-testid="pos-cart-backdrop"
          @click="cartOpen = false"
        />
        <div class="pos-till__cart">
          <PosCart
            :order="order"
            :label="order ? order.label : till.pendingLabel.value"
            :total="total"
            :ticket-discount="preview?.ticket_discount_amount ?? 0"
            :marks="marks"
            :staff-names="staffNames"
            :settings="settings"
            :customer-name="customer?.customer_name || null"
            :staff-id="staff.id"
            :staff-name="staff.name"
            :needs-customer="needsCustomer"
            :busy="till.busy.value"
            :drawer="phone"
            :open-checks="openChecks"
            :checks-notice="checksNotice"
            @park="openSheet(() => (parking = true))"
            @close="cartOpen = false"
            @rename="till.rename($event)"
            @staff="picking = { mode: 'check' }"
            @ask-customer="askCustomer"
            @mark="toggleMark"
            @quantity="(line, quantity) => till.setQuantity(line, quantity)"
            @line-discount="openSheet(() => (discounting = $event))"
            @note="openSheet(() => (noting = $event))"
            @gift="till.toggleGift($event)"
            @line-staff="picking = { mode: 'line', line: $event }"
            @void-line="openSheet(() => (voiding = $event))"
            @ticket-discount="openSheet(() => (discounting = 'ticket'))"
            @prebill="prebillOpen = true"
            @charge="charge"
            @resume="resume"
          >
            <template #customer>
              <CustomerSearch
                v-model:open="choosingCustomer"
                :model-value="customer"
                @update:model-value="onCustomer"
              />
            </template>
          </PosCart>
        </div>
      </div>

      <CheckFollower
        v-if="till.orderId.value"
        :key="till.orderId.value"
        :order-id="till.orderId.value"
        :valued="lines.length > 0"
        @order="onOrder"
        @preview="preview = $event"
        @gone="till.gone()"
      />

      <OpenPriceSheet
        v-model:open="pricing"
        :pending="sheetPending"
        :error="sheetError"
        @add="addOpenLine"
      />
      <LineNoteSheet
        :open="!!noting"
        :name="noting?.name ?? ''"
        :note="noting?.notes ?? ''"
        :pending="sheetPending"
        :error="sheetError"
        @update:open="(open) => !open && (noting = null)"
        @save="saveNote"
      />
      <DiscountSheet
        :open="!!discounting"
        :name="discountLine?.name ?? null"
        :amount="discounting === 'ticket' ? (order?.discount_amount ?? 0) : 0"
        :pending="sheetPending"
        :error="sheetError"
        @update:open="(open) => !open && (discounting = null)"
        @apply="applyDiscount"
      />
      <VoidLineSheet
        :open="!!voiding"
        :name="voiding?.name ?? ''"
        :pending="sheetPending"
        :error="sheetError"
        @update:open="(open) => !open && (voiding = null)"
        @void="voidLine"
      />
      <ParkSheet
        v-model:open="parking"
        :pending="sheetPending"
        :error="sheetError"
        @park="park"
      />
      <DirtyCheckDialog
        :open="!!switchingTo"
        :can-park="settings.enable_parked_tickets"
        :can-discard="session.can('sale.void_sale')"
        :pending="sheetPending"
        :error="sheetError"
        @update:open="(open) => !open && (switchingTo = null)"
        @choose="leaveCurrent"
      />
      <StaffPicker
        v-if="picking"
        :open="!!picking"
        :mode="picking.mode"
        :current="picking.mode === 'line' ? picking.line.staff_id : staff.id"
        @update:open="(open) => !open && (picking = null)"
        @choose="chooseStaff"
      />
      <PrebillModal
        v-if="prebillOpen && order"
        v-model:open="prebillOpen"
        :order="order"
        :customer-name="customer?.customer_name || null"
        :header="settings.receipt_header"
      />
      <CheckoutSheet
        v-if="order"
        v-model:open="charging"
        :order-id="order.id"
        :line-ids="marks"
        :order-version="order.version"
        :customer="customer"
        :staff-id="staff.id"
        @charged="onCharged"
      />
      <DocumentModal
        v-model:open="documentOpen"
        :sale-id="documentSaleId"
        :duplicate="false"
      />
    </div>
  </AppPage>
</template>

<style scoped>
.pos-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
}
/* The box the shell lays the till out in: every sheet and the drawer are anchored to it. */
.pos-till {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
  overflow: clip;
  background: var(--ion-background-color, #fff);
  border: 1px solid var(--ion-border-color, #e6e3db);
  border-radius: 16px;
}
.pos-till:fullscreen {
  border-radius: 0;
}
/* One row pinned to the box's height, so the grid scrolls inside its column and the cart's foot stays. */
.pos-till__body {
  position: relative;
  display: grid;
  flex: 1;
  grid-template-columns: minmax(0, 1fr) minmax(23rem, 24.5rem);
  grid-template-rows: minmax(0, 1fr);
  min-height: 0;
}
.pos-till__cart {
  display: flex;
  min-height: 0;
}
.pos-till__cart > * {
  flex: 1;
}
.pos-till__fab,
.pos-till__backdrop {
  display: none;
}
@media (min-width: 821px) and (max-width: 1100px) {
  .pos-till__body {
    grid-template-columns: minmax(0, 1fr) 22rem;
  }
}
/* The phone (and a phone on its side): the catalogue alone, the check a drawer from the right. */
@media not all and (min-width: 821px) and (min-height: 501px) {
  .pos-till__body {
    grid-template-columns: minmax(0, 1fr);
  }
  .pos-till__fab {
    display: inline-flex;
  }
  .pos-till__cart {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    z-index: 60;
    width: min(100%, 27rem);
    visibility: hidden;
    transform: translateX(100%);
    transition:
      transform 0.25s ease,
      visibility 0s linear 0.25s;
  }
  .pos-till--cart-open .pos-till__cart {
    visibility: visible;
    transform: none;
    transition:
      transform 0.25s ease,
      visibility 0s;
  }
  .pos-till__backdrop {
    position: absolute;
    inset: 0;
    z-index: 55;
    display: block;
    background: rgba(0, 0, 0, 0.5);
  }
}
@media (max-height: 500px) {
  .pos-till__cart {
    width: min(100%, 34rem);
  }
}
</style>
