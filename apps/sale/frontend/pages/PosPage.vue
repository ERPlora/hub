<script setup lang="ts">
// Sales & POS → Sell (WORKBOOK «Vender»; SALE-F01, F05, F09, F13–F22, F27, F38). The till: the catalogue
// and the check side by side (23–24.5rem on a desktop); on a phone (narrower than 821px or 500px tall or
// less), and wherever the till itself is narrower than both need (beside the docked assistant on a tablet), the
// check is a drawer from the right that the cart button opens. The page wires the pieces:
// the till settings, the check and its writes (`useTill`), the live check and its preview (mounted
// only while there is one), the customer (the Customers app's search; linked to the check by
// `customer.order.link`, read back on resuming), who serves, the sheets, the pre-bill, the checkout
// sheet and the sale's document after a whole charge. With Services on (SALE-F38) the catalogue sells its
// services: a fixed price goes straight to the check, any other asks its amount (ServicePriceSheet).
// With Tables on (SALE-F19) the check's bar has «Choose table» and the heading the check's table, both
// through Tables' operations only (Sales does not require Tables).
// `/sale/pos?order=<id>` (Appointments' «Charge», APPOINTMENT-F17) puts that check on the till as
// resuming it from «Open checks» does; one no longer open is said and the till carries on as it was.
// Nothing about money is decided here.
import { InlineFeedback } from '@erplora/ui/components';
import { ApiError, type OutputOf, useCommand, useLive } from '@erplora/ui/sdk';
import { AppPage, toast, toastError, toastSuccess, useSession } from '@erplora/ui/shell';
import { IonButton, IonSpinner } from '@ionic/vue';
import { computed, onBeforeUnmount, onMounted, shallowRef, useTemplateRef, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import CustomerSearch, { type CustomerSnapshot, snapshotOf } from '../../../customer/frontend/components/CustomerSearch.vue';
import CheckoutSheet from '../components/checkout/CheckoutSheet.vue';
import DocumentModal from '../components/document/DocumentModal.vue';
import CartFab from '../components/pos/CartFab.vue';
import CheckFollower from '../components/pos/CheckFollower.vue';
import ComboSheet from '../components/pos/ComboSheet.vue';
import DirtyCheckDialog from '../components/pos/DirtyCheckDialog.vue';
import DiscountSheet from '../components/pos/DiscountSheet.vue';
import LineNoteSheet from '../components/pos/LineNoteSheet.vue';
import ModifierSheet from '../components/pos/ModifierSheet.vue';
import OpenPriceSheet from '../components/pos/OpenPriceSheet.vue';
import ParkSheet from '../components/pos/ParkSheet.vue';
import PosCart from '../components/pos/PosCart.vue';
import PosCatalog from '../components/pos/PosCatalog.vue';
import PrebillModal from '../components/pos/PrebillModal.vue';
import ServicePriceSheet from '../components/pos/ServicePriceSheet.vue';
import StaffPicker from '../components/pos/StaffPicker.vue';
import TableButton from '../components/pos/TableButton.vue';
import TableFollower from '../components/pos/TableFollower.vue';
import TablePicker from '../components/pos/TablePicker.vue';
import { shortTime } from '../components/pos/till';
import VoidLineSheet from '../components/pos/VoidLineSheet.vue';
import { useDrawerFocus } from '../composables/pos/useDrawerFocus';
import { type OpenLine, useTill, type WriteResult } from '../composables/pos/useTill';
import { useLocale, useT } from '../composables/useT';
import type { SaleComboOut } from '../../../combo/frontend/operations';
import type { ProductOut } from '../../../inventory/frontend/operations';
import type { TargetGroupOut } from '../../../modifier/frontend/operations';
import type { ServiceSaleOut } from '../../../service/frontend/operations';
import type { ComboChoiceIn, OrderLineOut, OrderOut, OrderRow, PreviewOut, SaleOut } from '../operations';
import { refusal } from '../lib/refusal';
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

/** A closed check that arrived while the checkout sheet was open: applied once the sheet closes. */
let heldWhileCharging: OrderOut | null = null;

function onOrder(next: OrderOut): void {
  // While the checkout sheet is open the charge itself says how it ended; if it did not end it (the
  // check was closed on another device), the screen lets it go when the sheet closes.
  if (charging.value && next.status !== 'open') {
    heldWhileCharging = next;
    return;
  }
  till.follow(next);
}

watch(charging, (now) => {
  if (now || !heldWhileCharging) return;
  const held = heldWhileCharging;
  heldWhileCharging = null;
  till.follow(held);
});

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

/** The words of a refusal; the screen's own sentence (`fallbackKey`) when nobody worded it. */
function wordsOf(error: unknown, fallbackKey: string): string {
  const fallback = t(fallbackKey);
  return refusal(error, fallback)?.message ?? fallback;
}

async function linkCustomer(orderId: string, snapshot: CustomerSnapshot | null): Promise<void> {
  try {
    await link.run({ order_id: orderId, customer_id: snapshot?.customer_id ?? null });
  } catch (error) {
    void toastError(wordsOf(error, 'sale.pos.customerLinkFailed'));
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
    if (till.orderId.value === orderId) customer.value = snapshotOf(card, locale.value);
  } catch (error) {
    void toastError(wordsOf(error, 'sale.pos.customerLoadFailed'));
  }
}

function askCustomer(): void {
  void toast(t('sale.pos.customerRequiredCharge'), 'warning');
  choosingCustomer.value = true;
}

const needsCustomer = computed(() => !!settings.value?.require_customer && !customer.value);
/** Where the till shows the customer: the person; the charge keeps the fiscal recipient (`customer`). */
const customerName = computed(() => customer.value?.display_name || customer.value?.customer_name || null);

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
/** Open to everyone: whoever may not sell at an open price gets a manager's approval when it is added (SALE-F09). */
function openPrice(): void {
  openSheet(() => (pricing.value = true));
}
const addOpenLine = (line: OpenLine) =>
  fromSheet(
    () => till.addOpenLine(line, staff.value.id),
    () => (pricing.value = false),
  );

// ── The options of Modifiers (SALE-F11; Modifiers' operations only) ──────────────────────────────
/** A product may carry options: Modifiers on in this business and the right to read it. */
const modifiersOn = computed(
  () => !!session.me.value?.apps.some((app) => app.label === 'modifier' && app.state === 'on') && session.can('modifier.view'),
);
const groupsOf = useCommand('modifier.group.for_target');
const optioning = shallowRef<{ product: ProductOut; groups: TargetGroupOut[] } | null>(null);
const optionsOpen = computed({
  get: () => !!optioning.value,
  set: (open: boolean) => {
    if (!open) optioning.value = null;
  },
});

/** A tap on a product: with groups of Modifiers, the sheet asks first; without, it goes to the check. */
async function pickProduct(product: ProductOut): Promise<void> {
  if (!modifiersOn.value) return till.addProduct(product, staff.value.id);
  let groups: TargetGroupOut[];
  try {
    groups = (await groupsOf.run({ product_id: product.id })).groups;
  } catch (error) {
    void toastError(wordsOf(error, 'sale.pos.options.loadFailed'));
    return;
  }
  if (!groups.length) return till.addProduct(product, staff.value.id);
  openSheet(() => (optioning.value = { product, groups }));
}

const addWithOptions = (optionIds: string[]) => {
  const chosen = optioning.value;
  if (!chosen) return;
  void fromSheet(
    () => till.addProductLine(chosen.product, staff.value.id, optionIds),
    () => (optioning.value = null),
  );
};

// ── The menus of Menus (SALE-F12; Menus' operations only) ────────────────────────────────────────
/** The till offers menus: Menus on in this business and the right to read it. */
const combosOn = computed(
  () => !!session.me.value?.apps.some((app) => app.label === 'combo' && app.state === 'on') && session.can('combo.view'),
);
const composing = shallowRef<SaleComboOut | null>(null);
const menuOpen = computed({
  get: () => !!composing.value,
  set: (open: boolean) => {
    if (!open) composing.value = null;
  },
});

const pickCombo = (combo: SaleComboOut) => openSheet(() => (composing.value = combo));

const addCombo = (choices: ComboChoiceIn[]) => {
  const combo = composing.value;
  if (!combo) return;
  void fromSheet(
    () => till.addComboLine(combo, staff.value.id, choices),
    () => (composing.value = null),
  );
};

// ── Services of Services (SALE-F38) ─────────────────────────────────────────────────────────────
/** The till sells Services' services: the setting, Services on in this business, and the right to read it. */
const showServices = computed(
  () =>
    !!settings.value?.show_services &&
    !!session.me.value?.apps.some((app) => app.label === 'service' && app.state === 'on') &&
    session.can('service.view_service'),
);
const pricingService = shallowRef<ServiceSaleOut | null>(null);
const servicePriceOpen = computed({
  get: () => !!pricingService.value,
  set: (open: boolean) => {
    if (!open) pricingService.value = null;
  },
});

async function pickService(service: ServiceSaleOut): Promise<void> {
  if (service.pricing_type !== 'fixed') {
    openSheet(() => (pricingService.value = service));
    return;
  }
  const done = await till.addService(service, staff.value.id);
  if (!done.ok) void toastError(done.message);
}

const addPricedService = (cents: number) => {
  const service = pricingService.value;
  if (!service) return;
  void fromSheet(
    () => till.addService(service, staff.value.id, cents),
    () => (pricingService.value = null),
  );
};

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

// ── The table of the check (SALE-F19; Tables' operations only) ───────────────────────────────────
type TableCheck = OutputOf<'table.session.by_order'>['rows'][number];

/** «Choose table» is offered: Tables on in this business, and the right to see its tables and to seat. */
const tablesOn = computed(
  () =>
    !!session.me.value?.apps.some((app) => app.label === 'table' && app.state === 'on') &&
    session.can('table.view_table') &&
    session.can('table.add_session'),
);
/** The check's table is followed: Tables offered, the right to see its table checks, and a check. */
const followsTable = computed(() => tablesOn.value && session.can('table.view_session') && !!till.orderId.value);
const tableSeat = shallowRef<TableCheck | null>(null);
const tableParked = shallowRef<TableCheck | null>(null);
const seatOfCheck = computed(() => (followsTable.value ? tableSeat.value : null));
const parkedOfCheck = computed(() => (followsTable.value ? tableParked.value : null));
const choosingTable = shallowRef(false);

watch(
  () => till.orderId.value,
  () => {
    tableSeat.value = null;
    tableParked.value = null;
  },
);

/** Seated: a check Tables opened for the table (there was none on screen) goes on the till, with the
 *  customer already chosen; the check on screen stays, retitled by Tables. */
function onSeated(check: { order_id: string | null }): void {
  const id = check.order_id;
  if (!id || id === till.orderId.value) return;
  till.resume(id);
  if (customer.value) void linkCustomer(id, customer.value);
}

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

const switchingTo = shallowRef<Pick<OrderRow, 'id'> | null>(null);
function switchTo(row: Pick<OrderRow, 'id'>): void {
  till.resume(row.id);
  clearScreen();
  void loadCustomer(row.id);
}

function resume(row: Pick<OrderRow, 'id'>): void {
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

// ── A check opened by its address (/sale/pos?order=<id>) ─────────────────────────────────────────
const route = useRoute();
const router = useRouter();
const checkOf = useCommand('sale.order.get');

/** Puts the check `id` on the till, as «Open checks» does; one no longer open is said. */
async function openLinked(id: string): Promise<void> {
  void router.replace({ path: route.path, query: {} });
  if (id === till.orderId.value) return;
  try {
    const linked = await checkOf.run({ order_id: id });
    if (linked.status === 'open') resume(linked);
    else void toastError(t('sale.pos.linkedCheckGone'));
  } catch (error) {
    const gone = error instanceof ApiError && error.status === 404;
    void toastError(gone ? t('sale.pos.linkedCheckGone') : wordsOf(error, 'sale.pos.linkedCheckGone'));
  }
}

/** The till's own address: Ionic keeps this page alive behind others, whose `order` may mean a sort. */
const POS_PATH = '/sale/pos';

// Once the till can show it (its settings read): on arriving and whenever its address names a check.
watch(
  () => (settings.value && route.path === POS_PATH ? route.query.order : undefined),
  (id) => {
    if (typeof id === 'string' && id) void openLinked(id);
  },
  { immediate: true },
);

// ── Charging ─────────────────────────────────────────────────────────────────────────────────────
const documentOpen = shallowRef(false);
const documentSaleId = shallowRef<string | null>(null);
/** The charge already queued its original for the printer (PRINTING-F07): the paper on screen is a copy. */
const documentDuplicate = shallowRef(false);

/** The lines of the check when «Charge» opened the sheet: what a charge of all of them means. */
let chargingLines: string[] = [];

// ── The round to the kitchen (SALE-F20; Kitchen's KITCHEN-F18) ────────────────────────────────────
/** The VeriFactu notice of the catalogue (SALE-F07): VeriFactu on in this business and the right to read it. */
const verifactuOn = computed(
  () => !!session.me.value?.apps.some((app) => app.label === 'verifactu' && app.state === 'on') && session.can('verifactu.view_record'),
);
/** Kitchen is on in this business. */
const kitchenActive = computed(() => !!session.me.value?.apps.some((app) => app.label === 'kitchen' && app.state === 'on'));
/** «Current order» and its send: Kitchen on in this business and the right to send to it. */
const kitchenOn = computed(() => kitchenActive.value && session.can('kitchen.add_ticket'));
/** «Tickets · N» and «Order tickets» (KITCHEN-F19, F20): Kitchen on and the right to see its tickets. */
const kitchenTickets = computed(() => kitchenActive.value && session.can('kitchen.view_ticket'));
/** Nothing new to send (another device sent it, or only services wait): not a failure. */
const NOTHING_TO_SEND = new Set(['sale.nothing_to_fire', 'kitchen.nothing_to_cook']);

async function sendRound(rush: boolean): Promise<boolean> {
  // kitchen#82: the ticket names who attends the check («Atiende»); with «Yo», the kitchen names who sends it.
  const sent = await till.sendToKitchen(rush, staff.value.id ? staff.value.name : null);
  if (sent.ok) {
    // hub#2257: sent, but its sheet did not print — said in words (the reason is Printing's, not the waiter's).
    if (sent.printed === false) void toast(t('sale.pos.kitchen.sentNotPrinted', { n: sent.round ?? '' }), 'warning', 4500);
    else void toastSuccess(t('sale.pos.kitchen.sent', { n: sent.round ?? '' }));
    return true;
  }
  if (sent.code && NOTHING_TO_SEND.has(sent.code)) return true;
  void toastError(sent.message);
  return false;
}

async function charge(): Promise<void> {
  if (!order.value || !lines.value.length) return;
  if (needsCustomer.value) {
    askCustomer();
    return;
  }
  // sales#439: what is pending goes to the kitchen before the charge, or the customer pays for a dish nobody cooks.
  if (kitchenOn.value && lines.value.some((line) => !line.fired_at && !line.is_service) && !(await sendRound(false))) return;
  chargingLines = lines.value.map((line) => line.id);
  heldWhileCharging = null;
  charging.value = true;
}

/**
 * Charged: whole or partial is what the sheet charged (`lineIds`, frozen when it opened; none = the
 * whole check), never the marks now — a live update may have dropped them. Whole: the screen starts
 * afresh. Partial: the check stays with what is left. Either way the sale's document opens; a receipt the
 * charge queued for the printer is said, and the paper on screen is then a copy.
 */
function onCharged(sale: SaleOut, lineIds: readonly string[]): void {
  const whole = lineIds.length === 0 || chargingLines.every((id) => lineIds.includes(id));
  if (whole) {
    till.release();
    clearScreen();
    cartOpen.value = false;
  } else {
    marks.value = [];
  }
  if (sale.printed?.queued) void toastSuccess(t('sale.document.queued', { printer: sale.printed.printer ?? '' }));
  documentDuplicate.value = !!sale.printed?.queued;
  documentSaleId.value = sale.id;
  documentOpen.value = true;
}

function toggleMark(line: OrderLineOut): void {
  marks.value = marks.value.includes(line.id) ? marks.value.filter((id) => id !== line.id) : [...marks.value, line.id];
}

const prebillOpen = shallowRef(false);

// ── Layout: the phone's drawer and its button ────────────────────────────────────────────────────
const PHONE = '(max-width: 820px), (max-height: 500px)';
/** The till's own width under which the catalogue and the check no longer fit side by side (FIX-SALE-POS-NO-SPEAK-KEY:
 *  the docked assistant takes up to 420px of a tablet). Without it, the narrowest two-column till is a 992px
 *  window with the side menu, about 720px. */
const NARROW_TILL = 700;
const phoneWindow = shallowRef(false);
const narrowTill = shallowRef(false);
const phone = computed(() => phoneWindow.value || narrowTill.value);
const tillBox = useTemplateRef<HTMLElement>('tillBox');
const cartOpen = shallowRef(false);
/** On a phone the open cart is a modal dialog over the till: focus inside, trapped, back to the button. */
const drawerOpen = computed(() => phone.value && cartOpen.value);
const drawer = useTemplateRef<HTMLElement>('drawer');
const fab = useTemplateRef<{ $el: HTMLElement }>('fab');
const drawerFocus = useDrawerFocus({ container: drawer, open: cartOpen, enabled: phone, returnTo: () => fab.value?.$el });
let media: MediaQueryList | undefined;
const onMedia = () => (phoneWindow.value = !!media?.matches);
const resize =
  typeof ResizeObserver === 'undefined'
    ? undefined
    : new ResizeObserver((entries) => {
        const width = entries.at(-1)?.contentRect.width;
        if (width) narrowTill.value = width < NARROW_TILL;
      });
watch(tillBox, (box) => {
  resize?.disconnect();
  if (box) resize?.observe(box);
});

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
onBeforeUnmount(() => {
  media?.removeEventListener('change', onMedia);
  resize?.disconnect();
});
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
      ref="tillBox"
      class="pos-till"
      :class="{ 'pos-till--cart-open': cartOpen, 'pos-till--phone': phone }"
      data-testid="pos-till"
      @keydown.esc="cartOpen = false"
    >
      <div class="pos-till__body">
        <PosCatalog
          :show-products="settings.show_products"
          :show-services="showServices"
          :show-combos="combosOn"
          :fiscal="verifactuOn"
          @add="pickProduct"
          @combo="pickCombo"
          @service="pickService"
          @open-price="openPrice"
        >
          <CartFab
            ref="fab"
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
        <div
          ref="drawer"
          class="pos-till__cart"
          data-testid="pos-cart-drawer"
          :role="drawerOpen ? 'dialog' : undefined"
          :aria-modal="drawerOpen ? 'true' : undefined"
          :aria-label="drawerOpen ? $t('sale.pos.cartLabel') : undefined"
          :tabindex="phone ? -1 : undefined"
          @keydown="drawerFocus.onKeydown"
        >
          <PosCart
            :order="order"
            :label="order ? order.label : till.pendingLabel.value"
            :total="total"
            :ticket-discount="preview?.ticket_discount_amount ?? 0"
            :marks="marks"
            :staff-names="staffNames"
            :settings="settings"
            :customer-name="customerName"
            :staff-id="staff.id"
            :staff-name="staff.name"
            :needs-customer="needsCustomer"
            :busy="till.busy.value"
            :drawer="phone"
            :open-checks="openChecks"
            :table-number="seatOfCheck?.table_number ?? null"
            :kitchen="kitchenOn"
            :kitchen-tickets="kitchenTickets"
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
            @send="sendRound"
            @resume="resume"
          >
            <template #table>
              <TableButton
                v-if="tablesOn"
                :table-number="seatOfCheck?.table_number ?? null"
                @open="choosingTable = true"
              />
            </template>
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

      <!-- The followers mount once a check opens, often from a sheet still on screen: in a box of their own, never
           inserted next to an ion-modal that Ionic moved out when it presented it (SALE-F09: the first line of a
           check from «Open price» broke the till). Siblings keyed apart: a shared key broke Vue's patch too. -->
      <div
        class="pos-followers"
        hidden
      >
        <CheckFollower
          v-if="till.orderId.value"
          :key="`check-${till.orderId.value}`"
          :order-id="till.orderId.value"
          :valued="lines.length > 0"
          @order="onOrder"
          @preview="preview = $event"
          @gone="till.gone()"
        />
        <TableFollower
          v-if="followsTable && till.orderId.value"
          :key="`table-${till.orderId.value}`"
          :order-id="till.orderId.value"
          @seat="tableSeat = $event"
          @parked="tableParked = $event"
        />
      </div>

      <OpenPriceSheet
        v-model:open="pricing"
        :pending="sheetPending"
        :error="sheetError"
        @add="addOpenLine"
      />
      <ServicePriceSheet
        v-model:open="servicePriceOpen"
        :service="pricingService"
        :pending="sheetPending"
        :error="sheetError"
        @add="addPricedService"
      />
      <ComboSheet
        v-model:open="menuOpen"
        :combo="composing"
        :pending="sheetPending"
        :error="sheetError"
        @add="addCombo"
      />
      <ModifierSheet
        v-model:open="optionsOpen"
        :product="optioning?.product ?? null"
        :groups="optioning?.groups ?? []"
        :pending="sheetPending"
        :error="sheetError"
        @add="addWithOptions"
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
        :can-discard="session.can('sale.add_sale')"
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
      <TablePicker
        v-if="choosingTable"
        v-model:open="choosingTable"
        :order-id="till.orderId.value"
        :seat="seatOfCheck"
        :parked="parkedOfCheck"
        @seated="onSeated"
      />
      <PrebillModal
        v-if="prebillOpen && order"
        v-model:open="prebillOpen"
        :order="order"
        :customer-name="customerName"
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
        :duplicate="documentDuplicate"
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
/* The phone (and a phone on its side, and a till too narrow for both): the catalogue alone, the check a drawer
   from the right. */
.pos-till--phone .pos-till__body {
  grid-template-columns: minmax(0, 1fr);
}
.pos-till--phone .pos-till__fab {
  display: inline-flex;
}
.pos-till--phone .pos-till__cart {
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
.pos-till--phone.pos-till--cart-open .pos-till__cart {
  visibility: visible;
  transform: none;
  transition:
    transform 0.25s ease,
    visibility 0s;
}
.pos-till--phone .pos-till__backdrop {
  position: absolute;
  inset: 0;
  z-index: 55;
  display: block;
  background: rgba(0, 0, 0, 0.5);
}
@media (max-height: 500px) {
  .pos-till--phone .pos-till__cart {
    width: min(100%, 34rem);
  }
}
</style>
